"""Семантические ограничения не отменяются высоким лексическим сходством."""
import copy

import pytest

from domain.article_comparison import compare_knowledge, maximum_alignment, compare_statements, rank_pairs
from domain.comparison_normalization import search_tokens, normalize_map, normalize_attribute
from domain.article_maps import ArticleMapError


def statement(**changes):
    return {"id": "S1", "predicate": "measured using", "roles": [{"role": "subject", "value": "mild cognitive impairment", "reference_kind": "concept"}],
            "scope": {"quantifier": "all", "modality": None, "time": "2010–2012", "conditions": [], "study_group": None},
            "negated": False, "attributes": [{"name": "rate", "value": 22.5, "unit": "percent"}],
            "unknown_context": False, "provenance": {"unit_ids": ["U1"]}, **changes}


def knowledge(statements=None, **changes):
    return {"kind": "state", "action_status": None, "logic": "single", "statements": statements or [statement()], "premise_groups": [], **changes}


@pytest.mark.parametrize("field, replacement", [
    ("negated", True), ("attributes", [{"name": "rate", "value": 22.5, "unit": "per1000personyear"}]),
    ("unknown_context", True), ("scope", {"quantifier": "some", "modality": None, "time": "2010–2012", "conditions": [], "study_group": None}),
    ("scope", {"quantifier": "all", "modality": "may", "time": "2010–2012", "conditions": [], "study_group": None}),
    ("scope", {"quantifier": "all", "modality": None, "time": "2020", "conditions": [], "study_group": None}),
    ("scope", {"quantifier": "all", "modality": None, "time": "2010–2012", "conditions": [], "study_group": "other-study"}),
])
def test_constraints_prevent_equivalence(field, replacement):
    a, b = knowledge(), knowledge([statement(**{field: replacement})])
    result = compare_knowledge(a, b)
    assert "equivalent" not in result["relations"]
    assert result["coverage_left"] == 0


def test_explicit_negation_in_same_scope_is_contradiction():
    result = compare_statements(statement(), statement(negated=True), knowledge(), knowledge())
    assert result["relation"] == "contradiction"


def test_negative_claim_in_different_time_is_not_contradiction():
    b = statement(negated=True)
    b["scope"] = b["scope"] | {"time": "2025"}
    assert compare_statements(statement(), b, knowledge(), knowledge())["relation"] != "contradiction"


def test_compound_preserves_logic_and_bidirectional_coverage():
    left = knowledge([statement(), statement(id="S2", predicate="has definition")], logic="contrast")
    right = knowledge()
    result = compare_knowledge(left, right)
    assert result["relations"] == ["partial"]
    assert result["coverage_left"] == .5 and result["coverage_right"] == 1
    assert result["logic_difference"] == ["contrast", "single"]


def test_action_status_is_not_dropped():
    result = compare_knowledge(knowledge(kind="action", action_status="unresolved"), knowledge(kind="action", action_status="performed"))
    assert "equivalent" not in result["relations"]


def test_negative_performed_action_does_not_contradict_an_unresolved_task():
    a = knowledge(kind="action",action_status="unresolved")
    b = knowledge([statement(negated=True)],kind="action",action_status="performed")
    assert "contradiction" not in compare_knowledge(a,b)["relations"]


def test_alignment_optimizes_global_matches():
    assert maximum_alignment([[.9, .8], [.85, .1]]) == [(0, 1), (1, 0)]
    assert maximum_alignment([[.9], [.95]]) == [(1, 0)]


def test_search_synonyms_and_bibliographic_identifiers():
    assert search_tokens("MCI") == search_tokens("Mild cognitive impairment")
    assert search_tokens("MCI [6] PMC10000452 10.1002/trc2.12267") == search_tokens("MCI")


def test_ties_have_stable_positions_and_zero_has_no_rrf_contribution():
    pairs = [{"text_score": v, "right_article_id": "a", "right_knowledge_id": str(i)} for i, v in enumerate([1, 1, 0])]
    rank_pairs(pairs, "text_score")
    assert [p["text_rank"] for p in pairs] == [1, 2, None]


def test_old_schemas_are_rejected_explicitly():
    with pytest.raises(ArticleMapError, match="schema 6"):
        normalize_map({"graph": {"schema_version": 5}})


