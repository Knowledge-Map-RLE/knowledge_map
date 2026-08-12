"""Тесты привязки автора (created_by_uid) к статьям, стейтментам и блокам.

Сценарии:
  1. _author_from_user_node: None и словари с fallback логина.
  2. create_article проставляет created_by_uid.
  3. save_statements / save_blocks передают создателя в cypher-батчи.
  4. get_article / get_blocks / list_articles включают author в ответ.
"""

import asyncio

from unittest.mock import AsyncMock

import services.article_editor_service as svc
from services.article_editor_service import ArticleEditorService, _author_from_user_node


# ── _author_from_user_node ─────────────────────────────────────────────────────

def test_author_from_user_node_none():
    assert _author_from_user_node(None) is None


def test_author_from_user_node_full():
    node = {"uid": "u1", "login": "bob", "nickname": "Bob"}
    assert _author_from_user_node(node) == {
        "uid": "u1", "login": "bob", "nickname": "Bob",
    }


def test_author_from_user_node_falls_back_to_login():
    node = {"uid": "u1", "login": "bob"}
    assert _author_from_user_node(node)["nickname"] == "bob"


# ── create_article ─────────────────────────────────────────────────────────────

def test_create_article_sets_created_by_uid(monkeypatch):
    class FakeDoc:
        uid = "doc1"
        title = "Title"
        original_filename = "file.md"
        processing_status = "ready_for_annotation"
        is_processed = False
        upload_date = None

    created: dict = {}

    class FakeDocument:
        def __init__(self, **kwargs):
            created.update(kwargs)

        def save(self):
            return FakeDoc()

    monkeypatch.setattr(svc, "Document", FakeDocument)
    monkeypatch.setattr(svc, "uuid8_str", lambda: "doc1")

    result = asyncio.run(ArticleEditorService().create_article(user_uid="u1", title="Title"))

    assert created["created_by_uid"] == "u1"
    assert result["uid"] == "doc1"


# ── save_statements / save_blocks ──────────────────────────────────────────────

def test_save_statements_passes_creator(monkeypatch):
    service = ArticleEditorService()
    monkeypatch.setattr(service, "get_document_status", AsyncMock(return_value="ready"))
    monkeypatch.setattr(service, "_is_editable_status", lambda _status: True)

    created_batches: list[dict] = []

    def fake_cypher(query, params):
        if "UNWIND $batch AS item" in query:
            created_batches.append(params["batch"])
        return ([], None)

    monkeypatch.setattr(svc.db, "cypher_query", fake_cypher)

    result = asyncio.run(service.save_statements(
        "doc1",
        [{"subject_text": "A", "predicate": "p", "object_text": "B"}],
        user_uid="u1",
    ))

    assert result["success"] is True
    assert created_batches
    assert created_batches[0][0]["creator"] == "u1"


def test_save_blocks_passes_creator(monkeypatch):
    service = ArticleEditorService()
    monkeypatch.setattr(service, "get_document_status", AsyncMock(return_value="ready"))
    monkeypatch.setattr(service, "_is_editable_status", lambda _status: True)

    created_batches: list[dict] = []

    def fake_cypher(query, params):
        if "UNWIND $batch AS item" in query:
            created_batches.append(params["batch"])
        return ([], None)

    monkeypatch.setattr(svc.db, "cypher_query", fake_cypher)

    result = asyncio.run(service.save_blocks(
        "doc1",
        [{"instanceId": "b1", "blockType": 1, "data": {}, "order": 0}],
        user_uid="u1",
    ))

    assert result["success"] is True
    assert created_batches
    assert created_batches[0][0]["creator"] == "u1"


# ── get_article / get_blocks / list_articles ───────────────────────────────────

USER_NODE = {"uid": "u1", "login": "bob", "nickname": "Bob"}


def test_get_article_includes_authors(monkeypatch):
    class FakeDoc:
        uid = "doc1"
        title = "Title"
        original_filename = "file.md"
        processing_status = "ready"
        is_processed = True
        upload_date = None
        created_by_uid = "u1"
        edit_date = None

    class FakeDocument:
        class nodes:
            @staticmethod
            def get_or_none(uid=None):
                return FakeDoc() if uid == "doc1" else None

    monkeypatch.setattr(svc, "Document", FakeDocument)

    def fake_cypher(query, params):
        if "HAS_STATEMENT" in query:
            stmt = {
                "uid": "s1", "subject_text": "A", "predicate": "p", "object_text": "B",
                "subject_type": "concept", "object_type": "concept", "type": "FACT",
                "confidence": 1.0, "sentence_text": "", "sort_order": 0,
            }
            return ([[stmt, USER_NODE]], None)
        return ([[USER_NODE]], None)

    monkeypatch.setattr(svc.db, "cypher_query", fake_cypher)

    article = asyncio.run(ArticleEditorService().get_article("doc1"))

    assert article["author"] == USER_NODE
    assert article["statements"][0]["author"] == USER_NODE


def test_get_blocks_includes_author(monkeypatch):
    def fake_cypher(query, params):
        row = ("blk1", 1, "{}", 0, USER_NODE)
        return ([list(row)], None)

    monkeypatch.setattr(svc.db, "cypher_query", fake_cypher)

    result = asyncio.run(ArticleEditorService().get_blocks("doc1"))

    assert result["success"] is True
    assert result["blocks"][0]["author"] == USER_NODE


def test_list_articles_includes_author(monkeypatch):
    def fake_cypher(query, params):
        rows = [["doc1", "Title", "file.md", "ready", None, "markdown/key", USER_NODE]]
        return (rows, None)

    monkeypatch.setattr(svc.db, "cypher_query", fake_cypher)

    articles = asyncio.run(ArticleEditorService().list_articles())

    assert articles[0]["author"] == USER_NODE
