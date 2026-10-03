from datetime import datetime, timezone
import time

from adapters.repositories.document_repository import (
    DocumentRepository,
    _build_ft_query,
    _row_to_domain,
)
import adapters.repositories.document_repository as repository_module


def _search_row(activity_at):
    return [
        "doc-1", "Biology 5 class", "Biology 5 class", "ready_for_annotation",
        False, "upload", "", "knowledge-map-data", None, None, None, None,
        None, None, False, None, "hash-1", activity_at,
    ]


def _list_row(uid, title, activity_at, processed=False):
    return [
        uid, f"{title}.md", title, "ready_for_annotation", processed, "upload",
        "", "knowledge-map-data", None, None, None, None, None, None, False,
        None, f"hash-{uid}", False, None, activity_at,
    ]


def test_record_user_edit_merges_user_activity(monkeypatch):
    captured = {}

    def fake_cypher(query, params):
        captured["query"] = query
        captured["params"] = params
        return ([[datetime.now(timezone.utc)]], None)

    monkeypatch.setattr(repository_module.db, "cypher_query", fake_cypher)

    assert DocumentRepository().record_user_edit("user-1", "doc-1") is True
    assert "MERGE (u:User {uid: $user_uid})" in captured["query"]
    assert "MERGE (u)-[activity:RECENTLY_EDITED]->(d)" in captured["query"]
    assert captured["params"] == {"user_uid": "user-1", "doc_uid": "doc-1"}


def test_list_all_includes_current_users_documents_and_orders_them_first(monkeypatch):
    captured = []
    edited_at = datetime(2026, 9, 29, 12, 30, tzinfo=timezone.utc)

    def fake_cypher(query, params):
        captured.append((query, params))
        if (
            "MATCH (:User {uid: $user_uid})-[activity:RECENTLY_EDITED]" in query
            and "OPTIONAL MATCH" not in query
        ):
            return ([_list_row("edited", "Edited", edited_at)], None)
        if "MATCH (d:Document {created_by_uid: $user_uid})" in query:
            return ([], None)
        return ([_list_row("regular", "Regular", None, processed=True)], None)

    monkeypatch.setattr(repository_module.db, "cypher_query", fake_cypher)

    docs = DocumentRepository().list_all(full_text_only=True, user_uid="user-1")

    assert [doc.uid for doc in docs] == ["edited", "regular"]
    assert docs[0].current_user_last_edited_at == edited_at
    assert "current_user_last_edited_at DESC" not in captured[-1][0]
    assert "NOT (d.uid IN $personal_uids)" in captured[-1][0]
    assert captured[-1][1]["personal_uids"] == ["edited"]
    assert "OPTIONAL MATCH" not in captured[-1][0]


def test_list_all_maps_created_document_epoch_timestamp(monkeypatch):
    upload_epoch = 1_790_674_200.0
    captured = []

    def fake_cypher(query, params):
        captured.append(query)
        if (
            "MATCH (:User {uid: $user_uid})-[activity:RECENTLY_EDITED]" in query
            and "OPTIONAL MATCH" not in query
        ):
            return ([], None)
        if "MATCH (d:Document {created_by_uid: $user_uid})" in query:
            return ([_list_row("created", "Created", upload_epoch)], None)
        return ([], None)

    monkeypatch.setattr(repository_module.db, "cypher_query", fake_cypher)

    docs = DocumentRepository().list_all(full_text_only=True, user_uid="user-1")

    assert len(docs) == 1
    assert docs[0].current_user_last_edited_at == datetime.fromtimestamp(
        upload_epoch, tz=timezone.utc
    )


def test_personal_full_text_count_adds_only_documents_without_full_text(monkeypatch):
    monkeypatch.setattr(
        DocumentRepository, "_full_text_count_cache", (12, time.monotonic())
    )
    captured = {}

    def fake_cypher(query, params):
        captured["query"] = query
        captured["params"] = params
        return ([[3]], None)

    monkeypatch.setattr(repository_module.db, "cypher_query", fake_cypher)

    assert DocumentRepository().count_full_text(user_uid="user-1") == 15
    assert "MATCH (:User {uid: $user_uid})-[:RECENTLY_EDITED]->(d:Document)" in captured["query"]
    assert "coalesce(d.has_full_text, false) = false" in captured["query"]
    assert captured["params"]["user_uid"] == "user-1"


def test_title_search_returns_recent_personal_document_without_full_text(monkeypatch):
    edited_at = datetime(2026, 9, 29, 12, 30, tzinfo=timezone.utc)
    calls = []

    def fake_cypher(query, params):
        calls.append((query, params))
        if "RETURN count(d) AS total" in query:
            return ([[1]], None)
        return ([_search_row(edited_at)], None)

    monkeypatch.setattr(repository_module.db, "cypher_query", fake_cypher)

    docs, total = DocumentRepository().search(
        "Biology 5 class", full_text_only=True, user_uid="user-1"
    )

    assert total == 1
    assert docs[0].uid == "doc-1"
    assert docs[0].current_user_last_edited_at == edited_at
    assert len(calls) == 2
    assert "user_last_edited_at IS NOT NULL" in calls[0][0]
    assert calls[0][1]["user_uid"] == "user-1"


def test_search_row_maps_personal_edit_timestamp():
    edited_at = datetime(2026, 9, 29, 12, 30, tzinfo=timezone.utc)

    doc = _row_to_domain(
        _search_row(edited_at), activity_index=17, include_gold_fields=False
    )

    assert doc.current_user_last_edited_at == edited_at


def test_search_row_converts_epoch_personal_timestamp():
    upload_epoch = 1_790_674_200.0

    doc = _row_to_domain(
        _search_row(upload_epoch), activity_index=17, include_gold_fields=False
    )

    assert doc.current_user_last_edited_at == datetime.fromtimestamp(
        upload_epoch, tz=timezone.utc
    )


def test_fulltext_query_preserves_cyrillic_title_tokens_and_grade_number():
    assert _build_ft_query("Биология 5 класс") == "Биология AND 5 AND класс"
