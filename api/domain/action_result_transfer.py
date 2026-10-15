"""Перенос типов авторских операций на категории связанных результатов."""
from __future__ import annotations

import random
from collections import Counter, defaultdict
from copy import deepcopy

from domain.article_maps import fingerprint, require
from domain.development_prediction import validate_visible_dag
from domain.operator_frame_routing import PREDICATES
from domain.cohort_operation_transfer import OUTPUT_ALIASES

VERSION = "whole-map-action-result-family-ranking-1"
MINIMUM_SUPPORT = 2
PERMUTATION_SEEDS = tuple(range(100))

_EVIDENCE_SYNTHESIS = frozenset({
    "assess bias", "conduct review", "extract study data", "meta analysis",
    "meta analyze proportions", "screen studies", "search literature",
    "summarize conversion", "synthesize prevalence",
})
_COHORT_DESIGN = frozenset({
    "adjudicate dementia and stop follow up", "define analysis samples",
    "obtain consent", "recruit cohort", "recruit participants",
    "recruit randomized trial", "screen and select", "select case cohort",
    "select complete cases", "select complete data", "split cohort",
    "follow cohort", "performed recruitment and follow up",
})
_TRIAL_ASSIGNMENT = frozenset({"random assignment"})
_EXPERIMENT = frozenset({
    "administer and assess", "administer treatment", "confirm efficacy",
    "engineer fusion", "evaluate fusion", "evaluate intervention",
    "house animals", "induce disease", "perform experimental procedure",
    "physical activity intervention", "prepare radiolabeled drug",
    "test cellular cmv mechanism", "test clinical treatment", "test combined intervention",
    "test fusion",
})
_STATISTICAL_ANALYSIS = frozenset({
    "analyze associations", "analyze data", "assess interactions and joint markers",
    "calculate annual change", "calculate bmi", "compare sample distributions",
    "cox risk factor analysis", "descriptive analysis", "estimate incidence rate",
    "estimate trajectory", "evaluate biomarker prediction", "evaluate statistical models",
    "fit cross sectional tobit", "fit cox proportional hazards model",
    "fit individual association models", "fit interaction model",
    "fit longitudinal linear regression", "fit mixed effects models",
    "fit time to decline models", "fit validation models", "fit weighting models",
    "incidence calculation method", "interpret estimates",
    "inverse probability weighting for follow up", "intervention by il 6 interaction test",
    "meta regression coefficient", "meta analyze proportions", "optimize cutoff",
    "ordinal logistic regression analysis", "run sensitivity models",
    "stratify baseline mci", "summarize and compare baseline measures",
    "transform biomarkers",
})
_MEASUREMENT = frozenset({
    "assay baseline plasma", "assay blood chemistry", "assess cognition",
    "assess covariates", "assess histology", "assess ultrastructure",
    "baseline plasma il 6 measurement", "baseline risk factor measurement",
    "cognitive assessment", "collect and store blood", "genotype apoe",
    "measure biomarkers", "measure biodistribution", "measure carotid plaques",
    "measure clinical course", "measure cmv igg", "measure cognition",
    "measure cognition repeatedly", "measure csf mediators", "measure diet",
    "measure drug levels", "measure il 6", "measure objective sleep",
    "measure physical activity", "measure subjective sleep", "measure tnf alpha",
    "neuropsychological measurement protocol", "performed dementia subtype classification",
    "performed diagnostic procedure", "performed neuropathology protocol",
    "performed repeated clinical assessment", "psychiatric assessment protocol",
    "quantify transcripts", "screen cognition",
})
_RESEARCH_VALIDATION = frozenset({
    "assess interactions and joint markers", "combine clinical risk profile",
    "develop and validate risk index", "evaluate longitudinal index change",
    "evaluate screening", "evaluate vascular risk management", "harmonize research",
    "investigate associations", "investigate cell targeting", "investigate mechanism",
    "investigate patient stratification", "investigate tnf source",
    "investigate unresolved", "investigate", "resolve generalizability",
    "test prevention feasibility", "validate biomarker utility",
    "validate causal benefits", "validate in independent populations",
    "validate independent population",
})

