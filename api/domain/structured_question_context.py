"""Явные признаки контекста: нормализация не является доказательством переноса."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from itertools import combinations

from domain.article_maps import fingerprint, require, digest
from domain.qualitative_question_prediction import (
    prepare_observations, fit_qualitative_forecast, learn_rules, qualitative_projection,
    evaluate_qualitative_holdout, IDENTITY,
)
from domain.question_prediction import generate_question_candidates, ForecastQuestion, question_matches
from domain.research_semantics import context_value

VERSION = "structured-question-context-1"
FEATURES = ("age", "dementia_entry", "mci", "baseline_score", "exposure", "outcome", "followup", "adjustments", "model", "alpha", "sample_size")
# Только явно заданные синонимы и точные преобразования единиц.
ALIASES = {"gender": "sex", "apoe4": "apoe_epsilon4", "apoe epsilon4": "apoe_epsilon4", "3mse": "3ms"}
UNITS = {"year": ("year", Decimal(1)), "years": ("year", Decimal(1)), "month": ("year", Decimal(1) / 12),
         "pg/ml": ("pg/ml", Decimal(1)), "ng/l": ("pg/ml", Decimal(1)), "ng/ml": ("pg/ml", Decimal(1000)),
         "dimensionless": ("dimensionless", Decimal(1)), "participant": ("participant", Decimal(1)),
         "mmse_point": ("mmse_point", Decimal(1)), "3ms_point": ("3ms_point", Decimal(1)),
         "summary_point": ("summary_point", Decimal(1)),
         "3ms_point/year": ("3ms_point/year", Decimal(1))}


def canonical_value(value):
    if isinstance(value, dict):
        if set(value) == {"value", "unit"}:
            require(value["unit"] in UNITS, "Unsupported structured unit")
            unit, factor = UNITS[value["unit"]]
            def convert(raw):
                if isinstance(raw, list):
                    require(bool(raw), "Empty structured quantity interval")
                    return [convert(item) for item in raw]
                require(type(raw) in (int, float, str), "Explicit finite structured quantity required")
                try: number = Decimal(str(raw))
                except InvalidOperation: require(False, "Invalid structured quantity")
                require(number.is_finite(), "Finite structured quantity required")
                # Месяцы переводятся в годы делением на 12 без округления множителя.
                number = number / 12 if value["unit"] == "month" else number * factor
                return format(number.normalize(), "f")
            return {"value": convert(value["value"]), "unit": unit}
        return {k: canonical_value(v) for k, v in sorted(value.items())}
    if isinstance(value, list): return [canonical_value(v) for v in value]
    if isinstance(value, str): return ALIASES.get(value.casefold().strip(), value.casefold().strip())
    require(value is None or type(value) in (bool, int, float), "Unsupported structured value")
    if type(value) is float: require(Decimal(str(value)).is_finite(), "Finite structured value required")
    return value


def normalized_features(raw):
    require(set(raw) == set(FEATURES), "Structured feature fields differ")
    result = {}
    for name in FEATURES:
        feature = raw[name]
        require(set(feature) == {"status", "value", "evidence", "note_ru", "note_en"}, "Structured feature contract differs")
        require(feature["status"] in {"known", "not_reported", "not_applicable"}, "Explicit structured status required")
        require((feature["value"] is not None) == (feature["status"] == "known"), "Unknown feature cannot have a presumed value")
        require(bool(feature["evidence"]) and bool(feature["note_ru"]) and bool(feature["note_en"]), "Feature provenance and bilingual review notes required")
        value = canonical_value(feature["value"])
        if name == "adjustments" and feature["status"] == "known":
            require(isinstance(value, list) and all(isinstance(v, str) and v for v in value), "Explicit adjustment set required")
            value = sorted(set(value))
        if name == "age" and feature["status"] == "known":
            require(set(value) == {"minimum", "maximum"}, "Explicit age bounds required")
            lo, hi = value["minimum"], value["maximum"]
            require(isinstance(lo, dict) and lo.get("unit") == "year" and Decimal(lo["value"]) >= 0, "Invalid minimum age")
            require(hi == "unrestricted_by_entry_requirement" or isinstance(hi, dict) and hi.get("unit") == "year" and Decimal(hi["value"]) >= Decimal(lo["value"]), "Invalid maximum age")
        result[name] = {"status": feature["status"], "value": value}
    return result


def compare_features(left, right):
    def incomplete(value):
        if isinstance(value, dict):
            return value.get("status") == "not_reported" or any(incomplete(v) for v in value.values())
        if isinstance(value, list): return any(incomplete(v) for v in value)
        return False
    unknown = [name for name in FEATURES if incomplete(left[name]) or incomplete(right[name])]
    differences = [{"feature": name, "left": left[name], "right": right[name]} for name in FEATURES if name not in unknown and left[name] != right[name]]
    return {"status": "unknown_context" if unknown else "different_context" if differences else "same_structured_applicability",
            "unknown": unknown, "differences": differences,
            "knowledge_equivalence_confirmed": False, "transfer_authorized": not unknown and not differences}


def validate_feature_records(raw, claims, maps, scope, supporting_sources=()):
    require(set(raw) == {"version", "scope", "author", "expert_validated", "records"}, "Structured registry fields differ")
    require(raw["version"] == VERSION and raw["scope"] == scope and raw["author"] == "Codex" and raw["expert_validated"] is False, "Structured registry attribution or scope differs")
    support = {s["id"]: s for s in supporting_sources}
    index = {}
    for record in raw["records"]:
        require(set(record) == {"article_id", "run_id", "source_sha256", "graph_sha256", "claim_id", "claim_sha256", "features"}, "Structured record fields differ")
        key = (record["article_id"], record["claim_id"])
        require(key in claims and key not in index, "Unknown or duplicated structured claim")
        claim, m = claims[key], maps[key[0]]
        require(record["run_id"] == m["run_id"] and record["source_sha256"] == m["source"]["sha256"]
                and record["graph_sha256"] == fingerprint(m["graph"]) and record["claim_sha256"] == fingerprint(claim.to_dict()), "Structured record binding differs")
        for feature in record["features"].values():
            for span in feature["evidence"]:
                require(set(span) == {"source_id", "sha256", "start", "end", "text", "offset_encoding"}, "Structured evidence fields differ")
                source = m["source"] if span["source_id"] == key[0] else support.get(span["source_id"])
                require(source is not None and span["sha256"] == source["sha256"], "Unknown or changed structured evidence source")
                require(digest(source["text"]) == source["sha256"], "Structured evidence content hash differs")
                require(span["offset_encoding"] == "unicode_code_points" and type(span["start"]) is int and type(span["end"]) is int
                        and 0 <= span["start"] < span["end"] <= len(source["text"])
                        and source["text"][span["start"]:span["end"]] == span["text"], "Structured evidence fragment differs")
                if span["source_id"] != key[0]:
                    require(source["available_on"] <= claim.evidence.available_on and source["training"] is False, "Context evidence leaks future or training source")
        index[key] = {"normalized": normalized_features(record["features"]), "record": deepcopy(record)}
    return index


def structured_projection(claim, profile):
    # Оба поля содержат ключ всего явного профиля. Числа остаются в profile и исходной семантике.
    # Смена описания не меняет ключ; ни одно содержательное ограничение не удаляется.
    context = dict(claim.context)
    token = "structured_context:" + fingerprint(profile)
    context["stratum"] = context_value(token)
    context["conditions"] = context_value(token)
    measurements = tuple(sorted(({**m, **canonical_value({"value": m["value"], "unit": m["unit"]})} for m in claim.measurements), key=lambda m: m["name"]))
    return replace(claim, context=context, measurements=measurements)


class StructuredQualitativeEngine:
    """Структурированные признаки меняют сопоставление, сохраняя прежние границы гипотез."""
    def __init__(self, profiles):
        self.profiles = deepcopy(profiles)
        self.analysis_binding = {"workflow_version": "structured-question-workflow-1", "context_version": VERSION,
                                 "context_registry_sha256": fingerprint({"/".join(k): profiles[k] for k in sorted(profiles)})}

    def binding_for(self, claims):
        return fingerprint({"/".join(k): self.profiles[k] for k in sorted(claims) if k in self.profiles})

    def fit(self, claims, episodes, maps, question, policy):
        base = fit_qualitative_forecast(claims, episodes, maps, question, policy)
        observations, _ = prepare_observations(claims, question, policy)
        require(set(observations) <= self.profiles.keys(), "Missing required structured context; no lexical fallback")
        profiles = {k: self.profiles[k]["normalized"] for k in sorted(observations)}
        views = {k: structured_projection(c, profiles[k]) for k, c in observations.items()}
        def context_check(a, b):
            result = compare_features(profiles[a.evidence.article_id, a.claim_id], profiles[b.evidence.article_id, b.claim_id])
            return ["unknown:" + key for key in result["unknown"]] + ["feature:" + d["feature"] for d in result["differences"]]
        literal = {"mode_counts": {m: len(base["modes"][m]) for m in ("semantic", "dependency")}, "diagnostics": deepcopy(base["diagnostics"])}
        for mode in ("semantic", "dependency"):
            rules, diagnostics = learn_rules(claims, views, episodes, maps, question, policy, mode == "dependency", context_check=context_check)
            candidates, bounded = generate_question_candidates(views, rules, question)
            candidates = [c for c in candidates if not set(c["abstracted_context_fields"]) - IDENTITY]
            for c in candidates:
                c["finding"] = c["proposition"]["modality"]
                c["status"] = "structured_qualitative_forecast_hypothesis"
                c["application_features"] = profiles[c["premises"][0]["evidence"]["article_id"], c["premises"][0]["claim_id"]]
                c["numerical_evidence"] = [claims[p["evidence"]["article_id"], p["claim_id"]].to_dict() for p in c["premises"]]
            base["modes"][mode], base["rules"][mode] = candidates, rules
            base["diagnostics"][mode] = {**diagnostics, "bounded_searches": bounded}
        base["structured_context"] = {"version": VERSION, "training_features_sha256": self.binding_for(claims), "profiles": [{"reference": list(k), **self.profiles[k]} for k in sorted(observations)], "literal_comparison": literal}
        return base

    def evaluate(self, sealed, targets):
        result = evaluate_qualitative_holdout(sealed, targets)
        q = ForecastQuestion.parse(sealed["question"])
        from domain.qualitative_question_prediction import QualitativePolicy
        policy = QualitativePolicy.parse(sealed["policy"], q)
        target_views = []
        for c in targets:
            if c.evidence.presentation != "own_result" or not question_matches(c.proposition, q): continue
            projected, _ = qualitative_projection(c, policy)
            if projected:
                key = (c.evidence.article_id, c.claim_id)
                require(key in self.profiles, "Missing heldout context; no lexical fallback")
                target_views.append((c, projected, self.profiles[key]["normalized"]))
        for mode in ("semantic", "dependency"):
            answers = []
            for candidate in sealed["modes"][mode]:
                matches = []
                for raw, view, features in target_views:
                    p = candidate["proposition"]
                    compare = compare_features(candidate["application_features"], features)
                    same_roles = p["predicate"] == view.predicate and p["roles"] == view.roles
                    same_logic = all(p[name] == getattr(view, name) for name in ("negated", "quantifier", "action_status", "logic"))
                    status = "context_mismatch" if not compare["transfer_authorized"] else "participants_or_logic_differ" if not same_roles or not same_logic else "qualitative_agreement" if p["modality"] == view.modality else "different_statistical_finding"
                    matches.append({"target": [raw.evidence.article_id, raw.claim_id], "status": status, "context_comparison": compare})
                agree = any(m["status"] == "qualitative_agreement" for m in matches)
                differ = any(m["status"] == "different_statistical_finding" for m in matches)
                status = "mixed" if agree and differ else "agreement" if agree else "different_finding" if differ else "abstain_or_incompatible"
                answers.append({"id": candidate["id"], "status": status, "matches": matches})
            scored = lambda xs: [a for a in xs if a["status"] in {"agreement", "different_finding", "mixed"}]
            result["modes"][mode] = {"issued_answers": len(answers), "agreements": sum(a["status"] == "agreement" for a in answers), "different_findings": sum(a["status"] == "different_finding" for a in answers), "results": answers, "scorable_answers": len(scored(answers)), "agreement_at_k": {str(k): sum(a["status"] == "agreement" for a in answers[:k]) / len(scored(answers[:k])) if scored(answers[:k]) else None for k in (1, 5, 10)}}
        return result


def structured_matrix(profiles):
    result = []
    for a, b in combinations(profiles, 2):
        result.append({"left": a["reference"], "right": b["reference"], **compare_features(a["normalized"], b["normalized"])})
    return result
