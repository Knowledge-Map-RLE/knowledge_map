"""Проверяет новую семантику переходов, скрытые циклы, контексты и каноничность."""
import copy
import json

import pytest

from domain.article_maps import ArticleMapError, parse_json_response, prepare_source
from domain.knowledge_development import (apply_development_review, initialize_occurrences,
                                          model_contract, validate_development_map)
from domain.knowledge_development_schema import development_map_json_schema

TEXT = "# Study\n\nSome treated mice did not develop fibrosis in 2020. Measurements were collected and compared.\n\n## References\n\nExcluded citation."
SOURCE = prepare_source("article", TEXT)


def knowledge(number, *, kind="state", display=None, **semantic):
    statement = {"statement_id": f"S{number}", "predicate": display or f"Observation {number} was reported",
                 "roles": [{"role": "subject", "concept_id": "C1", "knowledge_id": None}],
                 "quantifier": None, "modality": None, "negated": False, "conditions": [],
                 "temporal_context": None, "qualifiers": {"attributes": []}, "provenance": {"unit_ids": ["U2"]}}
    statement.update(semantic)
    return {"knowledge_id": f"K{number}", "kind": kind, "knowledge_kind": "observation" if kind == "state" else "operation",
            "display_text": display or f"Observation {number} was reported", "aliases": [],
            "action_status": None if kind == "state" else "performed", "grounding": "source_explicit",
            "semantic_frame": {"logic": "single", "statements": [statement]}, "provenance": {"unit_ids": ["U2"]}}


def extracted(*items):
    return {"schema_version": 6, "concepts": [{"id": "C1", "display_text": "Mice", "aliases": ["Study mice"],
            "provenance": {"unit_ids": ["U2"]}}], "knowledge": list(items or (knowledge(1), knowledge(2))),
            "nodes": [], "edges": [], "transitions": []}


def transition(identifier, sources, target, usage="evidence", conditions=None):
    return {"id": identifier, "sources": sources, "target": target, "usage": usage,
            "reason": f"{target} immediately uses the source-grounded knowledge in {', '.join(sources)}.",
            "unit_ids": ["U2"], "conditions": conditions or []}


def reviewed(graph, transitions):
    return apply_development_review(json.dumps({"occurrences": [], "transitions": transitions}),
                                    initialize_occurrences(graph, SOURCE), SOURCE, final=True)


@pytest.mark.parametrize("parent_kind,child_kind", [("state", "state"), ("state", "action"),
                                                    ("action", "state"), ("action", "action")])
def test_four_forms_and_no_entity_incidence(parent_kind, child_kind):
    result = reviewed(extracted(knowledge(1, kind=parent_kind), knowledge(2, kind=child_kind)),
                      [transition("T1", ["B1"], "B2", "development")])
    assert result["edges"] == [{"source": "B1", "target": "B2"}]
    assert result["analysis"]["depth"] == 2
    assert {n["kind"] for n in result["nodes"]} <= {"state", "action"}
    assert "C1" not in result["reading_order"]
    assert validate_development_map(model_contract(result), SOURCE) == result


def test_hidden_cycles_do_not_create_visible_edges():
    graph = extracted()
    for index, item in enumerate(graph["knowledge"]):
        item["semantic_frame"]["statements"][0]["roles"].append(
            {"role": "related_knowledge", "concept_id": None, "knowledge_id": f"K{2 - index}"})
    result = initialize_occurrences(graph, SOURCE)
    assert not result["edges"] and result["analysis"]["isolated_count"] == 2


def test_joint_premises_and_alternatives_remain_distinct():
    graph = extracted(knowledge(1), knowledge(2), knowledge(3))
    result = reviewed(graph, [transition("T1", ["B1", "B2"], "B3"),
                              transition("T2", ["B1"], "B3", conditions=["Alternative stated context"])])
    assert len(result["edges"]) == 2
    assert result["transitions"][0]["sources"] == ["B1", "B2"]
    assert result["transitions"][1]["sources"] == ["B1"]


def test_compound_partition_keeps_individual_negation_and_values():
    item = knowledge(1, quantifier="some", negated=True, temporal_context="2020",
                     conditions=["Treated mice"], qualifiers={"attributes": [{"name": "sample_size", "value": 12, "unit": None}]})
    other = copy.deepcopy(item["semantic_frame"]["statements"][0])
    other.update(statement_id="S2", predicate="developed fibrosis", negated=False, quantifier="others")
    item["semantic_frame"] = {"logic": "partition", "statements": [item["semantic_frame"]["statements"][0], other]}
    result = initialize_occurrences(extracted(item), SOURCE)
    frame = result["knowledge"][0]["semantic_frame"]
    assert len(result["nodes"]) == 1 and len(frame["statements"]) == 2
    assert [s["negated"] for s in frame["statements"]] == [True, False]
    assert frame["statements"][0]["qualifiers"]["attributes"][0]["value"] == 12


@pytest.mark.parametrize("usage", ["development", "prerequisite", "method", "result"])
def test_refinement_prerequisite_and_action_result_justifications(usage):
    result = reviewed(extracted(), [transition("T1", ["B1"], "B2", usage)])
    assert result["transitions"][0]["usage"] == usage
    assert set(result["edges"][0]) == {"source", "target"}