def test_hidden_cycles_are_resolved_without_mutating_map():
    s = {"statement_id": "S1", "predicate": "refers_to", "roles": [{"role": "subject", "knowledge_id": "K1", "concept_id": None}],
         "quantifier": None, "modality": None, "temporal_context": None, "conditions": [], "negated": False,
         "qualifiers": {"attributes": []}, "provenance": {"unit_ids": ["U1"]}}
    result = {"article_id": "article", "run_id": "run", "graph": {"schema_version": 6, "concepts": [], "nodes": [], "transitions": [],
        "knowledge": [{"knowledge_id": "K1", "kind": "state", "knowledge_kind": "definition", "display_text": "A self reference", "action_status": None,
                       "semantic_frame": {"logic": "single", "statements": [s]}, "provenance": {"unit_ids": ["U1"]}}]}}
    before = copy.deepcopy(result)
    adapted = normalize_map(result)
    assert "cycle" in str(adapted[0]["statements"])
    assert adapted[0]["statements"][0]["unknown_context"] is True
    assert "equivalent" not in compare_knowledge(adapted[0], copy.deepcopy(adapted[0]))["relations"]
    assert result == before


def test_explicit_units_convert_without_equating_rates_with_percentages():
    assert normalize_attribute({"name": "duration", "value": 1, "unit": "hours"}) == {"name": "duration", "value": "60", "unit": "minute"}
    a = normalize_attribute({"name": "rate", "value": 6, "unit": "per 100 person-years"})
    b = normalize_attribute({"name": "rate", "value": 60, "unit": "per 1000 person-years"})
    assert a == b
    assert a != normalize_attribute({"name": "rate", "value": 60, "unit": "percent"})


def test_templates_do_not_require_factual_equivalence():
    a, b = knowledge(), knowledge([statement(scope=statement()["scope"] | {"study_group": "different"})])
    a["chain_signature"] = b["chain_signature"] = [{"premises": [{"predicates": ["measured using"], "upstream": []}]}]
    result = compare_knowledge(a, b)
    assert result["dag_shape_score"] == 1 and "equivalent" not in result["relations"]


def test_absent_constraints_do_not_score_unrelated_statements():
    a = statement(attributes=[], roles=[])
    b = statement(attributes=[], roles=[], predicate="unrelated operation")
    assert compare_statements(a, b, knowledge(), knowledge())["score"] == 0


def test_partial_participant_overlap_does_not_cover_the_entire_assertion():
    shared = {"role": "class", "value": "living things", "reference_kind": "concept"}
    a = statement(roles=[shared, {"role": "subject", "value": "trees", "reference_kind": "concept"}])
    b = statement(roles=[shared, {"role": "subject", "value": "people", "reference_kind": "concept"}])
    result = compare_knowledge(knowledge([a]), knowledge([b]))
    assert result["relations"] == ["partial"] and result["coverage_left"] == 0 and result["coverage_right"] == 0
    assert "roles" in [d["field"] for d in result["statement_matches"][0]["differences"]]


def test_same_sample_label_in_distinct_studies_is_not_equivalent():
    s = {"statement_id":"S1","predicate":"measured using","roles":[{"role":"sample","concept_id":"C1","knowledge_id":None}],
         "quantifier":None,"modality":None,"temporal_context":"baseline","conditions":[],"negated":False,
         "qualifiers":{"attributes":[]},"provenance":{"unit_ids":["U1"]}}
    graph = {"schema_version":6,"concepts":[{"id":"C1","display_text":"Eligible adults","aliases":[]}],"nodes":[],"transitions":[],
             "knowledge":[{"knowledge_id":"K1","kind":"state","knowledge_kind":"observation","display_text":"Sample observation",
                 "action_status":None,"semantic_frame":{"logic":"single","statements":[s]},"provenance":{"unit_ids":["U1"]}}]}
    a = normalize_map({"article_id":"study-a","run_id":"run-a","graph":graph})[0]
    b = normalize_map({"article_id":"study-b","run_id":"run-b","graph":graph})[0]
    assert a["statements"][0]["scope"]["study_group"] == "study-a"
    result = compare_knowledge(a,b)
    assert "equivalent" not in result["relations"] and result["coverage_left"] == 0
