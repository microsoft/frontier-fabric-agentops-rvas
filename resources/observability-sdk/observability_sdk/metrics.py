from __future__ import annotations

from typing import Optional

from opentelemetry import metrics
from opentelemetry.metrics import Counter, Histogram, Meter, ObservableGauge


class AgentMetrics:
    """OpenTelemetry metrics following the ``metrics.agent.{name}.*`` namespace."""

    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name
        namespace = f"metrics.agent.{agent_name}"
        self._meter: Meter = metrics.get_meter(namespace)

        # Technical
        self.execution_time: Histogram = self._meter.create_histogram(
            name=f"{namespace}.agent_execution_time_ms",
            description="Agent execution time in milliseconds",
            unit="ms",
        )
        self.success_count: Counter = self._meter.create_counter(
            name=f"{namespace}.success_count",
            description="Number of successful agent executions",
        )
        self.error_count: Counter = self._meter.create_counter(
            name=f"{namespace}.error_count",
            description="Number of failed agent executions",
        )
        self.retries_count: Counter = self._meter.create_counter(
            name=f"{namespace}.retries_count",
            description="Number of retries across all steps",
        )

        # LLM
        self.llm_tokens_in: Counter = self._meter.create_counter(
            name=f"{namespace}.llm_tokens_in",
            description="Total input tokens sent to LLM",
        )
        self.llm_tokens_out: Counter = self._meter.create_counter(
            name=f"{namespace}.llm_tokens_out",
            description="Total output tokens received from LLM",
        )
        self._llm_cost_value: float = 0.0
        self.llm_cost_estimated: ObservableGauge = self._meter.create_observable_gauge(
            name=f"{namespace}.llm_cost_estimated",
            description="Estimated cost of the last LLM call in USD",
            callbacks=[self._observe_llm_cost],
        )

        # Cache
        self.cache_hit: Counter = self._meter.create_counter(
            name=f"{namespace}.cache_hit",
            description="Number of cache hits",
        )
        self.cache_miss: Counter = self._meter.create_counter(
            name=f"{namespace}.cache_miss",
            description="Number of cache misses",
        )

    # -- observable gauge callback -----------------------------------------------

    def _observe_llm_cost(
        self,
        options: metrics.CallbackOptions,
    ) -> list[metrics.Observation]:
        return [metrics.Observation(self._llm_cost_value)]

    # -- convenience helpers -----------------------------------------------------

    def record_execution(
        self,
        duration_ms: float,
        success: bool,
        agent_name: Optional[str] = None,
    ) -> None:
        """Record a completed execution with its duration and outcome."""
        labels = {"agent": agent_name or self.agent_name}
        self.execution_time.record(duration_ms, labels)
        if success:
            self.success_count.add(1, labels)
        else:
            self.error_count.add(1, labels)

    def record_llm(
        self,
        tokens_in: int,
        tokens_out: int,
        cost: float,
        model: str,
    ) -> None:
        """Record LLM usage metrics."""
        labels = {"model": model, "agent": self.agent_name}
        self.llm_tokens_in.add(tokens_in, labels)
        self.llm_tokens_out.add(tokens_out, labels)
        self._llm_cost_value = cost

    def record_cache(self, *, hit: bool) -> None:
        """Record a cache hit or miss."""
        labels = {"agent": self.agent_name}
        if hit:
            self.cache_hit.add(1, labels)
        else:
            self.cache_miss.add(1, labels)

    def record_retry(self, step: str) -> None:
        """Increment retry counter for a given step."""
        self.retries_count.add(1, {"agent": self.agent_name, "step": step})
