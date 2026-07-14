"""Optional OTLP tracing configuration for a local or remote collector."""

from fastapi import FastAPI

from app.services.config import Settings


def configure_telemetry(app: FastAPI, settings: Settings) -> bool:
    """有効時だけ依存パッケージを読み込み、FastAPI の span を OTLP へ送る。"""
    if not settings.otel_enabled:
        return False
    # 無効な環境では OpenTelemetry を必須依存にしないため遅延 import する。
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        raise RuntimeError(
            "OTEL_ENABLED requires the OpenTelemetry packages from requirements.txt"
        ) from exc

    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.otel_service_name})
    )
    exporter = OTLPSpanExporter(
        endpoint=f"{settings.otel_exporter_endpoint.rstrip('/')}/v1/traces"
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    return True
