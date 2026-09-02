"""
Генерация знаний: единый конверт результата — «происхождение знания».

Каждый сгенерированный кандидат обязан нести:
  * способ получения (knowledge_method): pattern | logical | syllogism | thinking;
  * конкретную операцию (operation) и её русское название (operation_label);
  * исходные утверждения (source_statements), над которыми выполнялась операция;
  * сгенерированные утверждения (new_statements);
  * описание вывода (description) — как именно получено знание.

Проверка существующего знания (check) выполняется на уровне репозитория/сервиса:
результат добавляется в каждый new-триплет как
  {"status": "new"|"exists"|"conflicts", "evidence_doc_ids": [...], "note": "..."}.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from application.generation.statements import unique_triplets

# Способы получения знания
PATTERN = "pattern"
LOGICAL = "logical"
SYLLOGISM = "syllogism"
THINKING = "thinking"

KNOWLEDGE_METHODS = (PATTERN, LOGICAL, SYLLOGISM, THINKING)

METHOD_LABELS = {
    PATTERN: "Паттерн",
    LOGICAL: "Логическая операция",
    SYLLOGISM: "Силлогизм",
    THINKING: "Операция мышления",
}


def build_knowledge_result(
    *,
    method: str,
    operation: str,
    operation_label: str,
    source_statements: Sequence[Dict[str, Any]],
    new_statements: Sequence[Dict[str, Any]],
    description: str,
) -> Dict[str, Any]:
    """Собирает конверт знания из операции.

    Args:
        method: один из KNOWLEDGE_METHODS.
        operation: канонический идентификатор операции (напр. 'transitivity',
            'barbara_aaa_1', 'generalization', 'causality').
        operation_label: человекочитаемое русское название операции.
        source_statements: исходные утверждения (посылки).
        new_statements: сгенерированные утверждения (кандидаты).

    Returns:
        Составной результат {knowledge_method, operation, operation_label,
        description, source_statements, new_statements, provenance}.
    """
    src = unique_triplets(source_statements)
    new = unique_triplets(new_statements)
    return {
        "knowledge_method": method,
        "operation": operation,
        "operation_label": operation_label,
        "description": description,
        "source_statements": src,
        "new_statements": new,
        "provenance": {
            "method": method,
            "method_label": METHOD_LABELS.get(method, method),
            "operation": operation,
            "operation_label": operation_label,
            "source_count": len(src),
            "new_count": len(new),
        },
    }


def as_generate_group(label: str, results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Группирует результаты одного способа для ответа API."""
    r = list(results)
    return {
        "label": label,
        "results": r,
        "count": len(r),
        "new_total": sum(len(x.get("new_statements", [])) for x in r),
    }
