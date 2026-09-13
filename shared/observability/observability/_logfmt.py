"""logfmt (key=value) логгер для stdout → Loki.

Строка вида::

    ts=2026-09-12T13:05:02.951 level=info logger=web.app service=api trace_id=... span_id=... msg="..."

- trace_id/span_id берутся из активного OTel span (автокорреляция с Tempo);
- дополнительные поля можно передать через ``extra={"attrs": {...}}`` или
  ``logger.info(..., extra={"session_id": ...})`` (ключи из ``_EXTRA``);
- значения с пробелами/спецсимволами экранируются кавычками.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any, Optional

from opentelemetry import trace

_EXTRA = (
    "service", "session_id", "user_id", "method", "path", "status",
    "duration_ms", "error_class", "error_message",
)


def _escape(value: str) -> str:
    if value == "":
        return '""'
    if _needs_quoting(value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def _needs_quoting(value: str) -> bool:
    for ch in value:
        if ch in ' "' or ch in "=\t\r\n" or ord(ch) < 32:
            return True
    return False


def _kv(key: str, value: Any) -> str:
    if isinstance(value, bool):
        text = "true" if value else "false"
    else:
        text = str(value)
    return f"{key}={_escape(text)}"


def _iso_timestamp(ts: float) -> str:
    base = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts))
    frac = int((ts % 1) * 1000)
    return f"{base}.{frac:03d}"


class LogfmtFormatter(logging.Formatter):
    """Форматтер Python logging в формате logfmt."""

    def __init__(self, service_name: Optional[str] = None) -> None:
        super().__init__()
        self._service = service_name

    def format(self, record: logging.LogRecord) -> str:
        parts = [
            "ts=" + _iso_timestamp(record.created),
            "level=%s" % record.levelname.lower(),
            "logger=" + _escape(record.name),
        ]
        if self._service:
            parts.append("service=" + _escape(self._service))

        trace_id = span_id = ""
        otel_trace_id = record.__dict__.get("otel_trace_id")
        if otel_trace_id:
            trace_id = str(otel_trace_id)
            span_id = str(record.__dict__.get("otel_span_id", ""))
        else:
            ctx = trace.get_current_span().get_span_context()
            if ctx.is_valid:
                trace_id = format(ctx.trace_id, "032x")
                span_id = format(ctx.span_id, "016x")
        if trace_id:
            parts.append("trace_id=" + trace_id)
            parts.append("span_id=" + span_id)

        parts.append("msg=" + _escape(record.getMessage()))

        if record.exc_info:
            exc_type = record.exc_info[0]
            exc_value = record.exc_info[1]
            parts.append("error_class=" + _escape(exc_type.__name__ if exc_type else "Exception"))
            parts.append("error_message=" + _escape(str(exc_value)))

        attrs = record.__dict__.get("attrs")
        if isinstance(attrs, dict):
            for key, value in attrs.items():
                if value is not None:
                    parts.append(_kv(str(key), value))

        for key in _EXTRA:
            value = record.__dict__.get(key)
            if value is not None:
                parts.append(_kv(key, value))

        return " ".join(parts)


def setup_logging(
    service_name: Optional[str] = None,
    log_level: Optional[str] = None,
) -> logging.Logger:
    """Устанавливает единый logfmt-хендлер на root logger (идемпотентно).

    FileHandler создаётся только при ``WRITE_LOGS_TO=<директория>`` (локальный dev:
    лимитированный Alloy тайлит файлы; Docker-логи собираются из stdout).
    """
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler, StreamLogfmtHandler):
            return root

    level = _resolve_level(log_level)
    root.setLevel(level)
    handler = StreamLogfmtHandler(service_name)
    root.addHandler(handler)

    log_dir = os.getenv("WRITE_LOGS_TO")
    if log_dir:
        _add_file_handler(root, level, service_name, log_dir)

    # Дребезг инфраструктурных библиотек в INFO — в WARNING.
    for noisy in ("botocore", "boto3", "urllib3", "httpcore", "aiohttp", "aiobotocore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return root


def _add_file_handler(
    root: logging.Logger,
    level: int,
    service_name: Optional[str],
    log_dir: str,
) -> None:
    os.makedirs(log_dir, exist_ok=True)
    file_name = f"{service_name or 'service'}.log"
    for handler in root.handlers:
        if isinstance(handler, FileLogfmtHandler) and handler.baseFilename.endswith(file_name):
            return
    handler = FileLogfmtHandler(os.path.join(log_dir, file_name), service_name)
    handler.setLevel(level)
    root.addHandler(handler)


class FileLogfmtHandler(logging.FileHandler):
    """FileHandler с LogfmtFormatter — локальный dev-дубль stdout-логов."""

    def __init__(self, file_path: str, service_name: Optional[str] = None) -> None:
        super().__init__(file_path, mode="a", encoding="utf-8")
        self.setFormatter(LogfmtFormatter(service_name))


class StreamLogfmtHandler(logging.StreamHandler):
    """StreamHandler на stdout с LogfmtFormatter — маркер для идемпотентности."""

    def __init__(self, service_name: Optional[str] = None) -> None:
        super().__init__(sys.stdout)
        self.setFormatter(LogfmtFormatter(service_name))


def _resolve_level(log_level: Optional[str]) -> int:
    import os

    level_name = (log_level or os.getenv("LOG_LEVEL") or "INFO").upper()
    return getattr(logging, level_name, logging.INFO)