"""Свободный перенос форм «операция → тип результата» без чтения цели."""
from __future__ import annotations

import random
from collections import Counter, defaultdict
from copy import deepcopy

from domain.article_maps import fingerprint, require

VERSION = "whole-map-action-result-free-citation-holdout-3"
MINIMUM_SUPPORT = 2
TOP_K = (1, 3, 5, 10)
MODES = ("graph", "without_dependencies")


def _supported_pairs(training: list[dict], field: str,
                     minimum_support: int) -> list[dict]:
    support: dict[tuple[str, str], set[str]] = defaultdict(set)
    for record in training:
        for raw_pair in record[field]:
            require(len(raw_pair) == 2, "Ожидается пара «операция → результат»")
            pair = tuple(raw_pair)
            support[pair].add(record["support_family"])
    ranked = [
        {"pair": list(pair), "distinct_source_families": len(families)}
        for pair, families in support.items()
        if len(families) >= minimum_support
    ]
    return sorted(ranked, key=lambda row: (-row["distinct_source_families"],
                                            row["pair"]))


def forecast_free(training: list[dict], minimum_support: int = MINIMUM_SUPPORT) -> dict:
    """Строит прогнозы только по обучающим переходам и совместному присутствию.

    Функция намеренно не принимает сведения о целевой статье.
    """
    require(minimum_support >= 1, "Минимальная поддержка должна быть положительной")
    ids = [row["article_id"] for row in training]
    require(len(ids) == len(set(ids)), "Повторяющийся источник в обучении")
    graph = _supported_pairs(training, "graph_links", minimum_support)
    without_dependencies = _supported_pairs(training, "cooccurrence_links",
                                            minimum_support)
    result = {
        "version": VERSION,
        "minimum_support": minimum_support,
        "training_article_ids": sorted(ids),
        "predictions": {
            "graph": [row["pair"] for row in graph],
            "without_dependencies": [row["pair"] for row in without_dependencies],
        },
        "ranked_candidates": {
            "graph": graph,
            "without_dependencies": without_dependencies,
        },
    }
    return result


def _expected_hits_at_k(ranked: list[dict], actual: set[tuple[str, str]],
                        k: int) -> tuple[float, int]:
    require(k > 0, "k должен быть положительным")
    slots = min(k, len(ranked))
    hits = 0.0
    remaining = slots
    index = 0
    while index < len(ranked) and remaining:
        support = ranked[index]["distinct_source_families"]
        end = index + 1
        while end < len(ranked) and ranked[end]["distinct_source_families"] == support:
            end += 1
        group = ranked[index:end]
        selected = min(remaining, len(group))
        relevant = sum(tuple(row["pair"]) in actual for row in group)
        hits += selected * relevant / len(group)
        remaining -= selected
        index = end
    return hits, slots


def seal_forecasts(records: list[dict],
                   exclusions: dict[str, list[dict]],
                   minimum_support: int = MINIMUM_SUPPORT) -> dict:
    """Замораживает полный прогноз по обучающим источникам без входов цели."""
    ids = {row["article_id"] for row in records}
    require(len(ids) == len(records), "Повторяющийся article_id")
    require(set(exclusions) == ids, "Для каждой статьи нужен явный список исключений")
    by_id = {row["article_id"]: row for row in records}
    folds = []
    for target_id in sorted(ids):
        excluded = {row["citing_article_id"] for row in exclusions[target_id]}
        require(target_id not in excluded, "Цель нельзя исключать как собственного цитатора")
        require(excluded <= ids, "Исключённая статья отсутствует в корпусе")
        training_ids = ids - excluded - {target_id}
        training = [by_id[source_id] for source_id in sorted(training_ids)]
        forecast = forecast_free(training, minimum_support)
        folds.append({
            "target_article_id": target_id,
            "excluded_direct_citers": sorted(excluded),
            "training_article_ids": forecast["training_article_ids"],
            "predictions": forecast["predictions"],
            "ranked_candidates": forecast["ranked_candidates"],
        })
    sealed = {
        "version": VERSION,
        "minimum_support": minimum_support,
        "target_fields_used": ["article_id", "direct_citation_exclusions"],
        "target_operation_families_used": False,
        "target_outcomes_or_dependencies_used": False,
        "folds": folds,
    }
    return sealed


