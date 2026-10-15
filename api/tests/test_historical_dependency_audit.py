"""Отделяет авторское использование, хронологию, совместные входы и поддержку семей."""
from dataclasses import replace

import pytest

from domain.article_maps import ArticleMapError, digest
from domain.historical_dependency_audit import audit_historical_dependencies
from domain.research_semantics import SemanticClaim, Evidence, context_value as cv


def setup_case(count=1):
    claims, episodes, maps, use = {}, [], {}, {}
    for i in range(count):
        def claim(article, kid, predicate, date, family):
            return SemanticClaim(kid, kid, predicate, {"exposure": "il6", "outcome": "cognition"},
                False, None, None, {"species": cv("human"), "study": cv("study" + str(i))}, (),
                None, "single", "Known statement", Evidence(article, "run", digest(article), date, family,
                "own_result", ({"start": 0, "end": 1, "text": "x", "offset_encoding": "unicode_code_points"},)))
        prior = claim("prior" + str(i), "P", "measured", "2010-01-01", "prior-family")
        local = replace(prior, knowledge_id="L", claim_id="L",
                        evidence=replace(prior.evidence, article_id="later" + str(i), available_on="2015-01-01"))
        head = claim("later" + str(i), "H", "associated with", "2015-01-01", "family" + str(i))
        for c in (prior, local, head): claims[c.evidence.article_id, c.claim_id] = c
        identifier = "episode" + str(i)
        episodes.append({"id": identifier, "premises": [[prior.evidence.article_id, "P"]],
                         "conclusion": [[head.evidence.article_id, "H"]][0], "transition_id": "T"})
        maps[head.evidence.article_id] = {"graph": {"nodes": [{"id": "B1", "knowledge_id": "L"},
            {"id": "B2", "knowledge_id": "H"}], "transitions": [{"id": "T", "sources": ["B1"], "target": "B2"}]}}
        use[identifier] = True
    return claims, episodes, maps, use


def audit(values):
    claims, episodes, maps, use = values
    return audit_historical_dependencies(claims, episodes, maps, "2022-12-31", use)


def test_two_independent_families_with_same_verified_template_are_ready():
    result = audit(setup_case(2))
    assert result["candidate_episodes"] == 2 and result["ready_groups"] == 1
    assert result["ready_for_graph_trial"] and not result["forecast_issued"] and not result["training_performed"]


def test_one_family_or_one_episode_cannot_establish_support():
    values = setup_case(2)
    values[0]["later1", "H"] = replace(values[0]["later1", "H"],
        evidence=replace(values[0]["later1", "H"].evidence, family="family0"))
    assert not audit(values)["ready_for_graph_trial"]
    assert not audit(setup_case())["ready_for_graph_trial"]


def test_citation_or_similar_topic_is_not_verified_author_use():
    values = setup_case(2); values[3]["episode0"] = False
    result = audit(values)
    assert "author_use_not_verified" in result["episodes"][0]["reasons"]
    assert not result["ready_for_graph_trial"]


def test_same_publication_is_reconstruction_only():
    values = setup_case(); c = values[0]["prior0", "P"]
    values[0]["prior0", "P"] = replace(c, evidence=replace(c.evidence, available_on="2015-01-01"))
    assert "not_strictly_earlier_publication" in audit(values)["episodes"][0]["reasons"]


def test_unknown_context_and_unbound_numerical_conclusion_are_reported():
    values = setup_case(); c = values[0]["later0", "H"]
    values[0]["later0", "H"] = replace(c, context={**c.context, "population": cv(None, "not_reported")},
        measurements=({"name": "beta", "value": -0.13, "unit": "mmse points/year"},))
    assert {"unresolved_context_or_logic", "unbound_conclusion"} <= set(audit(values)["episodes"][0]["reasons"])


def test_method_transfer_does_not_become_empirical_conclusion():
    values = setup_case(); c = values[0]["later0", "H"]
    values[0]["later0", "H"] = replace(c, evidence=replace(c.evidence, presentation="method"))
    assert "independent_empirical_result_missing" in audit(values)["episodes"][0]["reasons"]


def test_missing_or_incomplete_joint_inputs_block_graph_support():
    values = setup_case(); values[1][0]["transition_id"] = None
    assert "joint_dependency_not_supported" in audit(values)["episodes"][0]["reasons"]
    values = setup_case(); values[2]["later0"]["graph"]["nodes"].append({"id": "B3", "knowledge_id": "unmapped"})
    values[2]["later0"]["graph"]["transitions"][0]["sources"].append("B3")
    assert not audit(values)["episodes"][0]["joint_dependency_supported"]


def test_explicit_assessment_and_unique_references_required():
    values = setup_case(); values[3].clear()
    with pytest.raises(ArticleMapError, match="Explicit"): audit(values)
    values = setup_case(); values[1].append(values[1][0])
    with pytest.raises(ArticleMapError, match="Duplicate"): audit(values)
    values = setup_case(); values[1][0]["premises"] = [["unknown", "P"]]
    with pytest.raises(ArticleMapError, match="Unknown"): audit(values)
