"""Свободно переносит шаблоны результатов с растущей семантической точностью."""
from __future__ import annotations

from collections import defaultdict

from domain.action_result_transfer import classify_operation, classify_outcome
from domain.article_maps import require
from domain.development_prediction import validate_visible_dag

VERSION = "whole-map-action-result-semantic-resolution-1"
MINIMUM_SUPPORT = 2
LEVELS = {
    0: "family",
    1: "predicate",
    2: "roles_and_logic",
    3: "knowledge_kind_and_frame_logic",
    4: "qualifier_units_and_context_shape",
}


def _claim_signature(knowledge: dict, statement: dict, level: int) -> tuple:
    """Возвращает шаблон знания, не перенося численные значения."""
    family = classify_outcome(statement["predicate"])
    require(family is not None, "Знание не относится к распознанному результату")
    signature: list = [family]
    if level >= 1:
        signature.append(statement["predicate"])
    if level >= 2:
        signature.extend([
            tuple(sorted(role["role"] for role in statement["roles"])),
            statement["negated"],
            statement["quantifier"],
            statement["modality"],
        ])
    if level >= 3:
        signature.extend([knowledge["knowledge_kind"], knowledge["semantic_frame"]["logic"]])
    if level >= 4:
        signature.extend([
            tuple(sorted(
                (attribute["name"].casefold(), (attribute.get("unit") or "").casefold())
                for attribute in statement["qualifiers"]["attributes"]
            )),
            bool(statement["conditions"]),
            bool(statement["temporal_context"]),
        ])
    return tuple(signature)


def _pairs_json(pairs: set[tuple[str, tuple]]) -> list[dict]:
    return [
        {"operation_family": operation, "outcome_signature": list(signature)}
        for operation, signature in sorted(pairs, key=repr)
    ]


def extract_article(snapshot: dict, support_family: str) -> dict:
    """Извлекает связанные и совместно встречающиеся шаблоны из карты."""
    graph = snapshot.get("graph", {})
    require(graph.get("schema_version") == 6, "Требуется карта схемы 6")
    validate_visible_dag(graph)
    knowledge = {item["knowledge_id"]: item for item in graph["knowledge"]}
    occurrences = {node["id"]: node["knowledge_id"] for node in graph["nodes"]}
    require(len(knowledge) == len(graph["knowledge"]), "Повторяющийся knowledge_id")
    require(len(occurrences) == len(graph["nodes"]), "Повторяющийся id вхождения")

    operations_by_occurrence: dict[str, set[str]] = defaultdict(set)
    outcomes_by_occurrence: dict[str, list[tuple]] = defaultdict(list)
    all_operations: set[str] = set()
    for occurrence_id, knowledge_id in occurrences.items():
        item = knowledge[knowledge_id]
        if item["kind"] == "action":
            if item.get("action_status") != "performed":
                continue
            families = {
                classify_operation(statement["predicate"])
                for statement in item["semantic_frame"]["statements"]
            } - {None}
            operations_by_occurrence[occurrence_id].update(families)
            all_operations.update(families)
            continue
        for statement in item["semantic_frame"]["statements"]:
            if classify_outcome(statement["predicate"]) is None:
                continue
            for level in LEVELS:
                outcomes_by_occurrence[occurrence_id].append(
                    (level, _claim_signature(item, statement, level))
                )

    graph_pairs = {level: set() for level in LEVELS}
    for transition in graph["transitions"]:
        require(transition["target"] in occurrences, "Неизвестная цель перехода")
        require(all(source in occurrences for source in transition["sources"]),
                "Неизвестный источник перехода")
        action_sources = [source for source in transition["sources"]
                          if source in operations_by_occurrence
                          and operations_by_occurrence[source]]
        if len(action_sources) != 1:
            continue
        operation_families = operations_by_occurrence[action_sources[0]]
        if len(operation_families) != 1:
            continue
        operation = next(iter(operation_families))
        for level, signature in outcomes_by_occurrence.get(transition["target"], []):
            graph_pairs[level].add((operation, signature))

    all_outcomes_by_level = {level: set() for level in LEVELS}
    for values in outcomes_by_occurrence.values():
        for level, signature in values:
            all_outcomes_by_level[level].add(signature)
    no_edge_pairs = {
        level: {
            (operation, signature)
            for operation in all_operations
            for signature in all_outcomes_by_level[level]
        }
        for level in LEVELS
    }
    return {
        "article_id": snapshot["article_id"],
        "run_id": snapshot["run_id"],
        "support_family": support_family,
        "graph_pairs": {level: _pairs_json(values) for level, values in graph_pairs.items()},
        "without_dependencies_pairs": {
            level: _pairs_json(values) for level, values in no_edge_pairs.items()
        },
        "target_pairs": {level: _pairs_json(values) for level, values in graph_pairs.items()},
    }


