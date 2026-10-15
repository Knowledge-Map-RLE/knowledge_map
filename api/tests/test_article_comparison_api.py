"""API не выдаёт сохранённое сравнение без доступа ко всем участникам."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from domain.article_maps import ArticleMapAccessDenied
from infrastructure.neo4j.article_comparisons_repository import Neo4jArticleComparisonsRepository
from web.routers import article_comparisons as routes


class Maps:
    def __init__(self): self.calls = []
    def authorize(self, article, user):
        self.calls.append(article)
        if article == "foreign": raise ArticleMapAccessDenied("Foreign article")


class Saved:
    pair_filters = {}
    def __init__(self, maps): self.maps = maps
    def get(self, cid, user):
        if cid == "missing": return None
        result = {"references": [{"article_id": "target"}, {"article_id": "foreign" if cid == "denied" else "source"}]}
        Neo4jArticleComparisonsRepository._access(self, result, user)
        return result
    def pairs(self, cid, user, **kwargs):
        self.get(cid, user)
        type(self).pair_filters = kwargs
        return {"total": 0, "pairs": []}


@pytest.fixture
def client(monkeypatch):
    app = FastAPI(); app.include_router(routes.router, prefix="/api")
    maps = Maps()
    app.dependency_overrides[routes.repository] = lambda: maps
    app.dependency_overrides[routes.get_current_user] = lambda: {"uid": "owner"}
    monkeypatch.setattr(routes, "Neo4jArticleComparisonsRepository", Saved)
    with TestClient(app) as client: yield client, maps


def test_all_participant_access_checks_and_not_found(client):
    http, maps = client
    assert http.get("/api/article_editor/comparisons/good").status_code == 200
    assert maps.calls == ["target", "source"]
    assert http.get("/api/article_editor/comparisons/denied").status_code == 403
    assert http.get("/api/article_editor/comparisons/denied/pairs").status_code == 403
    assert http.get("/api/article_editor/comparisons/missing").status_code == 404


def test_invalid_modes_pagination_and_extra_reference_fields_rejected(client):
    http, _ = client
    assert http.get("/api/article_editor/comparisons/good/pairs?mode=typed_edges").status_code == 422
    assert http.get("/api/article_editor/comparisons/good/pairs?limit=1000").status_code == 422
    body = {"target": {"article_id": "a", "pipeline_id": "text_reified", "run_id": "r", "latest": True}, "sources": []}
    assert http.post("/api/article_editor/comparisons", json=body).status_code == 422


def test_selected_source_knowledge_filter_is_forwarded(client):
    http, _ = client
    assert http.get("/api/article_editor/comparisons/good/pairs?left_knowledge_id=K5&source_article_id=source&right_knowledge_id=K8&limit=1").status_code == 200
    assert Saved.pair_filters["right_knowledge_id"] == "K8"
    assert Saved.pair_filters["limit"] == 1
