from __future__ import annotations

import networkx as nx
import pytest

from src.domain.uniqueness import (
    CanonicalStatement,
    CandidateSubgraph,
    EdgeType,
    PatternEdge,
    PatternGraph,
    PatternNode,
    Polarity,
    StatementNodeType,
    SubgraphEdge,
    SubgraphNode,
    UniquenessStatus,
)
from src.infrastructure.frequent_miner import FSGMiner, GastonMiner, GSpanMiner
from src.infrastructure.subgraph_matcher import SubgraphMatcherVF2
from src.infrastructure.wl_hasher import compute_wl_hash


# ── CanonicalStatement.fingerprint ────────────────────────────────────────────


class TestCanonicalFingerprint:
    def test_is_deterministic(self):
        s1 = CanonicalStatement(
            subject_id="c0", subject_text="dopamine",
            predicate="IS_A", object_id="c1", object_text="neurotransmitter",
        )
        s2 = CanonicalStatement(
            subject_id="c0", subject_text="dopamine",
            predicate="IS_A", object_id="c1", object_text="neurotransmitter",
        )
        assert s1.fingerprint() == s2.fingerprint()

    def test_sensitive_to_object(self):
        a = CanonicalStatement("c0", "a", "IS_A", "c1", "b")
        b = CanonicalStatement("c0", "a", "IS_A", "c2", "b")
        assert a.fingerprint() != b.fingerprint()

    def test_sensitive_to_predicate(self):
        a = CanonicalStatement("c0", "a", "IS_A", "c1", "b")
        b = CanonicalStatement("c0", "a", "CAUSES", "c1", "b")
        assert a.fingerprint() != b.fingerprint()

    def test_sensitive_to_polarity(self):
        a = CanonicalStatement("c0", "a", "IS_A", "c1", "b", Polarity.POSITIVE)
        b = CanonicalStatement("c0", "a", "IS_A", "c1", "b", Polarity.NEGATIVE)
        assert a.fingerprint() != b.fingerprint()

    def test_returns_sha256_hex(self):
        s = CanonicalStatement("c0", "a", "IS_A", "c1", "b")
        assert len(s.fingerprint()) == 64
        int(s.fingerprint(), 16)  # is valid hex


# ── CandidateSubgraph ─────────────────────────────────────────────────────────


class TestCandidateSubgraph:
    def _subgraph(self) -> CandidateSubgraph:
        return CandidateSubgraph(
            nodes=[
                SubgraphNode("n0", StatementNodeType.CONCEPT, text="a"),
                SubgraphNode("n1", StatementNodeType.STATEMENT, text="b"),
            ],
            edges=[
                SubgraphEdge("n0", "n1", EdgeType.RELATES_TO, predicate="IS_A"),
            ],
        )

    def test_node_count(self):
        assert self._subgraph().node_count == 2

    def test_edge_count(self):
        assert self._subgraph().edge_count == 1

    def test_node_ids(self):
        assert self._subgraph().node_ids == ["n0", "n1"]


# ── compute_wl_hash ───────────────────────────────────────────────────────────


