"""Azure AI Agent Service - FastAPI application with OpenTelemetry instrumentation."""

import hashlib
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from typing import Optional

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.monitor.opentelemetry import configure_azure_monitor
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import AzureOpenAI
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.trace import SpanKind
from pydantic import BaseModel, Field

# Foundry emits its own telemetry for agent runs; used to suppress duplicate spans on our side.
try:
    from opentelemetry import context as _otel_context
    from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
except Exception:  # pragma: no cover - telemetry libs optional in local dev
    _otel_context = None
    _SUPPRESS_INSTRUMENTATION_KEY = None

logger = logging.getLogger(__name__)

AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
APPLICATIONINSIGHTS_CONNECTION_STRING = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING", "")
AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID", "")

# Azure AI Foundry Agent Service configuration
AZURE_AI_PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "")
AZURE_AI_AGENT_NAME = os.environ.get("AZURE_AI_AGENT_NAME", "observability-agent")
AZURE_AI_AGENT_MODEL = os.environ.get("AZURE_AI_AGENT_MODEL", AZURE_OPENAI_DEPLOYMENT)

SYSTEM_MESSAGE = (
    "You are a helpful AI assistant powered by Azure AI Foundry. "
    "You provide clear, accurate, and concise responses."
)

COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"

# Configure Azure Monitor at import time, before the FastAPI app is created, so the
# OpenTelemetry auto-instrumentation attaches to this app instance. Doing this inside
# lifespan runs too late (the app already exists) and no request telemetry is emitted.
os.environ.setdefault("OTEL_SERVICE_NAME", "agent")
if APPLICATIONINSIGHTS_CONNECTION_STRING:
    configure_azure_monitor(connection_string=APPLICATIONINSIGHTS_CONNECTION_STRING)
    # Structured contract events are emitted at INFO; without this they are filtered
    # by the default WARNING level and never reach the Azure Monitor log exporter.
    logger.setLevel(logging.INFO)
    logger.info("Azure Monitor telemetry configured")
else:
    logger.warning("APPLICATIONINSIGHTS_CONNECTION_STRING not set; telemetry disabled")

_tracer = trace.get_tracer(__name__)

# --- Telemetry contract (observability-sdk) for the direct-model path ----------
# Foundry emits its own telemetry for agent-mode runs, so the direct-model path
# reproduces the shared contract: metrics under "metrics.agent.{agent}.*" plus the
# AgentStart / ExternalCall / LLMUsage / AgentEnd / Error structured events.
SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "agent")
AGENT_VERSION = os.environ.get("AGENT_VERSION", "1.0.0")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "")
MODEL_AGENT_NAME = os.environ.get("MODEL_AGENT_NAME", AZURE_AI_AGENT_NAME)

# Estimated USD price per 1K tokens (input, output), used for llm_cost_estimated.
_MODEL_PRICING = {
    "gpt-5.4": (0.00125, 0.01),
    "gpt-4o": (0.0025, 0.01),
    "gpt-4o-mini": (0.00015, 0.0006),
}

_metrics_namespace = f"metrics.agent.{MODEL_AGENT_NAME}"
_meter = metrics.get_meter(_metrics_namespace)
_execution_time = _meter.create_histogram(
    f"{_metrics_namespace}.agent_execution_time_ms",
    unit="ms",
    description="Agent execution time in milliseconds",
)
_success_count = _meter.create_counter(
    f"{_metrics_namespace}.success_count",
    description="Number of successful agent executions",
)
_error_count = _meter.create_counter(
    f"{_metrics_namespace}.error_count",
    description="Number of failed agent executions",
)
_llm_tokens_in = _meter.create_counter(
    f"{_metrics_namespace}.llm_tokens_in",
    description="Total input tokens sent to LLM",
)
_llm_tokens_out = _meter.create_counter(
    f"{_metrics_namespace}.llm_tokens_out",
    description="Total output tokens received from LLM",
)
_llm_cost_value = 0.0


def _observe_llm_cost(options: metrics.CallbackOptions):
    return [metrics.Observation(_llm_cost_value)]


_llm_cost_estimated = _meter.create_observable_gauge(
    f"{_metrics_namespace}.llm_cost_estimated",
    callbacks=[_observe_llm_cost],
    description="Estimated cost of the last LLM call in USD",
)


