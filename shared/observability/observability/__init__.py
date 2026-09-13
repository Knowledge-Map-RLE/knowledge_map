"""OpenTelemetry + logfmt для микросервисов Knowledge Map.

Единая точка инициализации observability::

    from observability import init_telemetry, setup_logging, instrument_fastapi

    setup_logging(service_name="api")
    init_telemetry(service_name="api")
    instrument_fastapi()

Конфигурация — стандартными OTel env-переменными:
- ``OTEL_EXPORTER_OTLP_ENDPOINT`` (по умолчанию http://127.0.0.1:4317)
- ``OTEL_SERVICE_NAME`` / ``OTEL_SERVICE_VERSION``
- ``OTEL_RESOURCE_ATTRIBUTES`` (key=value, разделитель `,`)
- ``OTEL_TRACES_SAMPLER`` / ``OTEL_TRACES_SAMPLER_ARG``
- ``OTEL_METRIC_EXPORT_INTERVAL`` (мс, по умолчанию 30000)
- ``OTEL_SDK_DISABLED=true`` — полное отключение (трассировка/метрики), логи остаются.

Логи всегда пишутся в stdout (logfmt) и НЕ дублируются в файлы.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import (
    Resource,
    SERVICE_NAME,
    SERVICE_NAMESPACE,
    SERVICE_VERSION,
    DEPLOYMENT_ENVIRONMENT,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import (
    ALWAYS_OFF,
    ALWAYS_ON,
    ParentBased,
    TraceIdRatioBased,
)

from ._logfmt import LogfmtFormatter, setup_logging

_INITIALIZED = False
_LOGGER_SETUP_DONE = False

_DEFAULT_OTLP_ENDPOINT = "http://127.0.0.1:4317"
_SAMPLERS = {
    "always_on": ALWAYS_ON,
    "always_off": ALWAYS_OFF,
    "parentbased_always_on": ParentBased(ALWAYS_ON),
    "parentbased_always_off": ParentBased(ALWAYS_OFF),
}


def build_resource(service_name: Optional[str] = None, extra: Optional[dict] = None) -> Resource:
    """Собирает OTel Resource из env + явных атрибутов."""
    attributes = {
        SERVICE_NAMESPACE: "knowledge-map",
        DEPLOYMENT_ENVIRONMENT: os.getenv("ENVIRONMENT", "development"),
        "service.instance.id": str(uuid.uuid4()),
    }
    service = service_name or os.getenv("OTEL_SERVICE_NAME")
    if service:
        attributes[SERVICE_NAME] = service
    version = os.getenv("OTEL_SERVICE_VERSION")
    if version:
        attributes[SERVICE_VERSION] = version
    for chunk in os.getenv("OTEL_RESOURCE_ATTRIBUTES", "").split(","):
        if "=" in chunk:
            key, _, value = chunk.partition("=")
            attributes[key.strip()] = value.strip()
    if extra:
        attributes.update(extra)
    return Resource.create(attributes)


def _build_sampler():
    name = os.getenv("OTEL_TRACES_SAMPLER", "parentbased_always_on")
    try:
        if name in _SAMPLERS:
            return _SAMPLERS[name]
        if name == "traceidratio":
            return TraceIdRatioBased(_sampler_arg())
        if name == "parentbased_traceidratio":
            return ParentBased(TraceIdRatioBased(_sampler_arg()))
    except ValueError:
        pass
    return ParentBased(ALWAYS_ON)


def _sampler_arg() -> float:
    try:
        return float(os.getenv("OTEL_TRACES_SAMPLER_ARG", "1.0"))
    except ValueError:
        return 1.0


def _endpoint() -> str:
    return os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", _DEFAULT_OTLP_ENDPOINT)


def is_enabled() -> bool:
    return not os.getenv("OTEL_SDK_DISABLED", "").lower() in ("1", "true", "yes")


def init_telemetry(service_name: Optional[str] = None, extra_attrs: Optional[dict] = None) -> bool:
    """Инициализирует tracer/meter providers с OTLP-экспортерами. Идемпотентна."""
    global _INITIALIZED
    if _INITIALIZED:
        return True
    if not is_enabled():
        _INITIALIZED = True
        return False

    resource = build_resource(service_name, extra_attrs)

    tracer_provider = TracerProvider(resource=resource, sampler=_build_sampler())
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=_endpoint(), insecure=True),
        )
    )
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=_endpoint(), insecure=True),
        export_interval_millis=_metric_export_interval(),
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    _INITIALIZED = True
    return True


def _metric_export_interval() -> int:
    import re

    value = os.getenv("OTEL_METRIC_EXPORT_INTERVAL", "30000")
    if re.fullmatch(r"\d+", value):
        return max(int(value), 1000)
    return 30000


def get_tracer(*parts: str) -> trace.Tracer:
    name = ".".join(part.strip("/") for part in parts if part) or "knowledge-map"
    return trace.get_tracer(name)


def attach_request_attrs(session_id: Optional[str] = None, user_id: Optional[str] = None) -> None:
    """Прокидывает идентификаторы клиента в активный span."""
    span = trace.get_current_span()
    if not span.is_recording():
        return
    if session_id:
        span.set_attribute("client.session_id", session_id)
    if user_id:
        span.set_attribute("auth.user_id", user_id)


def instrument_fastapi() -> bool:
    """Включает автоматическую инструментацию FastAPI (ASGI)."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor().instrument()
        return True
    except Exception as exc:  # pragma: no cover
        logging.getLogger("observability").warning("fastapi instrumentation skipped: %s", exc)
        return False


def instrument_grpc_server() -> bool:
    try:
        from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer

        GrpcInstrumentorServer().instrument()
        return True
    except Exception as exc:  # pragma: no cover
        logging.getLogger("observability").warning("grpc server instrumentation skipped: %s", exc)
        return False


def instrument_grpc_client() -> bool:
    try:
        from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient

        GrpcInstrumentorClient().instrument()
        return True
    except Exception as exc:  # pragma: no cover
        logging.getLogger("observability").warning("grpc client instrumentation skipped: %s", exc)
        return False


def instrument_httpx() -> bool:
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
        return True
    except Exception as exc:  # pragma: no cover
        logging.getLogger("observability").warning("httpx instrumentation skipped: %s", exc)
        return False


def instrument_asyncio() -> bool:
    try:
        from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor

        AsyncioInstrumentor().instrument()
        return True
    except Exception as exc:  # pragma: no cover
        logging.getLogger("observability").warning("asyncio instrumentation skipped: %s", exc)
        return False


__all__ = [
    "LogfmtFormatter",
    "setup_logging",
    "init_telemetry",
    "build_resource",
    "get_tracer",
    "attach_request_attrs",
    "instrument_fastapi",
    "instrument_grpc_server",
    "instrument_grpc_client",
    "instrument_httpx",
    "instrument_asyncio",
    "is_enabled",
]