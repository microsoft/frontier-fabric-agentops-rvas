from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AlertSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    IMPORTANT = "IMPORTANT"
    DEGRADATION = "DEGRADATION"


@dataclass
class Alert:
    """A single triggered alert."""

    severity: AlertSeverity
    name: str
    message: str
    current_value: float
    threshold: float


@dataclass
class AlertConfig:
    """Threshold configuration derived from the AI Factory KPI targets."""

    error_rate_threshold: float = 0.02
    p95_latency_threshold_ms: float = 15_000.0
    retry_rate_threshold: float = 0.03
    daily_cost_variance_threshold: float = 0.20
    cache_hit_rate_min: float = 0.50
    avg_parsing_time_max_ms: float = 10_000.0


@dataclass
class MetricsSnapshot:
    """Point-in-time snapshot of agent metrics used for threshold checks."""

    error_rate: float = 0.0
    p95_latency_ms: float = 0.0
    retry_rate: float = 0.0
    daily_cost_variance: float = 0.0
    cache_hit_rate: float = 1.0
    avg_parsing_time_ms: float = 0.0


def check_thresholds(
    snapshot: MetricsSnapshot,
    config: AlertConfig | None = None,
) -> list[Alert]:
    """Evaluate a metrics snapshot against the configured thresholds.

    Returns a list of ``Alert`` objects for every threshold that is exceeded.
    """
    cfg = config or AlertConfig()
    alerts: list[Alert] = []

    # CRITICAL — error rate
    if snapshot.error_rate > cfg.error_rate_threshold:
        alerts.append(
            Alert(
                severity=AlertSeverity.CRITICAL,
                name="high_error_rate",
                message=(
                    f"Error rate {snapshot.error_rate:.2%} exceeds "
                    f"threshold {cfg.error_rate_threshold:.2%}"
                ),
                current_value=snapshot.error_rate,
                threshold=cfg.error_rate_threshold,
            )
        )

    # CRITICAL — P95 latency
    if snapshot.p95_latency_ms > cfg.p95_latency_threshold_ms:
        alerts.append(
            Alert(
                severity=AlertSeverity.CRITICAL,
                name="high_p95_latency",
                message=(
                    f"P95 latency {snapshot.p95_latency_ms:.0f}ms exceeds "
                    f"threshold {cfg.p95_latency_threshold_ms:.0f}ms"
                ),
                current_value=snapshot.p95_latency_ms,
                threshold=cfg.p95_latency_threshold_ms,
            )
        )

    # IMPORTANT — daily cost variance
    if snapshot.daily_cost_variance > cfg.daily_cost_variance_threshold:
        alerts.append(
            Alert(
                severity=AlertSeverity.IMPORTANT,
                name="high_cost_variance",
                message=(
                    f"Daily cost variance {snapshot.daily_cost_variance:.2%} exceeds "
                    f"threshold {cfg.daily_cost_variance_threshold:.2%}"
                ),
                current_value=snapshot.daily_cost_variance,
                threshold=cfg.daily_cost_variance_threshold,
            )
        )

    # DEGRADATION — cache hit rate
    if snapshot.cache_hit_rate < cfg.cache_hit_rate_min:
        alerts.append(
            Alert(
                severity=AlertSeverity.DEGRADATION,
                name="low_cache_hit_rate",
                message=(
                    f"Cache hit rate {snapshot.cache_hit_rate:.2%} below "
                    f"minimum {cfg.cache_hit_rate_min:.2%}"
                ),
                current_value=snapshot.cache_hit_rate,
                threshold=cfg.cache_hit_rate_min,
            )
        )

    # DEGRADATION — avg parsing time
    if snapshot.avg_parsing_time_ms > cfg.avg_parsing_time_max_ms:
        alerts.append(
            Alert(
                severity=AlertSeverity.DEGRADATION,
                name="slow_parsing",
                message=(
                    f"Avg parsing time {snapshot.avg_parsing_time_ms:.0f}ms exceeds "
                    f"threshold {cfg.avg_parsing_time_max_ms:.0f}ms"
                ),
                current_value=snapshot.avg_parsing_time_ms,
                threshold=cfg.avg_parsing_time_max_ms,
            )
        )

    # CRITICAL — retry rate (treated as latency-class SLA breach)
    if snapshot.retry_rate > cfg.retry_rate_threshold:
        alerts.append(
            Alert(
                severity=AlertSeverity.CRITICAL,
                name="high_retry_rate",
                message=(
                    f"Retry rate {snapshot.retry_rate:.2%} exceeds "
                    f"threshold {cfg.retry_rate_threshold:.2%}"
                ),
                current_value=snapshot.retry_rate,
                threshold=cfg.retry_rate_threshold,
            )
        )

    return alerts