def _estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    prices = _MODEL_PRICING.get(model)
    if prices is None:
        prices = next(
            (p for key, p in _MODEL_PRICING.items() if model.startswith(key)),
            (0.0, 0.0),
        )
    price_in, price_out = prices
    return round(tokens_in / 1000 * price_in + tokens_out / 1000 * price_out, 6)


def _log_base(session_id: Optional[str], channel: str) -> dict:
    """Build the common log base mandated by the observability-sdk contract."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": "INFO",
        "service": SERVICE_NAME,
        "agent": MODEL_AGENT_NAME,
        "agent_version": AGENT_VERSION,
        "request_id": f"req-{uuid.uuid4().hex[:8]}",
        "client_id_hash": hashlib.sha256(session_id.encode()).hexdigest()[:6] if session_id else "",
        "channel": channel,
        "environment": ENVIRONMENT,
    }


def _emit_event(base: dict, event: dict, level: str = "INFO") -> None:
    # Pass fields as flat `extra` keys: the OpenTelemetry logging handler maps those to
    # log attributes (Properties), whereas a nested "custom_dimensions" dict is dropped.
    merged = {**base, **event, "level": level}
    log_fn = logger.error if level == "ERROR" else logger.info
    log_fn(event["event"], extra=merged)


@contextmanager
def _track_model_request(session_id: Optional[str], input_type: str, channel: str = "api"):
    """AgentStart -> AgentEnd lifecycle with execution-time and success/error metrics."""
    base = _log_base(session_id, channel)
    _emit_event(base, {"event": "AgentStart", "agent": MODEL_AGENT_NAME, "input_type": input_type})
    start = time.perf_counter()
    success = True
    with _tracer.start_as_current_span(
        f"agent.{MODEL_AGENT_NAME}",
        attributes={
            "agent.name": MODEL_AGENT_NAME,
            "agent.version": AGENT_VERSION,
            "agent.request_id": base["request_id"],
            "agent.input_type": input_type,
        },
    ) as span:
        try:
            yield base
        except Exception as exc:
            success = False
            _emit_event(
                base,
                {"event": "Error", "step": "agent_root", "error_type": type(exc).__name__, "retry": False},
                level="ERROR",
            )
            _error_count.add(1, {"agent": MODEL_AGENT_NAME})
            raise
        finally:
            elapsed = round((time.perf_counter() - start) * 1000, 2)
            status = "success" if success else "error"
            _emit_event(
                base,
                {"event": "AgentEnd", "agent": MODEL_AGENT_NAME, "total_duration_ms": elapsed, "status": status},
            )
            span.set_attribute("agent.total_duration_ms", elapsed)
            span.set_attribute("agent.status", status)
            _execution_time.record(elapsed, {"agent": MODEL_AGENT_NAME})
            if success:
                _success_count.add(1, {"agent": MODEL_AGENT_NAME})


@contextmanager
def _track_external_call(base: dict, dependency: str, request_model: str):
    """ExternalCall event + CLIENT span so the model surfaces as an Azure OpenAI dependency."""
    result = {"status": 200}
    start = time.perf_counter()
    with _tracer.start_as_current_span(f"external.{dependency}", kind=SpanKind.CLIENT) as span:
        span.set_attribute("external.dependency", dependency)
        span.set_attribute("gen_ai.system", "az.ai.openai")
        span.set_attribute("gen_ai.request.model", request_model)
        try:
            yield result, span
        except Exception:
            if result["status"] == 200:
                result["status"] = 500
            raise
        finally:
            elapsed = round((time.perf_counter() - start) * 1000, 2)
            _emit_event(
                base,
                {"event": "ExternalCall", "dependency": dependency, "duration_ms": elapsed, "status": result["status"]},
            )
            span.set_attribute("external.duration_ms", elapsed)
            span.set_attribute("external.status", result["status"])


def _record_llm_usage(base: dict, model: str, tokens_in: int, tokens_out: int) -> None:
    """Emit llm_tokens_in/out counters, the cost gauge, and the LLMUsage event."""
    global _llm_cost_value
    cost = _estimate_cost(model, tokens_in, tokens_out)
    _llm_tokens_in.add(tokens_in, {"model": model, "agent": MODEL_AGENT_NAME})
    _llm_tokens_out.add(tokens_out, {"model": model, "agent": MODEL_AGENT_NAME})
    _llm_cost_value = cost
    _emit_event(
        base,
        {"event": "LLMUsage", "model": model, "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_estimated": cost},
    )


# Cached Foundry project client and the OpenAI client bound to the pre-created agent endpoint.
# The agent itself is created at deployment time (see scripts/create_agent.py), never here.
_project_client: Optional[AIProjectClient] = None
_agent_openai_client = None


class Message(BaseModel):
    role: str
    content: str


class AgentRequest(BaseModel):
    messages: list[Message]
    session_id: Optional[str] = None
    model: Optional[str] = Field(default=None, description="Model override (uses deployment default if not set)")
    mode: str = Field(default="model", description="Chat mode: 'model' for direct model calls or 'agent' for the Foundry agent")


class UsageInfo(BaseModel):
    prompt_tokens: int
    completion_tokens: int


class AgentResponse(BaseModel):
    response: str
    model: str
    usage: UsageInfo


class StreamChunk(BaseModel):
    content: str
    done: bool
    usage: Optional[UsageInfo] = None


class HealthResponse(BaseModel):
    status: str
    service: str


def _get_openai_client() -> AzureOpenAI:
    credential = DefaultAzureCredential(
        managed_identity_client_id=AZURE_CLIENT_ID if AZURE_CLIENT_ID else None
    )
    token_provider = get_bearer_token_provider(credential, COGNITIVE_SERVICES_SCOPE)
    return AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        azure_ad_token_provider=token_provider,
        api_version="2024-10-21",
    )


def _build_messages(request: AgentRequest) -> list[dict]:
    return [{"role": "system", "content": SYSTEM_MESSAGE}] + [
        {"role": m.role, "content": m.content} for m in request.messages
    ]


def _get_project_client() -> AIProjectClient:
    global _project_client
    if not AZURE_AI_PROJECT_ENDPOINT:
        raise RuntimeError("AZURE_AI_PROJECT_ENDPOINT not set; agent mode is unavailable")
    if _project_client is None:
        credential = DefaultAzureCredential(
            managed_identity_client_id=AZURE_CLIENT_ID if AZURE_CLIENT_ID else None
        )
        _project_client = AIProjectClient(
            endpoint=AZURE_AI_PROJECT_ENDPOINT, credential=credential, allow_preview=True
        )
    return _project_client


def _get_agent_client():
    """Return an OpenAI client bound to the deployment-time Foundry agent endpoint."""
    global _agent_openai_client
    if _agent_openai_client is None:
        _agent_openai_client = _get_project_client().get_openai_client(agent_name=AZURE_AI_AGENT_NAME)
    return _agent_openai_client


@contextmanager
def _suppress_telemetry():
    """Suppress local OpenTelemetry spans; Foundry reports agent-run telemetry itself."""
    if _otel_context is None:
        yield
        return
    token = _otel_context.attach(
        _otel_context.set_value(_SUPPRESS_INSTRUMENTATION_KEY, True)
    )
    try:
        yield
    finally:
        _otel_context.detach(token)


def _run_agent(request: AgentRequest) -> AgentResponse:
    inputs = [{"role": m.role, "content": m.content} for m in request.messages]

    # Contact the pre-created Foundry agent through the Responses API. The agent endpoint
    # defines the model and instructions, so we only pass the conversation input.
    # Telemetry is suppressed here because Foundry emits agent-run traces automatically.
    with _suppress_telemetry():
        response = _get_agent_client().responses.create(input=inputs)

    usage = getattr(response, "usage", None)
    return AgentResponse(
        response=response.output_text or "",
        model=AZURE_AI_AGENT_MODEL,
        usage=UsageInfo(
            prompt_tokens=getattr(usage, "input_tokens", 0) or 0,
            completion_tokens=getattr(usage, "output_tokens", 0) or 0,
        ),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Agent service starting up")
    if AZURE_AI_PROJECT_ENDPOINT:
        logger.info("Agent mode enabled; using Foundry agent '%s'", AZURE_AI_AGENT_NAME)
    else:
        logger.warning("AZURE_AI_PROJECT_ENDPOINT not set; agent mode disabled")

    yield
    logger.info("Agent service shutting down")


app = FastAPI(title="Agent Service", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Explicitly instrument this app instance so inbound requests produce server spans.
FastAPIInstrumentor.instrument_app(app)


@app.get("/api/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="healthy", service="agent")


@app.get("/api/agent/status")
async def agent_status():
    """Report readiness of the deployment-time Foundry agent (read-only; never creates it)."""
    if not AZURE_AI_PROJECT_ENDPOINT:
        return {"ready": False, "reason": "AZURE_AI_PROJECT_ENDPOINT not set"}
    try:
        agent = _get_project_client().agents.get(agent_name=AZURE_AI_AGENT_NAME)
        return {
            "ready": True,
            "agentName": getattr(agent, "name", AZURE_AI_AGENT_NAME),
            "model": AZURE_AI_AGENT_MODEL,
            "projectEndpoint": AZURE_AI_PROJECT_ENDPOINT,
        }
    except Exception as e:
        logger.exception("Agent status check failed")
        return {"ready": False, "reason": str(e)}


@app.post("/api/agent/invoke", response_model=AgentResponse)
async def invoke(request: AgentRequest):
    if request.mode == "agent":
        # No server-side telemetry for agent mode; Foundry reports it automatically.
        with _suppress_telemetry():
            try:
                return _run_agent(request)
            except Exception as e:
                logger.exception("Error invoking Foundry agent")
                raise HTTPException(status_code=500, detail=str(e))

    try:
        with _track_model_request(request.session_id, input_type="chat") as base:
            client = _get_openai_client()
            deployment = request.model or AZURE_OPENAI_DEPLOYMENT
            messages = _build_messages(request)

            # The OpenAI SDK is not auto-instrumented; the ExternalCall span keeps the
            # model visible as an Azure OpenAI dependency in the Application Map.
            with _track_external_call(base, "azure_openai", deployment) as (_ext, span):
                completion = client.chat.completions.create(
                    model=deployment,
                    messages=messages,
                )
                span.set_attribute("gen_ai.response.model", completion.model)
                span.set_attribute("gen_ai.usage.input_tokens", completion.usage.prompt_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", completion.usage.completion_tokens)

            _record_llm_usage(
                base,
                completion.model,
                completion.usage.prompt_tokens,
                completion.usage.completion_tokens,
            )

            choice = completion.choices[0]
            return AgentResponse(
                response=choice.message.content or "",
                model=completion.model,
                usage=UsageInfo(
                    prompt_tokens=completion.usage.prompt_tokens,
                    completion_tokens=completion.usage.completion_tokens,
                ),
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error invoking agent")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agent/stream")
async def stream(request: AgentRequest):
    async def event_generator():
        if request.mode == "agent":
            # No server-side telemetry for agent mode; Foundry reports it automatically.
            with _suppress_telemetry():
                try:
                    result = _run_agent(request)
                    chunk = StreamChunk(content=result.response, done=False)
                    yield f"data: {chunk.model_dump_json()}\n\n"
                    final = StreamChunk(content="", done=True, usage=result.usage)
                    yield f"data: {final.model_dump_json()}\n\n"
                except Exception as e:
                    error_data = json.dumps({"error": str(e), "done": True})
                    yield f"data: {error_data}\n\n"
            return

        try:
            with _track_model_request(request.session_id, input_type="chat") as base:
                client = _get_openai_client()
                deployment = request.model or AZURE_OPENAI_DEPLOYMENT
                messages = _build_messages(request)

                usage_info = None
                with _track_external_call(base, "azure_openai", deployment) as (_ext, span):
                    response = client.chat.completions.create(
                        model=deployment,
                        messages=messages,
                        stream=True,
                        stream_options={"include_usage": True},
                    )

                    for chunk in response:
                        if chunk.usage:
                            usage_info = UsageInfo(
                                prompt_tokens=chunk.usage.prompt_tokens,
                                completion_tokens=chunk.usage.completion_tokens,
                            )

                        if chunk.choices:
                            delta = chunk.choices[0].delta
                            content = delta.content or ""
                            data = StreamChunk(content=content, done=False)
                            yield f"data: {data.model_dump_json()}\n\n"

                    if usage_info:
                        span.set_attribute("gen_ai.usage.input_tokens", usage_info.prompt_tokens)
                        span.set_attribute("gen_ai.usage.output_tokens", usage_info.completion_tokens)

                if usage_info:
                    _record_llm_usage(
                        base,
                        deployment,
                        usage_info.prompt_tokens,
                        usage_info.completion_tokens,
                    )

                final = StreamChunk(content="", done=True, usage=usage_info)
                yield f"data: {final.model_dump_json()}\n\n"

        except Exception as e:
            logger.exception("Error during streaming")
            error_data = json.dumps({"error": str(e), "done": True})
            yield f"data: {error_data}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
