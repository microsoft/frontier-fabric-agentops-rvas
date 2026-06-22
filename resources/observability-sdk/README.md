# Observability SDK — AI Factory Framework

Shared Python library that provides **structured event logging**, **OpenTelemetry metrics & traces**, and **Azure Monitor integration** for AI-powered agents.

## Installation

```bash
pip install -e /path/to/observability-sdk
```

## Quick Start

```python
from observability_sdk import AgentTracker, create_context

ctx = create_context(
    service="billing-agent",
    agent="BillingAgent",
    version="1.3.0",
    channel="web",
    environment="prod",
    client_id_hash="c9f1a2",
)

tracker = AgentTracker(ctx)

with tracker.track_request(input_type="billing_question"):
    with tracker.track_step("ocr_extraction"):
        invoice_id = extract_invoice(image)

    with tracker.track_external_call("DOKOS_API") as ext:
        data = dokos.get(invoice_id)
        ext.status = 200

    tracker.record_llm_usage(
        tokens_in=350, tokens_out=120,
        cost_estimated=0.0071, model="gpt-4o-mini",
    )

# All events are available in tracker.events
```

### Using Decorators

```python
from observability_sdk import track_agent, track_step, track_external

@track_agent(name="BillingAgent", version="1.3.0")
def handle_billing(question: str, tracker=None):
    result = parse_invoice(question, tracker=tracker)
    return result

@track_step("invoice_parsing")
def parse_invoice(text: str, tracker=None):
    ...

@track_external("DOKOS_API")
def call_dokos(invoice_id: str, tracker=None):
    ...
```

## Event Reference

| Event | Key Fields |
|-------|-----------|
| `AgentStart` | `agent`, `input_type` |
| `AgentStep` | `step`, `duration_ms`, `success` |
| `ExternalCall` | `dependency`, `duration_ms`, `status` |
| `AgentEnd` | `agent`, `total_duration_ms`, `status` |
| `Error` | `step`, `error_type`, `retry` |

Every event is merged with the **common log base**:

```json
{
  "timestamp": "2024-11-10T14:23:01Z",
  "level": "INFO",
  "service": "billing-agent",
  "agent": "BillingAgent",
  "agent_version": "1.3.0",
  "request_id": "req-abc12345",
  "client_id_hash": "c9f1a2",
  "channel": "web",
  "environment": "prod"
}
```

## Metrics Reference

All metrics follow the namespace pattern `metrics.agent.{agent_name}.*`.

| Metric | Type | Description |
|--------|------|-------------|
| `agent_execution_time_ms` | Histogram | End-to-end agent latency |
| `success_count` | Counter | Successful executions |
| `error_count` | Counter | Failed executions |
| `retries_count` | Counter | Retry attempts |
| `llm_tokens_in` | Counter | LLM input tokens |
| `llm_tokens_out` | Counter | LLM output tokens |
| `llm_cost_estimated` | Gauge | Estimated LLM cost (USD) |
| `cache_hit` | Counter | Cache hits |
| `cache_miss` | Counter | Cache misses |

## KPI Targets

| KPI | Target |
|-----|--------|
| P95 latency | < 15 000 ms |
| Error rate | < 1 % |
| Retry rate | < 3 % |
| Avg cost / request | Tracked via `llm_cost_estimated` |

## Azure Monitor / Application Insights

```python
from observability_sdk import configure_azure_monitor

configure_azure_monitor(
    connection_string="InstrumentationKey=...",
    service_name="billing-agent",
    service_version="1.3.0",
    agent_name="BillingAgent",
    environment="prod",
)
```

This wires up:

* **Trace exporter** — spans appear in the Application Insights *Transaction search*.
* **Metric exporter** — counters and histograms flow into *Metrics Explorer*.
* **Log exporter** — structured JSON events appear in *Traces* / *Custom Events*.

## Alert Configuration

```python
from observability_sdk import AlertConfig, MetricsSnapshot, check_thresholds

config = AlertConfig(
    error_rate_threshold=0.02,
    p95_latency_threshold_ms=15_000,
    retry_rate_threshold=0.03,
    daily_cost_variance_threshold=0.20,
)

snapshot = MetricsSnapshot(error_rate=0.03, p95_latency_ms=16_000)
alerts = check_thresholds(snapshot, config)

for alert in alerts:
    print(f"[{alert.severity}] {alert.name}: {alert.message}")
```

**Severity levels:**

| Severity | Triggers |
|----------|----------|
| `CRITICAL` | Error rate, P95 latency, retry rate |
| `IMPORTANT` | Daily cost variance |
| `DEGRADATION` | Cache hit rate, parsing time |
