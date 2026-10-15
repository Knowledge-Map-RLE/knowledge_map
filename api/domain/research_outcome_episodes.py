"""Проекция зависимостей schema 6 в проверяемые эпизоды действия и исхода."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256

from domain.article_maps import fingerprint, require
from domain.development_prediction import validate_visible_dag


VERSION = "schema6-research-outcome-episodes-2"

# Эти роли указывают на вмешательство или его компаратор, а не на любой метод исследования.
INTERVENTION_ROLES = frozenset({"intervention", "treatment", "exposure", "program", "programme"})
COMPARATOR_ROLES = frozenset({"comparison intervention", "control intervention", "comparator"})
OUTCOME_ROLES = frozenset({"outcome", "result", "endpoint", "dependent variable"})
OUTCOME_KINDS = frozenset({"result", "comparison"})
ANALYTIC_ROLES = frozenset({"analysis", "model", "statistical test", "interaction test", "measurement", "assay"})
ANALYTIC_PREDICATE_PARTS = ("analysis", "regression", "interaction test", "model", "measurement", "assay", "weighting")


def _treatment_roles(knowledge: dict) -> tuple[set[str], set[str]]:
    """Отделяет действия вмешательства от операций анализа, где вмешательство — переменная."""
    intervention_roles, comparator_roles = set(), set()
    for statement in knowledge.get("semantic_frame", {}).get("statements", []):
        predicate = " ".join(statement.get("predicate", "").casefold().replace("_", " ").split())
        grounded_roles = {
            " ".join(role.get("role", "").casefold().replace("_", " ").split())
            for role in statement.get("roles", [])
            if role.get("concept_id") is not None or role.get("knowledge_id") is not None
        }
        if grounded_roles & ANALYTIC_ROLES or any(part in predicate for part in ANALYTIC_PREDICATE_PARTS):
            continue
        intervention_roles.update(grounded_roles & INTERVENTION_ROLES)
        comparator_roles.update(grounded_roles & COMPARATOR_ROLES)
    return intervention_roles, comparator_roles


def _outcome_statements(knowledge: dict) -> list[dict]:
    return [
        statement for statement in knowledge.get("semantic_frame", {}).get("statements", [])
        if (_statement_role_names(statement) & OUTCOME_ROLES)
        or {"intervention", "comparator"}.issubset(_statement_role_names(statement))
    ]


def _statement_role_names(statement: dict) -> set[str]:
    return {
        " ".join(role.get("role", "").casefold().replace("_", " ").split())
        for role in statement.get("roles", [])
    }


def _evidence_for(knowledge_ids: set[str], knowledge: dict, source_text: str, content_end: int) -> list[dict]:
    evidence = {}
    for knowledge_id in sorted(knowledge_ids):
        item = knowledge[knowledge_id]
        for statement in item.get("semantic_frame", {}).get("statements", []):
            provenance = statement.get("provenance", {})
            for span in provenance.get("source_spans", []):
                start, end = span.get("start"), span.get("end")
                require(type(start) is int and type(end) is int and 0 <= start < end <= content_end <= len(source_text),
                        "Invalid Unicode source span in episode provenance")
                excerpt = source_text[start:end]
                require(bool(excerpt.strip()), "Empty source evidence span")
                key = (knowledge_id, statement["statement_id"], start, end)
                evidence[key] = {
                    "knowledge_id": knowledge_id,
                    "statement_id": statement["statement_id"],
                    "start": start,
                    "end": end,
                    "text": excerpt,
                    "sha256": sha256(excerpt.encode("utf-8")).hexdigest(),
                }
    return [evidence[key] for key in sorted(evidence)]


def project_outcome_episodes(snapshot: dict) -> dict:
    """Выделяет только явно связанные переходом выполненные вмешательства и измеренные исходы.

    Наличие зависимости означает, что знания поддерживают описание результата; оно само по себе
    не задаёт причинность, достижение цели, знак эффекта или переносимость на другие исследования.
    """
    graph = snapshot.get("graph", {})
    require(graph.get("schema_version") == 6, "Требуется карта schema 6")
    validate_visible_dag(graph)
    require(isinstance(snapshot.get("article_id"), str) and snapshot["article_id"], "Article identity required")
    require(isinstance(snapshot.get("run_id"), str) and snapshot["run_id"], "Immutable map run required")
    source = snapshot.get("source", {})
    source_text = source.get("text")
    content_end = source.get("content_end")
    require(isinstance(source_text, str) and type(content_end) is int and 0 < content_end <= len(source_text),
            "Source text and content boundary required")

    knowledge = {item["knowledge_id"]: item for item in graph.get("knowledge", [])}
    occurrences = {node["id"]: node["knowledge_id"] for node in graph.get("nodes", [])}
    require(len(knowledge) == len(graph.get("knowledge", [])), "Repeated canonical knowledge id")
    require(len(occurrences) == len(graph.get("nodes", [])), "Repeated occurrence id")

    episodes = []
    for transition in graph.get("transitions", []):
        require(transition.get("target") in occurrences
                and all(source_id in occurrences for source_id in transition.get("sources", [])),
                "Transition references an unknown occurrence")
        target_id = occurrences[transition["target"]]
        target = knowledge[target_id]
        statements = _outcome_statements(target)
        if target.get("knowledge_kind") not in OUTCOME_KINDS or not statements:
            continue

        parent_ids = [occurrences[source_id] for source_id in transition["sources"]]
        interventions, comparators, support = [], [], []
        for parent_id in parent_ids:
            parent = knowledge[parent_id]
            if parent.get("kind") != "action" or parent.get("action_status") != "performed":
                support.append(parent_id)
                continue
            intervention_roles, comparator_roles = _treatment_roles(parent)
            if comparator_roles:
                comparators.append(parent_id)
            if intervention_roles:
                interventions.append(parent_id)
            if not comparator_roles and not intervention_roles:
                support.append(parent_id)
        if not interventions:
            continue

        evidence_ids = set(parent_ids) | {target_id}
        record = {
            "article_id": snapshot["article_id"],
            "run_id": snapshot["run_id"],
            "source_sha256": source.get("sha256"),
            "transition_id": transition["id"],
            "dependency_usage": transition.get("usage"),
            "dependency_reason": transition.get("reason"),
            "intervention_knowledge_ids": sorted(set(interventions)),
            "comparator_knowledge_ids": sorted(set(comparators)),
            "other_support_knowledge_ids": sorted(set(support)),
            "outcome_knowledge_id": target_id,
            "outcome_knowledge_kind": target["knowledge_kind"],
            "outcome_display_text": target["display_text"],
            "outcome_statements": deepcopy(statements),
            "source_evidence": _evidence_for(evidence_ids, knowledge, source_text, content_end),
            "dependency_is_causal_claim": False,
            "causal_effect_inferred": False,
            "goal_attainment": "unscored",
            "direction_inferred": False,
            "cross_article_transfer_supported": False,
        }
        record["episode_id"] = fingerprint(record)
        episodes.append(record)

    return {
        "version": VERSION,
        "article_id": snapshot["article_id"],
        "run_id": snapshot["run_id"],
        "source_sha256": source.get("sha256"),
        "episodes": episodes,
        "episode_count": len(episodes),
        "model_calls": 0,
        "network_calls": 0,
        "neo4j_calls": 0,
        "goal_success_labels_assigned": 0,
        "causal_effects_inferred": 0,
        "same_article_source_bound": True,
    }
