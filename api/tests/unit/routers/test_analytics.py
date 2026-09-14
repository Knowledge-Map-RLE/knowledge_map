"""Юнит-тесты REST-роутера /api/analytics/*.

Подменяет get_analytics_repository / get_optional_user / get_current_admin,
чтобы проверить HTTP-слой без реального Neo4j и auth.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from domain.models.analytics import (
    AnalyticsSummary,
    DailyStats,
    ReferrerStats,
    RouteStats,
)
from web import dependencies
from web.app import app


class FakeAnalyticsRepo:
    def __init__(self):
        self.records = []
        self.summary_url = None

    async def record_page_view(self, visit) -> None:
        self.records.append(visit)

    async def get_analytics_summary(self, from_ts: float, to_ts: float) -> AnalyticsSummary:
        self.summary_url = "called"
        return AnalyticsSummary(
            total_views=11,
            total_sessions=7,
            total_unique_visitors=7,
            start_date="2026-08-14",
            end_date="2026-09-13",
            routes=[RouteStats(route="/km", views=8, sessions=5)],
            referrers=[ReferrerStats(referrer_domain="direct", views=11, sessions=7)],
            daily=[DailyStats(date="2026-09-13", views=11, sessions=7, unique_visitors=7)],
        )


@pytest.fixture
def client():
    async def fake_optional_user():
        return None

    async def fake_admin():
        return {"uid": "admin-1", "login": "admin", "is_admin": True}

    fake = FakeAnalyticsRepo()
    app.dependency_overrides[dependencies.get_analytics_repository] = lambda: fake
    app.dependency_overrides[dependencies.get_optional_user] = fake_optional_user
    app.dependency_overrides[dependencies.get_current_admin] = fake_admin

    test_client = TestClient(app)
    yield test_client, fake
    app.dependency_overrides.clear()


class TestLogPageView:
    def test_post_page_view_records_session_and_route(self, client):
        test_client, fake = client
        resp = test_client.post(
            "/api/analytics/page-view",
            json={"route": "/km", "referrer": "https://example.com/a"},
            headers={"X-Client-Session-ID": "sess-abc"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"success": True}

        assert len(fake.records) == 1
        visit = fake.records[0]
        assert visit.session_id == "sess-abc"
        assert visit.route == "/km"
        assert visit.referrer_domain == "https://example.com/a"
        assert visit.authenticated is False
        assert visit.user_uid == ""
        assert visit.visited_at > 0

    def test_post_page_view_without_session_uses_unknown(self, client):
        test_client, fake = client
        resp = test_client.post(
            "/api/analytics/page-view",
            json={"route": "/introduction"},
        )
        assert resp.status_code == 200
        assert fake.records[0].session_id == "unknown"

    def test_post_page_view_without_referrer_uses_direct(self, client):
        test_client, fake = client
        resp = test_client.post(
            "/api/analytics/page-view",
            json={"route": "/science_articles"},
            headers={"X-Client-Session-ID": "sess-xyz"},
        )
        assert resp.status_code == 200
        assert fake.records[0].referrer_domain == "direct"

    def test_post_page_view_rejects_empty_route(self, client):
        test_client, _ = client
        resp = test_client.post(
            "/api/analytics/page-view",
            json={"route": "   "},
        )
        assert resp.status_code == 422


class TestAnalyticsSummary:
    def test_summary_requires_admin(self, client):
        test_client, fake = client

        async def denied():
            from domain.exceptions import AuthorizationFailed
            raise AuthorizationFailed()

        app.dependency_overrides[dependencies.get_current_admin] = denied
        resp = test_client.get("/api/analytics/summary?days=30")
        assert resp.status_code == 403

    def test_summary_returns_structure(self, client):
        test_client, fake = client
        resp = test_client.get("/api/analytics/summary?days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_views"] == 11
        assert data["total_sessions"] == 7
        assert data["total_unique_visitors"] == 7
        assert data["routes"][0] == {"route": "/km", "views": 8, "sessions": 5}
        assert data["referrers"][0]["referrer_domain"] == "direct"
        day_of_interest = next(
            d for d in data["daily"] if d["date"] == "2026-09-13"
        )
        assert day_of_interest == {
            "date": "2026-09-13",
            "views": 11,
            "sessions": 7,
            "unique_visitors": 7,
        }

    def test_summary_rejects_bad_days(self, client):
        test_client, _ = client
        resp = test_client.get("/api/analytics/summary?days=0")
        assert resp.status_code == 422