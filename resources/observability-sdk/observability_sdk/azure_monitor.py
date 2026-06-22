from __future__ import annotations

import logging
from typing import Optional

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger("observability_sdk.azure_monitor")


def configure_azure_monitor(
    connection_string: str,
    *,
    service_name: str = "ai-factory-agent",
    service_version: str = "1.0.0",
    agent_name: str = "",
    environment: str = "",
    export_interval_ms: int = 60_000,
) -> None:
    """Wire up OpenTelemetry exporters for Azure Monitor.

    This sets up:
    * **Trace exporter** (``AzureMonitorTraceExporter``) attached via
      ``BatchSpanProcessor`` to the global ``TracerProvider``.
    * **Metric exporter** (``AzureMonitorMetricExporter``) attached via
      ``PeriodicExportingMetricReader`` to the global ``MeterProvider``.
    * **Log exporter** (``AzureMonitorLogExporter``) attached to the root
      ``logging`` handler so structured logs appear in Application Insights.

    Parameters
    ----------
    connection_string:
        Application Insights connection string.
    service_name:
        Value written to the ``service.name`` resource attribute.
    service_version:
        Value written to the ``service.version`` resource attribute.
    agent_name:
        Optional agent identifier stored as ``agent.name`` resource attribute.
    environment:
        Deployment environment (``prod``, ``staging``, …).
    export_interval_ms:
        How often the periodic metric reader flushes (default 60 s).
    """
    from azure.monitor.opentelemetry.exporter import (
        AzureMonitorLogExporter,
        AzureMonitorMetricExporter,
        AzureMonitorTraceExporter,
    )
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

    resource_attrs: dict[str, str] = {
        "service.name": service_name,
        "service.version": service_version,
    }
    if agent_name:
        resource_attrs["agent.name"] = agent_name
    if environment:
        resource_attrs["deployment.environment"] = environment

    resource = Resource.create(resource_attrs)

    # -- Traces ------------------------------------------------------------------
    trace_exporter = AzureMonitorTraceExporter(connection_string=connection_string)
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(tracer_provider)

    # -- Metrics -----------------------------------------------------------------
    metric_exporter = AzureMonitorMetricExporter(connection_string=connection_string)
    metric_reader = PeriodicExportingMetricReader(
        metric_exporter,
        export_interval_millis=export_interval_ms,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # -- Logs --------------------------------------------------------------------
    log_exporter = AzureMonitorLogExporter(connection_string=connection_string)
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    handler = LoggingHandler(logger_provider=logger_provider)
    handler.setLevel(logging.INFO)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    logger.info(
        "Azure Monitor configured: service=%s version=%s",
        service_name,
        service_version,
    )
