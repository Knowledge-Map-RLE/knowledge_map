"""Типизированные эмпирические факты и ограниченный статистический вывод."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from decimal import Decimal, InvalidOperation
from typing import Any

from domain.article_maps import fingerprint, require

VERSION = "typed-empirical-inference-1"
CONTRACT_VERSION = 1
POLICY = {
    "purpose": "Reconstruct withheld statistical summaries, not predict new study findings",
    "operator": "signed_coefficient_and_reported_p_with_explicit_threshold",
    "premises": ["reported_coefficient", "reported_p_value", "context_bound_test_policy"],
    "context": "Identical study, analysis, population, design, time, outcome, adjustment and scale",
    "non_significance": "Failure to meet the threshold is not a zero effect or proof of no association",
    "coding": "Unknown or ambiguous coding blocks real-world directional interpretation",
    "prohibited": ["causality", "longitudinal_prediction_from_cross_sectional_data", "cohort_transfer", "numeric_effect_invention"],
}


def number(value: str) -> Decimal:
    require(isinstance(value, str), "Numbers must retain their source strings")
    try:
        result = Decimal(value.replace("−", "-"))
    except InvalidOperation as exc:
        raise ValueError("Invalid empirical numeric value") from exc
    require(result.is_finite(), "Nonfinite empirical value")
    return result


def strict_fields(cls, data: dict) -> dict:
    require(isinstance(data, dict) and set(data) == {f.name for f in fields(cls)}, f"Invalid {cls.__name__} contract")
    return data


@dataclass(frozen=True)
class AnalysisContext:
    study_id: str
    analysis_id: str
    population_id: str
    design: str
    time: str
    outcome: str
    outcome_scale: str
    adjustment: tuple[str, ...]
    sample_n: int | None

    @classmethod
    def parse(cls, data):
        values = dict(strict_fields(cls, data))
        require(all(isinstance(values[k], str) and values[k] for k in
                    ("study_id", "analysis_id", "population_id", "design", "time", "outcome", "outcome_scale")), "Incomplete empirical context")
        require(values["design"] in {"cross_sectional", "meta_regression", "longitudinal"}, "Unsupported study design")
        require(isinstance(values["adjustment"], list) and all(isinstance(x, str) and x for x in values["adjustment"]), "Invalid adjustment variables")
        require(len(set(values["adjustment"])) == len(values["adjustment"]), "Duplicate adjustment variable")
        require(values["sample_n"] is None or type(values["sample_n"]) is int and values["sample_n"] > 0, "Invalid empirical sample size")
        values["adjustment"] = tuple(sorted(values["adjustment"]))
        return cls(**values)


@dataclass(frozen=True)
class EffectEstimate:
    id: str
    context: AnalysisContext
    predictor: str
    measure: str
    coefficient: str
    coefficient_unit: str | None
    p_value: str | None
    interval: tuple[str, str] | None
    interval_level: str | None
    coding: str
    evidence_ids: tuple[str, ...]

    @classmethod
    def parse(cls, data):
        values = dict(strict_fields(cls, data))
        values["context"] = AnalysisContext.parse(values["context"])
        require(all(isinstance(values[k], str) and values[k] for k in ("id", "predictor", "measure")), "Missing empirical identity")
        number(values["coefficient"])
        require(values["coefficient_unit"] is None or isinstance(values["coefficient_unit"], str) and values["coefficient_unit"], "Invalid coefficient unit")
        if values["p_value"] is not None:
            require(0 <= number(values["p_value"]) <= 1, "P value outside [0,1]")
        if values["interval"] is not None:
            require(isinstance(values["interval"], list) and len(values["interval"]) == 2, "Invalid coefficient interval")
            require(number(values["interval"][0]) <= number(values["interval"][1]), "Reversed coefficient interval")
            require(values["interval_level"] is not None and 0 < number(values["interval_level"]) < 1, "Invalid confidence level")
            values["interval"] = tuple(values["interval"])
        else:
            require(values["interval_level"] is None, "Confidence level without interval")
        require(values["coding"] in {"higher_intake", "binary_label_ambiguous", "reported_scale_unknown"}, "Unsupported coding state")
        require(isinstance(values["evidence_ids"], list) and values["evidence_ids"] and len(set(values["evidence_ids"])) == len(values["evidence_ids"]), "Missing or duplicate empirical evidence")
        values["evidence_ids"] = tuple(values["evidence_ids"])
        return cls(**values)


@dataclass(frozen=True)
class TestPolicy:
    id: str
    context: AnalysisContext
    measure: str
    alpha: str
    comparison: str
    correction: str
    evidence_ids: tuple[str, ...]

    @classmethod
    def parse(cls, data):
        values = dict(strict_fields(cls, data))
        values["context"] = AnalysisContext.parse(values["context"])
        require(isinstance(values["id"], str) and values["id"], "Missing policy identity")
        require(isinstance(values["measure"], str) and values["measure"], "Missing policy measure")
        require(0 < number(values["alpha"]) < 1, "Invalid significance threshold")
        require(values["comparison"] == "lt", "An explicit strict threshold is required")
        require(values["correction"] in {"Bonferroni_reported_rounded", "nominal_reported"}, "Unknown test correction")
        require(isinstance(values["evidence_ids"], list) and values["evidence_ids"], "Policy lacks provenance")
        values["evidence_ids"] = tuple(values["evidence_ids"])
        return cls(**values)


def infer(effect: EffectEstimate, policy: TestPolicy) -> dict[str, Any]:
    """Выводит статистическую сводку только из полной совместной группы входов."""
    base = {"case_id": effect.id, "operator": POLICY["operator"], "input_ids": [effect.id, policy.id],
            "premise_groups": [[effect.id, policy.id]], "evidence_ids": sorted(set(effect.evidence_ids + policy.evidence_ids)),
            "context": asdict(effect.context), "predictor": effect.predictor, "causal": False,
            "future_outcome": False, "invented_effect": None}

    def abstain(reason):
        return {**base, "status": "abstain", "direction": None, "real_world_direction": None, "reason": reason}

    if effect.context != policy.context:
        return abstain("incompatible_context")
    if effect.measure != policy.measure or effect.measure != "unstandardized_linear_coefficient":
        return abstain("unsupported_or_mismatched_measure")
    if effect.p_value is None:
        return abstain("missing_p_value")
    point = number(effect.coefficient)
    if effect.interval is not None and not number(effect.interval[0]) <= point <= number(effect.interval[1]):
        return abstain("coefficient_outside_its_reported_interval")
    significant = number(effect.p_value) < number(policy.alpha)
    if significant and point == 0:
        return abstain("zero_coefficient_with_significant_p_requires_review")
    direction = ("positive" if point > 0 else "negative") if significant else None
    return {**base, "status": "threshold_met" if significant else "threshold_not_met", "direction": direction,
            "real_world_direction": direction if significant and effect.coding == "higher_intake" else None,
            "reason": None, "point_sign": "positive" if point > 0 else "negative" if point < 0 else "zero",
            "coding": effect.coding, "alpha": policy.alpha, "correction": policy.correction,
            "caution": "Threshold failure does not establish absence of an effect" if not significant else
                       "Association on the reported scale; no causal or future-outcome claim"}


def run_cases(cases: list[dict]) -> list[dict]:
    require(isinstance(cases, list) and bool(cases), "Explicit empirical cases required")
    require(all(isinstance(c,dict) and set(c) == {"effect", "policy"} for c in cases), "Expected labels or unknown fields in operator input")
    effects = [EffectEstimate.parse(c["effect"]) for c in cases]
    require(len({e.id for e in effects}) == len(effects), "Duplicate empirical case")
    return [infer(effect, TestPolicy.parse(case["policy"])) for effect, case in zip(effects, cases)]


def nominal_baseline(cases: list[dict]) -> list[dict]:
    """Контроль игнорирует поправку, проверки интервала и совместимость контекста."""
    result = []
    for case in cases:
        effect = EffectEstimate.parse(case["effect"])
        significant = effect.p_value is not None and number(effect.p_value) < Decimal("0.05")
        result.append({"case_id": effect.id, "status": "threshold_met" if significant else "threshold_not_met",
                       "direction": ("positive" if number(effect.coefficient) > 0 else "negative") if significant else None,
                       "reason": None})
    return result


def score(results: list[dict], controls: list[dict]) -> dict:
    require(len({c["case_id"] for c in controls}) == len(controls), "Duplicate holdout")
    require({r["case_id"] for r in results} == {c["case_id"] for c in controls}, "Holdout cases differ")
    by_id = {r["case_id"]: r for r in results}
    rows = []
    for control in controls:
        actual = by_id[control["case_id"]]
        expected = control["expected"]
        matched = all(actual.get(k) == v for k, v in expected.items())
        rows.append({"case_id": control["case_id"], "matched": matched, "kind": control["kind"],
                     "expected": expected, "actual": {k: actual.get(k) for k in expected},
                     "source_claim_relation": control["source_claim_relation"]})
    return {"case_count": len(rows), "matched": sum(r["matched"] for r in rows), "rows": rows,
            "new_scientific_predictions": 0, "independent_success": False}


def case_fingerprint(cases):
    return fingerprint(cases)
