"""Прогноз схемы 6: известные утверждения и статистические гипотезы раздельно."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import replace, asdict

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import normalize_map
from domain.reference_prediction import Atom, Occurrence, Corpus, Rule, learn_rules, predict, abstract_rule

VERSION = "schema6-symbolic-predictor-2"
EVALUATOR_VERSION = "schema6-prediction-evaluator-1"
LOCAL_GROUP = "source-local-cohort-variable"
LIMITS = {"min_support": 2, "max_premises": 3, "prediction_limit": 20, "max_neighbors": 12,
          "max_matches_per_rule": 1000}


def validate_visible_dag(graph):
    nodes = {n["id"] for n in graph["nodes"]}
    incoming = {n: 0 for n in nodes}
    children = defaultdict(list)
    for edge in graph.get("edges", []):
        require(edge["source"] in nodes and edge["target"] in nodes, "Unknown visible prediction edge")
        incoming[edge["target"]] += 1
        children[edge["source"]].append(edge["target"])
    ready = [n for n, count in incoming.items() if count == 0]
    seen = 0
    while ready:
        node = ready.pop(); seen += 1
        for child in children[node]:
            incoming[child] -= 1
            if incoming[child] == 0:
                ready.append(child)
    require(seen == len(nodes), "Visible prediction graph must be a DAG")


def project_sources(maps):
    require(bool(maps), "Explicit source maps required")
    require(len({m["article_id"] for m in maps}) == len(maps), "Duplicate prediction source")
    for m in maps:
        validate_visible_dag(m["graph"])
    normalized = [k for m in maps for k in normalize_map(m)]
    records, by_knowledge = [], defaultdict(list)
    for k in normalized:
        for s in k["statements"]:
            # Статус действия, ограничения и числовые атрибуты никогда не обобщаются.
            scope = json.dumps({"scope": s["scope"], "attributes": s["attributes"],
                                "action_status": k["action_status"], "logic": k["logic"]},
                               ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            roles = tuple(sorted((r["role"], r["value"] if isinstance(r["value"], str)
                                   else "knowledge:" + json.dumps(r["value"], sort_keys=True, ensure_ascii=False))
                                  for r in s["roles"]))
            atom = Atom(s["predicate"], k["kind"], roles, scope, s["negated"])
            occurrence = Occurrence(k["article_id"], s["id"], k["text"], s["provenance"], atom)
            record = {"occurrence": occurrence, "statement": s, "knowledge": k,
                      "eligible": not s["unknown_context"] and k["logic"] in {"single", "conjunction"}}
            records.append(record)
            by_knowledge[(k["article_id"], k["id"])].append(record)
    edges = set()
    for k in normalized:
        for group in k["premise_groups"]:
            for parent in group:
                for a in by_knowledge[(k["article_id"], parent)]:
                    for b in by_knowledge[(k["article_id"], k["id"])]:
                        edges.add(((a["occurrence"].source_id, a["occurrence"].node_id),
                                   (b["occurrence"].source_id, b["occurrence"].node_id)))
    return normalized, records, by_knowledge, edges


def grouped_rules(normalized, by_knowledge, edges):
    grouped, skipped = {}, 0
    for k in normalized:
        for group in k["premise_groups"]:
            body = [r for parent in group for r in by_knowledge[(k["article_id"], parent)]]
            if not 1 <= len(body) <= LIMITS["max_premises"] or not all(r["eligible"] for r in body):
                skipped += 1
                continue
            for head in by_knowledge[(k["article_id"], k["id"])]:
                if not head["eligible"] or any(r["occurrence"].atom.key == head["occurrence"].atom.key for r in body):
                    continue
                variant = abstract_rule(tuple(learning_occurrence(r["occurrence"]) for r in body), learning_occurrence(head["occurrence"]), edges, True)
                if variant is None:
                    continue
                key, premises, conclusion, internal, ordered = variant
                rule = grouped.setdefault(key, Rule(fingerprint(key), premises, conclusion, internal, set(), [], "graph"))
                rule.support_sources.add(k["article_id"])
                if len(rule.examples) < 3:
                    rule.examples.append({"source_id": k["article_id"], "premises": [o.node_id for o in ordered], "head": head["statement"]["id"]})
    rules = sorted((r for r in grouped.values() if len(r.support_sources) >= LIMITS["min_support"]),
                   key=lambda r: (-len(r.support_sources), len(r.body), r.id))
    return rules, {"candidate_templates": len(grouped), "accepted_rules": len(rules),
                   "skipped_joint_groups": skipped, "min_support": LIMITS["min_support"], "max_premises": 3}


def learning_occurrence(occurrence):
    # Локальная когорта является переменной шаблона; применение остаётся в одной статье.
    scope = json.loads(occurrence.atom.scope)
    if scope["scope"]["study_group"] is not None:
        scope["scope"]["study_group"] = LOCAL_GROUP
    atom = replace(occurrence.atom, scope=json.dumps(scope, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return replace(occurrence, atom=atom)


def contextual_predictions(eligible, learned, known):
    local, global_rules = [], []
    for rule in learned:
        head_local = json.loads(rule.head.scope)["scope"]["study_group"] == LOCAL_GROUP
        body_local = any(json.loads(a.scope)["scope"]["study_group"] == LOCAL_GROUP for a in rule.body)
        if head_local and not body_local:
            continue
        (local if head_local or body_local else global_rules).append(rule)
    groups = defaultdict(list)
    for o in eligible.occurrences:
        groups[o.source_id].append(o)
    jobs = [(eligible, global_rules)] + [(Corpus(occurrences, eligible.edges), local) for _, occurrences in sorted(groups.items())]
    candidates, stats = {}, {"novel_candidates": 0, "bounded_matches": 0, "max_matches_per_rule": LIMITS["max_matches_per_rule"]}
    for corpus, rules in jobs:
        generated, info = predict(corpus, rules, limit=20, max_matches_per_rule=LIMITS["max_matches_per_rule"])
        stats["bounded_matches"] += info["bounded_matches"]
        for c in generated:
            payload = dict(c["atom"]); scope = json.loads(payload["scope"])
            if scope["scope"]["study_group"] == LOCAL_GROUP:
                sources = {p["source_id"] for p in c["premises"]}
                require(len(sources) == 1, "Prediction mixed distinct study groups")
                scope["scope"]["study_group"] = next(iter(sources))
                payload["scope"] = json.dumps(scope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            atom = Atom(payload["predicate"], payload["kind"], tuple(tuple(r) for r in payload["roles"]), payload["scope"], payload["negated"])
            if atom.key not in known:
                item = {**c, "id": atom.key, "atom": asdict(atom), "cohort_binding": scope["scope"]["study_group"]}
                existing = candidates.get(atom.key)
                if existing is None or (-item["support"], item["rule_id"]) < (-existing["support"], existing["rule_id"]):
                    candidates[atom.key] = item
    ranked = sorted(candidates.values(), key=lambda c: (-c["support"], len(c["premises"]), c["id"]))
    stats.update(novel_candidates=len(ranked), returned=min(20, len(ranked)))
    return ranked[:20], stats


def fit_predict(maps):
    normalized, records, by_knowledge, edges = project_sources(maps)
    all_corpus = Corpus([r["occurrence"] for r in records], edges)
    eligible = Corpus([learning_occurrence(r["occurrence"]) for r in records if r["eligible"]], edges)
    known = {}
    for r in records:
        o, s, k = r["occurrence"], r["statement"], r["knowledge"]
        item = known.setdefault(o.atom.key, {"id": o.atom.key, "status": "known_source_knowledge",
            "statement": s, "kind": k["kind"], "action_status": k["action_status"], "logic": k["logic"],
            "source_occurrences": []})
        item["source_occurrences"].append({"article_id": o.source_id, "run_id": k["run_id"],
            "knowledge_id": k["id"], "statement_id": s["id"], "display_text": o.display_text,
            "provenance": o.provenance})
    for item in known.values():
        item["support"] = len({o["article_id"] for o in item["source_occurrences"]})
    output, rules, diagnostics = {}, {}, {}
    for mode in ("semantic", "graph"):
        if mode == "graph":
            learned, stats = grouped_rules(normalized, by_knowledge, edges)
        else:
            learned, stats = learn_rules(eligible, graph_mode=False, min_support=2, max_premises=3,
                                        max_neighbors=LIMITS["max_neighbors"])
        # Неизвестный контекст запрещает обучение, но известный источник остаётся известным для исключения повторов.
        existing = {o.atom.key for o in all_corpus.occurrences}
        candidates, pred_stats = contextual_predictions(eligible, learned, existing)
        output[mode], rules[mode], diagnostics[mode] = candidates, [r.to_dict() for r in learned], {**stats, **pred_stats, "returned": len(candidates)}
    output["known_union"] = sorted(known.values(), key=lambda c: (-c["support"], c["id"]))
    return {"predictor_version": VERSION, "limits": LIMITS, "normalization": normalized,
            "predictions": output, "rules": rules, "diagnostics": diagnostics,
            "source_statement_count": len(records), "eligible_statement_count": len(eligible.occurrences),
            "model_calls": 0, "needs_expert_review": True}


def candidate_statement(candidate):
    if "statement" in candidate:
        return candidate["statement"], {"kind": candidate["kind"], "action_status": candidate["action_status"]}
    atom = candidate["atom"]
    scope = json.loads(atom["scope"])
    statement = {"id": candidate["id"], "predicate": atom["predicate"],
        "roles": [{"role": role, "value": value, "reference_kind": "knowledge" if value.startswith("knowledge:") else "concept"}
                  for role, value in atom["roles"]], "scope": scope["scope"], "attributes": scope["attributes"],
        "negated": atom["negated"], "unknown_context": False, "provenance": {"unit_ids": []}}
    statement["roles"].sort(key=fingerprint)
    return statement, {"kind": atom["kind"], "action_status": scope["action_status"]}


def evaluate_sealed(sealed, target, controls):
    from domain.article_comparison import compare_statements
    target_knowledge = normalize_map(target)
    anchors = controls.get("pairs", [])
    citations = [a for a in anchors if a.get("kind") == "citation"]
    anchor_ids = {kid for c in citations for kid in c["left_knowledge_ids"]}
    cited_units = {c["left_fragment"]["unit_id"] for c in citations}
    modes = {}
    for mode, candidates in sealed["predictions"].items():
        rows = []
        for candidate in candidates:
            s, meta = candidate_statement(candidate)
            matches = []
            for k in target_knowledge:
                for t in k["statements"]:
                    matched = compare_statements(t, s, k, meta)
                    if matched["relation"] in {"equivalent", "contradiction", "partial"} or matched["shared_attributes"]:
                        if k["id"] in anchor_ids:
                            citation_status = "citation_control_anchor"
                        elif cited_units.intersection(t["provenance"]["unit_ids"]):
                            citation_status = "citation_paragraph_unresolved"
                        else:
                            citation_status = "no_direct_citation_to_five" if citations else "citation_unannotated"
                        matches.append({"target_knowledge_id": k["id"], "target_statement_id": t["id"],
                            "citation_status": citation_status, **matched})
            rows.append({"candidate_id": candidate["id"], "status": candidate["status"], "matches": matches,
                         "not_confirmed_is_not_refuted": not bool(matches)})
        equivalent = [(r, m) for r in rows for m in r["matches"] if m["relation"] == "equivalent"]
        covered = {m["target_statement_id"] for _, m in equivalent}
        modes[mode] = {"candidate_count": len(candidates), "matched_candidate_count": len({r["candidate_id"] for r, _ in equivalent}),
            "matched_target_statements": sorted({m["target_statement_id"] for _, m in equivalent}),
            "matched_target_knowledge": sorted({m["target_knowledge_id"] for _, m in equivalent}),
            "fully_covered_target_blocks": sorted(k["id"] for k in target_knowledge if k["logic"] in {"single", "conjunction"}
                                                   and all(s["id"] in covered for s in k["statements"])),
            "partial_target_knowledge": sorted({m["target_knowledge_id"] for r in rows for m in r["matches"] if m["relation"] == "partial"}),
            "shared_attribute_targets": sorted({m["target_knowledge_id"] for r in rows for m in r["matches"] if m["shared_attributes"]}),
            "shared_attributes_by_citation": {label: sorted({m["target_knowledge_id"] for r in rows for m in r["matches"]
                                                             if m["shared_attributes"] and m["citation_status"] == label})
                for label in ("citation_control_anchor", "citation_paragraph_unresolved", "no_direct_citation_to_five", "citation_unannotated")},
            "citation_counts": {label: len({m["target_statement_id"] for _, m in equivalent if m["citation_status"] == label})
                for label in ("citation_control_anchor", "citation_paragraph_unresolved", "no_direct_citation_to_five", "citation_unannotated")},
            "results": rows}
    return {"modes": modes, "target_knowledge_count": len(target_knowledge), "expert_validated": False,
            "note": "Source-only candidates were sealed before target loading. This is a previously inspected debugging case, not an independent prospective test."}
