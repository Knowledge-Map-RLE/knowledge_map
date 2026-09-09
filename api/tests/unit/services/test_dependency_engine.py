"""Unit tests for services.dependency_engine."""

from domain.models.dependency import DependencyType, DiscoveryMethod
from services.dependency_engine import (
    CandidateGenerator,
    _normalize_entity,
    _normalize_text,
    _predicate_direction,
    _state_matches,
)


def _stmt(
    uid: str,
    subject_text: str,
    predicate: str,
    object_text: str,
    type_: str = "FACT",
) -> dict:
    return {
        "uid": uid,
        "subject_type": "concept",
        "subject_text": subject_text,
        "predicate": predicate,
        "object_type": "concept",
        "object_text": object_text,
        "type": type_,
        "source_block_id": "",
        "is_goal": False,
    }


def _meta_stmt(uid: str, subject_text: str, object_text: str) -> dict:
    """META-утверждение decomposed_into с subject/object типа statement."""
    stmt = _stmt(uid, subject_text, "decomposed_into", object_text, type_="META")
    stmt["subject_type"] = "statement"
    stmt["object_type"] = "statement"
    return stmt


class TestNormalization:
    def test_normalize_entity_strips_articles(self):
        assert _normalize_entity("The mTOR pathway") == "mtor pathway"

    def test_predicate_direction(self):
        assert _predicate_direction("inhibits") == "down"
        assert _predicate_direction("increases") == "up"
        assert _predicate_direction("supports") == "other"

    def test_state_matches_exact(self):
        assert _state_matches("mTOR", "mTOR", "down") is True

    def test_state_matches_nominalization(self):
        assert _state_matches("mTOR", "mTOR inhibition", "down") is True
        assert _state_matches("mTOR", "autophagy", "down") is False


class TestCandidateGenerator:
    def test_level1_exact_match(self):
        triples = {
            "A1": _stmt("A1", "Rapamycin", "increases", "autophagy"),
            "A2": _stmt("A2", "autophagy", "reduces", "cellular damage"),
        }
        edges = CandidateGenerator(triples).generate()
        edges_by_b = {e.target_uid: e for e in edges}
        assert "A2" in edges_by_b
        assert edges_by_b["A2"].source_uid == "A1"
        assert edges_by_b["A2"].dependency_type == DependencyType.CAUSAL
        assert edges_by_b["A2"].discovery_method == DiscoveryMethod.EXACT_MATCH

    def test_level2_nominalization(self):
        triples = {
            "A1": _stmt("A1", "Rapamycin", "inhibits", "mTOR"),
            "A2": _stmt("A2", "mTOR inhibition", "increases", "autophagy"),
        }
        edges = CandidateGenerator(triples).generate()
        chain = {(e.source_uid, e.target_uid) for e in edges}
        assert ("A1", "A2") in chain

    def test_goal_decomposition_meta(self):
        triples = {
            "M1": _meta_stmt("M1", "child", "parent"),
            "child": _stmt("child", "child", "is", "thing"),
            "parent": _stmt("parent", "parent", "is", "thing"),
        }
        # META-триплеты не должны участвовать как узлы, но должны давать ребро.
        edges = CandidateGenerator(triples).generate()
        goal_edges = [e for e in edges if e.discovery_method == DiscoveryMethod.GOAL_DECOMPOSITION]
        assert any(e.source_uid == "child" and e.target_uid == "parent" for e in goal_edges)

    def test_no_duplicate_edges(self):
        triples = {
            "A1": _stmt("A1", "X", "increases", "Y"),
            "A2": _stmt("A2", "Y", "increases", "Z"),
        }
        edges = CandidateGenerator(triples).generate()
        keys = {(e.source_uid, e.target_uid) for e in edges}
        assert len(keys) == len(edges)

    def test_ignores_meta_as_nodes(self):
        triples = {
            "M1": _stmt("M1", "A", "decomposed_into", "B", type_="META"),
            "A": _stmt("A", "A", "increases", "X"),
            "B": _stmt("B", "B", "increases", "Y"),
            "X": _stmt("X", "X", "reduces", "B"),
        }
        edges = CandidateGenerator(triples).generate()
        for e in edges:
            assert e.source_uid != "M1"
            assert e.target_uid != "M1"