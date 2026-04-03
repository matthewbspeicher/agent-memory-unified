import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource


_TELEMETRY_SETUP_DONE = False

def setup_telemetry():
    global _TELEMETRY_SETUP_DONE
    if _TELEMETRY_SETUP_DONE:
        return
        
    resource = Resource(attributes={
        SERVICE_NAME: "stock-trading-api"
    })
    provider = TracerProvider(resource=resource)
    
    otlp_endpoint = os.getenv("ARIZE_OTLP_ENDPOINT", "https://otlp.arize.com/v1/traces")
    arize_api_key = os.getenv("ARIZE_API_KEY", "")
    arize_space_id = os.getenv("ARIZE_SPACE_ID", "")
    
    if arize_api_key and arize_space_id:
        otlp_exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            headers={
                "Authorization": f"Bearer {arize_api_key}",
                "space_id": arize_space_id
            }
        )
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    
    # Provider fallback / console output can be toggled by env var
    if os.getenv("ENABLE_CONSOLE_TRACING", "false").lower() == "true":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        
    trace.set_tracer_provider(provider)
    _TELEMETRY_SETUP_DONE = True

def get_tracer(name: str):
    return trace.get_tracer(name)
