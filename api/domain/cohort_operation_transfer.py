"""Отложенная проверка переноса связей «операция → результат» между картами когорт."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy

from domain.operator_frame_routing import PREDICATES, VERSION as ROUTING_VERSION
from domain.operator_pattern_forecast import validate_map_snapshot

VERSION = "cohort-operation-result-transfer-lopo-7"
OPERATOR_FAMILIES = frozenset({
    "incidence_estimation",
    "person_time_calculation",
    "survival_model_fitting",
})
OUTPUT_FAMILIES = frozenset({
    "reported_association",
    "reported_frequency",
    "reported_model_parameter",
})
OUTPUT_ALIASES = {
    "adjusted hazard ratio": "reported_model_parameter",
    "adjusted incidence rate": "reported_frequency",
    "age-specific incidence": "reported_frequency",
    "age and education incidence patterns": "reported_association",
    "amnestic mci incidence rate": "reported_frequency",
    "association not statistically detected": "reported_association",
    "estimated association": "reported_association",
    "incident mci rate": "reported_frequency",
    "incidence rate": "reported_frequency",
    "incidence rate in men": "reported_frequency",
    "incidence rate in women": "reported_frequency",
    "nonamnestic mci incidence rate": "reported_frequency",
    "reported cox relative estimate": "reported_model_parameter",
    "reported cox-model association": "reported_model_parameter",
    "reported incidence rate difference": "reported_frequency",
    "reported subtype association": "reported_association",
    "statistically significant adjusted association reported": "reported_association",
    "higher hazard associated with baseline smi": "reported_association",
    "higher hazard associated with iadl impairment": "reported_association",
    "lower hazard per additional mmse point": "reported_association",
}
OPERATION_ALIASES = {
    "cox risk-factor analysis": "survival_model_fitting",
    "incidence calculation method": "incidence_estimation",
    "fit time-to-decline models": "survival_model_fitting",
}
MODEL_PARAMETER_ATTRIBUTES = frozenset({
    "hazard ratio",
    "odds ratio",
    "risk ratio",
    "regression coefficient",
    "beta coefficient",
})


def normalize_predicate(value: str) -> str:
    return " ".join(value.casefold().replace("_", " ").split())


def operation_families(item: dict) -> set[str]:
    if item.get("kind") != "action":
        return set()
    families = set()
    for statement in item["semantic_frame"]["statements"]:
        predicate = normalize_predicate(statement["predicate"])
        family = OPERATION_ALIASES.get(predicate, PREDICATES.get(predicate))
        if family in OPERATOR_FAMILIES:
            families.add(family)
    return families


def output_families(item: dict) -> set[str]:
    families = set()
    for statement in item["semantic_frame"]["statements"]:
        predicate = normalize_predicate(statement["predicate"])
        attributes = {normalize_predicate(attribute["name"])
                      for attribute in statement["qualifiers"]["attributes"]}
        if attributes & MODEL_PARAMETER_ATTRIBUTES:
            family = "reported_model_parameter"
        else:
            family = OUTPUT_ALIASES.get(predicate, PREDICATES.get(predicate))
        if family in OUTPUT_FAMILIES:
            families.add(family)
    return families


def extract_map(snapshot: dict) -> dict:
    """Извлекает только явно типизированные операции, результаты и прямые переходы."""
    validate_map_snapshot(snapshot)
    graph = snapshot["graph"]
    knowledge = {item["knowledge_id"]: item for item in graph["knowledge"]}
    occurrence_to_knowledge = {node["id"]: node["knowledge_id"] for node in graph["nodes"]}
    action_occurrences = {
        node_id: operation_families(knowledge[knowledge_id])
        for node_id, knowledge_id in occurrence_to_knowledge.items()
        if knowledge[knowledge_id]["kind"] == "action"
        and operation_families(knowledge[knowledge_id])
    }
    operation_set = set().union(*action_occurrences.values()) if action_occurrences else set()
    output_set = set().union(*(
        output_families(item) for item in graph["knowledge"]
        if item["kind"] != "action"
    )) if graph["knowledge"] else set()

    graph_links: set[tuple[str, str]] = set()
    evidence: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for transition in graph["transitions"]:
        action_sources = [source for source in transition["sources"] if source in action_occurrences]
        action_families = set().union(*(action_occurrences[source] for source in action_sources)) if action_sources else set()
        if len(action_sources) != 1 or len(action_families) != 1:
            continue
        target_id = occurrence_to_knowledge[transition["target"]]
        target = knowledge[target_id]
        target_families = output_families(target)
        for operation in action_families:
            for outcome in target_families:
                pair = (operation, outcome)
                graph_links.add(pair)
                evidence[pair].append({
                    "transition_id": transition["id"],
                    "usage": transition["usage"],
                    "action_knowledge_id": occurrence_to_knowledge[action_sources[0]],
                    "target_knowledge_id": target_id,
                    "other_source_count": len(transition["sources"]) - 1,
                })

    cooccurrence_links = {(operation, outcome) for operation in operation_set for outcome in output_set}
    return {
        "article_id": snapshot["article_id"],
        "run_id": snapshot["run_id"],
        "source_sha256": snapshot["source"]["sha256"],
        "operator_families": sorted(operation_set),
        "output_families": sorted(output_set),
        "graph_links": sorted([list(pair) for pair in graph_links]),
        "cooccurrence_links": sorted([list(pair) for pair in cooccurrence_links]),
        "graph_evidence": {"|".join(pair): deepcopy(evidence[pair]) for pair in sorted(evidence)},
        "action_occurrence_count": len(action_occurrences),
    }


def learn_links(rows_by_source: dict[str, list[list[str]]], minimum_support: int) -> dict:
    """Считает поддержку по публикациям, а не по повторам внутри одной карты."""
    support: dict[tuple[str, str], set[str]] = defaultdict(set)
    for source_id, pairs in rows_by_source.items():
        for raw_pair in pairs:
            pair = tuple(raw_pair)
            if len(pair) == 2:
                support[pair].add(source_id)
    return {pair for pair, sources in support.items() if len(sources) >= minimum_support}


def forecast_for_known_operations(rows_by_source: dict[str, dict], known_operations: set[str],
                                 minimum_support: int = 2) -> dict:
    """Считает кандидаты только по обучающим связям и заданным целевым методам."""
    cooccurrence = learn_links(
        {key: row["cooccurrence_links"] for key, row in rows_by_source.items()}, minimum_support)
    graph = learn_links(
        {key: row["graph_links"] for key, row in rows_by_source.items()}, minimum_support)
    return {
        "same_article_cooccurrence": sorted([list(pair) for pair in cooccurrence
                                              if pair[0] in known_operations]),
        "dependency_edges": sorted([list(pair) for pair in graph if pair[0] in known_operations]),
    }


def score(predicted: set[tuple[str, str]], target: set[tuple[str, str]]) -> dict:
    hits = predicted & target
    return {
        "predicted_count": len(predicted),
        "target_count": len(target),
        "hits": len(hits),
        "precision": len(hits) / len(predicted) if predicted else None,
        "recall": len(hits) / len(target) if target else None,
        "matched_pairs": [list(pair) for pair in sorted(hits)],
        "missed_pairs": [list(pair) for pair in sorted(target - predicted)],
        "extra_pairs": [list(pair) for pair in sorted(predicted - target)],
    }


def evaluate_lopo(rows: list[dict], minimum_support: int = 2) -> dict:
    """Сравнивает прогноз наличия операций и результаты при известном методе статьи."""
    by_source = {row["article_id"]: row for row in rows}
    folds = []
    mode_totals = {
        mode: {"predicted": 0, "target": 0, "hits": 0}
        for mode in ("operator_family_only", "same_article_cooccurrence", "dependency_edges")
    }
    for target_id in sorted(by_source):
        target = by_source[target_id]
        training = {key: value for key, value in by_source.items() if key != target_id}
        operator_prediction = {
            operation for operation in OPERATOR_FAMILIES
            if sum(operation in row["operator_families"] for row in training.values()) >= minimum_support
        }
        known_target_operations = set(target["operator_families"])
        predictions = forecast_for_known_operations(training, known_target_operations, minimum_support)
        cooccurrence_prediction = {tuple(pair) for pair in predictions["same_article_cooccurrence"]}
        graph_prediction = {tuple(pair) for pair in predictions["dependency_edges"]}
        target_operators = set(target["operator_families"])
        target_links = {tuple(pair) for pair in target["graph_links"]}
        scores = {
            "operator_family_only": score({(item, "operator_present") for item in operator_prediction},
                                           {(item, "operator_present") for item in target_operators}),
            "same_article_cooccurrence": score(cooccurrence_prediction, target_links),
            "dependency_edges": score(graph_prediction, target_links),
        }
        pair_fold_eligible = bool(known_target_operations)
        for mode, scored in scores.items():
            if mode != "operator_family_only" and not pair_fold_eligible:
                continue
            mode_totals[mode]["predicted"] += scored["predicted_count"]
            mode_totals[mode]["target"] += scored["target_count"]
            mode_totals[mode]["hits"] += scored["hits"]
        folds.append({
            "target_article_id": target_id,
            "target_run_id": target["run_id"],
            "training_article_ids": sorted(training),
            "target_operator_families": sorted(target_operators),
            "known_operator_context_used_before_result_forecast": True,
            "scored_for_operator_conditioned_forecast": pair_fold_eligible,
            "scores": scores,
            "graph_training_links": [list(pair) for pair in sorted(graph_prediction)],
            "cooccurrence_training_links": [list(pair) for pair in sorted(cooccurrence_prediction)],
            "target_links": [list(pair) for pair in sorted(target_links)],
            "target_graph_evidence": target["graph_evidence"],
        })
    aggregate = {}
    for mode, totals in mode_totals.items():
        aggregate[mode] = {
            **totals,
            "precision": totals["hits"] / totals["predicted"] if totals["predicted"] else None,
            "recall": totals["hits"] / totals["target"] if totals["target"] else None,
        }
    return {
        "version": VERSION,
        "routing_version": ROUTING_VERSION,
        "minimum_publication_support": minimum_support,
        "source_count": len(rows),
        "aggregate": aggregate,
        "folds": folds,
        "model_calls": 0,
        "network_disabled": True,
        "target_maps_read_only_after_fold_prediction": True,
        "sealed_blind_evaluation": False,
        "scientific_fact_forecast": False,
    }
