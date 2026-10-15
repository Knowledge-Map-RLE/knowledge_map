"""Качественный результат исследования отделён от числовых свидетельств."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace, field
from decimal import Decimal, InvalidOperation

from domain.article_maps import fingerprint, require
from domain.question_prediction import (
    ForecastQuestion, eligible, generate_question_candidates, graph_supported,
    make_template, question_matches,
)
from domain.research_semantics import context_value

VERSION = "qualitative-question-predictor-2"
LABELS = ("positive_association", "inverse_association", "not_statistically_detected", "insufficient_data")
IDENTITY = {"study", "cohort", "sample"}
POLICY_FIELDS = {"version", "question_id", "min_families", "measurement_rules", "measure_groups", "statistical_fields", "constraint_fields"}


@dataclass(frozen=True)
class QualitativePolicy:
    version: str
    question_id: str
    min_families: int
    measurement_rules: tuple[dict, ...]
    measure_groups: dict
    statistical_fields: tuple[str, ...]
    constraint_fields: tuple[str, ...]
    symbolic_directions: dict = field(default_factory=dict)

    @classmethod
    def parse(cls, raw, question):
        require(set(raw) in (POLICY_FIELDS, POLICY_FIELDS | {"symbolic_directions"}), "Qualitative policy fields differ")
        require(raw["question_id"] == question.question_id, "Qualitative policy belongs to another question")
        require(isinstance(raw["version"], str) and bool(raw["version"]), "Policy version required")
        require(type(raw["min_families"]) is int and raw["min_families"] >= 2, "Two independent families required")
        require(isinstance(raw["measure_groups"], dict) and all(isinstance(k, str) and isinstance(v, str) and k and v for k, v in raw["measure_groups"].items()), "Explicit qualitative measure groups required")
        rules = raw["measurement_rules"]
        require(isinstance(rules, list), "Explicit direction rules required")
        require(all(set(r) == {"name", "unit", "higher_means_decline"} and isinstance(r["name"], str) and isinstance(r["unit"], str)
                    and type(r["higher_means_decline"]) is bool for r in rules), "Invalid direction rule")
        require(len({(r["name"], r["unit"]) for r in rules}) == len(rules), "Duplicate direction rule")
        for key in ("statistical_fields", "constraint_fields"):
            require(isinstance(raw[key], list) and all(isinstance(v, str) and v for v in raw[key]) and len(set(raw[key])) == len(raw[key]), "Invalid measurement field list")
        require(not set(raw["statistical_fields"]) & set(raw["constraint_fields"]), "Evidence and applicability fields overlap")
        require(all(r["name"] in raw["statistical_fields"] for r in rules), "Direction estimate must remain statistical evidence")
        symbolic = raw.get("symbolic_directions", {})
        require(isinstance(symbolic, dict), "Explicit symbolic directions required")
        require(all(isinstance(name, str) and name in raw["statistical_fields"] and isinstance(values, dict) and values
                    and all(isinstance(value, str) and value and label in LABELS[:2] for value, label in values.items())
                    for name, values in symbolic.items()), "Invalid symbolic direction rule")
        require(not set(symbolic).intersection(r["name"] for r in rules), "Symbolic and numeric direction rules overlap")
        return cls(raw["version"], raw["question_id"], raw["min_families"], tuple(rules), dict(raw["measure_groups"]), tuple(raw["statistical_fields"]), tuple(raw["constraint_fields"]), symbolic)

    def to_dict(self):
        return {**asdict(self), "measurement_rules": list(self.measurement_rules),
                "statistical_fields": list(self.statistical_fields), "constraint_fields": list(self.constraint_fields)}


def finding_label(claim, policy):
    """Статистический нулевой результат не является отрицанием биологической связи."""
    if claim.negated or claim.action_status not in (None, "performed") or claim.unresolved or claim.logic != "single":
        return "insufficient_data", "unsupported_negation_action_or_logic"
    if claim.modality == "not statistically detected":
        return "not_statistically_detected", "explicit_source_statistical_modality"
    if claim.modality != "statistically detected":
        return "insufficient_data", "statistical_detection_not_explicit"
    directions = set()
    rules = {(r["name"], r["unit"]): r for r in policy.measurement_rules}
    for measurement in claim.measurements:
        if measurement["name"] in policy.symbolic_directions:
            declared = policy.symbolic_directions[measurement["name"]].get(str(measurement["value"])) if measurement["unit"] == "categorical" else None
            if declared:
                directions.add(declared)
            else:
                return "insufficient_data", "invalid_symbolic_direction"
            continue
        rule = rules.get((measurement["name"], measurement["unit"]))
        if not rule:
            continue
        try:
            estimate = Decimal(str(measurement["value"]))
        except InvalidOperation:
            continue
        if not estimate.is_finite():
            continue
        reference = Decimal(1) if measurement["name"] in {"hazard ratio", "odds ratio", "risk ratio"} else Decimal(0)
        if estimate == reference:
            continue
        more_decline = (estimate > reference) == rule["higher_means_decline"]
        directions.add("positive_association" if more_decline else "inverse_association")
    if len(directions) != 1:
        return "insufficient_data", "direction_missing_or_conflicting"
    return directions.pop(), "explicit_statistical_detection_with_declared_measure_orientation"


def qualitative_projection(claim, policy):
    label, reason = finding_label(claim, policy)
    unknown_fields = sorted({m["name"] for m in claim.measurements} - set(policy.statistical_fields) - set(policy.constraint_fields))
    measure = claim.context.get("measure")
    if not eligible(claim) or label == "insufficient_data" or unknown_fields or not measure or measure["status"] != "known" or measure["value"] not in policy.measure_groups:
        return None, {"label": label, "reason": "unclassified_measurements" if unknown_fields else "unresolved_applicability_or_measure" if not eligible(claim) or not measure or measure["value"] not in policy.measure_groups else reason,
                      "unclassified_fields": unknown_fields}
    # Числа экспозиции, пороги и длительность остаются условиями применения.
    # Только оценки результата, ДИ и p исключены из прогнозируемой части.
    context = dict(claim.context)
    context["measure"] = context_value(policy.measure_groups[measure["value"]])
    constraints = tuple(m for m in claim.measurements if m["name"] in policy.constraint_fields)
    projected = replace(claim, modality=label, context=context, measurements=constraints)
    return projected, {"label": label, "reason": reason, "unclassified_fields": [],
                       "source_context": claim.context, "source_measurements": claim.measurements,
                       "identity_fields_excluded_from_transfer_checks": sorted(IDENTITY & claim.context.keys()),
                       "measure_group": policy.measure_groups[measure["value"]]}


def applicability_difference(left, right):
    differences = ["context:" + key for key in sorted((left.context.keys() | right.context.keys()) - IDENTITY) if left.context.get(key) != right.context.get(key)]
    a, b = {m["name"]: m for m in left.measurements}, {m["name"]: m for m in right.measurements}
    differences += ["constraint:" + key for key in sorted(a.keys() | b.keys()) if a.get(key) != b.get(key)]
    for key in ("quantifier", "negated", "action_status", "logic"):
        if getattr(left, key) != getattr(right, key):
            differences.append(key)
    return differences


def prepare_observations(claims, question, policy):
    projected, rows = {}, []
    for key, claim in sorted(claims.items()):
        require(claim.evidence.available_on <= question.cutoff, "Training source is later than cutoff")
        if claim.evidence.presentation != "own_result" or not claim.evidence.family or not question_matches(claim.proposition, question):
            continue
        observation, diagnostic = qualitative_projection(claim, policy)
        rows.append({"reference": list(key), "original": claim.to_dict(), "projected": observation.to_dict() if observation else None,
                     "diagnostic": diagnostic})
        if observation:
            projected[key] = observation
    return projected, rows


def learn_rules(originals, observations, episodes, maps, question, policy, graph_mode=False, context_check=None):
    grouped, rejected = {}, []
    require(len({e["id"] for e in episodes}) == len(episodes), "Duplicate historical episode")
    for episode in sorted(episodes, key=lambda e: e["id"]):
        require(set(episode) <= {"id", "premises", "conclusion", "transition_id", "note_ru"}, "Unknown historical episode field")
        require(1 <= len(episode["premises"]) <= 3, "Invalid historical premise count")
        refs = [tuple(r) for r in [*episode["premises"], episode["conclusion"]]]
        require(all(r in originals for r in refs), "Unknown historical claim")
        original_body, original_head = [originals[r] for r in refs[:-1]], originals[refs[-1]]
        require(all(c.evidence.available_on < original_head.evidence.available_on <= question.cutoff for c in original_body), "Historical episode leaks future or same-publication result")
        if not all(r in observations for r in refs):
            rejected.append({"episode": episode["id"], "reason": "question_or_qualitative_applicability_failed"}); continue
        if any(c.evidence.family == original_head.evidence.family for c in original_body):
            rejected.append({"episode": episode["id"], "reason": "same_study_family"}); continue
        body, head = [observations[r] for r in refs[:-1]], observations[refs[-1]]
        if context_check:
            reasons = sorted({reason for c in body for reason in context_check(c, head)})
            if reasons:
                rejected.append({"episode": episode["id"], "reason": "structured_context_transfer_failed", "differences": reasons}); continue
        differences = sorted({d for c in body for d in applicability_difference(c, head)})
        if differences:
            rejected.append({"episode": episode["id"], "reason": "unsupported_context_transfer", "differences": differences}); continue
        if graph_mode and not graph_supported(episode, original_body, original_head, maps, originals):
            rejected.append({"episode": episode["id"], "reason": "joint_dependency_not_supported"}); continue
        template = make_template(body, head)
        if template is None:
            rejected.append({"episode": episode["id"], "reason": "unbound_applicability_constraint"}); continue
        key = fingerprint(template)
        rule = grouped.setdefault(key, {"id": key, "template": template, "families": set(), "episodes": [], "outcomes": []})
        rule["families"].add(head.evidence.family)
        rule["episodes"].append(episode["id"])
        rule["outcomes"].append({"article_id": head.evidence.article_id, "claim_id": head.claim_id, "family": head.evidence.family,
                                  "available_on": head.evidence.available_on})
    accepted = []
    for rule in sorted(grouped.values(), key=lambda r: r["id"]):
        support = len(rule["families"])
        if support < policy.min_families:
            rejected.append({"rule_id": rule["id"], "reason": "insufficient_independent_families", "support": support}); continue
        core = {**rule["template"], "conclusion": {**rule["template"]["conclusion"], "modality": "qualitative_result"}}
        trials = set()
        for other in grouped.values():
            other_core = {**other["template"], "conclusion": {**other["template"]["conclusion"], "modality": "qualitative_result"}}
            if core == other_core:
                trials.update(other["families"])
        accepted.append({**rule, "families": sorted(rule["families"]), "support": support, "tested_families": len(trials),
                         "ranking_score": (support + 1) / (len(trials) + len(LABELS) - 1), "status": "qualitative_statistical_hypothesis_template"})
    return sorted(accepted, key=lambda r: (-r["ranking_score"], r["id"])), {"episodes": len(episodes), "candidate_templates": len(grouped),
                                                                       "accepted_rules": len(accepted), "rejected": rejected}


def fit_qualitative_forecast(claims, episodes, maps, question, policy):
    observations, rows = prepare_observations(claims, question, policy)
    modes, rules, diagnostics = {}, {}, {}
    for mode in ("semantic", "dependency"):
        learned, stats = learn_rules(claims, observations, episodes, maps, question, policy, mode == "dependency")
        candidates, bounded = generate_question_candidates(observations, learned, question)
        # Фаза исследования не относится к разрешённой абстракции идентификаторов.
        candidates = [c for c in candidates if not set(c["abstracted_context_fields"]) - IDENTITY]
        for candidate in candidates:
            candidate["finding"] = candidate["proposition"]["modality"]
            candidate["numerical_evidence"] = [claims[(c["evidence"]["article_id"], c["claim_id"])].to_dict() for c in candidate["premises"]]
            candidate["status"] = "qualitative_forecast_hypothesis"
        modes[mode], rules[mode], diagnostics[mode] = candidates, learned, {**stats, "bounded_searches": bounded}
    modes["known_union"] = [{"id": fingerprint(row["reference"]), "status": "known_source_knowledge", "finding": row["diagnostic"]["label"],
                             "original": row["original"], "projection": row["projected"]} for row in rows if row["projected"]]
    frequency = {}
    for row in rows:
        if not row["projected"]: continue
        raw_proposition = row["projected"]["proposition"]
        proposition = {**raw_proposition, "context": {k: v for k, v in raw_proposition["context"].items() if k not in IDENTITY}}
        key = fingerprint(proposition)
        item = frequency.setdefault(key, {"id": key, "status": "descriptive_frequency_baseline", "finding": row["diagnostic"]["label"],
                                         "proposition": proposition, "families": set(), "evidence": []})
        item["families"].add(row["original"]["evidence"]["family"])
        item["evidence"].append(row["original"])
    modes["frequency"] = [{**r, "families": sorted(r["families"]), "support": len(r["families"])} for r in sorted(frequency.values(), key=lambda r: (-len(r["families"]), r["id"]))][:question.limit]
    # Обзор ответа на вопрос описывает корпус, но не объявляет разные контексты эквивалентными.
    summary = []
    for label in LABELS:
        found = [r for r in rows if r["projected"] and r["diagnostic"]["label"] == label]
        summary.append({"finding": label, "claim_count": len(found), "families": sorted({r["original"]["evidence"]["family"] for r in found}),
                        "references": [r["reference"] for r in found], "status": "descriptive_question_scope_only"})
    return {"predictor_version": VERSION, "policy": policy.to_dict(), "question": asdict(question), "modes": modes, "rules": rules,
            "diagnostics": diagnostics, "observations": rows, "question_scope_summary": summary, "claim_count": len(claims),
            "eligible_question_claim_count": len(observations), "model_calls": 0, "expert_validated": False,
            "future_target_read": False, "scientific_predictive_success_measured": False}


def family_time_plan(registry, question):
    rows = []
    for family in sorted({r["family"] for r in registry.values() if r.get("family")}):
        heldout = sorted(a for a, r in registry.items() if r.get("family") == family)
        first_date = min(registry[a]["available_on"] for a in heldout)
        training = sorted(a for a, r in registry.items() if r.get("family") != family and r["available_on"] < first_date)
        rows.append({"family": family, "first_publication": first_date, "training": training, "heldout": heldout,
                     "status": "retrospective_diagnostic_previously_read_corpus"})
    return rows


def evaluate_qualitative_holdout(sealed, targets):
    question = ForecastQuestion.parse(sealed["question"])
    policy = QualitativePolicy.parse(sealed["policy"], question)
    require(all(question.cutoff < c.evidence.available_on <= question.horizon_end for c in targets), "Retrospective target outside forecast horizon")
    training = set(sealed["binding"]["training_families"])
    require(not training.intersection(c.evidence.family for c in targets), "Heldout study family leaked into training")
    relevant = {}
    for claim in targets:
        if question_matches(claim.proposition, question) and claim.evidence.presentation == "own_result":
            projected, _ = qualitative_projection(claim, policy)
            if projected: relevant[(claim.evidence.article_id, claim.claim_id)] = projected
    result = {}
    for mode, candidates in sealed["modes"].items():
        predictions = []
        # Исходные факты и частотная база оцениваются отдельно от новых гипотез.
        for item in candidates:
            proposition = item.get("proposition") or (item.get("projection") or {}).get("proposition")
            if not proposition: continue
            matches = []
            for ref, target in sorted(relevant.items()):
                if proposition["predicate"] != target.predicate or proposition["roles"] != target.roles:
                    status = "participants_differ"
                else:
                    pseudo = replace(target, context=proposition["context"], measurements=tuple(proposition["measurements"]),
                                     quantifier=proposition["quantifier"], negated=proposition["negated"], action_status=proposition["action_status"], logic=proposition["logic"])
                    differences = applicability_difference(pseudo, target)
                    status = "context_mismatch" if differences else "qualitative_agreement" if proposition["modality"] == target.modality else "different_statistical_finding"
                matches.append({"target": list(ref), "status": status})
            agreements = any(m["status"] == "qualitative_agreement" for m in matches)
            different = any(m["status"] == "different_statistical_finding" for m in matches)
            status = "mixed" if agreements and different else "agreement" if agreements else "different_finding" if different else "abstain_or_incompatible"
            predictions.append({"id": item["id"], "status": status, "matches": matches})
        result[mode] = {"issued_answers": len(candidates), "agreements": sum(r["status"] == "agreement" for r in predictions),
                        "different_findings": sum(r["status"] == "different_finding" for r in predictions), "results": predictions,
                        "scorable_answers": sum(r["status"] in {"agreement", "different_finding", "mixed"} for r in predictions),
                        "agreement_at_k": {str(k): sum(r["status"] == "agreement" for r in predictions[:k]) / sum(r["status"] in {"agreement", "different_finding", "mixed"} for r in predictions[:k])
                                           if any(r["status"] in {"agreement", "different_finding", "mixed"} for r in predictions[:k]) else None for k in (1, 5, 10)}}
    return {"modes": result, "eligible_target_claims": len(relevant), "absence_is_not_refutation": True,
            "different_statistical_findings_are_not_logical_contradictions": True, "retrospective_only": True, "model_calls": 0}
