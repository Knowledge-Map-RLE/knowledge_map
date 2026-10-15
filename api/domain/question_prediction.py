"""Исторические символьные шаблоны и прогноз по явно заданному научному вопросу."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from itertools import product, permutations

from domain.article_maps import fingerprint, require
from domain.research_semantics import (SemanticClaim, Evidence, context_difference, validate_context, valid_date,
                                       compare_claims, unknown_measurement_units)
from domain.comparison_normalization import canonical
from domain.research_diagnostics import eligibility_issues, eligibility_summary

VERSION = "question-predictor-4"
LIMITS = {"min_families": 2, "max_premises": 3, "max_candidates": 20, "max_bindings": 1000}
IDENTITY_CONTEXT = {"study", "cohort", "sample", "phase", "time"}


@dataclass(frozen=True)
class ForecastQuestion:
    question_id: str
    text_en: str
    text_ru: str
    predicate: str
    roles: dict
    context: dict
    cutoff: str
    horizon_end: str
    limit: int = 20

    @classmethod
    def parse(cls, raw):
        require(set(raw) == set(cls.__dataclass_fields__), "Question fields differ")
        for field in ("question_id", "text_en", "text_ru", "predicate"):
            require(isinstance(raw[field], str) and bool(raw[field].strip()), "Question text is required")
        valid_date(raw["cutoff"]); valid_date(raw["horizon_end"])
        require(raw["cutoff"] < raw["horizon_end"], "Prediction horizon must follow cutoff")
        require(type(raw["limit"]) is int and 1 <= raw["limit"] <= LIMITS["max_candidates"], "Invalid prediction budget")
        require(isinstance(raw["roles"], dict) and len(raw["roles"]) >= 2
                and all(isinstance(v, str) and bool(v) for v in raw["roles"].values()), "Explicit question participants required")
        validate_context(raw["context"])
        require(raw["context"] and all(v["status"] != "not_reported" for v in raw["context"].values()), "Question applicability must be explicit")
        return cls(**{**raw, "predicate": canonical(raw["predicate"], "predicates"),
                       "roles": {canonical(k, "roles"): canonical(v, "concepts") for k, v in raw["roles"].items()}})


def eligible(claim):
    return not eligibility_issues(claim)


def _template_for_order(body, head):
    participants, measurements, local = {}, {}, {}

    def variable(value, table, kind):
        key = fingerprint(value)
        if key not in table:
            table[key] = {"var": kind + str(len(table)), "type": kind}
        return table[key]

    def atom(claim):
        context = {}
        for key, value in sorted(claim.context.items()):
            if key in {"study", "cohort", "sample", "phase", "time"} and value["status"] == "known":
                context[key] = {"status": "known", "value": variable(value["value"], local, "context")}
            else:
                context[key] = value
        return {"predicate": claim.predicate,
                "roles": {r: variable(v, participants, "participant") for r, v in sorted(claim.roles.items())},
                "negated": claim.negated, "quantifier": claim.quantifier, "modality": claim.modality,
                "context": context, "action_status": claim.action_status, "logic": claim.logic,
                "measurements": [{**m, "value": variable(m["value"], measurements, "measurement")} for m in claim.measurements]}

    premises = [atom(c) for c in body]
    bound = {v["var"] for table in (participants, measurements, local) for v in table.values()}
    conclusion = atom(head)
    unbound = variables(conclusion) - bound
    # Новое исследование имеет собственные идентификаторы. Они обозначают область будущей
    # гипотезы и не превращаются в придуманные факты о конкретной когорте или выборке.
    future_context = {key: value["value"] for key, value in conclusion["context"].items()
                      if key in IDENTITY_CONTEXT and isinstance(value["value"], dict) and value["value"].get("var") in unbound}
    allowed = {v["var"] for v in future_context.values()}
    if not unbound <= allowed:
        return None
    return {"premises": premises, "conclusion": conclusion, "future_context": future_context}


def make_template(body, head):
    require(1 <= len(body) <= LIMITS["max_premises"], "Invalid template premise count")
    # Для не более трёх предпосылок перебор устраняет зависимость шаблона от локальных имён и порядка входов.
    variants = [t for order in permutations(body) if (t := _template_for_order(order, head)) is not None]
    return min(variants, key=fingerprint) if variants else None


def variables(value):
    if isinstance(value, dict):
        return {value["var"]} if set(value) == {"var", "type"} else set().union(*(variables(v) for v in value.values()))
    if isinstance(value, (list, tuple)):
        return set().union(*(variables(v) for v in value)) if value else set()
    return set()


def bind(pattern, value, assignment):
    if isinstance(pattern, dict):
        if set(pattern) == {"var", "type"}:
            key = pattern["var"]
            if key in assignment and assignment[key] != value:
                return None
            return {**assignment, key: value}
        if not isinstance(value, dict) or pattern.keys() != value.keys():
            return None
        for key in sorted(pattern):
            assignment = bind(pattern[key], value[key], assignment)
            if assignment is None:
                return None
        return assignment
    if isinstance(pattern, (list, tuple)):
        if not isinstance(value, (list, tuple)) or len(pattern) != len(value):
            return None
        for a, b in zip(pattern, value):
            assignment = bind(a, b, assignment)
            if assignment is None:
                return None
        return assignment
    return assignment if pattern == value else None


def instantiate(value, assignment):
    if isinstance(value, dict):
        if set(value) == {"var", "type"}:
            require(value["var"] in assignment, "Unbound conclusion variable")
            return assignment[value["var"]]
        return {k: instantiate(v, assignment) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [instantiate(v, assignment) for v in value]
    return value


def graph_supported(episode, body, head, maps, claims):
    if not episode.get("transition_id"):
        return False
    graph = maps[head.evidence.article_id]["graph"]
    transition = next((t for t in graph["transitions"] if t["id"] == episode["transition_id"]), None)
    require(transition is not None, "Historical transition missing")
    nodes = {n["id"]: n["knowledge_id"] for n in graph["nodes"]}
    require(nodes[transition["target"]] == head.knowledge_id, "Historical transition targets another result")
    incoming = {nodes[s] for s in transition["sources"]}
    local_claims = [c for c in claims.values() if c.evidence.article_id == head.evidence.article_id and c.knowledge_id in incoming]
    # Все совместные входы обязательны; альтернативные группы не смешиваются.
    return (incoming == {c.knowledge_id for c in local_claims}
            and all(any(compare_claims(a, b)["relation"] == "equivalent" for b in local_claims) for a in body)
            and all(any(compare_claims(a, b)["relation"] == "equivalent" for a in body) for b in local_claims))


def learn_temporal_rules(claims, episodes, maps, cutoff, graph_mode=False):
    grouped, rejected = {}, []
    for episode in episodes:
        require(set(episode) <= {"id", "premises", "conclusion", "transition_id", "note_ru"}, "Unknown episode field")
        require(1 <= len(episode["premises"]) <= LIMITS["max_premises"], "Historical premise count differs")
        refs = [*episode["premises"], episode["conclusion"]]
        require(all(tuple(r) in claims for r in refs), "Unknown historical claim")
        body = [claims[tuple(r)] for r in episode["premises"]]
        head = claims[tuple(episode["conclusion"])]
        require(all(c.evidence.available_on < head.evidence.available_on <= cutoff for c in body), "Historical episode leaks future or same-publication result")
        if not all(eligible(c) for c in [*body, head]):
            rejected.append({"episode": episode["id"], "reason": "unresolved_context_or_logic"}); continue
        if head.evidence.presentation != "own_result" or not head.evidence.family:
            rejected.append({"episode": episode["id"], "reason": "independent_empirical_result_missing"}); continue
        if graph_mode and not graph_supported(episode, body, head, maps, claims):
            rejected.append({"episode": episode["id"], "reason": "joint_dependency_not_supported"}); continue
        template = make_template(body, head)
        if template is None:
            rejected.append({"episode": episode["id"], "reason": "unbound_conclusion"}); continue
        key = fingerprint(template)
        rule = grouped.setdefault(key, {"id": key, "template": template, "families": set(), "episodes": [], "outcomes": []})
        rule["families"].add(head.evidence.family)
        rule["episodes"].append(episode["id"])
        rule["outcomes"].append({"article_id": head.evidence.article_id, "claim_id": head.claim_id,
                                  "available_on": head.evidence.available_on, "family": head.evidence.family})
    rules = []
    for rule in grouped.values():
        support = len(rule["families"])
        if support < LIMITS["min_families"]:
            rejected.append({"rule_id": rule["id"], "reason": "insufficient_independent_families", "support": support}); continue
        # В знаменатель входит явно проведённая проверка той же связи. Необнаруженная
        # статистическая связь сохраняет собственную модальность и не становится отрицанием.
        core = trial_template(rule["template"])
        trials = set()
        for other in grouped.values():
            other_core = trial_template(other["template"])
            if core == other_core:
                trials.update(other["families"])
        rules.append({**rule, "families": sorted(rule["families"]), "support": support, "tested_families": len(trials),
                      "ranking_score": (support + 1) / (len(trials) + 2), "status": "statistical_hypothesis_template"})
    return sorted(rules, key=lambda r: (-r["ranking_score"], -r["support"], r["id"])), {
        "episodes": len(episodes), "candidate_templates": len(grouped), "accepted_rules": len(rules), "rejected": rejected}


def trial_template(template):
    head = {**template["conclusion"], "negated": False}
    if head["modality"] in {"statistically detected", "not statistically detected"}:
        head["modality"] = "empirical statistical association test"
    return {**template, "conclusion": head}


def question_matches(proposition, question):
    if proposition["predicate"] != question.predicate or proposition["roles"] != question.roles:
        return False
    # Вопрос задаёт область гипотезы; идентификаторы отдельных исследований не становятся тождественными фактами.
    selected = {k: proposition["context"].get(k, {"status": "not_reported", "value": None}) for k in question.context}
    conflicts, unknown = context_difference(selected, question.context)
    return not conflicts and not unknown


def hypothesis_scope(proposition, question):
    removed = sorted(IDENTITY_CONTEXT.intersection(proposition["context"]) - question.context.keys())
    return {**proposition, "context": {k: v for k, v in proposition["context"].items() if k not in removed}}, removed


def generate_question_candidates(claims, rules, question):
    candidates, bounded = {}, 0
    available = [c for c in claims.values() if eligible(c) and c.evidence.available_on <= question.cutoff]
    for rule in rules:
        head = rule["template"]["conclusion"]
        if head["predicate"] != question.predicate or head["roles"].keys() != question.roles.keys():
            continue
        buckets = [[c for c in available if c.predicate == p["predicate"]] for p in rule["template"]["premises"]]
        for index, body in enumerate(product(*buckets)):
            if index >= LIMITS["max_bindings"]:
                bounded += 1; break
            if len({(c.evidence.article_id, c.claim_id) for c in body}) != len(body):
                continue
            assignment = {}
            for template, claim in zip(rule["template"]["premises"], body):
                assignment = bind(template, claim.proposition, assignment)
                if assignment is None:
                    break
            if assignment is None:
                continue
            head_context = dict(head["context"])
            unbound_context = []
            for key, variable in rule["template"].get("future_context", {}).items():
                value = question.context.get(key)
                if value is None:
                    # Общий вопрос не задаёт календарь наблюдения. Не выдаём неизвестное будущее время за конкретное.
                    head_context.pop(key)
                    unbound_context.append(key)
                    continue
                if value["status"] != "known":
                    assignment = None; break
                assignment[variable["var"]] = value["value"]
            if assignment is None:
                continue
            proposition = instantiate({**head, "context": head_context}, assignment)
            if not question_matches(proposition, question):
                continue
            concrete_context = proposition["context"]
            proposition, abstracted = hypothesis_scope(proposition, question)
            abstracted = sorted(set(abstracted + unbound_context))
            fact_id = fingerprint(proposition)
            if any(c.fact_id == fact_id for c in available):
                continue
            known_core = any(c.predicate == proposition["predicate"] and c.roles == proposition["roles"]
                             and c.negated == proposition["negated"] for c in available)
            item = {"id": fact_id, "status": "forecast_hypothesis", "proposition": proposition,
                    "scope_kind": "generalized_question_hypothesis", "application_context": concrete_context,
                    "abstracted_context_fields": abstracted,
                    "unbound_context_fields": unbound_context,
                    "novelty": "known_relation_new_context" if known_core else "new_relation_in_input_corpus",
                    "rule_id": rule["id"], "support": rule["support"], "tested_families": rule["tested_families"],
                    "ranking_score": rule["ranking_score"], "premises": [c.to_dict() for c in body],
                    "historical_outcomes": rule["outcomes"]}
            if fact_id not in candidates or candidates[fact_id]["ranking_score"] < item["ranking_score"]:
                candidates[fact_id] = item
    return sorted(candidates.values(), key=lambda c: (-c["ranking_score"], -c["support"], c["id"]))[:question.limit], bounded


def fit_question_forecast(claims, episodes, maps, question):
    require(all(c.evidence.available_on <= question.cutoff for c in claims.values()), "Training source is later than cutoff")
    modes, diagnostics, rules = {}, {}, {}
    for mode in ("semantic", "dependency"):
        learned, stats = learn_temporal_rules(claims, episodes, maps, question.cutoff, mode == "dependency")
        candidates, bounded = generate_question_candidates(claims, learned, question)
        modes[mode], rules[mode], diagnostics[mode] = candidates, learned, {**stats, "bounded_searches": bounded, "candidates": len(candidates)}
    modes["known_union"] = [{"id": c.fact_id, "status": "known_source_knowledge", "proposition": c.proposition,
                            "evidence": asdict(c.evidence)} for c in claims.values() if question_matches(c.proposition, question)]
    # Частотный baseline не является автоматическим запасным предиктором.
    frequency = {}
    for c in claims.values():
        if c.evidence.presentation == "own_result" and c.evidence.family and eligible(c) and question_matches(c.proposition, question):
            proposition, abstracted = hypothesis_scope(c.proposition, question)
            signature = fingerprint(proposition)
            row = frequency.setdefault(signature, {"id": signature, "status": "frequency_baseline",
                "proposition": proposition, "families": set(), "scope_kind": "generalized_question_hypothesis",
                "abstracted_context_fields": abstracted, "evidence": []})
            row["families"].add(c.evidence.family)
            row["evidence"].append(c.to_dict())
    modes["frequency"] = [{**r, "families": sorted(r["families"]), "support": len(r["families"])}
                          for r in sorted(frequency.values(), key=lambda r: (-len(r["families"]), r["id"]))][:question.limit]
    return {"predictor_version": VERSION, "question": asdict(question), "limits": LIMITS, "modes": modes,
            "rules": rules, "diagnostics": diagnostics, "claim_count": len(claims),
            "eligible_claim_count": sum(eligible(c) for c in claims.values()),
            "eligibility": eligibility_summary(claims.values()),
            "learning_status": "ready" if rules["semantic"] else "not_ready",
            "evidence_diagnostics": {"presentations": {kind: sum(c.evidence.presentation == kind for c in claims.values())
                for kind in sorted({c.evidence.presentation for c in claims.values()})},
                "eligible_empirical_families": sorted({c.evidence.family for c in claims.values()
                    if eligible(c) and c.evidence.presentation == "own_result" and c.evidence.family}),
                "historical_episode_count": len(episodes)},
            "model_calls": 0, "needs_expert_review": True}


def evaluate_question_forecast(sealed, targets):
    question = ForecastQuestion.parse(sealed["question"])
    require(targets and all(question.cutoff < c.evidence.available_on <= question.horizon_end for c in targets), "Target is outside forecast horizon")
    relevant = [c for c in targets if c.predicate == question.predicate and c.roles == question.roles]
    modes = {}
    for mode, candidates in sealed["modes"].items():
        rows = []
        for item in candidates:
            p = item["proposition"]
            claim = SemanticClaim(item["id"], "forecast", p["predicate"], p["roles"], p["negated"], p["quantifier"], p["modality"],
                p["context"], tuple(p["measurements"]), p["action_status"], p["logic"], question.text_en,
                Evidence("forecast", sealed["run_id"], "", question.cutoff, None, "hypothesis", ()))
            from dataclasses import replace
            matches = []
            for t in relevant:
                scoped = t
                if item.get("scope_kind") == "generalized_question_hypothesis":
                    # Оценивается сформулированная гипотеза; конкретное свидетельство остаётся в полном виде.
                    target_p, _ = hypothesis_scope(t.proposition, question)
                    scoped = replace(t, context=target_p["context"])
                matches.append({"target": t.to_dict(), "scope_kind": item.get("scope_kind", "concrete_fact"),
                                **compare_claims(claim, scoped)})
            confirmed = [m for m in matches if m["relation"] == "equivalent"]
            contradicted = [m for m in matches if m["relation"] == "contradiction"]
            status = "mixed_evidence" if confirmed and contradicted else "confirmed" if confirmed else "contradicted" if contradicted else "unresolved"
            rows.append({"candidate_id": item["id"], "status": status, "matches": matches})
        modes[mode] = {"candidate_count": len(rows), "confirmed": sum(r["status"] == "confirmed" for r in rows),
                       "contradicted": sum(r["status"] == "contradicted" for r in rows),
                       "unresolved": sum(r["status"] == "unresolved" for r in rows), "results": rows,
                       "confirmation_at_k": {str(k): sum(r["status"] == "confirmed" for r in rows[:k]) / len(rows[:k]) if rows[:k] else None for k in (1, 5, 10, 20)}}
    return {"modes": modes, "relevant_target_claims": len(relevant), "absence_is_not_refutation": True,
            "needs_expert_review": True, "model_calls": 0}
