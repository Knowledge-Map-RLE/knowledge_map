"""
Layer: Application (Use Cases)
Package: application.patterns.get_specific_patterns
Responsibility: Вычисляет специфичные паттерны (set difference) для пар типов аннотаций.

Allowed imports: typing, dataclasses, domain.*, application.ports.*
Forbidden imports: neomodel, fastapi, grpc, aioboto3, infrastructure, adapters, web
"""
from __future__ import annotations

from typing import Any, List

from application.patterns.analyze_document_patterns import AnnotationTypePatterns, PatternRow


_SPECIFIC_PAIRS = []


def _pattern_key(row: PatternRow) -> tuple:
    return (row.pattern_type, row.pattern_str)


def get_specific_patterns(pattern_repo: Any, doc_id: str) -> List[AnnotationTypePatterns]:
    """
    Загружает паттерны из репозитория и возвращает 4 группы специфичных паттернов:
    для каждой пары типов аннотаций вычисляет set difference (source - exclude).
    """
    rows = pattern_repo.get_for_document(doc_id)

    # Группируем по annotation_type
    groups: dict[str, list[PatternRow]] = {}
    for row in rows:
        at = row.get("annotation_type", "")
        pr = PatternRow(
            pattern_str=row["pattern_str"],
            pattern_type=row["pattern_type"],
            frequency=row["frequency"],
        )
        groups.setdefault(at, []).append(pr)

    result: List[AnnotationTypePatterns] = []
    for pair in _SPECIFIC_PAIRS:
        source_patterns = groups.get(pair["source"], [])
        exclude_keys = {_pattern_key(p) for p in groups.get(pair["exclude"], [])}
        specific = [p for p in source_patterns if _pattern_key(p) not in exclude_keys]
        # Сортируем по убыванию частоты (уже отсортированы из репо, но на всякий случай)
        specific.sort(key=lambda p: p.frequency, reverse=True)
        result.append(AnnotationTypePatterns(
            annotation_type=pair["title"],
            patterns=specific,
            total_annotations=len(source_patterns),
        ))

    return result