_OPERATION_FAMILY_RULES = (
    (_EVIDENCE_SYNTHESIS, "evidence_synthesis"),
    (_COHORT_DESIGN, "cohort_design_and_followup"),
    (_TRIAL_ASSIGNMENT, "trial_assignment"),
    (_STATISTICAL_ANALYSIS, "statistical_analysis"),
    (_MEASUREMENT, "measurement_or_assessment"),
    (_EXPERIMENT, "experimental_intervention_or_assay"),
    (_RESEARCH_VALIDATION, "research_question_or_validation"),
)


def normalize_predicate(value: str) -> str:
    """Нормализует только регистр, подчёркивания и пробелы."""
    return " ".join(value.casefold().replace("_", " ").split())


def _operation_key(value: str) -> str:
    return normalize_predicate(value).replace("-", " ")


def classify_operation(predicate: str) -> str | None:
    """Возвращает проверяемое семейство операции или оставляет её неразмеченной."""
    value = _operation_key(predicate)
    for predicates, family in _OPERATION_FAMILY_RULES:
        if value in predicates:
            return family
    return None


def classify_outcome(predicate: str) -> str | None:
    """Сохраняет отдельные типы результатов, включая нулевые и ограничительные."""
    value = normalize_predicate(predicate)
    family = OUTPUT_ALIASES.get(value) or PREDICATES.get(value)
    if family and family.startswith("reported_"):
        return family
    return None


