"""Локальный logfmt (key=value) логгер для stdout (без OTel).

Строка вида: ``ts=2026-09-12T13:05:02.951 level=info logger=data_to_db msg="..."``

Дублируется логика shared/observability, но без OTel-зависимости:
data_to_db — автономный пакет скриптов без внешних наблюдательных стеков.
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Any, Optional

_EXTRA = (
    "session_id", "user_id", "method", "path", "status",
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


class LogfmtStreamHandler(logging.StreamHandler):
    """StreamHandler на stdout с LogfmtFormatter — маркер для идемпотентности."""

    def __init__(self, service_name: Optional[str] = None) -> None:
        super().__init__(sys.stdout)
        self.setFormatter(LogfmtFormatter(service_name))


def logfmt_handler(service_name: Optional[str] = None) -> logging.StreamHandler:
    """Возвращает logfmt-хендлер для stdout (для совместного использования с FileHandler)."""
    return LogfmtStreamHandler(service_name)