"""Юнит-тесты REST-роутера /api/uniqueness/*.

Подменяет get_current_user (auth) и use case-функции алгоритма уникальности,
чтобы проверить HTTP-слой без реальных gRPC/Neo4j/Qdrant.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web import dependencies
from web.app import app


@pytest.fixture
def client():
    async def fake_current_user():
        return {"uid": "test-user", "login": "tester"}

    app.dependency_overrides[dependencies.get_current_user] = fake_current_user
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestUniquenessRouter:
    def test_check_returns_json(self, client, monkeypatch):
        async def fake_check(**kwargs):
            return {
                "status": "DIFFERENT",
                "existing_statement_id": "",
                "confidence": 0.1,
                "candidates": [],
                "message": "knowledge not found",
            }

        monkeypatch.setattr(
            "application.uniqueness.check_uniqueness.check_knowledge_uniqueness",
            fake_check,
        )

        resp = client.post(
            "/api/uniqueness/check",
            json={
                "subject_text": "dopamine",
                "predicate": "IS_A",
                "object_text": "neurotransmitter",
                "sentence_text": "dopamine is a neurotransmitter",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["status"] == "DIFFERENT"

    def test_check_returns_same_for_existing(self, client, monkeypatch):
        async def fake_check(**kwargs):
            return {
                "status": "SAME",
                "existing_statement_id": "stmt-42",
                "confidence": 0.99,
                "candidates": [],
                "message": "Такое знание уже есть",
            }

        monkeypatch.setattr(
            "application.uniqueness.check_uniqueness.check_knowledge_uniqueness",
            fake_check,
        )
        resp = client.post(
            "/api/uniqueness/check",
            json={
                "subject_text": "a",
                "predicate": "IS_A",
                "object_text": "b",
                "sentence_text": "a is b",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["existing_statement_id"] == "stmt-42"

    def test_invalid_body_returns_422(self, client):
        resp = client.post(
            "/api/uniqueness/check",
            json={"subject_text": "only-subject"},
        )
        assert resp.status_code == 422

    def test_add_returns_success(self, client, monkeypatch):
        async def fake_add(**kwargs):
            return {
                "success": True,
                "uniqueness_status": "NEW",
                "statement_id": "stmt-new",
                "existing_statement_id": "",
                "message": "created",
            }

        monkeypatch.setattr(
            "application.uniqueness.add_knowledge.add_knowledge_with_uniqueness",
            fake_add,
        )
        resp = client.post(
            "/api/uniqueness/add",
            json={
                "subject_text": "a",
                "predicate": "IS_A",
                "object_text": "b",
                "sentence_text": "a is b",
                "doc_id": "doc-1",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_check_pattern_returns_matches(self, client, monkeypatch):
        async def fake_pattern(**kwargs):
            return {
                "status": "SAME",
                "matches": [
                    {"pattern_to_graph": {"p0": "g0"}, "matched_node_ids": ["g0"]}
                ],
                "total_matches": 1,
                "message": "found",
            }

        monkeypatch.setattr(
            "application.uniqueness.check_subgraph.check_pattern_match",
            fake_pattern,
        )
        resp = client.post(
            "/api/uniqueness/check-pattern",
            json={
                "nodes": [{"id": "p0", "required_type": "concept"}],
                "edges": [],
                "max_results": 10,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["total_matches"] == 1
