"""
Self Telemetry

Configures OpenTelemetry exactly once for the PatchNoz agent process and
exports spans to the SigNoz OTLP collector. This is what makes PatchNoz's
own diagnose/act pipeline show up inside SigNoz, right next to the
telemetry it is investigating.

Standard span names used across PatchNoz modules:
    patchnoz.incident.run
    patchnoz.telemetry.collect_evidence
    patchnoz.signoz_mcp.call
    patchnoz.diagnosis.summarize
    patchnoz.action.execute
    patchnoz.action.slack
    patchnoz.action.github
"""

import os
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from src.env import load_env

load_env()

DEFAULT_OTLP_ENDPOINT = "http://localhost:4317"
DEFAULT_SERVICE_NAME = "patchnoz-agent"

_provider: Optional[TracerProvider] = None
_tracer: Optional[trace.Tracer] = None


def configure_tracing(service_name: str = DEFAULT_SERVICE_NAME, otlp_endpoint: Optional[str] = None) -> trace.Tracer:
    """Idempotently configures the global TracerProvider + OTLP exporter and returns a tracer."""
    global _provider, _tracer
    if _tracer is not None:
        return _tracer

    endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", DEFAULT_OTLP_ENDPOINT)
    resource = Resource.create({"service.name": service_name})
    _provider = TracerProvider(resource=resource)
    _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
    trace.set_tracer_provider(_provider)
    _tracer = trace.get_tracer(service_name)
    return _tracer


def get_tracer() -> trace.Tracer:
    """Returns the PatchNoz tracer, configuring tracing on first use."""
    if _tracer is None:
        return configure_tracing()
    return _tracer


@contextmanager
def start_span(name: str, attributes: Optional[Dict[str, Any]] = None) -> Generator[trace.Span, None, None]:
    """Convenience context manager: starts a span with the given name/attributes."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        _set_attributes(span, attributes)
        yield span


def _set_attributes(span: trace.Span, attributes: Optional[Dict[str, Any]]) -> None:
    if not attributes:
        return
    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            span.set_attribute(key, value)
        else:
            span.set_attribute(key, str(value))


def flush_telemetry() -> None:
    """Flushes and shuts down the TracerProvider so all spans reach SigNoz before exit."""
    global _provider
    if _provider is not None:
        _provider.force_flush()
        _provider.shutdown()
