"""Юнит-тесты дружбы и BFS-сортировки в SocialNetworkService.

Подменяет neomodel db (services.social_network_service.db) синтетическим
объектом FakeDb, возвращающим строки по подстроке запроса, чтобы проверить
поток «заявка → подтверждение», public-список друзей и расстояния по графу
дружбы без реального Neo4j.
"""
from __future__ import annotations

import services.social_network_service as svc
from services.social_network_service import SocialNetworkService


class FakeDb:
    """Симуляция neomodel db.cypher_query.

    Ответы задаются подстроками запроса ``(pattern, rows)`` или callable
    ``(query, params) -> rows | None`` (None — продолжить поиск).
    """

    def __init__(self, responses=None):
        self.queries: list = []
        self.responses = list(responses or [])

    def cypher_query(self, query, params=None):
        params = params or {}
        self.queries.append((query, params))
        for response in self.responses:
            if callable(response):
                rows = response(query, params)
                if rows is not None:
                    return rows, None
            else:
                pattern, rows = response
                if pattern in query:
                    return rows, None
        return [], None


def _count_queries(fake_db: FakeDb, *substrings: str) -> list[tuple[str, dict]]:
    return [
        (q, p)
        for q, p in fake_db.queries
        if all(sub in q for sub in substrings)
    ]


def _make_svc(monkeypatch, fake_db: FakeDb) -> SocialNetworkService:
    monkeypatch.setattr(svc, "db", fake_db)
    return SocialNetworkService()


# ── send_friend_request ───────────────────────────────────────────────────────

def test_send_friend_request_creates_edge(monkeypatch):
    fake = FakeDb()
    service = _make_svc(monkeypatch, fake)

    result = service.send_friend_request("a", "b")

    assert result == {"success": True, "status": "requested"}
    created = _count_queries(fake, "FRIEND_REQUEST", "CREATE")
    assert len(created) == 1
    request_query, params = created[0]
    assert params["a"] == "a"
    assert params["b"] == "b"


def test_send_friend_request_self_friend(monkeypatch):
    fake = FakeDb()
    service = _make_svc(monkeypatch, fake)
    assert service.send_friend_request("a", "a") == {
        "success": False, "error": "self_friend"}


def test_send_friend_request_already_friends(monkeypatch):
    fake = FakeDb([("MATCH (a:User {uid: $a})-[:FRIEND]-(b", [[1]])])
    service = _make_svc(monkeypatch, fake)
    result = service.send_friend_request("a", "b")
    assert result == {"success": True, "status": "friends"}
    assert not _count_queries(fake, "FRIEND_REQUEST", "CREATE")


def test_send_friend_request_outgoing_duplicate(monkeypatch):
    fake = FakeDb([
        ("-[:FRIEND_REQUEST]->", [[1]]),
    ])
    service = _make_svc(monkeypatch, fake)
    result = service.send_friend_request("a", "b")
    assert result == {"success": True, "status": "requested"}
    assert not _count_queries(fake, "FRIEND_REQUEST", "CREATE")


def test_send_friend_request_accepts_incoming(monkeypatch):
    def _answer(query, params):
        if "FRIEND_REQUEST" not in query or "RETURN count" not in query:
            return None
        if "<-" in query:
            return [[1]]
        if params.get("a") == "b" and params.get("b") == "a":
            return [[1]]
        return [[0]]

    fake = FakeDb([_answer])
    service = _make_svc(monkeypatch, fake)
    result = service.send_friend_request("a", "b")
    assert result["status"] == "friends"
    assert result["is_friend"] is True
    assert _count_queries(fake, "FRIEND {created_at: $ts}]->(b)")


# ── accept / decline / cancel ─────────────────────────────────────────────────

def test_accept_friend_request(monkeypatch):
    fake = FakeDb([
        ("FRIEND_REQUEST", [[1]]),
        ("RETURN count(*) AS c", [[0]]),
    ])
    service = _make_svc(monkeypatch, fake)
    result = service.accept_friend_request("a", "b")
    assert result == {"success": True, "is_friend": True}
    assert _count_queries(fake, "DELETE r")
    assert _count_queries(fake, "CREATE (a)-[:FRIEND")


def test_accept_friend_request_without_request(monkeypatch):
    fake = FakeDb()
    service = _make_svc(monkeypatch, fake)
    assert service.accept_friend_request("a", "b") == {
        "success": False, "error": "request_not_found"}


def test_decline_friend_request(monkeypatch):
    fake = FakeDb([("FRIEND_REQUEST", [[1]])])
    service = _make_svc(monkeypatch, fake)
    result = service.decline_friend_request("a", "b")
    assert result == {"success": True, "status": "none"}
    assert _count_queries(fake, "DELETE r")