class TestWLHash:
    def _candidate(self) -> CandidateSubgraph:
        return CandidateSubgraph(
            nodes=[
                SubgraphNode("n0", StatementNodeType.CONCEPT, text="dopamine"),
                SubgraphNode("n1", StatementNodeType.CONCEPT, text="parkinson"),
            ],
            edges=[
                SubgraphEdge("n0", "n1", EdgeType.RELATES_TO, predicate="CAUSES"),
            ],
        )

    def test_deterministic(self):
        assert compute_wl_hash(self._candidate()) == compute_wl_hash(self._candidate())

    def test_sensitive_to_node_type(self):
        a = self._candidate()
        b = CandidateSubgraph(
            nodes=[
                SubgraphNode("n0", StatementNodeType.STATEMENT, text="dopamine"),
                SubgraphNode("n1", StatementNodeType.CONCEPT, text="parkinson"),
            ],
            edges=[SubgraphEdge("n0", "n1", EdgeType.RELATES_TO, predicate="CAUSES")],
        )
        assert compute_wl_hash(a) != compute_wl_hash(b)

    def test_sensitive_to_text(self):
        a = self._candidate()
        b = CandidateSubgraph(
            nodes=[
                SubgraphNode("n0", StatementNodeType.CONCEPT, text="serotonin"),
                SubgraphNode("n1", StatementNodeType.CONCEPT, text="parkinson"),
            ],
            edges=[SubgraphEdge("n0", "n1", EdgeType.RELATES_TO, predicate="CAUSES")],
        )
        assert compute_wl_hash(a) != compute_wl_hash(b)

    def test_sensitive_to_structure(self):
        """Разные структуры (ребро стороне наоборот / другое ребро) дают разные хеши."""
        two_edge = CandidateSubgraph(
            nodes=[
                SubgraphNode("n0", StatementNodeType.CONCEPT, text="dopamine"),
                SubgraphNode("n1", StatementNodeType.CONCEPT, text="parkinson"),
            ],
            edges=[
                SubgraphEdge("n0", "n1", EdgeType.RELATES_TO, predicate="CAUSES"),
                SubgraphEdge("n1", "n0", EdgeType.RELATES_TO, predicate="SUPPORTS"),
            ],
        )
        assert compute_wl_hash(self._candidate()) != compute_wl_hash(two_edge)

    def test_empty_returns_empty(self):
        assert compute_wl_hash(CandidateSubgraph()) == ""

    def test_permutation_invariance(self):
        """Порядок узлов не должен менять хеш изоморфного подграфа."""
        a = self._candidate()
        b = CandidateSubgraph(
            nodes=[
                SubgraphNode("n1", StatementNodeType.CONCEPT, text="parkinson"),
                SubgraphNode("n0", StatementNodeType.CONCEPT, text="dopamine"),
            ],
            edges=[SubgraphEdge("n0", "n1", EdgeType.RELATES_TO, predicate="CAUSES")],
        )
        assert compute_wl_hash(a) == compute_wl_hash(b)


# ── SubgraphMatcherVF2 ────────────────────────────────────────────────────────


