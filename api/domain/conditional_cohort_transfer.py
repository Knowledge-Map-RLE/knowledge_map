"""Выбор условий переноса только на внутренних групповых разбиениях обучения."""
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from fractions import Fraction

from domain.article_maps import fingerprint, require
from domain.cohort_transfer import (RateObservation, RateQuery, core_matches, differences,
                                   forecast_fold, global_frequency, order, witness_pairs)
from domain.empirical_inference import number

VERSION = "conditional-cohort-order-transfer-1"
FIELDS = ((), ("criteria",), ("threshold_sd",), ("criteria", "threshold_sd", "dementia_exclusion"),
          ("norms",), ("followup_kind",))
POLICY = {
    "candidate_fields": [list(fields) for fields in FIELDS],
    "vote_rules": ["unanimous", "two_thirds"],
    "minimum_support_groups": 2,
    "minimum_inner_covered_groups": 2,
    "age_matching": "Identical adjacent age bands, same endpoint/measure/unit/design",
    "unknown_required_modifier": "Reject witness; unknown equals unknown is not established equality",
    "family_vote": "One vote per provenance group; conflicting within-group orders remain mixed",
    "majority": "At least two clear provenance-group votes; winner >=2/3 of all eligible groups, including mixed",
    "selection_objective": "Mean across inner groups of (matched - 2*wrong)/all_queries; abstention reward 0",
    "tie_break": "Higher group-balanced coverage, fewer required fields, unanimity, lexicographic id",
    "selection_scope": "One global specification fitted per outer training fold, not per held-out outcome",
    "scientific_status": "Retrospective development diagnostic on previously inspected review; no independent scientific success",
    "outer_controls_allowed_during_fit": False,
    "numeric_prediction": False,
    "causal_claim": False,
}


@dataclass(frozen=True)
class Specification:
    id: str
    required_fields: tuple[str, ...]
    vote_rule: str


CANDIDATES = tuple(Specification(("none" if not fields else "+".join(fields))+":"+vote, fields, vote)
                   for fields in FIELDS for vote in POLICY["vote_rules"])


def predict(query, witnesses, spec):
    """Отдельный прогноз не получает значений удержанной группы."""
    require(spec in CANDIDATES, "Unknown conditional specification")
    eligible, rejected = [], Counter()
    for w in witnesses:
        ctx = w["context"]
        if ctx.family_id == query.context.family_id:
            rejected["same_or_possible_overlap_family"] += 1
            continue
        if not core_matches(ctx, query.context) or w["ages"] != query.ages:
            continue
        if any(getattr(ctx, f) is None or getattr(query.context, f) is None or
               getattr(ctx, f) != getattr(query.context, f) for f in spec.required_fields):
            rejected["required_modifier_unknown_or_different"] += 1
            continue
        eligible.append({**w, "context": asdict(ctx), "differences": differences(ctx, query.context)})
    groups = defaultdict(list)
    for w in eligible:
        groups[w["context"]["family_id"]].append(w["order"])
    votes = {g: vals[0] if len(set(vals)) == 1 else "mixed" for g, vals in sorted(groups.items())}
    counts = Counter(v for v in votes.values() if v != "mixed")
    winner = None
    reason = "insufficient_distinct_provenance_groups"
    if sum(counts.values()) >= POLICY["minimum_support_groups"]:
        ranked = counts.most_common()
        if spec.vote_rule == "unanimous":
            if len(counts) == 1 and "mixed" not in votes.values():
                winner = ranked[0][0]
        elif ranked and 3*ranked[0][1] >= 2*len(votes):
            winner = ranked[0][0]
        reason = None if winner else "conflicting_source_orders"
    return {"query_id": query.id, "context": asdict(query.context), "ages": query.ages,
            "specification": asdict(spec), "family_votes": votes, "witnesses": eligible, "rejected": dict(rejected),
            "status": "conditional_transfer_hypothesis" if winner else "abstain", "order": winner, "reason": reason,
            "statement_kind": "hypothesis_about_reported_point_estimate_order", "numeric_prediction": None,
            "causal": False, "statistical_difference_claimed": False, "equivalence_confirmed": False}


def validation_queries(observations):
    """Внутренние известные числа используются как метки, отдельно от прогноза."""
    result = []
    for w in witness_pairs(observations):
        q = RateQuery.parse({"id": "inner:"+"|".join(w["observation_ids"]), "context": asdict(w["context"]),
                             "ages": [list(a) for a in w["ages"]], "evidence_ids": w["evidence_ids"]})
        result.append((q, w["order"]))
    return result


