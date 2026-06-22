from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class LogContext(BaseModel):
    """Common log base — mandatory for every agent event."""

    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    level: str = "INFO"
    service: str
    agent: str
    agent_version: str
    request_id: str = Field(default_factory=lambda: f"req-{uuid.uuid4().hex[:8]}")
    client_id_hash: str = ""
    channel: Literal["web", "ivr", "whatsapp", "api", ""] = ""
    environment: Literal["prod", "staging", "dev", "test", ""] = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    def to_json(self) -> str:
        return self.model_dump_json()


class AgentStartEvent(BaseModel):
    """Emitted when an agent begins processing a request."""

    event: Literal["AgentStart"] = "AgentStart"
    agent: str
    input_type: str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    def to_json(self) -> str:
        return self.model_dump_json()


class AgentStepEvent(BaseModel):
    """Emitted after each logical step inside an agent."""

    event: Literal["AgentStep"] = "AgentStep"
    step: str
    duration_ms: float
    success: bool

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    def to_json(self) -> str:
        return self.model_dump_json()


class ExternalCallEvent(BaseModel):
    """Emitted after an external dependency call."""

    event: Literal["ExternalCall"] = "ExternalCall"
    dependency: str
    duration_ms: float
    status: int

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    def to_json(self) -> str:
        return self.model_dump_json()


class AgentEndEvent(BaseModel):
    """Emitted when the agent finishes processing."""

    event: Literal["AgentEnd"] = "AgentEnd"
    agent: str
    total_duration_ms: float
    status: Literal["success", "error", "timeout"]

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    def to_json(self) -> str:
        return self.model_dump_json()


class ErrorEvent(BaseModel):
    """Emitted when an error occurs during processing."""

    event: Literal["Error"] = "Error"
    step: str
    error_type: str
    retry: bool = False

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    def to_json(self) -> str:
        return self.model_dump_json()


def create_context(
    service: str,
    agent: str,
    version: str,
    channel: str = "",
    environment: str = "",
    *,
    client_id_hash: str = "",
) -> LogContext:
    """Factory that builds a LogContext with auto-generated request_id and timestamp."""
    return LogContext(
        service=service,
        agent=agent,
        agent_version=version,
        channel=channel,
        environment=environment,
        client_id_hash=client_id_hash,
    )


def merge_event(context: LogContext, event: BaseModel) -> dict[str, Any]:
    """Merge the common log context with an event payload into a single dict."""
    merged = context.to_dict()
    merged.update(event.to_dict())
    return merged


def merge_event_json(context: LogContext, event: BaseModel) -> str:
    """Merge context + event and serialise to a JSON string."""
    return json.dumps(merge_event(context, event))