class TestSubgraphMatcherVF2:
    def _host_graph(self) -> nx.DiGraph:
        g = nx.DiGraph()
        g.add_node("g0", node_type="concept", text="dopamine")
        g.add_node("g1", node_type="concept", text="parkinson")
        g.add_node("g2", node_type="statement", text="s")
        g.add_edge("g0", "g1", edge_type="RELATES_TO", predicate="CAUSES")
        g.add_edge("g1", "g2", edge_type="RELATES_TO", predicate="TREATS")
        return g

    def _pattern(self) -> PatternGraph:
        return PatternGraph(
            nodes=[
                PatternNode(id="p0", required_type=StatementNodeType.CONCEPT),
                PatternNode(id="p1", required_type=StatementNodeType.CONCEPT),
            ],
            edges=[
                PatternEdge(
                    source_id="p0",
                    target_id="p1",
                    required_edge_type=EdgeType.RELATES_TO,
                ),
            ],
        )

    @pytest.mark.asyncio
    async def test_finds_matching_subgraph(self):
        matcher = SubgraphMatcherVF2()
        result = await matcher.find_pattern_matches(self._pattern(), host_graph=self._host_graph())
        assert result.status == UniquenessStatus.SAME
        assert result.total_matches >= 1
        assert result.matches[0].matched_graph_node_ids

    @pytest.mark.asyncio
    async def test_type_mismatch_rejects(self):
        """Паттерн на STATEMENT не должен совпасть на concept-подграфе."""
        pattern = PatternGraph(
            nodes=[
                PatternNode(id="p0", required_type=StatementNodeType.STATEMENT),
                PatternNode(id="p1", required_type=StatementNodeType.CONCEPT),
            ],
            edges=[PatternEdge("p0", "p1", required_edge_type=EdgeType.RELATES_TO)],
        )
        matcher = SubgraphMatcherVF2()
        result = await matcher.find_pattern_matches(pattern, host_graph=self._host_graph())
        assert result.total_matches == 0
        assert result.status == UniquenessStatus.NEW

    @pytest.mark.asyncio
    async def test_no_host_returns_new(self):
        matcher = SubgraphMatcherVF2()
        result = await matcher.find_pattern_matches(self._pattern(), host_graph=None)
        assert result.status == UniquenessStatus.NEW

    @pytest.mark.asyncio
    async def test_find_occurrences_empty_for_no_host(self):
        matcher = SubgraphMatcherVF2()
        candidate = CandidateSubgraph(
            nodes=[SubgraphNode("n0", StatementNodeType.CONCEPT)],
            edges=[],
        )
        matches = await matcher.find_occurrences(candidate, host_graph=None)
        assert matches == []

    def _host_with_parallel_predicates(self) -> nx.DiGraph:
        """Ребро между парой концептов несёт набор предикатов (limit + neutralize)."""
        g = nx.DiGraph()
        g.add_node("g0", node_type="concept", text="vitamin D")
        g.add_node("g1", node_type="concept", text="oxidative stress")
        g.add_edge("g0", "g1", edge_type="RELATES_TO", predicates={"limit", "neutralize"})
        return g

    def _predicate_pattern(self, predicate: str) -> PatternGraph:
        return PatternGraph(
            nodes=[
                PatternNode(id="p0", required_type=StatementNodeType.CONCEPT, text_constraint="vitamin D"),
                PatternNode(id="p1", required_type=StatementNodeType.CONCEPT, text_constraint="oxidative stress"),
            ],
            edges=[
                PatternEdge("p0", "p1", required_edge_type=EdgeType.RELATES_TO, predicate_constraint=predicate),
            ],
        )

    @pytest.mark.asyncio
    async def test_edge_predicate_set_matches_any_preserved_predicate(self):
        """Загрузчик сохраняет все предикаты ребра; каждый из них должен матчиться."""
        matcher = SubgraphMatcherVF2()
        host = self._host_with_parallel_predicates()
        r_limit = await matcher.find_pattern_matches(self._predicate_pattern("limit"), host)
        r_neut = await matcher.find_pattern_matches(self._predicate_pattern("neutralize"), host)
        assert r_limit.total_matches == 1
        assert r_neut.total_matches == 1

    @pytest.mark.asyncio
    async def test_edge_predicate_set_rejects_missing_predicate(self):
        matcher = SubgraphMatcherVF2()
        host = self._host_with_parallel_predicates()
        result = await matcher.find_pattern_matches(self._predicate_pattern("nonexistent"), host)
        assert result.total_matches == 0
        assert result.status == UniquenessStatus.NEW


# ── Frequent miners (gSpan / Gaston / FSG) ────────────────────────────────────


def _frequent_graph() -> nx.DiGraph:
    g = nx.DiGraph()
    # два схожих подграфа (повторяющееся ребро CAUSES)
    g.add_node("a", node_type="concept", predicate="")
    g.add_node("b", node_type="concept", predicate="")
    g.add_node("c", node_type="concept", predicate="")
    g.add_node("d", node_type="concept", predicate="")
    g.add_edge("a", "b", edge_type="RELATES_TO", predicate="CAUSES")
    g.add_edge("c", "d", edge_type="RELATES_TO", predicate="CAUSES")
    return g


class TestFrequentMiners:
    def test_gspan_finds_repeated_edge(self):
        miner = GSpanMiner(min_support=2, max_edges=5)
        patterns = miner.mine(_frequent_graph())
        assert len(patterns) >= 1
        assert all(p.support >= 2 for p in patterns)

    def test_gaston_returns_patterns(self):
        miner = GastonMiner(min_support=2, max_size=5)
        patterns = miner.mine(_frequent_graph())
        assert len(patterns) >= 1

    def test_fsg_finds_frequent_edges(self):
        miner = FSGMiner(min_support=2, max_size=5)
        patterns = miner.mine(_frequent_graph())
        assert len(patterns) >= 1
        assert all(p.support >= 2 for p in patterns)

    def test_miners_empty_on_isolated_nodes(self):
        g = nx.DiGraph()
        g.add_node("x")
        g.add_node("y")
        for miner in (GSpanMiner(min_support=2), GastonMiner(min_support=2), FSGMiner(min_support=2)):
            assert miner.mine(g) == []

    def test_support_respects_min_support(self):
        miner = FSGMiner(min_support=3, max_size=5)
        # только 2 ребра CAUSES → support < 3 → нет частых паттернов
        assert miner.mine(_frequent_graph()) == []