def _tuple_value(value):
    if isinstance(value, list):
        return tuple(_tuple_value(item) for item in value)
    return value


def _pair_set(rows: list[dict]) -> set[tuple[str, tuple]]:
    return {
        (row["operation_family"], _tuple_value(row["outcome_signature"]))
        for row in rows
    }


def _support(records: list[dict], field: str, level: int) -> dict[tuple, set[str]]:
    support: dict[tuple, set[str]] = defaultdict(set)
    for record in records:
        for pair in _pair_set(record[field][level]):
            support[pair].add(record["support_family"])
    return support


def seal_forecasts(records: list[dict], citation_exclusions: dict[str, list[dict]],
                   minimum_support: int = MINIMUM_SUPPORT) -> dict:
    """Замораживает прогнозы до чтения целевых утверждений и связей."""
    require(minimum_support >= 1, "Минимальная поддержка должна быть положительной")
    ids = [record["article_id"] for record in records]
    require(len(ids) == len(set(ids)), "Повторяющийся article_id")
    require(set(ids) == set(citation_exclusions), "Список цитатных исключений неполон")
    folds = []
    for target in sorted(records, key=lambda record: record["article_id"]):
        target_id = target["article_id"]
        excluded = {row["citing_article_id"] for row in citation_exclusions[target_id]}
        training = [row for row in records
                    if row["article_id"] != target_id and row["article_id"] not in excluded]
        modes = {}
        for mode, field in (("graph", "graph_pairs"),
                            ("without_dependencies", "without_dependencies_pairs")):
            modes[mode] = {}
            for level in LEVELS:
                support = _support(training, field, level)
                candidates = [
                    {"operation_family": pair[0],
                     "outcome_signature": list(pair[1]),
                     "support_families": sorted(families),
                     "support_count": len(families)}
                    for pair, families in support.items()
                    if len(families) >= minimum_support
                ]
                candidates.sort(key=lambda item: (
                    -item["support_count"], item["operation_family"],
                    repr(item["outcome_signature"]),
                ))
                modes[mode][level] = candidates
        folds.append({
            "target_article_id": target_id,
            "training_article_ids": sorted(row["article_id"] for row in training),
            "excluded_citer_article_ids": sorted(excluded),
            "predictions": modes,
        })
    result = {
        "version": VERSION,
        "minimum_support": minimum_support,
        "levels": {str(level): name for level, name in LEVELS.items()},
        "target_operation_families_used": False,
        "target_outcomes_or_dependencies_used": False,
        "citation_exclusions_applied_before_forecast": True,
        "folds": folds,
    }
    return result


def score_forecasts(records: list[dict], sealed: dict) -> dict:
    """Оценивает только после фиксации прогнозов по картам целей."""
    by_id = {record["article_id"]: record for record in records}
    totals = {
        mode: {level: {"predicted": 0, "target": 0, "hits": 0}
               for level in LEVELS}
        for mode in ("graph", "without_dependencies")
    }
    folds = []
    for fold in sealed["folds"]:
        target = by_id[fold["target_article_id"]]
        score_fold = {"target_article_id": fold["target_article_id"], "levels": {}}
        for level in LEVELS:
            actual = _pair_set(target["target_pairs"][level])
            score_fold["levels"][level] = {}
            for mode in ("graph", "without_dependencies"):
                predicted = {
                    (row["operation_family"], _tuple_value(row["outcome_signature"]))
                    for row in fold["predictions"][mode][level]
                }
                matched = predicted & actual
                totals[mode][level]["predicted"] += len(predicted)
                totals[mode][level]["target"] += len(actual)
                totals[mode][level]["hits"] += len(matched)
                score_fold["levels"][level][mode] = {
                    "predicted": len(predicted),
                    "target": len(actual),
                    "hits": len(matched),
                    "matched": [
                        {"operation_family": operation,
                         "outcome_signature": list(signature)}
                        for operation, signature in sorted(matched, key=repr)
                    ],
                }
        folds.append(score_fold)
    aggregate = {}
    for mode, levels in totals.items():
        aggregate[mode] = {}
        for level, values in levels.items():
            aggregate[mode][level] = {
                **values,
                "precision": values["hits"] / values["predicted"] if values["predicted"] else None,
                "recall": values["hits"] / values["target"] if values["target"] else None,
            }
    return {"version": VERSION, "aggregate": aggregate, "folds": folds}
