"""Ограниченный свободный прогноз: аналогия не объявляется дедукцией."""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, replace

from domain.article_maps import fingerprint, require
from domain.development_prediction import project_sources, fit_predict, candidate_statement
from domain.reference_prediction import Atom
from domain.comparison_normalization import normalize

VERSION = "bounded-free-forecast-3"
LIMITS = {"candidate_limit": 20, "max_analogy_combinations": 100000,
          "min_template_families": 2, "max_premises": 3}
POLICY = {
    "question": None,
    "topic": "Aging, cognitive impairment and related mechanisms in the explicit source corpus",
    "operators": ["source_supported_template", "single_role_analogy"],
    "analogy": "P(a,x) and P(b,x) and Q(a,y) suggest testing Q(b,y); not entailment; replace only a non-outcome role, and require distinct canonical knowledge blocks for all premises",
    "constraints": "Exact scope, polarity, status and role signature; no numeric prediction; no cohort substitution",
    "novelty": "Exclude known propositions, association inverses, and explicit source contradictions",
    "ranking": "Source provenance-family count, premise count, deterministic content hash; no target features",
    "success": "At least one novel candidate strictly equivalent to a target statement; prior-known target is debugging only",
    "unknown_context": "Cannot confirm equivalence",
    "baselines": ["known_union_top20", "frequency_top20"],
    "budget": "One pooled list of at most 20 candidates, no replacement after evaluation",
}


def semantic_key(atom):
    """Обратная запись симметричной ассоциации не является новым знанием."""
    roles = atom.roles
    if atom.predicate in {"associated with", "correlated with"} and len(roles) == 2:
        roles = tuple(("participant", term) for term in sorted(term for _, term in roles))
    return fingerprint({**asdict(atom), "roles": roles})


