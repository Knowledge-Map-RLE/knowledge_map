"""Проверки проекции карт schema 6 в эмпирические эпизоды."""
from copy import deepcopy

import pytest

from domain.article_maps import ArticleMapError
from domain.research_outcome_episodes import project_outcome_episodes


def statement(statement_id, predicate, roles, span):
    start, end = span
    roles = [{"role": name, "concept_id": None, "knowledge_id": None} for name in roles]
    for role in roles:
        if role["role"] in {"intervention", "comparison intervention"}:
            role["concept_id"] = f"C-{role['role']}"
    return {
        "statement_id": statement_id,
        "predicate": predicate,
        "roles": roles,
        "quantifier": None,
        "modality": None,
        "negated": False,
        "conditions": [],
        "temporal_context": "baseline to follow-up",
        "qualifiers": {"attributes": []},
        "provenance": {"source_spans": [{"start": start, "end": end}]},
    }


def knowledge(knowledge_id, kind, knowledge_kind, text, statement_item, status=None):
    return {
        "knowledge_id": knowledge_id,
        "kind": kind,
        "knowledge_kind": knowledge_kind,
        "display_text": text,
        "action_status": status,
        "semantic_frame": {"statements": [statement_item]},
    }


def snapshot():
    source_text = "randomized exercise compared with education; mobility outcome measured over follow-up."
    records = [
        knowledge("K1", "action", "method", "Randomized allocation to exercise or education.",
                  statement("S1", "random_assignment", ["assigned arms"], (0, 17)), "performed"),
        knowledge("K2", "action", "method", "Participants received exercise.",
                  statement("S2", "exercise_program", ["intervention"], (18, 35)), "performed"),
        knowledge("K3", "action", "method", "Education was the comparator.",
                  statement("S3", "education_program", ["comparison intervention"], (36, 45)), "performed"),
        knowledge("K4", "state", "method", "Mobility outcome was measured.",
                  statement("S4", "measure_mobility", ["outcome"], (46, 61))),
        knowledge("K5", "state", "result", "The intervention group had less worsening.",
                  statement("S5", "lower_worsening", ["outcome", "intervention", "comparison"], (62, len(source_text)))),
        knowledge("K6", "action", "method", "A statistical model was fit.",
                  statement("S6", "fit_model", ["analysis"], (46, 61)), "performed"),
    ]
    return {
        "article_id": "TEST-ARTICLE",
        "run_id": "TEST-RUN",
        "source": {"text": source_text, "sha256": "a" * 64, "content_end": len(source_text)},
        "graph": {
            "schema_version": 6,
            "knowledge": records,
            "nodes": [{"id": f"N{i}", "knowledge_id": f"K{i}"} for i in range(1, 7)],
            "edges": [{"source": "N1", "target": "N5"}],
            "transitions": [{
                "id": "T1", "sources": ["N1", "N2", "N3", "N4", "N6"], "target": "N5",
                "usage": "data", "reason": "Trial assignment, programs, outcome definition, and analysis support the comparison.",
            }],
        },
    }


def test_projects_only_supported_intervention_outcome_and_keeps_other_basis():
    result = project_outcome_episodes(snapshot())
    assert result["episode_count"] == 1
    episode = result["episodes"][0]
    assert episode["intervention_knowledge_ids"] == ["K2"]
    assert episode["comparator_knowledge_ids"] == ["K3"]
    assert episode["other_support_knowledge_ids"] == ["K1", "K4", "K6"]
    assert episode["outcome_knowledge_id"] == "K5"
    assert episode["outcome_statements"][0]["predicate"] == "lower_worsening"
    assert episode["dependency_is_causal_claim"] is False
    assert episode["causal_effect_inferred"] is False
    assert episode["goal_attainment"] == "unscored"
    assert episode["direction_inferred"] is False
    assert episode["source_evidence"]
    assert result["model_calls"] == result["network_calls"] == result["neo4j_calls"] == 0


def test_analysis_action_is_not_misclassified_as_intervention():
    raw = snapshot()
    raw["graph"]["knowledge"][1]["semantic_frame"]["statements"][0]["roles"] = [
        {"role": "intervention", "concept_id": None, "knowledge_id": None}
    ]
    assert project_outcome_episodes(raw)["episode_count"] == 0


def test_intervention_named_as_a_model_variable_is_not_a_treatment_action():
    raw = snapshot()
    raw["graph"]["knowledge"][1]["semantic_frame"]["statements"][0]["predicate"] = \
        "intervention_by_marker_interaction_test"
    assert project_outcome_episodes(raw)["episode_count"] == 0


def test_target_without_explicit_outcome_role_is_not_projected():
    raw = snapshot()
    raw["graph"]["knowledge"][4]["semantic_frame"]["statements"][0]["roles"] = [
        {"role": "authors", "concept_id": None, "knowledge_id": None}
    ]
    assert project_outcome_episodes(raw)["episode_count"] == 0


def test_comparison_roles_can_mark_a_measured_comparison_without_an_outcome_role():
    raw = snapshot()
    raw["graph"]["knowledge"][4]["semantic_frame"]["statements"][0]["roles"] = [
        {"role": "intervention", "concept_id": "C-exercise", "knowledge_id": None},
        {"role": "comparator", "concept_id": "C-education", "knowledge_id": None},
    ]
    episode = project_outcome_episodes(raw)["episodes"][0]
    assert episode["outcome_knowledge_id"] == "K5"
    assert episode["intervention_knowledge_ids"] == ["K2"]
    assert episode["comparator_knowledge_ids"] == ["K3"]


def test_missing_source_provenance_is_rejected_instead_of_invented():
    raw = snapshot()
    raw["graph"]["knowledge"][4]["semantic_frame"]["statements"][0]["provenance"]["source_spans"][0]["end"] += 1000
    with pytest.raises(ArticleMapError):
        project_outcome_episodes(raw)


def test_schema_and_visible_dag_are_required():
    raw = snapshot()
    raw["graph"]["schema_version"] = 4
    with pytest.raises(ArticleMapError):
        project_outcome_episodes(raw)
    raw = snapshot()
    raw["graph"]["edges"].append({"source": "N5", "target": "N1"})
    with pytest.raises(ArticleMapError):
        project_outcome_episodes(raw)


def test_projection_does_not_mutate_map():
    raw = snapshot()
    before = deepcopy(raw)
    project_outcome_episodes(raw)
    assert raw == before
