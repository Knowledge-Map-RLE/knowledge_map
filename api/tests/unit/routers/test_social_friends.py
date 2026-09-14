"""Юнит-тесты REST-роутера /api/social/* (дружба и публичные друзья).

Подменяет neomodel db и зависимости аутентификации, чтобы проверить HTTP-слой
без реального Neo4j и auth.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import services.social_network_service as svc
from web import dependencies
from web.app import app


class FakeDb:
    """Симуляция neomodel db.cypher_query по подстроке запроса."""

    def __init__(self, responses=None):
        self.queries: list = []
        self.responses = list(responses or [])

    def cypher_query(self, query, params=None):
        self.queries.append((query, params or {}))
        for pattern, rows in self.responses:
            if pattern in query:
                return rows, None
        return [], None


_USER_T = {"uid": "t", "login": "t", "nickname": "T"}


@pytest.fixture
def client_anon(monkeypatch):
    fake = FakeDb()
    monkeypatch.setattr(svc, "db", fake)

    async def fake_optional_user():
        return None

    app.dependency_overrides[dependencies.get_optional_user] = fake_optional_user
    test_client = TestClient(app)
    yield test_client, fake
    app.dependency_overrides.clear()


@pytest.fixture
def client_auth(monkeypatch):
    fake = FakeDb()
    monkeypatch.setattr(svc, "db", fake)

    async def fake_current_user():
        return {"uid": "me", "login": "me", "nickname": "Me"}

    async def fake_optional_user():
        return {"uid": "me", "login": "me", "nickname": "Me"}

    app.dependency_overrides[dependencies.get_current_user] = fake_current_user
    app.dependency_overrides[dependencies.get_optional_user] = fake_optional_user
    test_client = TestClient(app)
    yield test_client, fake
    app.dependency_overrides.clear()


def _seen(fake: FakeDb, *substrings: str) -> bool:
    return any(all(s in q for s in substrings) for q, _ in fake.queries)


# ── Публичные друзья профиля ─────────────────────────────────────────────────

def test_user_friends_alphabetical_for_anon(client_anon):
    test_client, fake = client_anon
    fake.responses = [
        ("RETURN u", [[_USER_T]]),
        ("RETURN f ORDER BY f.nickname", [[
            {"uid": "b", "login": "b", "nickname": "Bravo"},
        ]]),
    ]
    resp = test_client.get("/api/social/users/t/friends")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["friends"][0]["login"] == "b"
    assert "distance" not in body["friends"][0]


def test_user_friends_sorted_by_distance_for_auth(client_auth):
    test_client, fake = client_auth
    fake.responses = [
        ("RETURN u", [[_USER_T]]),
        ("RETURN a.uid, b.uid", [["me", "b"], ["b", "c"]]),
        ("RETURN f ORDER BY f.nickname", [[
            {"uid": "c", "login": "c", "nickname": "Charlie"},
        ], [
            {"uid": "b", "login": "b", "nickname": "Bravo"},
        ]]),
    ]
    resp = test_client.get("/api/social/users/t/friends")
    assert resp.status_code == 200
    friend_uids = [f["uid"] for f in resp.json()["friends"]]
    assert friend_uids == ["b", "c"]
    assert resp.json()["friends"][0]["distance"] == 1
    assert resp.json()["friends"][1]["distance"] == 2


def test_user_friends_404(client_anon):
    test_client, fake = client_anon
    assert test_client.get("/api/social/users/missing/friends").status_code == 404


# ── Отправка / приём заявки ──────────────────────────────────────────────────

def test_send_friend_request(client_auth):
    test_client, fake = client_auth
    resp = test_client.post("/api/social/friends/b")
    assert resp.status_code == 200
    assert resp.json() == {"success": True, "status": "requested"}
    assert _seen(fake, "FRIEND_REQUEST", "CREATE")


def test_self_friend_400(client_auth):
    test_client, fake = client_auth
    resp = test_client.post("/api/social/friends/me")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "self_friend"


def test_accept_friend_request(client_auth):
    test_client, fake = client_auth
    fake.responses = [
        ("FRIEND_REQUEST", [[1]]),
        ("RETURN count(*) AS c", [[0]]),
    ]
    resp = test_client.post("/api/social/friends/b/accept")
    assert resp.status_code == 200
    assert resp.json()["is_friend"] is True
    assert _seen(fake, "CREATE (a)-[:FRIEND")


def test_accept_friend_request_without_request_400(client_auth):
    test_client, fake = client_auth
    resp = test_client.post("/api/social/friends/b/accept")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "request_not_found"


def test_decline_friend_request(client_auth):
    test_client, fake = client_auth
    fake.responses = [("FRIEND_REQUEST", [[1]])]
    resp = test_client.post("/api/social/friends/b/decline")
    assert resp.status_code == 200
    assert resp.json() == {"success": True, "status": "none"}
    assert _seen(fake, "DELETE r")


def test_cancel_friend_request(client_auth):
    test_client, fake = client_auth
    fake.responses = [("FRIEND_REQUEST", [[1]])]
    resp = test_client.post("/api/social/friends/b/cancel")
    assert resp.status_code == 200
    assert resp.json() == {"success": True, "status": "none"}
    assert _seen(fake, "DELETE r")


# ── Список заявок ────────────────────────────────────────────────────────────

def test_list_friend_requests(client_auth):
    test_client, fake = client_auth
    fake.responses = [
        ("<-[:FRIEND_REQUEST]", [[
            {"uid": "x", "login": "x", "nickname": "X"},
        ]]),
        ("-[:FRIEND_REQUEST]->", [[
            {"uid": "y", "login": "y", "nickname": "Y"},
        ]]),
    ]
    resp = test_client.get("/api/social/friends/requests")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["incoming"][0]["login"] == "x"
    assert body["outgoing"][0]["login"] == "y"