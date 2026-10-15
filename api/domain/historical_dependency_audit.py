"""Проверяет основания исторических эпизодов, не обучая и не выдавая прогноз."""
from collections import defaultdict

from domain.article_maps import require, fingerprint
from domain.question_prediction import graph_supported, make_template
from domain.research_diagnostics import eligibility_issues
from domain.research_semantics import valid_date

VERSION = "historical-dependency-audit-1"


def audit_historical_dependencies(claims, episodes, maps, cutoff, author_use):
    """Ручная проверка использования независима от даты, DAG и сходства шаблонов.

    author_use содержит явные решения проверяющего по каждому эпизоду.
    Наличие цитаты, одинаковых терминов или пути само по себе их не заменяет.
    Результат — диагностическая готовность по этому набору, не гарантия прогноза.
    """
    valid_date(cutoff)
    identifiers = [e["id"] for e in episodes]
    require(len(identifiers) == len(set(identifiers)), "Duplicate historical episode")
    require(set(author_use) == set(identifiers), "Explicit author-use assessments required")
    rows, groups = [], defaultdict(set)
    for episode in episodes:
        refs = [*episode["premises"], episode["conclusion"]]
        require(1 <= len(episode["premises"]) <= 3, "Invalid historical premise count")
        require(all(tuple(r) in claims for r in refs), "Unknown historical claim")
        assessment = author_use[episode["id"]]
        require(type(assessment) is bool, "Author-use assessment must be explicit boolean")
        body = [claims[tuple(r)] for r in episode["premises"]]
        head = claims[tuple(episode["conclusion"])]
        for c in [*body, head]:
            valid_date(c.evidence.available_on)
        chronological = all(c.evidence.available_on < head.evidence.available_on <= cutoff for c in body)
        issues = [{"article_id": c.evidence.article_id, "claim_id": c.claim_id,
                   "issues": eligibility_issues(c)} for c in [*body, head]]
        own_result = head.evidence.presentation == "own_result" and bool(head.evidence.family)
        # Даже одобренное использование метода не заменяет входы конкретного заключения.
        has_transition = bool(episode.get("transition_id"))
        supported = graph_supported(episode, body, head, maps, claims) if has_transition else False
        template = make_template(body, head)
        reasons = []
        if not chronological: reasons.append("not_strictly_earlier_publication")
        if any(r["issues"] for r in issues): reasons.append("unresolved_context_or_logic")
        if not own_result: reasons.append("independent_empirical_result_missing")
        if not assessment: reasons.append("author_use_not_verified")
        if not supported: reasons.append("joint_dependency_not_supported")
        if template is None: reasons.append("unbound_conclusion")
        candidate = not reasons
        if candidate:
            groups[fingerprint(template)].add(head.evidence.family)
        rows.append({"id": episode["id"], "chronological": chronological,
                     "author_use_verified": assessment, "transition_declared": has_transition,
                     "joint_dependency_supported": supported, "own_result": own_result,
                     "conclusion_family": head.evidence.family,
                     "premise_families": sorted({c.evidence.family for c in body if c.evidence.family}),
                     "same_family_as_premise": head.evidence.family in {c.evidence.family for c in body},
                     "claim_issues": issues, "bound_template": template is not None,
                     "candidate": candidate, "reasons": reasons})
    supported_groups = [{"template_id": key, "families": sorted(families), "support": len(families)}
                        for key, families in sorted(groups.items())]
    ready_groups = [g for g in supported_groups if g["support"] >= 2]
    return {"version": VERSION, "episodes": rows, "candidate_episodes": sum(r["candidate"] for r in rows),
            "groups": supported_groups, "ready_groups": len(ready_groups), "ready_for_graph_trial": bool(ready_groups),
            "minimum_independent_families": 2, "forecast_issued": False, "training_performed": False}
