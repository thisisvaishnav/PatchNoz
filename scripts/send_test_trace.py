from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
import time

trace.set_tracer_provider(TracerProvider())
span_exporter = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(span_exporter))
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("test-manual"):
    print("Trace sent.")
# force flush
time.sleep(2)
