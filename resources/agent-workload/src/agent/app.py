"""Azure AI Agent Service - FastAPI application with OpenTelemetry instrumentation."""

import json
import logging
import os
from contextlib import asynccontextmanager, contextmanager
from typing import Optional

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.monitor.opentelemetry import configure_azure_monitor
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import AzureOpenAI
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
    if APPLICATIONINSIGHTS_CONNECTION_STRING:
        configure_azure_monitor(
            connection_string=APPLICATIONINSIGHTS_CONNECTION_STRING,
        )
        logger.info("Azure Monitor telemetry configured")
    else:
        logger.warning("APPLICATIONINSIGHTS_CONNECTION_STRING not set; telemetry disabled")

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
        client = _get_openai_client()
        deployment = request.model or AZURE_OPENAI_DEPLOYMENT
        messages = _build_messages(request)

        completion = client.chat.completions.create(
            model=deployment,
            messages=messages,
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
            client = _get_openai_client()
            deployment = request.model or AZURE_OPENAI_DEPLOYMENT
            messages = _build_messages(request)

            response = client.chat.completions.create(
                model=deployment,
                messages=messages,
                stream=True,
                stream_options={"include_usage": True},
            )

            usage_info = None
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

            final = StreamChunk(content="", done=True, usage=usage_info)
            yield f"data: {final.model_dump_json()}\n\n"

        except Exception as e:
            logger.exception("Error during streaming")
            error_data = json.dumps({"error": str(e), "done": True})
            yield f"data: {error_data}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
