from __future__ import annotations

import asyncio
import functools
import inspect
from typing import Any, Callable, TypeVar

from .events import create_context
from .tracker import AgentTracker

F = TypeVar("F", bound=Callable[..., Any])

_TRACKER_ATTR = "_obs_tracker"


def _get_tracker_from_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> AgentTracker | None:
    """Try to find an existing AgentTracker from the call arguments."""
    for v in kwargs.values():
        if isinstance(v, AgentTracker):
            return v
    for v in args:
        if isinstance(v, AgentTracker):
            return v
    return None


# ---------------------------------------------------------------------------
# @track_agent
# ---------------------------------------------------------------------------

def track_agent(
    name: str,
    version: str = "0.0.0",
    *,
    service: str = "",
    channel: str = "",
    environment: str = "",
    input_type: str = "unknown",
) -> Callable[[F], F]:
    """Wrap a function with full AgentStart / AgentEnd lifecycle tracking.

    The decorated function receives an ``AgentTracker`` instance as the
    keyword argument ``tracker`` (unless it already has one).

    Works with both sync and async functions.
    """

    def decorator(fn: F) -> F:
        svc = service or name

        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                ctx = create_context(
                    service=svc,
                    agent=name,
                    version=version,
                    channel=channel,
                    environment=environment,
                )
                tracker = AgentTracker(ctx)
                kwargs.setdefault("tracker", tracker)
                with tracker.track_request(input_type=input_type):
                    return await fn(*args, **kwargs)

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = create_context(
                service=svc,
                agent=name,
                version=version,
                channel=channel,
                environment=environment,
            )
            tracker = AgentTracker(ctx)
            kwargs.setdefault("tracker", tracker)
            with tracker.track_request(input_type=input_type):
                return fn(*args, **kwargs)

        return sync_wrapper  # type: ignore[return-value]

    return decorator


# ---------------------------------------------------------------------------
# @track_step
# ---------------------------------------------------------------------------

def track_step(name: str) -> Callable[[F], F]:
    """Wrap a function so it is tracked as an ``AgentStep``.

    The function must receive a ``tracker`` keyword argument (or positional
    ``AgentTracker`` argument) so the decorator can emit events.
    """

    def decorator(fn: F) -> F:
        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                tracker = _get_tracker_from_args(args, kwargs)
                if tracker is None:
                    return await fn(*args, **kwargs)
                with tracker.track_step(name):
                    return await fn(*args, **kwargs)

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            tracker = _get_tracker_from_args(args, kwargs)
            if tracker is None:
                return fn(*args, **kwargs)
            with tracker.track_step(name):
                return fn(*args, **kwargs)

        return sync_wrapper  # type: ignore[return-value]

    return decorator


# ---------------------------------------------------------------------------
# @track_external
# ---------------------------------------------------------------------------

def track_external(dependency: str) -> Callable[[F], F]:
    """Wrap a function so it is tracked as an ``ExternalCall``.

    The function must receive a ``tracker`` keyword argument (or positional
    ``AgentTracker`` argument) so the decorator can emit events.
    """

    def decorator(fn: F) -> F:
        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                tracker = _get_tracker_from_args(args, kwargs)
                if tracker is None:
                    return await fn(*args, **kwargs)
                with tracker.track_external_call(dependency):
                    return await fn(*args, **kwargs)

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            tracker = _get_tracker_from_args(args, kwargs)
            if tracker is None:
                return fn(*args, **kwargs)
            with tracker.track_external_call(dependency):
                return fn(*args, **kwargs)

        return sync_wrapper  # type: ignore[return-value]

    return decorator