def test_question_remains_unresolved_action():
    item = knowledge(1, kind="action", display="Determine why the groups differ")
    item["action_status"] = "unresolved"
    result = initialize_occurrences(extracted(item), SOURCE)
    assert result["knowledge"][0]["action_status"] == "unresolved"
    assert not result["transitions"]


@pytest.mark.parametrize("damage", ["cycle", "unknown", "self", "duplicate_group", "unsupported_usage"])
def test_invalid_transitions_are_rejected_whole(damage):
    candidates = [transition("T1", ["B1"], "B2")]
    if damage == "cycle":
        candidates.append(transition("T2", ["B2"], "B1"))
    elif damage == "unknown":
        candidates[0]["sources"] = ["missing"]
    elif damage == "self":
        candidates[0]["target"] = "B1"
    elif damage == "duplicate_group":
        candidates.append({**candidates[0], "id": "T2"})
    else:
        candidates[0]["usage"] = "causes"
    with pytest.raises(ArticleMapError):
        reviewed(extracted(), candidates)


def test_unknown_semantic_reference_and_incomplete_json():
    graph = extracted()
    graph["knowledge"][0]["semantic_frame"]["statements"][0]["roles"][0]["concept_id"] = "missing"
    with pytest.raises(ArticleMapError, match="participant"):
        initialize_occurrences(graph, SOURCE)
    with pytest.raises(ArticleMapError, match="incomplete"):
        parse_json_response('{"schema_version":6,')


def test_mergeable_repeated_occurrence_is_rejected():
    result = initialize_occurrences(extracted(), SOURCE)
    with pytest.raises(ArticleMapError, match="merged"):
        apply_development_review(json.dumps({"occurrences": [{"id": "B3", "knowledge_id": "K1",
            "occurrence_context": "Another branch", "duplication": {"reason": "The other branch uses this knowledge", "unit_ids": ["U2"]}}],
            "transitions": []}), result, SOURCE, final=True)


def test_canonical_context_negation_and_modality_are_not_merged():
    items = [knowledge(1, predicate="develop fibrosis", negated=True, quantifier="some", temporal_context="2020"),
             knowledge(2, predicate="develop fibrosis", negated=False, quantifier="all", temporal_context="2022", modality="may")]
    result = initialize_occurrences(extracted(*items), SOURCE)
    assert len(result["knowledge"]) == 2


def test_duplicate_meaning_and_unanchored_provenance_rejected():
    graph = extracted(knowledge(1), knowledge(2, predicate="Observation 1 was reported"))
    with pytest.raises(ArticleMapError, match="meaning"):
        initialize_occurrences(graph, SOURCE)
    graph = extracted()
    graph["knowledge"][0]["provenance"]["unit_ids"] = ["U999"]
    with pytest.raises(ArticleMapError, match="source units"):
        initialize_occurrences(graph, SOURCE)


def test_target_scope_and_empty_extraction_graph():
    result = initialize_occurrences(extracted(), SOURCE)
    with pytest.raises(ArticleMapError, match="outside"):
        apply_development_review(json.dumps({"occurrences": [], "transitions": [transition("T1", ["B1"], "B2")]}),
                                 result, SOURCE, target_keys=["K1"])
    validated = validate_development_map(extracted(), SOURCE, extraction=True)
    assert not validated["nodes"]
    schema = development_map_json_schema(extraction=True)
    assert schema["properties"]["schema_version"]["const"] == 6
    assert all(schema["properties"][f]["maxItems"] == 0 for f in ("nodes", "edges", "transitions"))


def test_necessary_occurrence_repeat_preserves_distinct_chains():
    graph = extracted(*(knowledge(i) for i in range(1, 6)))
    value = initialize_occurrences(graph, SOURCE)
    result = apply_development_review(json.dumps({"occurrences": [{"id": "B6", "knowledge_id": "K3",
        "occurrence_context": "Use in the second independently grounded chain", "duplication": {
            "reason": "Merging would combine the first chain input with the second chain output", "unit_ids": ["U2"]}}],
        "transitions": [transition("T1", ["B1"], "B3"), transition("T2", ["B3"], "B4"),
                        transition("T3", ["B2"], "B6"), transition("T4", ["B6"], "B5")]}), value, SOURCE, final=True)
    assert result["analysis"]["repeated_occurrence_count"] == 1
    assert result["analysis"]["depth"] == 3


def test_duplicate_complete_canonical_chain_detected_without_path_expansion():
    from domain.knowledge_development import _check_occurrences
    def node(identifier, kid, context, repeated=False):
        return {"id": identifier, "knowledge_id": kid, "occurrence_context": context,
            "duplication": {"reason": "Claimed different chain", "unit_ids": ["U2"]} if repeated else None,
            "provenance": {"unit_ids": ["U2"]}}
    # Две цепочки K1 -> K2 не становятся разными знаниями от новых id.
    nodes = {n["id"]: n for n in [node("A", "K1", "first"), node("B", "K2", "first"),
                                  node("C", "K1", "second", True), node("D", "K2", "second", True)]}
    with pytest.raises(ArticleMapError):
        _check_occurrences(nodes, {("A", "B"), ("C", "D")}, {"U2": SOURCE["units"][1]})