def score_forecasts(records: list[dict], sealed: dict) -> dict:
    """Открывает целевые переходы только после фиксации прогнозов."""
    require(sealed.get("target_operation_families_used") is False,
            "Целевые операции попали в свободный прогноз")
    require(sealed.get("target_outcomes_or_dependencies_used") is False,
            "Целевые связи попали в свободный прогноз")
    by_id = {row["article_id"]: row for row in records}
    require(set(by_id) == {fold["target_article_id"] for fold in sealed["folds"]},
            "Состав целей не совпадает с замороженным прогнозом")
    aggregate = {mode: {"predicted": 0, "hits": 0, "target": 0}
                 for mode in MODES}
    top_k = {str(k): {mode: {"expected_hits": 0.0, "slots": 0, "target": 0}
                      for mode in MODES} for k in TOP_K}
    folds = []
    for fold in sealed["folds"]:
        truth = {tuple(pair) for pair in by_id[fold["target_article_id"]]["graph_links"]}
        scores = {}
        for mode in MODES:
            predicted = {tuple(pair) for pair in fold["predictions"][mode]}
            hits = predicted & truth
            scores[mode] = {
                "predicted": len(predicted), "hits": len(hits), "target": len(truth),
                "precision": len(hits) / len(predicted) if predicted else None,
                "recall": len(hits) / len(truth) if truth else None,
                "matched": [list(pair) for pair in sorted(hits)],
                "missed": [list(pair) for pair in sorted(truth - predicted)],
                "extra": [list(pair) for pair in sorted(predicted - truth)],
            }
            for key in ("predicted", "hits", "target"):
                aggregate[mode][key] += scores[mode][key]
            ranked = fold["ranked_candidates"][mode]
            for k in TOP_K:
                hits_at_k, slots = _expected_hits_at_k(ranked, truth, k)
                total = top_k[str(k)][mode]
                total["expected_hits"] += hits_at_k
                total["slots"] += slots
                total["target"] += len(truth)
        folds.append({**fold, "target_links": [list(pair) for pair in sorted(truth)],
                      "scores": scores})
    for values in aggregate.values():
        values["precision"] = values["hits"] / values["predicted"] if values["predicted"] else None
        values["recall"] = values["hits"] / values["target"] if values["target"] else None
    for modes in top_k.values():
        for values in modes.values():
            values["precision"] = values["expected_hits"] / values["slots"] if values["slots"] else None
            values["recall"] = values["expected_hits"] / values["target"] if values["target"] else None
    return {"aggregate": aggregate, "top_k": top_k, "folds": folds}