def test_decline_friend_request_without_request(monkeypatch):
    fake = FakeDb()
    service = _make_svc(monkeypatch, fake)
    assert service.decline_friend_request("a", "b") == {
        "success": False, "error": "request_not_found"}


def test_cancel_friend_request(monkeypatch):
    fake = FakeDb([("FRIEND_REQUEST", [[1]])])
    service = _make_svc(monkeypatch, fake)
    result = service.cancel_friend_request("a", "b")
    assert result == {"success": True, "status": "none"}
    assert _count_queries(fake, "DELETE r")


def test_cancel_friend_request_without_request(monkeypatch):
    fake = FakeDb()
    service = _make_svc(monkeypatch, fake)
    assert service.cancel_friend_request("a", "b") == {
        "success": False, "error": "request_not_found"}


# ── list_friend_requests ──────────────────────────────────────────────────────

def test_list_friend_requests(monkeypatch):
    fake = FakeDb([
        ("<-[:FRIEND_REQUEST]", [[{
            "uid": "x", "login": "x", "nickname": "X",
        }]]),
        ("-[:FRIEND_REQUEST]->", [[{
            "uid": "y", "login": "y", "nickname": "Y",
        }]]),
    ])
    service = _make_svc(monkeypatch, fake)
    requests = service.list_friend_requests("me")
    assert len(requests["incoming"]) == 1
    assert requests["incoming"][0]["login"] == "x"
    assert requests["incoming"][0]["nickname"] == "X"
    assert len(requests["outgoing"]) == 1
    assert requests["outgoing"][0]["login"] == "y"


# ── BFS-дистанции ─────────────────────────────────────────────────────────────

def test_bfs_distances_shortest_path(monkeypatch):
    fake = FakeDb([
        ("RETURN a.uid, b.uid", [["a", "b"], ["b", "c"], ["c", "d"]]),
    ])
    service = _make_svc(monkeypatch, fake)
    distances = service._bfs_distances("a")
    assert distances == {"a": 0, "b": 1, "c": 2, "d": 3}


def test_bfs_distances_respects_max_depth(monkeypatch):
    fake = FakeDb([
        ("RETURN a.uid, b.uid", [["a", "b"], ["b", "c"]]),
    ])
    service = _make_svc(monkeypatch, fake)
    assert service._bfs_distances("a", max_depth=1) == {"a": 0, "b": 1}
    assert service._bfs_distances("a", max_depth=2) == {"a": 0, "b": 1, "c": 2}


def test_bfs_beyond_six_hops_excluded(monkeypatch):
    edges = [[f"u{i}", f"u{i + 1}"] for i in range(8)]
    fake = FakeDb([("RETURN a.uid, b.uid", edges)])
    service = _make_svc(monkeypatch, fake)
    distances = service._bfs_distances("u0")
    assert distances["u6"] == 6
    assert "u7" not in distances
    assert "u8" not in distances


# ── list_public_friends ───────────────────────────────────────────────────────

def test_list_public_friends_alphabetical_for_guest(monkeypatch):
    friends = [
        {"uid": "c", "login": "c", "nickname": "Charlie"},
        {"uid": "b", "login": "b", "nickname": "Bravo"},
    ]
    fake = FakeDb([
        ("RETURN f ORDER BY f.nickname", [[f] for f in friends]),
    ])
    service = _make_svc(monkeypatch, fake)
    result = service.list_public_friends("t", viewer_uid=None)
    assert [f["login"] for f in result] == ["c", "b"]
    assert all("distance" not in f for f in result)


def test_list_public_friends_no_distance_for_self(monkeypatch):
    friends = [
        {"uid": "b", "login": "b", "nickname": "Bravo"},
    ]
    fake = FakeDb([
        ("RETURN f ORDER BY f.nickname", [[f] for f in friends]),
    ])
    service = _make_svc(monkeypatch, fake)
    result = service.list_public_friends("me", viewer_uid="me")
    assert len(result) == 1
    assert "distance" not in result[0]


def test_list_public_friends_sorted_by_distance(monkeypatch):
    friends = [
        {"uid": "z", "login": "z", "nickname": "Zulu"},
        {"uid": "c", "login": "c", "nickname": "Charlie"},
        {"uid": "b", "login": "b", "nickname": "Bravo"},
    ]
    fake = FakeDb([
        ("RETURN a.uid, b.uid", [["a", "b"], ["b", "c"]]),
        ("RETURN f ORDER BY f.nickname", [[f] for f in friends]),
    ])
    service = _make_svc(monkeypatch, fake)
    result = service.list_public_friends("t", viewer_uid="a")
    assert [f["uid"] for f in result] == ["b", "c", "z"]
    assert result[0]["distance"] == 1
    assert result[1]["distance"] == 2
    assert result[2]["distance"] is None