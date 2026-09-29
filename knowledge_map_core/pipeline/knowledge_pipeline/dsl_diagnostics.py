"""Render non-blocking extraction diagnostics as DSL-compatible comments."""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping


def render_warning_report(
    case_id: str, prompt_version: str,
    warnings: Iterable[Mapping[str, object]],
) -> str:
    """Serialize semantic warnings without adding non-DSL rows or JSON files."""
    lines = [f"# WARNING_REPORT case={_comment_value(case_id)} "
             f"prompt_version={_comment_value(prompt_version)}"]
    for warning in warnings:
        if warning.get("severity") != "warning":
            continue
        parts = ["# WARNING", f"code={_safe_token(warning.get('code'), 'semantic')}"]
        unit = _safe_identifier(warning.get("unit"), r"S[1-9][0-9]*")
        tag = _safe_identifier(warning.get("tag"), r"B[1-9][0-9]*")
        if unit:
            parts.append(f"unit={unit}")
        if tag:
            parts.append(f"row={tag}")
        parts.append(f"detail={_comment_value(warning.get('message') or 'warning')}")
        lines.append(" ".join(parts))
    return "\n".join(lines) + "\n"


def _safe_identifier(value: object, pattern: str) -> str:
    candidate = str(value or "")
    return candidate if re.fullmatch(pattern, candidate) else ""


def _safe_token(value: object, fallback: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_-]", "_", str(value or ""))
    return candidate or fallback


def _comment_value(value: object) -> str:
    return " ".join(str(value).replace("|", "\\|").split())
