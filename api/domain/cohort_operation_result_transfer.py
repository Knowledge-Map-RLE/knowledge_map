"""Строгое представление переходов «операция → результат» по метке usage=result."""
from __future__ import annotations

from copy import deepcopy

from domain.article_maps import require
from domain.cohort_operation_transfer import extract_map as extract_base_map

VERSION = "cohort-operation-result-usage-lopo-1"
REQUIRED_USAGE = "result"


def filter_result_usage(graph_links: list[list[str]], graph_evidence: dict[str, list[dict]]) -> tuple[list[list[str]], dict[str, list[dict]]]:
    """Оставляет пары, у которых хотя бы одно прямое основание помечено как результат."""
    result_evidence = {}
    for pair_key, evidence_rows in graph_evidence.items():
        selected = [deepcopy(row) for row in evidence_rows if row.get("usage") == REQUIRED_USAGE]
        if selected:
            result_evidence[pair_key] = selected

    allowed_pairs = {tuple(pair_key.split("|", 1)) for pair_key in result_evidence}
    filtered_links = [list(pair) for pair in graph_links if tuple(pair) in allowed_pairs]
    require(all("|".join(pair) in result_evidence for pair in filtered_links),
            "Отфильтрованная связь результата должна иметь прямое основание")
    return filtered_links, result_evidence


def extract_map(snapshot: dict) -> dict:
    """Возвращает представление статьи, где связи вывода используют только usage=result."""
    value = extract_base_map(snapshot)
    legacy_links = value["graph_links"]
    links, evidence = filter_result_usage(legacy_links, value["graph_evidence"])
    return {
        **value,
        "legacy_graph_links": legacy_links,
        "graph_links": links,
        "graph_evidence": evidence,
        "transition_usage_filter": REQUIRED_USAGE,
    }
