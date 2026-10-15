"""Причины отказа и покрытие исходной семантики без изменения готовой карты."""
from __future__ import annotations

from collections import Counter

from domain.research_semantics import compare_claims, context_difference, unknown_measurement_units

VERSION = "research-diagnostics-1"


def eligibility_issues(claim):
    issues = []
    if claim.unresolved: issues.append("unresolved_semantic_reference")
    if claim.logic not in {"single", "conjunction"}: issues.append("unsupported_logic:" + claim.logic)
    if not claim.context: issues.append("missing_context")
    for key, value in sorted(claim.context.items()):
        if value["status"] == "not_reported": issues.append("unknown_context:" + key)
    if not all(isinstance(v, str) and bool(v) for v in claim.roles.values()): issues.append("unresolved_participant")
    issues.extend(unknown_measurement_units(claim.measurements))
    if claim.action_status in {"planned", "prescribed", "unresolved"}: issues.append("action_not_performed")
    return issues


def eligibility_summary(claims):
    claims = list(claims)
    reasons = Counter()
    rows = []
    for claim in claims:
        issues = eligibility_issues(claim)
        reasons.update(issues)
        rows.append({"article_id": claim.evidence.article_id, "claim_id": claim.claim_id,
                     "knowledge_id": claim.knowledge_id, "eligible": not issues, "reasons": issues,
                     "presentation": claim.evidence.presentation})
    return {"total": len(rows), "eligible": sum(r["eligible"] for r in rows),
            "blocked": sum(not r["eligible"] for r in rows), "reason_counts": dict(sorted(reasons.items())),
            "counts_overlap": True, "claims": rows}


def coverage_detail(expected, native):
    """Сравниваем контрольный атом с исходным блоком, не выдавая ручной атом за результат извлечения."""
    native = list(native)
    candidates = [c for c in native if c.knowledge_id == expected.knowledge_id]
    if not candidates: candidates = native
    ranked = []
    for actual in candidates:
        comparison = compare_claims(expected, actual)
        shared_roles = sum(actual.roles.get(k) == v for k, v in expected.roles.items())
        score = (comparison["relation"] == "equivalent", actual.predicate == expected.predicate, shared_roles,
                 comparison["relation"] == "partial", -len(comparison["differences"] + comparison["unknown"]))
        ranked.append((score, actual, comparison))
    if not ranked:
        return {"claim_id": expected.claim_id, "knowledge_id": expected.knowledge_id,
                "represented": False, "reason": "native_statement_missing"}
    _, actual, comparison = max(ranked, key=lambda row: row[0])
    differences = []
    for field in ("predicate", "roles", "negated", "quantifier", "modality", "action_status", "logic", "measurements"):
        if getattr(actual, field) != getattr(expected, field):
            differences.append({"field": field, "native": getattr(actual, field), "expected": getattr(expected, field)})
    conflicts, unknown = context_difference(expected.context, actual.context)
    for field in conflicts:
        differences.append({"field": "context:" + field, "native": actual.context.get(field), "expected": expected.context.get(field)})
    overlap = any(a["start"] < b["end"] and a["end"] > b["start"]
                  for a in expected.evidence.spans for b in actual.evidence.spans)
    return {"claim_id": expected.claim_id, "knowledge_id": expected.knowledge_id,
            "native_claim_id": actual.claim_id, "represented": comparison["relation"] == "equivalent",
            "comparison": comparison, "field_differences": differences, "unknown_context": unknown,
            "source_spans_overlap": overlap, "native_eligibility_issues": eligibility_issues(actual),
            "expected_eligibility_issues": eligibility_issues(expected),
            "native_text": actual.text, "control_text": expected.text,
            "native_spans": actual.evidence.spans, "control_spans": expected.evidence.spans}