def extract_article(snapshot: dict, support_family: str | None = None) -> dict:
    """Строит проекцию операций и типов результатов, не меняя исходную карту."""
    require(snapshot.get("graph", {}).get("schema_version") == 6,
            "Требуется карта схемы 6")
    graph = snapshot["graph"]
    validate_visible_dag(graph)
    knowledge = {item["knowledge_id"]: item for item in graph["knowledge"]}
    occurrences = {node["id"]: node["knowledge_id"] for node in graph["nodes"]}
    require(len(knowledge) == len(graph["knowledge"]), "Повторяющийся knowledge_id")
    require(len(occurrences) == len(graph["nodes"]), "Повторяющийся id вхождения")

    actions: dict[str, set[str]] = {}
    outcomes: dict[str, set[str]] = {}
    action_statements = recognized_action_statements = 0
    state_statements = categorized_state_statements = 0
    outcome_family_counts: dict[str, int] = defaultdict(int)
    unknown_actions: dict[str, int] = defaultdict(int)
    unknown_outcomes: dict[str, int] = defaultdict(int)
    for knowledge_id, item in knowledge.items():
        statements = item.get("semantic_frame", {}).get("statements", [])
        if item.get("kind") == "action":
            if item.get("action_status") != "performed":
                continue
            families = set()
            for statement in statements:
                predicate = normalize_predicate(statement["predicate"])
                action_statements += 1
                family = classify_operation(predicate)
                if family:
                    families.add(family)
                    recognized_action_statements += 1
                else:
                    unknown_actions[predicate] += 1
            if families:
                actions[knowledge_id] = families
            continue

        families = set()
        for statement in statements:
            predicate = normalize_predicate(statement["predicate"])
            state_statements += 1
            family = classify_outcome(predicate)
            if family:
                families.add(family)
                categorized_state_statements += 1
                outcome_family_counts[family] += 1
            else:
                unknown_outcomes[predicate] += 1
        if families:
            outcomes[knowledge_id] = families

    direct_links = []
    for transition in graph["transitions"]:
        require(transition["target"] in occurrences, "Неизвестная цель перехода")
        require(all(source in occurrences for source in transition["sources"]),
                "Неизвестный источник перехода")
        action_sources = [occurrences[source] for source in transition["sources"]
                          if occurrences[source] in actions]
        operation_families = set().union(*(actions[key] for key in action_sources)) \
            if action_sources else set()
        result_families = outcomes.get(occurrences[transition["target"]], set())
        # Не приписываем совместной группе отдельное действие, если в ней несколько действий.
        if len(action_sources) != 1 or len(operation_families) != 1:
            continue
        operation = next(iter(operation_families))
        for outcome in sorted(result_families):
            direct_links.append({
                "operation_family": operation,
                "outcome_family": outcome,
                "transition_id": transition["id"],
                "action_knowledge_id": action_sources[0],
                "target_knowledge_id": occurrences[transition["target"]],
                "other_source_count": len(transition["sources"]) - 1,
            })

    operations = set().union(*actions.values()) if actions else set()
    outcome_families = set().union(*outcomes.values()) if outcomes else set()
    pairs = {(link["operation_family"], link["outcome_family"]) for link in direct_links}
    cooccurrence = {(operation, outcome) for operation in operations
                    for outcome in outcome_families}
    source_text = snapshot.get("source", {}).get("text", "")
    return {
        "article_id": snapshot["article_id"],
        "run_id": snapshot["run_id"],
        "source_sha256": snapshot.get("source", {}).get("sha256"),
        "support_family": support_family or snapshot["article_id"],
        "operation_families": sorted(operations),
        "outcome_families": sorted(outcome_families),
        "graph_links": [list(pair) for pair in sorted(pairs)],
        "cooccurrence_links": [list(pair) for pair in sorted(cooccurrence)],
        "direct_links": direct_links,
        "coverage": {
            "action_blocks_performed": len(actions),
            "action_statements_checked": action_statements,
            "action_statements_classified": recognized_action_statements,
            "action_statement_coverage": (recognized_action_statements / action_statements
                                           if action_statements else None),
            "unknown_action_predicates": dict(sorted(unknown_actions.items())),
            "state_predicates_checked": state_statements,
            "state_predicates_classified_as_reported_outcome": categorized_state_statements,
            "state_predicate_category_coverage": (
                categorized_state_statements / state_statements if state_statements else None),
            "reported_outcome_category_counts": dict(sorted(outcome_family_counts.items())),
            "unknown_outcome_predicates": dict(sorted(unknown_outcomes.items())),
            "source_characters": len(source_text),
        },
    }


def _supported_pairs(training: list[dict], link_field: str, minimum_support: int) -> set[tuple[str, str]]:
    support = _pair_support(training, link_field)
    return {pair for pair, families in support.items() if len(families) >= minimum_support}


def _pair_support(training: list[dict], link_field: str) -> dict[tuple[str, str], set[str]]:
    """Считает поддержку связей разными семействами публикаций."""
    support: dict[tuple[str, str], set[str]] = defaultdict(set)
    for record in training:
        for raw_pair in record[link_field]:
            pair = tuple(raw_pair)
            support[pair].add(record["support_family"])
    return support


