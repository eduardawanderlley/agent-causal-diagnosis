"""Exporter wiring.

In production the agent sends OTLP over HTTP to an OpenTelemetry Collector,
which fans the same traces out to Langfuse and LangSmith. See
deploy/otel-collector.yaml. The application code never talks to either vendor
directly, so comparing what each platform shows needs no re-instrumentation.
"""

from __future__ import annotations

import os


def otlp_exporter_from_env():
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return None
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    return OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")
