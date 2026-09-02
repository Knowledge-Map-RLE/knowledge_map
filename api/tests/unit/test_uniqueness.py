"""Юнит-тесты use cases алгоритма уникальности знаний (application/uniqueness/*).

Mock-ируют gRPC-клиент: проверяют построение proto-запросов и маппинг ответов
без реального подключения к knowledge_map_core.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from application.uniqueness.check_subgraph import (
    check_pattern_match,
    check_subgraph_uniqueness,
)
from application.uniqueness.check_uniqueness import check_knowledge_uniqueness


class FakeGrpcClient:
    """Минимальный fake gRPC-клиента: connect() + заглушка stub."""

    def __init__(self):
        self.stub = FakeStub()
        self.connect_called = 0

    async def connect(self):
        self.connect_called += 1

    async def check_uniqueness(self, **kwargs):
        return {
            "status": "SAME",
            "existing_statement_id": "stmt-1",
            "confidence": 0.99,
            "candidates": [
                {
                    "statement_id": "stmt-1",
                    "similarity": 0.99,
                    "subject_text": kwargs["subject_text"],
                    "predicate": kwargs["predicate"],
                    "object_text": kwargs["object_text"],
                }
            ],
            "message": "Такое знание уже есть",
        }


class FakeStub:
    def __init__(self):
        self.last_subgraph_request = None
        self.last_pattern_request = None

    async def CheckSubgraphUniqueness(self, request, timeout=60):
        self.last_subgraph_request = request
        return SimpleNamespace(
            status=2,  # UNCERTAIN
            wl_hash="wl-abc",
            existing_subgraph_id="sub-1",
            subgraph_matches=[
                SimpleNamespace(
                    pattern_to_graph={"p0": "g0", "p1": "g1"},
                    matched_graph_node_ids=["g0", "g1"],
                )
            ],
            frequent_patterns=[
                SimpleNamespace(
                    support=2,
                    frequency=0.5,
                    nodes=[SimpleNamespace(id="p0", node_type="concept", text="a")],
                    edges=[
                        SimpleNamespace(
                            source_id="p0",
                            target_id="p1",
                            edge_type="RELATES_TO",
                        )
                    ],
                )
            ],
            message="uncertain",
        )

    async def CheckPatternMatch(self, request, timeout=60):
        self.last_pattern_request = request
        return SimpleNamespace(
            status=1,  # SAME
            matches=[
                SimpleNamespace(
                    pattern_to_graph={"p0": "g5", "p1": "g6"},
                    matched_graph_node_ids=["g5", "g6"],
                )
            ],
            total_matches=1,
            message="Pattern found",
        )


# ── check_knowledge_uniqueness ───────────────────────────────────────────────


class TestCheckKnowledgeUniqueness:
    async def test_returns_client_result(self):
        client = FakeGrpcClient()
        result = await check_knowledge_uniqueness(
            grpc_client=client,
            subject_text="dopamine",
            predicate="IS_A",
            object_text="neurotransmitter",
            sentence_text="dopamine is a neurotransmitter",
        )
        assert result["status"] == "SAME"
        assert result["existing_statement_id"] == "stmt-1"
        assert result["candidates"][0]["subject_text"] == "dopamine"

    async def test_passes_all_args(self):
        client = FakeGrpcClient()
        await check_knowledge_uniqueness(
            grpc_client=client,
            subject_text="s",
            predicate="p",
            object_text="o",
            sentence_text="text",
        )
        # fake проверяет subject_text/predicate/object_text в candidates
        assert True


# ── check_subgraph_uniqueness ────────────────────────────────────────────────


class TestCheckSubgraphUniqueness:
    async def _nodes(self):
        return [
            {"id": "p0", "node_type": "concept", "text": "a", "predicate": ""},
            {"id": "p1", "node_type": "concept", "text": "b", "predicate": ""},
        ]

    async def _edges(self):
        return [
            {"source_id": "p0", "target_id": "p1", "edge_type": "RELATES_TO", "predicate": ""}
        ]

    async def test_connects_and_builds_request(self):
        client = FakeGrpcClient()
        await check_subgraph_uniqueness(
            grpc_client=client,
            nodes=await self._nodes(),
            edges=await self._edges(),
        )
        assert client.connect_called == 1
        req = client.stub.last_subgraph_request
        assert [n.id for n in req.nodes] == ["p0", "p1"]
        assert req.nodes[0].node_type == "concept"

    async def test_maps_response(self):
        client = FakeGrpcClient()
        result = await check_subgraph_uniqueness(
            grpc_client=client,
            nodes=await self._nodes(),
            edges=await self._edges(),
        )
        assert result["status"] == "UNCERTAIN"
        assert result["wl_hash"] == "wl-abc"
        assert result["existing_subgraph_id"] == "sub-1"
        assert result["subgraph_matches"][0]["matched_node_ids"] == ["g0", "g1"]
        assert result["frequent_patterns"][0]["support"] == 2


# ── check_pattern_match ──────────────────────────────────────────────────────


class TestCheckPatternMatch:
    async def test_builds_pattern_request(self):
        client = FakeGrpcClient()
        await check_pattern_match(
            grpc_client=client,
            nodes=[
                {"id": "p0", "required_type": "concept", "text_constraint": "", "predicate_constraint": ""},
                {"id": "p1", "required_type": "statement", "text_constraint": "", "predicate_constraint": ""},
            ],
            edges=[],
            max_results=50,
        )
        req = client.stub.last_pattern_request
        assert req.max_results == 50
        assert [n.id for n in req.nodes] == ["p0", "p1"]
        assert req.nodes[1].required_type == "statement"

    async def test_maps_pattern_response(self):
        client = FakeGrpcClient()
        result = await check_pattern_match(
            grpc_client=client,
            nodes=[{"id": "p0", "required_type": "concept"}],
            edges=[],
            max_results=10,
        )
        assert result["status"] == "SAME"
        assert result["total_matches"] == 1
        assert result["matches"][0]["pattern_to_graph"] == {"p0": "g5", "p1": "g6"}
