"""
OTel spans for PatchNoz itself.

Instruments PatchNoz internal execution (orchestration, telemetry collection, diagnosis)
with OpenTelemetry and sends traces to SigNoz OTLP collector on localhost:4317.
"""

import os
from contextlib import contextmanager
from typing import Generator, Optional, Dict, Any
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider, Span
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource

_PROVIDER: Optional[TracerProvider] = None
_TRACER: Optional[trace.Tracer] = None


def init_telemetry(service_name: str = "patchnoz-agent", otlp_endpoint: Optional[str] = None) -> trace.Tracer:
    """Initializes the global OpenTelemetry TracerProvider and BatchSpanProcessor."""
    global _PROVIDER, _TRACER
    if _TRACER is not None:
        return _TRACER

    endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    resource = Resource.create(attributes={"service.name": service_name})
    _PROVIDER = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    _PROVIDER.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(_PROVIDER)
    _TRACER = trace.get_tracer("patchnoz")
    return _TRACER


def get_tracer() -> trace.Tracer:
    """Gets or initializes the PatchNoz tracer."""
    global _TRACER
    if _TRACER is None:
        return init_telemetry()
    return _TRACER


@contextmanager
def trace_span(name: str, attributes: Optional[Dict[str, Any]] = None) -> Generator[Span, None, None]:
    """Context manager for creating a traced span with optional attributes."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                if isinstance(v, (str, int, float, bool)):
                    span.set_attribute(k, v)
                else:
                    span.set_attribute(str(k), str(v))
        yield span


def flush_telemetry():
    """Flushes and shuts down the TracerProvider to ensure all spans are transmitted."""
    global _PROVIDER
    if _PROVIDER is not None:
        _PROVIDER.force_flush()
        _PROVIDER.shutdown()