def seal_predictions(records: list[dict], minimum_support: int = MINIMUM_SUPPORT) -> dict:
    """Формирует выходы только из обучающих связей и контекста операций цели."""
    require(minimum_support >= 1, "Минимальная поддержка должна быть положительной")
    ids = [record["article_id"] for record in records]
    require(len(ids) == len(set(ids)), "Повторяющийся article_id")
    folds = []
    for target in sorted(records, key=lambda record: record["article_id"]):
        training = [record for record in records if record["article_id"] != target["article_id"]]
        target_operations = set(target["operation_families"])
        candidates = {}
        ranked_candidates = {}
        training_outcomes = sorted(set().union(*(
            set(record["outcome_families"]) for record in training
        ))) if training else []
        for mode, field in (("graph", "graph_links"),
                            ("same_article_cooccurrence", "cooccurrence_links")):
            supports = _pair_support(training, field)
            supported = {pair for pair, families in supports.items()
                         if len(families) >= minimum_support}
            candidates[mode] = sorted(pair for pair in supported
                                      if pair[0] in target_operations)
            ranked = []
            for operation in sorted(target_operations):
                for outcome in training_outcomes:
                    pair = (operation, outcome)
                    ranked.append({
                        "pair": list(pair),
                        "distinct_source_families": len(supports.get(pair, set())),
                    })
            ranked_candidates[mode] = sorted(
                ranked,
                key=lambda item: (-item["distinct_source_families"], item["pair"]),
            )
        # Целевые исходы и переходы здесь намеренно не читаются.
        folds.append({
            "target_article_id": target["article_id"],
            "target_run_id": target["run_id"],
            "training_article_ids": sorted(record["article_id"] for record in training),
            "target_operation_families": sorted(target_operations),
            "predictions": {name: [list(pair) for pair in pairs]
                            for name, pairs in candidates.items()},
            "ranked_candidates": ranked_candidates,
        })
    result = {
        "version": VERSION,
        "minimum_support": minimum_support,
        "target_fields_used": ["operation_families", "article_id", "run_id"],
        "target_outcomes_or_dependencies_used": False,
        "folds": folds,
    }
    result["prediction_sha256"] = fingerprint(result)
    return result


def _permuted_records(records: list[dict], seed: int) -> list[dict]:
    """Перетасовывает только целевые категории на переходах внутри каждой статьи."""
    rng = random.Random(seed)
    permuted = []
    for record in records:
        row = deepcopy(record)
        links = row["direct_links"]
        original_operations = Counter(link["operation_family"] for link in links)
        original_outcomes = Counter(link["outcome_family"] for link in links)
        shuffled = [link["outcome_family"] for link in links]
        rng.shuffle(shuffled)
        row["graph_links"] = sorted([
            (link["operation_family"], outcome)
            for link, outcome in zip(links, shuffled)
        ])
        require(original_operations == Counter(pair[0] for pair in row["graph_links"]),
                "Перестановка изменила число операций")
        require(original_outcomes == Counter(pair[1] for pair in row["graph_links"]),
                "Перестановка изменила число категорий результатов")
        row["graph_links"] = [list(pair) for pair in row["graph_links"]]
        permuted.append(row)
    return permuted


def seal_permuted_predictions(records: list[dict], minimum_support: int = MINIMUM_SUPPORT,
                              seeds: tuple[int, ...] = PERMUTATION_SEEDS) -> dict:
    """Строит контрольные прогнозы с переставленными учебными рёбрами."""
    require(bool(seeds) and len(set(seeds)) == len(seeds), "Нужны уникальные seed перестановок")
    controls = []
    for seed in seeds:
        permuted = _permuted_records(records, seed)
        sealed = seal_predictions(permuted, minimum_support)
        changed_source_count = 0
        changed_pair_assignments = 0
        for original, shuffled in zip(records, permuted):
            before = Counter((link["operation_family"], link["outcome_family"])
                             for link in original["direct_links"])
            after = Counter(tuple(pair) for pair in shuffled["graph_links"])
            missing = before - after
            if missing:
                changed_source_count += 1
                changed_pair_assignments += sum(missing.values())
        controls.append({"seed": seed, "folds": [
            {"target_article_id": fold["target_article_id"],
             "predictions": {"permuted_dependencies": fold["predictions"]["graph"]},
             "ranked_candidates": {
                 "permuted_dependencies": fold["ranked_candidates"]["graph"]
             }}
            for fold in sealed["folds"]
        ], "changed_source_count": changed_source_count,
            "changed_pair_assignments": changed_pair_assignments})
    result = {
        "version": VERSION + ":permuted-control",
        "minimum_support": minimum_support,
        "seed_count": len(seeds),
        "training_marginals_preserved": ["per-article operation families",
                                          "per-article outcome-link multiset"],
        "target_outcomes_or_dependencies_used": False,
        "controls": controls,
    }
    result["control_sha256"] = fingerprint(result)
    return result


