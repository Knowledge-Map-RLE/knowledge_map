"""Условные гипотезы о порядке оценок в полностью исключённой когорте."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, asdict, fields
from decimal import Decimal
from itertools import pairwise

from domain.article_maps import fingerprint, require
from domain.empirical_inference import number

VERSION = "cohort-order-transfer-1"
POLICY = {
    "task": "Retrospective source-only holdout of adjacent-age incidence estimate ordering",
    "novel_scientific_predictions": False,
    "minimum_support_groups": 2,
    "exploratory_rule": "All age-pair-specific provenance groups must agree; at least two groups",
    "strict_context": ["criteria", "threshold_sd", "dementia_exclusion", "norms", "followup_years", "followup_kind", "country",
                       "calendar_period", "attrition_adjustment", "sample_n", "female_percent", "education", "place", "response_rate"],
    "mandatory_context": ["endpoint", "measure", "unit", "design"],
    "moderators": "Exploratory mode retains diagnostic, geographic and follow-up differences; it does not prove transportability",
    "family": "Busse 2003 and Luck 2010 share a conservative possible-overlap group",
    "prohibited": ["numeric_estimate_invention", "statistical_significance_claim", "causal_claim", "individual_ageing_effect", "target_article_access"],
    "selection": "All adjacent age-band pairs with reported estimates; no target-guided filtering or refill",
}
ENDPOINTS = {"MCI", "aMCI", "naMCI", "AD_conversion", "IL6", "TNFalpha"}


@dataclass(frozen=True)
class RateContext:
    study_id: str
    family_id: str
    endpoint: str
    measure: str
    unit: str
    design: str
    criteria: str | None
    threshold_sd: str | None
    dementia_exclusion: str | None
    norms: str | None
    followup_years: str | None
    followup_kind: str | None
    country: str | None
    calendar_period: str | None
    attrition_adjustment: str | None
    sample_n: str | None
    female_percent: str | None
    education: str | None
    place: str | None
    response_rate: str | None

    @classmethod
    def parse(cls, data):
        require(isinstance(data, dict) and set(data) == {f.name for f in fields(cls)}, "Invalid rate context")
        require(all(isinstance(data[k], str) and data[k] for k in ("study_id", "family_id", *POLICY["mandatory_context"])), "Incomplete mandatory rate context")
        require(data["endpoint"] in ENDPOINTS, "Unknown endpoint")
        for k in POLICY["strict_context"]:
            require(data[k] is None or isinstance(data[k], str) and data[k], "Invalid context modifier")
        return cls(**data)


def band(data):
    require(isinstance(data, list) and len(data) == 2 and type(data[0]) is int and data[0] >= 0, "Invalid age band")
    require(data[1] is None or type(data[1]) is int and data[1] >= data[0], "Invalid age-band endpoint")
    return tuple(data)


@dataclass(frozen=True)
class RateObservation:
    id: str
    context: RateContext
    age: tuple[int, int | None]
    value: str
    interval: tuple[str, str]
    evidence_ids: tuple[str, ...]

    @classmethod
    def parse(cls, data):
        require(isinstance(data, dict) and set(data) == {f.name for f in fields(cls)}, "Invalid rate observation")
        require(isinstance(data["id"], str) and data["id"], "Missing rate identity")
        age = band(data["age"])
        require(isinstance(data["interval"], list) and len(data["interval"]) == 2, "Invalid rate interval")
        lo, hi = map(number, data["interval"])
        require(0 <= lo <= number(data["value"]) <= hi, "Rate outside its interval")
        require(isinstance(data["evidence_ids"], list) and data["evidence_ids"], "Missing rate provenance")
        return cls(data["id"], RateContext.parse(data["context"]), age, data["value"], tuple(data["interval"]), tuple(data["evidence_ids"]))


@dataclass(frozen=True)
class RateQuery:
    id: str
    context: RateContext
    ages: tuple[tuple[int, int | None], tuple[int, int | None]]
    evidence_ids: tuple[str, ...]

    @classmethod
    def parse(cls, data):
        require(isinstance(data, dict) and set(data) == {f.name for f in fields(cls)}, "Rate query must not contain hidden estimates")
        require(isinstance(data["id"], str) and data["id"], "Missing query identity")
        require(isinstance(data["ages"], list) and len(data["ages"]) == 2, "Invalid query ages")
        ages = tuple(band(x) for x in data["ages"])
        require(ages[0][1] is not None and ages[0][1] + 1 == ages[1][0], "Only adjacent reported age bands are supported")
        require(isinstance(data["evidence_ids"], list) and data["evidence_ids"], "Missing query provenance")
        return cls(data["id"], RateContext.parse(data["context"]), ages, tuple(data["evidence_ids"]))


def order(left: str, right: str) -> str:
    return "higher" if number(right) > number(left) else "lower" if number(right) < number(left) else "equal"


def differences(left: RateContext, right: RateContext) -> dict:
    return {k: {"source": getattr(left, k), "query": getattr(right, k)} for k in POLICY["strict_context"]
            if getattr(left, k) != getattr(right, k) or getattr(left, k) is None or getattr(right, k) is None}


def core_matches(left: RateContext, right: RateContext) -> bool:
    return all(getattr(left, k) == getattr(right, k) for k in POLICY["mandatory_context"]) and (
        left.measure, left.unit, left.design) == ("incidence_rate", "per1000personyears", "longitudinal")


def witness_pairs(observations):
    by_series = defaultdict(list)
    for obs in observations:
        by_series[(obs.context.study_id, obs.context.endpoint)].append(obs)
    pairs = []
    for series in by_series.values():
        series.sort(key=lambda o: o.age[0])
        require(len({o.age for o in series}) == len(series), "Duplicate cohort age observation")
        for left, right in pairwise(series):
            require(left.context == right.context, "A training series mixes incompatible contexts")
            if left.age[1] is None or left.age[1] + 1 != right.age[0]:
                continue
            pairs.append({"context": left.context, "ages": (left.age, right.age), "order": order(left.value, right.value),
                          "observation_ids": [left.id, right.id], "evidence_ids": sorted(set(left.evidence_ids + right.evidence_ids))})
    return pairs


def propose(query: RateQuery, witnesses: list[dict], mode: str) -> dict:
    eligible, rejected = [], Counter()
    for w in witnesses:
        if w["context"].family_id == query.context.family_id:
            rejected["same_or_possible_overlap_family"] += 1
            continue
        if not core_matches(w["context"], query.context) or w["ages"] != query.ages:
            continue
        diff = differences(w["context"], query.context)
        if mode == "strict" and diff:
            rejected["unbridged_context_difference_or_unknown"] += 1
            continue
        eligible.append({**w, "context": asdict(w["context"]), "differences": diff})
    by_family = defaultdict(list)
    for w in eligible:
        by_family[w["context"]["family_id"]].append(w["order"])
    votes = {f: vals[0] if len(set(vals)) == 1 else "mixed" for f, vals in sorted(by_family.items())}
    base = {"query_id": query.id, "mode": mode, "context": asdict(query.context), "ages": query.ages,
            "family_votes": votes, "witnesses": eligible, "rejected": dict(rejected), "causal": False,
            "statistical_difference_claimed": False, "numeric_prediction": None,
            "statement_kind": "hypothesis_about_reported_point_estimate_order"}
    if len(votes) < POLICY["minimum_support_groups"]:
        return {**base, "status": "abstain", "order": None, "reason": "insufficient_distinct_provenance_groups"}
    if "mixed" in votes.values() or len(set(votes.values())) != 1:
        return {**base, "status": "abstain", "order": None, "reason": "conflicting_source_orders"}
    return {**base, "status": "exploratory_hypothesis" if mode == "exploratory" else "context_matched_hypothesis",
            "order": next(iter(votes.values())), "reason": None}


def global_frequency(query, witnesses):
    by_family = defaultdict(Counter)
    for w in witnesses:
        if w["context"].family_id != query.context.family_id and core_matches(w["context"], query.context):
            by_family[w["context"].family_id][w["order"]] += 1
    votes = []
    for counts in by_family.values():
        ranked = counts.most_common()
        if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
            votes.append(ranked[0][0])
    ranked = Counter(votes).most_common()
    decision = ranked[0][0] if ranked and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]) else None
    return {"query_id": query.id, "status": "frequency_baseline" if decision else "abstain", "order": decision,
            "note": "Provenance-balanced order frequency; ignores exact age pair and context modifiers"}


def forecast_fold(data: dict) -> dict:
    require(isinstance(data, dict) and set(data) == {"fold_id", "withheld_family", "training", "queries", "evidence", "labels"}, "Invalid fold or leaked controls")
    observations = [RateObservation.parse(x) for x in data["training"]]
    queries = [RateQuery.parse(x) for x in data["queries"]]
    require(observations and queries, "Explicit training and held-out contexts required")
    require(len({o.id for o in observations}) == len(observations) and len({q.id for q in queries}) == len(queries), "Duplicate transfer item")
    require(not {o.context.family_id for o in observations} & {data["withheld_family"]}, "Held-out family leaked into training")
    require(all(q.context.family_id == data["withheld_family"] for q in queries), "Query outside held-out family")
    witnesses = witness_pairs(observations)
    return {"fold_id": data["fold_id"], "withheld_family": data["withheld_family"], "training_count": len(observations),
            "query_count": len(queries), "predictions": {m: [propose(q, witnesses, m) for q in queries] for m in ("strict", "exploratory")},
            "frequency": [global_frequency(q, witnesses) for q in queries], "model_calls": 0}


def evaluate_folds(folds: list[dict], controls: dict) -> dict:
    rows_by_mode = {mode: [] for mode in ("strict", "exploratory", "frequency")}
    all_queries = {r["query_id"] for fold in folds for r in fold["predictions"]["strict"]}
    require(all_queries == set(controls), "Transfer holdout identities differ")
    for fold in folds:
        for mode in rows_by_mode:
            results = fold["frequency"] if mode == "frequency" else fold["predictions"][mode]
            for prediction in results:
                control = controls[prediction["query_id"]]
                expected = order(control["values"][0], control["values"][1])
                issued = prediction["order"] is not None
                rows_by_mode[mode].append({"query_id": prediction["query_id"], "fold_id": fold["fold_id"],
                    "issued": issued, "predicted_order": prediction["order"], "reported_order": expected,
                    "matched": prediction["order"] == expected if issued else None,
                    "intervals_overlap": max(map(number, [x[0] for x in control["intervals"]])) <= min(map(number, [x[1] for x in control["intervals"]])),
                    "scientific_significance_of_difference": "not_established_by_this_order_comparison"})
    metrics = {}
    for mode, rows in rows_by_mode.items():
        issued = sum(r["issued"] for r in rows)
        matched = sum(r["matched"] is True for r in rows)
        metrics[mode] = {"queries": len(rows), "issued": issued, "matched": matched, "wrong_order": issued-matched,
                         "abstained": len(rows)-issued, "accuracy_among_issued": matched/issued if issued else None,
                         "coverage": issued/len(rows) if rows else None, "rows": rows}
    return {"modes": metrics, "new_scientific_predictions": 0, "independent_success": False,
            "note": "Previously read review-based retrospective holdouts; not a future-article test"}


def screen_pair(left: RateContext, right: RateContext) -> dict:
    incompatible=[field for field in ("endpoint","measure","unit","design") if getattr(left,field)!=getattr(right,field)]
    if incompatible:
        return {"status":"blocked","reason":"different_"+incompatible[0],"incompatible_fields":incompatible,
                "same_or_possible_overlap_family":left.family_id==right.family_id}
    if left.family_id == right.family_id:
        return {"status": "not_independent_support", "reason": "same_or_possible_overlap_family"}
    return {"status": "candidate_for_exploratory_comparison", "reason": None, "differences": differences(left, right),
            "equivalence_confirmed": False}
