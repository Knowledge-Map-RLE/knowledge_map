"""
Генерация знаний в PatternMiner: четыре способа получения нового утверждения.

  * pattern   — выявление частотных структур по корпусу (gSpan) и наложение;
  * logical   — логические операции над триплетами (транзитивность и т.д.);
  * syllogism — 24 модуса категорического силлогизма;
  * thinking  — операции мышления (анализ, синтез, причина и т.д.).

Каждый способ возвращает единый конверт KnowledgeResult (см. provenance),
который затем снабжается проверкой существующего знания (new/exists/conflicts).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from application.generation import logical_operations as logical
from application.generation import provenance
from application.generation import syllogisms
from application.generation import thinking_operations as thinking
from application.generation.provenance import (
    PATTERN,
    LOGICAL,
    SYLLOGISM,
    THINKING,
    KNOWLEDGE_METHODS,
    METHOD_LABELS,
    build_knowledge_result,
)

__all__ = [
    "PATTERN",
    "LOGICAL",
    "SYLLOGISM",
    "THINKING",
    "KNOWLEDGE_METHODS",
    "METHOD_LABELS",
    "build_knowledge_result",
    "method_metadata",
    "run_generation",
]


def method_metadata() -> List[Dict[str, Any]]:
    """Список способов с их операциями (для UI: селектор способа → операций)."""
    return [
        {
            "value": PATTERN,
            "label": METHOD_LABELS[PATTERN],
            "operations": [{"value": "", "label": "— (использовать выбранный паттерн)"}],
            "info": "Выявление частотных структур по корпусу и наложение на целевой граф.",
        },
        {
            "value": LOGICAL,
            "label": METHOD_LABELS[LOGICAL],
            "operations": [{"value": op.name, "label": op.label} for op in logical._OPERATIONS],
            "info": "Логические операции над утверждениями (транзитивность, обращение и т.д.).",
        },
        {
            "value": SYLLOGISM,
            "label": METHOD_LABELS[SYLLOGISM],
            "operations": [{"value": op.name, "label": op.label} for op in syllogisms._OPERATIONS],
            "moduses": syllogisms.syllogism_moduses(),
            "info": "24 модуса категорического силлогизма (Barbara/Celarent вывод по is_a-цепочкам).",
        },
        {
            "value": THINKING,
            "label": METHOD_LABELS[THINKING],
            "operations": [{"value": op.name, "label": op.label} for op in thinking._OPERATIONS],
            "info": "Операции мышления: анализ, синтез, сравнение, обобщение, причина и др.",
        },
    ]


def run_generation(
    *,
    method: str,
    statements: Sequence[Dict[str, Any]],
    operation: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Выполняет генерацию новым способом (logical/syllogism/thinking).

    Args:
        method: LOGICAL | SYLLOGISM | THINKING.
        statements: утверждения корпуса/статьи, над которыми ведётся операция.
        operation: конкретная операция (имя), иначе все операции способа.
        limit: суммарный лимит результатов.

    Returns:
        Список KnowledgeResult-конвертов.
    """
    if method == LOGICAL:
        return logical.run_logical_operations(statements, operation=operation, limit=limit)
    if method == SYLLOGISM:
        return syllogisms.run_syllogism_operations(statements, operation=operation, limit=limit)
    if method == THINKING:
        return thinking.run_thinking_operations(statements, operation=operation, limit=limit)
    raise ValueError(f"Неизвестный способ генерации: {method!r}")