def _expected_hits_at_k(ranked: list[dict], actual: set[tuple[str, str]], k: int) -> tuple[float, int]:
    """Считает попадания на границе равных рангов без алфавитной предвзятости."""
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
        relevant = sum(tuple(item["pair"]) in actual for item in group)
        hits += selected * relevant / len(group)
        remaining -= selected
        index = end
    return hits, slots


def score_predictions(records: list[dict], sealed: dict,
                      permuted: dict | None = None) -> dict:
    """Открывает истинные переходы только после того, как прогнозы зафиксированы."""
    require(sealed.get("target_outcomes_or_dependencies_used") is False,
            "В sealed прогноз попали целевые исходы")
    record_by_id = {record["article_id"]: record for record in records}
    require(set(record_by_id) == {fold["target_article_id"] for fold in sealed["folds"]},
            "Неполный набор целевых статей")
    folds = []
    totals = {mode: {"predicted": 0, "target": 0, "hits": 0}
              for mode in ("graph", "same_article_cooccurrence")}
    ranking_totals = {
        k: {mode: {"expected_hits": 0.0, "candidate_slots": 0, "target": 0,
                   "eligible_folds": 0}
            for mode in totals}
        for k in (1, 3, 5, 10)
    }
    for fold in sealed["folds"]:
        actual = {tuple(pair) for pair in record_by_id[fold["target_article_id"]]["graph_links"]}
        scored = {}
        ranked_scores = {}
        for mode in totals:
            predicted = {tuple(pair) for pair in fold["predictions"][mode]}
            hits = predicted & actual
            scored[mode] = {
                "predicted": len(predicted), "target": len(actual), "hits": len(hits),
                "precision": len(hits) / len(predicted) if predicted else None,
                "recall": len(hits) / len(actual) if actual else None,
                "matched": [list(pair) for pair in sorted(hits)],
                "missed": [list(pair) for pair in sorted(actual - predicted)],
                "extra": [list(pair) for pair in sorted(predicted - actual)],
            }
            for key in ("predicted", "target", "hits"):
                totals[mode][key] += scored[mode][key]
            ranked_scores[mode] = {}
            ranked = fold["ranked_candidates"][mode]
            for k, mode_totals in ranking_totals.items():
                expected_hits, candidate_slots = _expected_hits_at_k(ranked, actual, k)
                mode_totals[mode]["expected_hits"] += expected_hits
                mode_totals[mode]["candidate_slots"] += candidate_slots
                mode_totals[mode]["target"] += len(actual)
                mode_totals[mode]["eligible_folds"] += int(bool(ranked))
                ranked_scores[mode][str(k)] = {
                    "expected_hits": expected_hits,
                    "candidate_slots": candidate_slots,
                    "target": len(actual),
                }
        folds.append({**fold, "actual_links": [list(pair) for pair in sorted(actual)],
                      "scores": scored, "ranked_scores": ranked_scores})

    aggregate = {}
    for mode, values in totals.items():
        aggregate[mode] = {
            **values,
            "precision": values["hits"] / values["predicted"] if values["predicted"] else None,
            "recall": values["hits"] / values["target"] if values["target"] else None,
        }

    ranked_aggregate = {}
    for k, modes in ranking_totals.items():
        ranked_aggregate[str(k)] = {}
        for mode, values in modes.items():
            ranked_aggregate[str(k)][mode] = {
                **values,
                "precision": (values["expected_hits"] / values["candidate_slots"]
                              if values["candidate_slots"] else None),
                "recall": (values["expected_hits"] / values["target"]
                           if values["target"] else None),
                "candidate_coverage": (values["candidate_slots"] /
                                       (k * values["eligible_folds"])
                                       if values["eligible_folds"] else None),
            }

    permutation_summary = None
    if permuted is not None:
        require(permuted.get("target_outcomes_or_dependencies_used") is False,
                "В контроль попали целевые исходы")
        predicted_totals = []
        hit_totals = []
        prediction_signatures = set()
        ranked_signatures = set()
        ranked_hit_totals = {k: [] for k in ranking_totals}
        ranked_slot_totals = {k: [] for k in ranking_totals}
        for control in permuted["controls"]:
            count = hits = 0
            signature = []
            ranked_signature = []
            seed_ranked_hits = {k: 0.0 for k in ranking_totals}
            seed_ranked_slots = {k: 0 for k in ranking_totals}
            for fold in control["folds"]:
                actual = {tuple(pair) for pair in record_by_id[fold["target_article_id"]]["graph_links"]}
                predicted = {tuple(pair) for pair in fold["predictions"]["permuted_dependencies"]}
                count += len(predicted)
                hits += len(predicted & actual)
                signature.append((fold["target_article_id"], sorted(predicted)))
                ranked = fold["ranked_candidates"]["permuted_dependencies"]
                ranked_signature.append((
                    fold["target_article_id"],
                    [(tuple(item["pair"]), item["distinct_source_families"])
                     for item in ranked],
                ))
                for k in ranking_totals:
                    expected_hits, candidate_slots = _expected_hits_at_k(ranked, actual, k)
                    seed_ranked_hits[k] += expected_hits
                    seed_ranked_slots[k] += candidate_slots
            predicted_totals.append(count)
            hit_totals.append(hits)
            prediction_signatures.add(fingerprint(signature))
            ranked_signatures.add(fingerprint(ranked_signature))
            for k in ranking_totals:
                ranked_hit_totals[k].append(seed_ranked_hits[k])
                ranked_slot_totals[k].append(seed_ranked_slots[k])
        changed_sources = [control["changed_source_count"] for control in permuted["controls"]]
        changed_assignments = [control["changed_pair_assignments"] for control in permuted["controls"]]
        permutation_summary = {
            "seed_count": len(predicted_totals),
            "predicted_mean": sum(predicted_totals) / len(predicted_totals),
            "hits_mean": sum(hit_totals) / len(hit_totals),
            "hits_min": min(hit_totals), "hits_max": max(hit_totals),
            "unique_prediction_sets": len(prediction_signatures),
            "unique_ranked_profiles": len(ranked_signatures),
            "changed_sources_min": min(changed_sources),
            "changed_sources_max": max(changed_sources),
            "changed_sources_mean": sum(changed_sources) / len(changed_sources),
            "changed_pair_assignments_min": min(changed_assignments),
            "changed_pair_assignments_max": max(changed_assignments),
            "permutations_at_least_graph_hits": sum(
                hits >= totals["graph"]["hits"] for hits in hit_totals),
            "ranked_top_k": {
                str(k): {
                    "expected_hits_mean": sum(ranked_hit_totals[k]) / len(ranked_hit_totals[k]),
                    "expected_hits_min": min(ranked_hit_totals[k]),
                    "expected_hits_max": max(ranked_hit_totals[k]),
                    "candidate_slots_mean": sum(ranked_slot_totals[k]) /
                                            len(ranked_slot_totals[k]),
                    "controls_at_least_graph": sum(
                        hits >= ranking_totals[k]["graph"]["expected_hits"]
                        for hits in ranked_hit_totals[k]),
                }
                for k in ranking_totals
            },
            "is_confirmatory_p_value": False,
        }
    return {
        "version": VERSION,
        "prediction_sha256": sealed["prediction_sha256"],
        "source_count": len(records),
        "eligible_target_folds": sum(bool(record["operation_families"]) for record in records),
        "aggregate": aggregate,
        "ranked_aggregate": ranked_aggregate,
        "permuted_control": permutation_summary,
        "folds": folds,
        "scientific_fact_forecast": False,
        "expert_validated": False,
    }
