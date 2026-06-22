from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Generator, Optional

from opentelemetry import trace

from .events import (
    AgentEndEvent,
    AgentStartEvent,
    AgentStepEvent,
    ErrorEvent,
    ExternalCallEvent,
    LogContext,
    merge_event,
    merge_event_json,
)
from .metrics import AgentMetrics

logger = logging.getLogger("observability_sdk")
tracer = trace.get_tracer("observability_sdk")


class AgentTracker:
    """Central tracker that ties together events, metrics, and OTel spans."""

    def __init__(
        self,
        context: LogContext,
        *,
        metrics: Optional[AgentMetrics] = None,
    ) -> None:
        self.context = context
        self.metrics = metrics or AgentMetrics(context.agent)
        self.events: list[dict[str, Any]] = []
        self._start_time: float = 0.0
        self._root_span: Optional[trace.Span] = None

    # -- full request lifecycle --------------------------------------------------

    @contextmanager
    def track_request(
        self,
        input_type: str = "unknown",
    ) -> Generator[AgentTracker, None, None]:
        """Context manager for the entire agent request (AgentStart → AgentEnd)."""
        self._start_time = time.perf_counter()

        start_evt = AgentStartEvent(agent=self.context.agent, input_type=input_type)
        self._emit(start_evt)

        span_ctx = tracer.start_as_current_span(
            f"agent.{self.context.agent}",
            attributes={
                "agent.name": self.context.agent,
                "agent.version": self.context.agent_version,
                "agent.request_id": self.context.request_id,
                "agent.input_type": input_type,
            },
        )
        success = True
        with span_ctx as span:
            self._root_span = span
            try:
                yield self
            except Exception as exc:
                success = False
                self.record_error(
                    step="agent_root",
                    error_type=type(exc).__name__,
                    retry=False,
                )
                raise
            finally:
                elapsed = (time.perf_counter() - self._start_time) * 1000
                status = "success" if success else "error"
                end_evt = AgentEndEvent(
                    agent=self.context.agent,
                    total_duration_ms=round(elapsed, 2),
                    status=status,
                )
                self._emit(end_evt)
                span.set_attribute("agent.total_duration_ms", round(elapsed, 2))
                span.set_attribute("agent.status", status)
                self.metrics.record_execution(
                    duration_ms=round(elapsed, 2),
                    success=success,
                )

    # -- step tracking -----------------------------------------------------------

    @contextmanager
    def track_step(self, name: str) -> Generator[None, None, None]:
        """Time a logical agent step and emit an AgentStepEvent."""
        start = time.perf_counter()
        success = True
        with tracer.start_as_current_span(
            f"step.{name}",
            attributes={"step.name": name},
        ) as span:
            try:
                yield
            except Exception:
                success = False
                raise
            finally:
                elapsed = (time.perf_counter() - start) * 1000
                evt = AgentStepEvent(
                    step=name,
                    duration_ms=round(elapsed, 2),
                    success=success,
                )
                self._emit(evt)
                span.set_attribute("step.duration_ms", round(elapsed, 2))
                span.set_attribute("step.success", success)

    # -- external call tracking --------------------------------------------------

    @contextmanager
    def track_external_call(
        self,
        dependency: str,
    ) -> Generator[_ExternalCallResult, None, None]:
        """Time an external dependency call and emit an ExternalCallEvent.

        The yielded ``result`` object allows the caller to set the HTTP status::

            with tracker.track_external_call("DOKOS_API") as ext:
                resp = requests.get(...)
                ext.status = resp.status_code
        """
        result = _ExternalCallResult()
        start = time.perf_counter()
        with tracer.start_as_current_span(
            f"external.{dependency}",
            attributes={"external.dependency": dependency},
        ) as span:
            try:
                yield result
            except Exception:
                if result.status == 200:
                    result.status = 500
                raise
            finally:
                elapsed = (time.perf_counter() - start) * 1000
                evt = ExternalCallEvent(
                    dependency=dependency,
                    duration_ms=round(elapsed, 2),
                    status=result.status,
                )
                self._emit(evt)
                span.set_attribute("external.duration_ms", round(elapsed, 2))
                span.set_attribute("external.status", result.status)

    # -- error recording ---------------------------------------------------------

    def record_error(
        self,
        step: str,
        error_type: str,
        retry: bool = False,
    ) -> None:
        """Record an error event."""
        evt = ErrorEvent(step=step, error_type=error_type, retry=retry)
        self._emit(evt, level="ERROR")
        if retry:
            self.metrics.record_retry(step)
        self.metrics.record_execution(duration_ms=0, success=False)

    # -- LLM usage recording -----------------------------------------------------

    def record_llm_usage(
        self,
        tokens_in: int,
        tokens_out: int,
        cost_estimated: float,
        model: str,
    ) -> None:
        """Record LLM token usage and estimated cost."""
        self.metrics.record_llm(tokens_in, tokens_out, cost_estimated, model)
        payload = {
            "event": "LLMUsage",
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_estimated": cost_estimated,
        }
        merged = self.context.to_dict()
        merged.update(payload)
        self.events.append(merged)
        logger.info(
            "LLMUsage",
            extra={"custom_dimensions": merged},
        )

    # -- cache recording ---------------------------------------------------------

    def record_cache(self, *, hit: bool) -> None:
        """Record a cache hit or miss."""
        self.metrics.record_cache(hit=hit)

    # -- internal helpers --------------------------------------------------------

    def _emit(self, event: Any, *, level: str = "INFO") -> None:
        merged = merge_event(self.context, event)
        merged["level"] = level
        self.events.append(merged)
        log_fn = logger.error if level == "ERROR" else logger.info
        log_fn(
            event.event,
            extra={"custom_dimensions": merged},
        )


class _ExternalCallResult:
    """Mutable container so callers can set an HTTP status from inside a with-block."""

    __slots__ = ("status",)

    def __init__(self) -> None:
        self.status: int = 200
