#!/usr/bin/env python3
"""Complete billing-agent example using the observability SDK.

Run::

    pip install -e /path/to/observability-sdk
    python billing_agent_example.py

No Azure Monitor connection string is required — the example uses the
in-process OpenTelemetry SDK so you can inspect the emitted events in the
console output.
"""
from __future__ import annotations

import json
import logging
import random
import time

from observability_sdk import (
    AgentTracker,
    AlertConfig,
    MetricsSnapshot,
    check_thresholds,
    create_context,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")


# ---------------------------------------------------------------------------
# Simulated helpers
# ---------------------------------------------------------------------------

def simulate_ocr(tracker: AgentTracker) -> str:
    """Simulate OCR extraction of an invoice image."""
    with tracker.track_step("ocr_extraction"):
        time.sleep(random.uniform(0.05, 0.15))
        tracker.record_cache(hit=random.choice([True, False]))
        return "INV-2024-00421"


def simulate_dokos_lookup(tracker: AgentTracker, invoice_id: str) -> dict:
    """Simulate a call to the DOKOS billing API."""
    with tracker.track_external_call("DOKOS_API") as ext:
        time.sleep(random.uniform(0.05, 0.20))
        ext.status = 200
        return {"invoice_id": invoice_id, "amount": 142.50, "currency": "EUR"}


def simulate_llm_summarise(tracker: AgentTracker, data: dict) -> str:
    """Simulate an LLM call that summarises the invoice data."""
    with tracker.track_step("llm_summarisation"):
        time.sleep(random.uniform(0.03, 0.10))
        tokens_in = random.randint(200, 500)
        tokens_out = random.randint(80, 200)
        cost = round((tokens_in * 0.00001) + (tokens_out * 0.00003), 6)
        tracker.record_llm_usage(
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_estimated=cost,
            model="gpt-4o-mini",
        )
        return f"Invoice {data['invoice_id']}: {data['amount']} {data['currency']}"


def simulate_validation(tracker: AgentTracker, summary: str) -> bool:
    """Simulate a validation step that occasionally fails."""
    with tracker.track_step("validation"):
        time.sleep(random.uniform(0.01, 0.05))
        success = random.random() > 0.15
        if not success:
            tracker.record_error(
                step="validation",
                error_type="ValidationMismatch",
                retry=True,
            )
        return success


# ---------------------------------------------------------------------------
# Main agent flow
# ---------------------------------------------------------------------------

def run_billing_agent() -> None:
    """Execute the full billing-agent request lifecycle."""
    ctx = create_context(
        service="billing-agent",
        agent="BillingAgent",
        version="1.3.0",
        channel="web",
        environment="dev",
        client_id_hash="c9f1a2",
    )

    tracker = AgentTracker(ctx)

    with tracker.track_request(input_type="billing_question"):
        # Step 1 — OCR extraction
        invoice_id = simulate_ocr(tracker)

        # Step 2 — External dependency call
        invoice_data = simulate_dokos_lookup(tracker, invoice_id)

        # Step 3 — LLM summarisation
        summary = simulate_llm_summarise(tracker, invoice_data)

        # Step 4 — Validation (with possible retry)
        valid = simulate_validation(tracker, summary)
        if not valid:
            # Retry once
            valid = simulate_validation(tracker, summary)

    # -----------------------------------------------------------------------
    # Print all collected events
    # -----------------------------------------------------------------------
    print("\n===== Collected Events =====")
    for evt in tracker.events:
        print(json.dumps(evt, indent=2))

    # -----------------------------------------------------------------------
    # Alert check example
    # -----------------------------------------------------------------------
    snapshot = MetricsSnapshot(
        error_rate=0.03,
        p95_latency_ms=16_500,
        retry_rate=0.04,
        daily_cost_variance=0.10,
        cache_hit_rate=0.45,
    )
    alerts = check_thresholds(snapshot)
    if alerts:
        print("\n===== Triggered Alerts =====")
        for a in alerts:
            print(f"[{a.severity.value}] {a.name}: {a.message}")
    else:
        print("\nNo alerts triggered.")


if __name__ == "__main__":
    run_billing_agent()