def fit(observations):
    families = sorted({o.context.family_id for o in observations})
    require(len(families) >= 3, "At least three training provenance groups required for nested fitting")
    audits, scores = [], []
    for spec in CANDIDATES:
        groups = []
        for family in families:
            training = [o for o in observations if o.context.family_id != family]
            labels = validation_queries([o for o in observations if o.context.family_id == family])
            witnesses = witness_pairs(training)
            rows = []
            for q, expected in labels:
                p = predict(q, witnesses, spec)
                rows.append({"query_id": q.id, "issued": p["order"] is not None, "predicted_order": p["order"],
                             "training_label": expected, "matched": p["order"] == expected if p["order"] else None,
                             "support_groups": sorted(p["family_votes"]),
                             "support_observation_ids": sorted({k for w in p["witnesses"] for k in w["observation_ids"]})})
            groups.append({"validation_family": family, "fit_families": sorted({o.context.family_id for o in training}),
                           "fit_observation_ids": sorted(o.id for o in training), "rows": rows})
        nonempty = [g for g in groups if g["rows"]]
        covered_groups = sum(any(r["issued"] for r in g["rows"]) for g in nonempty)
        utility = sum((Fraction(sum(r["matched"] is True for r in g["rows"])-2*sum(r["matched"] is False for r in g["rows"]),
                                len(g["rows"])) for g in nonempty), Fraction(0))/len(nonempty) if nonempty else Fraction(0)
        coverage = sum((Fraction(sum(r["issued"] for r in g["rows"]), len(g["rows"])) for g in nonempty), Fraction(0))/len(nonempty) if nonempty else Fraction(0)
        score = {"specification": asdict(spec), "utility": str(utility), "group_balanced_coverage": str(coverage),
                 "covered_validation_groups": covered_groups, "eligible": covered_groups >= POLICY["minimum_inner_covered_groups"],
                 "issued": sum(r["issued"] for g in groups for r in g["rows"]),
                 "matched": sum(r["matched"] is True for g in groups for r in g["rows"]),
                 "wrong": sum(r["matched"] is False for g in groups for r in g["rows"])}
        scores.append(score)
        audits.append({"specification_id": spec.id, "groups": groups})
    eligible = [s for s in scores if s["eligible"]]
    ranked = sorted(eligible, key=lambda s: (-Fraction(s["utility"]), -Fraction(s["group_balanced_coverage"]),
                                           len(s["specification"]["required_fields"]),
                                           s["specification"]["vote_rule"] != "unanimous", s["specification"]["id"]))
    return {"selected": ranked[0]["specification"] if ranked else None, "scores": scores, "inner_audit": audits,
            "training_families": families, "training_observation_ids": sorted(o.id for o in observations),
            "training_sha256": fingerprint([asdict(o) for o in observations]),
            "outer_controls_read": False}


def forecast_conditional_fold(data):
    # Старый валидатор также проверяет, что вся внешняя группа удалена из обучения.
    prior = forecast_fold(data)
    observations = [RateObservation.parse(o) for o in data["training"]]
    queries = [RateQuery.parse(q) for q in data["queries"]]
    selection = fit(observations)
    spec = next((s for s in CANDIDATES if selection["selected"] and s.id == selection["selected"]["id"]), None)
    witnesses = witness_pairs(observations)
    predictions = []
    for q in queries:
        if spec is None:
            predictions.append({"query_id": q.id, "order": None, "status": "abstain", "witnesses": [],
                                "reason": "no_specification_with_sufficient_inner_coverage", "numeric_prediction": None,
                                "causal": False, "statistical_difference_claimed": False})
        else:
            predictions.append(predict(q, witnesses, spec))
    age_majority = next(s for s in CANDIDATES if s.id == "none:two_thirds")
    return {"fold_id": data["fold_id"], "withheld_family": data["withheld_family"], "selection": selection,
            "predictions": {"conditional": predictions, "age_majority": [predict(q, witnesses, age_majority) for q in queries],
                            "previous_unanimous": prior["predictions"]["exploratory"],
                            "frequency": [global_frequency(q, witnesses) for q in queries]}, "model_calls": 0}


def evaluate(folds, controls):
    modes = ("conditional", "age_majority", "previous_unanimous", "frequency")
    query_ids = [p["query_id"] for f in folds for p in f["predictions"]["conditional"]]
    require(len(query_ids) == len(set(query_ids)) and set(query_ids) == set(controls), "Holdout identities differ")
    metrics = {}
    for mode in modes:
        rows = []
        for fold in folds:
            require([p["query_id"] for p in fold["predictions"][mode]] ==
                    [p["query_id"] for p in fold["predictions"]["conditional"]], "Mode query identities differ")
            for p in fold["predictions"][mode]:
                c = controls[p["query_id"]]
                require(c["family_id"] == fold["withheld_family"], "Control outside held-out family")
                expected = order(*c["values"])
                rows.append({"query_id": p["query_id"], "fold_id": fold["fold_id"], "issued": p["order"] is not None,
                             "predicted_order": p["order"], "reported_order": expected,
                             "matched": p["order"] == expected if p["order"] else None,
                             "intervals_overlap": max(number(i[0]) for i in c["intervals"]) <= min(number(i[1]) for i in c["intervals"])})
        issued = sum(r["issued"] for r in rows)
        matched = sum(r["matched"] is True for r in rows)
        per_group = []
        for f in folds:
            group = [r for r in rows if r["fold_id"] == f["fold_id"]]
            per_group.append(Fraction(sum(r["matched"] is True for r in group)-2*sum(r["matched"] is False for r in group), len(group)))
        metrics[mode] = {"queries": len(rows), "issued": issued, "matched": matched, "wrong_order": issued-matched,
                         "abstained": len(rows)-issued, "accuracy_among_issued": matched/issued if issued else None,
                         "coverage": issued/len(rows), "group_balanced_utility": str(sum(per_group)/len(per_group)), "rows": rows}
    conditional = {r["query_id"]: r for r in metrics["conditional"]["rows"] if r["issued"]}
    paired = {}
    for mode in modes[1:]:
        base = {r["query_id"]: r for r in metrics[mode]["rows"] if r["issued"]}
        common = sorted(set(conditional) & set(base))
        paired[mode] = {"queries": len(common), "conditional_matched": sum(conditional[k]["matched"] for k in common),
                        "baseline_matched": sum(base[k]["matched"] for k in common),
                        "same_predictions": sum(conditional[k]["predicted_order"] == base[k]["predicted_order"] for k in common),
                        "conditional_only_correct": sum(conditional[k]["matched"] and not base[k]["matched"] for k in common),
                        "baseline_only_correct": sum(base[k]["matched"] and not conditional[k]["matched"] for k in common),
                        "query_ids": common}
    return {"modes": metrics, "paired": paired, "new_scientific_predictions": 0, "independent_success": False,
            "note": "Nested source-only development diagnostic; outer study outcomes had already been inspected in previous work"}
