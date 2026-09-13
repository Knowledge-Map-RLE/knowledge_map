"""Телеметрия API-слоя: счётчики и гистограммы для LLM-вызовов.

Используются *одноразовые* инструменты OTel Metrics SDK:
``request_counter`` (km_api_llm_requests_total),
``token_counter``   (km_api_llm_tokens_total),
``latency_hist``    (km_api_llm_duration_seconds — histogram).

Все операции идемпотентны и ленивы (Lazy singleton pattern):
первый вызов ``record_llm_*`` создаёт инструменты, далее они переиспользуются.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from opentelemetry import metrics

log = logging.getLogger(__name__)

_meter = None
_request_counter = None
_token_counter = None
_latency_hist = None

_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "api")
_METER_NAME = f"knowledge-map.{_SERVICE_NAME}"


def _get_meter():
    global _meter
    if _meter is None:
        _meter = metrics.get_meter(_METER_NAME)
    return _meter


def _ensure():
    global _request_counter, _token_counter, _latency_hist
    meter = _get_meter()
    if _request_counter is None:
        _request_counter = meter.create_counter(
            "km_api_llm_requests_total",
            unit="1",
            description="Total LLM requests initiated by the service",
        )
    if _token_counter is None:
        _token_counter = meter.create_counter(
            "km_api_llm_tokens_total",
            unit="tokens",
            description="Tokens consumed or produced by LLM calls",
        )
    if _latency_hist is None:
        _latency_hist = meter.create_histogram(
            "km_api_llm_duration_seconds",
            unit="s",
            description="Wall-clock duration of LLM request",
        )


def record_llm_request(
    model: str,
    *,
    ok: bool = True,
    duration_seconds: Optional[float] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
) -> None:
    """Записывает ONE LLM-вызов:
    - request counter (model, result=ok/error)
    - token counters  (model, direction=in|out)
    - latency histogram (seconds)
    """
    try:
        _ensure()
        attrs = {"model": model}
        _request_counter.add(1, attributes={**attrs, "result": "ok" if ok else "error"})
        if duration_seconds is not None:
            _latency_hist.record(duration_seconds, attributes=attrs)
        if input_tokens and input_tokens > 0:
            _token_counter.add(input_tokens, attributes={**attrs, "direction": "in"})
        if output_tokens and output_tokens > 0:
            _token_counter.add(output_tokens, attributes={**attrs, "direction": "out"})
    except Exception as exc:  # pragma: no cover — telemetry must never break business logic
        log.debug("record_llm_request telemetry error: %s", exc, exc_info=True)