def numeric(value):
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        return True
    if isinstance(value, str):
        return bool(re.search(r"\d", value))
    if isinstance(value, dict):
        return any(numeric(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(numeric(v) for v in value)
    return False


def replaceable(role, term):
    return (isinstance(term, str) and not term.startswith("knowledge:")
            and role not in {"sample", "cohort", "participants", "study group", "patient group", "control group"}
            and not re.search(r"\b(?:patients?|participants?|subjects?|cohort|phase|study sample)\b", term))


def already_represented(atom, records):
    """Утверждение с меньшим количеством числовых подробностей не считается новым."""
    proposed = json.loads(atom.scope)
    for record in records:
        observed = record["occurrence"].atom
        detail = json.loads(observed.scope)
        if semantic_key(replace(observed, scope=atom.scope)) != semantic_key(atom):
            continue
        if any(proposed[name] != detail[name] for name in ("scope", "action_status", "logic")):
            continue
        if all(attribute in detail["attributes"] for attribute in proposed["attributes"]):
            return True
    return False


def canonical_knowledge_id(node_id):
    """Сопоставляет statement_id его каноническому блоку схемы 6."""
    match = re.fullmatch(r"(.+?)S\d+", node_id)
    return match.group(1) if match else node_id


def same_canonical_knowledge(left, right):
    """Не считает несколько частей одного блока независимыми посылками."""
    return (left.source_id == right.source_id
            and canonical_knowledge_id(left.node_id) == canonical_knowledge_id(right.node_id))


def analogy_candidates(records, families):
    eligible = [r for r in records if r["eligible"]]
    known = {semantic_key(r["occurrence"].atom) for r in records}
    candidates = {}
    diagnostics = Counter()
    tried = 0
    # Все элементы остаются в своём контексте. Общий предикат не переносит область исследования.
    for first in eligible:
        a = first["occurrence"]
        for second in eligible:
            b = second["occurrence"]
            if same_canonical_knowledge(a, b):
                diagnostics["same_canonical_block_pair_blocked"] += 1
                continue
            if a == b or (a.atom.predicate, a.atom.scope, a.atom.kind, a.atom.negated) != (
                b.atom.predicate, b.atom.scope, b.atom.kind, b.atom.negated):
                continue
            if [r for r, _ in a.atom.roles] != [r for r, _ in b.atom.roles]:
                continue
            changes = [(ra, ta, tb) for (ra, ta), (_, tb) in zip(a.atom.roles, b.atom.roles) if ta != tb]
            if len(changes) != 1:
                continue
            role, old, new = changes[0]
            if role.casefold() in {"outcome", "result", "endpoint", "effect", "dependent variable"}:
                diagnostics["outcome_role_substitution_blocked"] += 1
                continue
            if not replaceable(role, old) or not replaceable(role, new):
                diagnostics["cohort_or_reference_substitution_blocked"] += 1
                continue
            for head in eligible:
                q = head["occurrence"]
                if same_canonical_knowledge(a, q) or same_canonical_knowledge(b, q):
                    diagnostics["same_canonical_block_premises_blocked"] += 1
                    continue
                if q in (a, b) or q.atom.predicate == a.atom.predicate or q.atom.scope != a.atom.scope:
                    continue
                positions = [r for r, term in q.atom.roles if term == old]
                if len(positions) != 1 or not replaceable(positions[0], old):
                    continue
                tried += 1
                require(tried <= LIMITS["max_analogy_combinations"], "Free forecast search exceeded frozen budget")
                if numeric(json.loads(q.atom.scope)["attributes"]):
                    diagnostics["numeric_transfer_blocked"] += 1
                    continue
                if q.atom.kind != "state" or head["knowledge"]["action_status"] is not None:
                    diagnostics["action_transfer_blocked"] += 1
                    continue
                new_roles = tuple(sorted((r, new if term == old else term) for r, term in q.atom.roles))
                if len({term for _, term in new_roles}) < len({term for _, term in q.atom.roles}):
                    diagnostics["participant_collapse_blocked"] += 1
                    continue
                atom = replace(q.atom, roles=new_roles)
                key = semantic_key(atom)
                if key in known or already_represented(atom, records):
                    diagnostics["already_known"] += 1
                    continue
                if semantic_key(replace(atom, negated=not atom.negated)) in known:
                    diagnostics["explicit_source_contradiction"] += 1
                    continue
                # Дедуктивные классификации здесь не используются как неподтверждённая аналогия.
                if normalize(atom.predicate) in {"is a", "subtype of", "characterized by", "diagnostic criteria"}:
                    diagnostics["definition_transfer_blocked"] += 1
                    continue
                premises = [{"source_id": o.source_id, "node_id": o.node_id,
                             "display_text": o.display_text, "provenance": o.provenance} for o in (a, b, q)]
                sources = sorted({o.source_id for o in (a, b, q)})
                provenance_families = sorted({families[s] for s in sources})
                witness = {"operator": "single_role_analogy", "changed_role": positions[0],
                           "from": old, "to": new, "premises": premises}
                item = candidates.setdefault(key, {"id": atom.key, "atom": asdict(atom),
                    "status": "exploratory_analogy", "operator": "single_role_analogy",
                    "rule_id": "single-role-analogy-1", "support": 0, "support_sources": [],
                    "support_families": [], "source_families": provenance_families, "premises": premises,
                    "witnesses": [], "evidence_note": "Premise sources are not independent confirmations of the conclusion"})
                if fingerprint(witness) not in {fingerprint(w) for w in item["witnesses"]}:
                    item["witnesses"].append(witness)
                item["source_families"] = sorted(set(item["source_families"]) | set(provenance_families))
    diagnostics["examined_analogy_combinations"] = tried
    return list(candidates.values()), dict(diagnostics)


def diagnose_witnesses(records):
    """Близость без совместимости показывается только как диагностический отказ."""
    eligible = [r for r in records if r["eligible"]]
    counts, examples = Counter(), []
    for i, first in enumerate(eligible):
        a = first["occurrence"]
        for second in eligible[i + 1:]:
            b = second["occurrence"]
            if (a.atom.predicate, a.atom.kind, a.atom.negated) != (b.atom.predicate, b.atom.kind, b.atom.negated):
                continue
            if [r for r, _ in a.atom.roles] != [r for r, _ in b.atom.roles]:
                continue
            changes = [(role, left, right) for (role, left), (_, right) in zip(a.atom.roles, b.atom.roles) if left != right]
            if len(changes) != 1:
                continue
            counts["single_role_structural_pairs"] += 1
            if a.atom.scope == b.atom.scope:
                counts["same_scope_pairs"] += 1
                if all(replaceable(role, term) for role, left, right in changes for term in (left,right)):
                    counts["replaceable_same_scope_pairs"] += 1
            else:
                counts["different_scope_bundle_pairs"] += 1
                if len(examples) < 10:
                    left, right = json.loads(a.atom.scope), json.loads(b.atom.scope)
                    examples.append({"predicate": a.atom.predicate,
                        "left": {"source_id":a.source_id,"statement_id":a.node_id,"text":a.display_text,"scope":left},
                        "right":{"source_id":b.source_id,"statement_id":b.node_id,"text":b.display_text,"scope":right},
                        "differences": [key for key in left if left[key] != right[key]],
                        "status":"diagnostic_only_not_a_forecast"})
                for name in json.loads(a.atom.scope):
                    if json.loads(a.atom.scope)[name] != json.loads(b.atom.scope)[name]:
                        label = "context" if name == "scope" else name
                        counts["different_" + label + "_pairs"] += 1
    return {"counts": dict(counts), "examples": examples}


def forecast(maps, families):
    require(set(families) == {m["article_id"] for m in maps}, "Explicit provenance families required")
    normalized, records, _, _ = project_sources(maps)
    legacy = fit_predict(maps)
    learned, unsupported = {}, 0
    for mode in ("semantic", "graph"):
        for item in legacy["predictions"][mode]:
            support_families = sorted({families[s] for s in item["support_sources"]})
            if len(support_families) < LIMITS["min_template_families"]:
                unsupported += 1
                continue
            learned[item["id"]] = {**item, "operator": "source_supported_template",
                                   "support_families": support_families, "source_families": support_families,
                                   "template_mode": mode}
    analogies, diagnostics = analogy_candidates(records, families)
    pool = {c["id"]: c for c in analogies}
    pool.update(learned)
    ranked = sorted(pool.values(), key=lambda c: (-len(c["support_families"]),
                    -len(c["source_families"]), len(c["premises"]), c["id"]))
    selected = ranked[:LIMITS["candidate_limit"]]
    known = legacy["predictions"]["known_union"]
    alphabetical = sorted(known, key=lambda c: c["id"])[:20]
    frequent = sorted(known, key=lambda c: (-len({families[s["article_id"]] for s in c["source_occurrences"]}), c["id"]))[:20]
    return {"predictor_version": VERSION, "policy": POLICY, "limits": LIMITS,
            "predictions": {"free": selected, "known_union": alphabetical, "frequency": frequent},
            "known_count": len(known), "source_statement_count": len(records),
            "eligible_statement_count": sum(r["eligible"] for r in records),
            "source_knowledge_count": len(normalized),
            "diagnostics": {"legacy": legacy["diagnostics"], "analogy": diagnostics,
                            "witness_screening": diagnose_witnesses(records),
                            "family_rejected_templates": unsupported, "candidate_pool": len(pool),
                            "returned": len(selected), "supported_candidates": len(learned)},
            "model_calls": 0, "expert_validated": False}