def score_permutations(records: list[dict], exclusions: dict[str, list[dict]],
                       original_targets: list[dict], seeds: list[int],
                       observed_scores: dict,
                       minimum_support: int = MINIMUM_SUPPORT) -> dict:
    """Перемешивает результаты между связями обучения после исключения цели.

    В каждом фолде сохраняются список операций каждой обучающей статьи, число её
    прямых переходов и общее распределение типов результатов в обучении. Цель и
    найденные цитаторы исключаются до генерации перестановки.
    """
    original_by_id = {row["article_id"]: row for row in original_targets}
    by_id = {row["article_id"]: row for row in records}
    permutation_runs = []
    prediction_signatures = set()
    ranked_signatures = set()
    changed_source_counts = []
    changed_assignment_counts = []
    for seed in seeds:
        run_hits = {mode: 0 for mode in MODES}
        run_top_k = {str(k): {mode: 0.0 for mode in MODES} for k in TOP_K}
        prediction_signature = []
        ranked_signature = []
        changed_sources = 0
        changed_assignments = 0
        for target_id in sorted(original_by_id):
            excluded = {row["citing_article_id"] for row in exclusions[target_id]}
            training_ids = set(by_id) - excluded - {target_id}
            training = [by_id[source_id] for source_id in sorted(training_ids)]
            rng = random.Random(f"{seed}:{target_id}")
            permuted_training = _permute_training_outcomes(training, rng)
            permuted_by_id = {row["article_id"]: row for row in permuted_training}
            for original in training:
                before = Counter(tuple(pair) for pair in original["graph_links"])
                after = Counter(tuple(pair) for pair in
                                permuted_by_id[original["article_id"]]["graph_links"])
                difference = before - after
                if difference:
                    changed_sources += 1
                    changed_assignments += sum(difference.values())
            forecast = forecast_free(permuted_training, minimum_support)
            truth = {tuple(pair) for pair in original_by_id[target_id]["graph_links"]}
            for mode in MODES:
                predicted = {tuple(pair) for pair in forecast["predictions"][mode]}
                run_hits[mode] += len(predicted & truth)
                if mode == "graph":
                    prediction_signature.append((target_id,
                                                 tuple(sorted(predicted))))
                    ranked_signature.append((
                        target_id,
                        tuple((tuple(row["pair"]), row["distinct_source_families"])
                              for row in forecast["ranked_candidates"][mode]),
                    ))
                ranked = forecast["ranked_candidates"][mode]
                for k in TOP_K:
                    hits, _ = _expected_hits_at_k(ranked, truth, k)
                    run_top_k[str(k)][mode] += hits
        prediction_signatures.add(fingerprint(prediction_signature))
        ranked_signatures.add(fingerprint(ranked_signature))
        changed_source_counts.append(changed_sources)
        changed_assignment_counts.append(changed_assignments)
        permutation_runs.append({"seed": seed, "hits": run_hits, "top_k_hits": run_top_k})
    summary = {}
    for mode in MODES:
        observed_exact = observed_scores["aggregate"][mode]["hits"]
        values = [row["hits"][mode] for row in permutation_runs]
        summary[mode] = {
            "mean_hits": sum(values) / len(values),
            "min_hits": min(values),
            "max_hits": max(values),
            "runs_at_least_observed": sum(value >= observed_exact for value in values),
            "empirical_tail_rate_plus_one":
                (sum(value >= observed_exact for value in values) + 1) / (len(values) + 1),
            "top_k": {},
        }
        for k in TOP_K:
            observed = observed_scores["top_k"][str(k)][mode]["expected_hits"]
            ranked_values = [row["top_k_hits"][str(k)][mode] for row in permutation_runs]
            at_least = sum(value + 1e-12 >= observed for value in ranked_values)
            summary[mode]["top_k"][str(k)] = {
                "mean_hits": sum(ranked_values) / len(ranked_values),
                "min_hits": min(ranked_values),
                "max_hits": max(ranked_values),
                "runs_at_least_observed": at_least,
                "empirical_tail_rate_plus_one": (at_least + 1) / (len(ranked_values) + 1),
            }
    return {"seed_count": len(seeds), "summary": summary, "runs": permutation_runs,
            "unique_prediction_sets": len(prediction_signatures),
            "unique_ranked_profiles": len(ranked_signatures),
            "changed_sources_min": min(changed_source_counts),
            "changed_sources_max": max(changed_source_counts),
            "changed_pair_assignments_min": min(changed_assignment_counts),
            "changed_pair_assignments_max": max(changed_assignment_counts),
            "policy": "For each target, direct citers are excluded before shuffling result categories across training links; per-article operation assignments, training edge counts, and global training outcome marginal are preserved. Targets are scored against original links."}


def _permute_training_outcomes(training: list[dict], rng: random.Random) -> list[dict]:
    """Случайно назначает исходы операциям, не меняя операционный инвентарь."""
    output = deepcopy(training)
    assignments = []
    outcomes = []
    for record in training:
        article_id = record["article_id"]
        for edge in record.get("direct_links", []):
            assignments.append((article_id, edge["operation_family"]))
            outcomes.append(edge["outcome_family"])
    require(bool(assignments), "В обучающем фолде нет прямых переходов для перестановки")
    rng.shuffle(outcomes)
    by_id = {row["article_id"]: row for row in output}
    for row in output:
        row["graph_links"] = []
    for (article_id, operation), outcome in zip(assignments, outcomes):
        by_id[article_id]["graph_links"].append([operation, outcome])
    for row in output:
        row["graph_links"].sort()
    return output
