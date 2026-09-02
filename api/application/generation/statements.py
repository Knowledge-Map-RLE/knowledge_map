"""
Выявление и генерация знаний: общая модель утверждения (триплета).

Используется всеми способами генерации знания (логические операции,
силлогизмы, операции мышления) и проверкой существующих утверждений.

Триплет имеет форму:
  subject_text --[predicate]--> object_text
с опциональными типом субъекта/объекта (concept|literal|statement) и источником
(doc_id, uid), чтобы сохранять происхождение сгенерированного знания.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


def to_triplet(stmt: Dict[str, Any], *, source: Optional[str] = None) -> Dict[str, Any]:
    """Приводит запись утверждения к каноническому виду триплета.

    Args:
        stmt: запись утверждения (из репозитория или из generated source).
        source: признак источника (doc_id корпуса).

    Returns:
        {"subject_text", "predicate", "object_text",
         "subject_type", "object_type", "doc_id"}
    """
    return {
        "subject_text": str(stmt.get("subject_text") or "").strip(),
        "predicate": str(stmt.get("predicate") or "").strip(),
        "object_text": str(stmt.get("object_text") or "").strip(),
        "subject_type": str(stmt.get("subject_type") or "concept").strip() or "concept",
        "object_type": str(stmt.get("object_type") or "concept").strip() or "concept",
        "doc_id": stmt.get("doc_id") or source,
    }


def normalize_triplet(stmt: Dict[str, Any]) -> str:
    """Канонический ключ триплета (для сверки с БД и дедупликации)."""
    return " || ".join(
        (
            str(stmt.get("subject_text") or "").strip().lower(),
            str(stmt.get("predicate") or "").strip().lower(),
            str(stmt.get("object_text") or "").strip().lower(),
        )
    )


def format_assertion(triplet: Dict[str, Any]) -> str:
    """Читаемая строка утверждения 'subject --pred--> object'."""
    return (
        f"{triplet.get('subject_text')} —[{triplet.get('predicate')}]→ "
        f"{triplet.get('object_text')}"
    )


def unique_triplets(triplets: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Дедупликация триплетов по (subject, predicate, object)."""
    seen = set()
    out: List[Dict[str, Any]] = []
    for t in triplets:
        key = normalize_triplet(t)
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


# Предикаты-категории: используются категорическими силлогизмами.
CATEGORY_PREDICATES = {"is_a", "is", "be", "are", "include", "have", "subclass_of", "belongs_to"}


def is_category_edge(predicate: str) -> bool:
    """Является ли предикат категориальным (для силлогизмов)."""
    return str(predicate or "").strip().lower() in CATEGORY_PREDICATES


def negated_form(predicate: str) -> Optional[str]:
    """Возвращает 'отрицательную' форму предиката, если она известна.

    Используется для вывода контрпозиции/отрицания и проверки конфликтов.
    """
    table = {
        "increases": "does not increase",
        "inhibit": "does not inhibit",
        "decreases": "does not decrease",
        "activates": "does not activate",
        "suppresses": "does not suppress",
        "promotes": "does not promote",
        "causes": "does not cause",
        "correlates": "does not correlate",
        "is": "is not",
        "is_a": "is not",
        "be": "is not",
        "include": "does not include",
        "have": "does not have",
        "affects": "does not affect",
    }
    return table.get(str(predicate or "").strip().lower())
