"""Юнит-тесты use case application.analytics.get_summary.

Проверяет gap-fill пустых дней и согласованные границы периода без реального Neo4j.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from domain.models.analytics import (
    AnalyticsSummary,
    DailyStats,
    ReferrerStats,
    RouteStats,
)
from application.analytics.get_summary import get_analytics_summary


class FakeAnalyticsRepo:
    """Фейковый репозиторий: возвращает предзаданную сырую сводку."""

    def __init__(self, raw: AnalyticsSummary):
        self.raw = raw
        self.called_with: dict = {}

    async def record_page_view(self, visit) -> None:
        pass

    async def get_analytics_summary(self, from_ts: float, to_ts: float) -> AnalyticsSummary:
        self.called_with = {"from_ts": from_ts, "to_ts": to_ts}
        return self.raw


def _make_raw(daily: list[DailyStats]) -> AnalyticsSummary:
    return AnalyticsSummary(
        total_views=11,
        total_sessions=7,
        total_unique_visitors=7,
        start_date="",
        end_date="",
        daily=daily,
        routes=[RouteStats(route="/km", views=8, sessions=5)],
        referrers=[ReferrerStats(referrer_domain="direct", views=11, sessions=7)],
    )


async def test_get_summary_fills_empty_days():
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    yesterday = (now.date() - timedelta(days=1)).isoformat()
    few_days_ago = (now.date() - timedelta(days=3)).isoformat()

    repo = FakeAnalyticsRepo(
        _make_raw(
            daily=[
                DailyStats(date=yesterday, views=5, sessions=3, unique_visitors=3),
                DailyStats(date=few_days_ago, views=2, sessions=2, unique_visitors=2),
            ]
        )
    )

    summary = await get_analytics_summary(repo, days=30)

    assert summary.total_views == 11
    assert summary.total_sessions == 7

    dates = [d.date for d in summary.daily]
    expected_start = datetime.fromtimestamp(
        repo.called_with["from_ts"], tz=timezone.utc
    ).strftime("%Y-%m-%d")
    assert dates[0] == expected_start

    # Дни жизни в периоде без данных — нулевые, конец периода — сегодня.
    assert summary.end_date == today
    assert summary.daily[-1].date == today
    assert summary.daily[-1].views == 0

    by_date = {d.date: d for d in summary.daily}
    assert by_date[yesterday].views == 5
    assert by_date[yesterday].sessions == 3
    assert by_date[few_days_ago].views == 2

    # Период сплошной: между первой и последней датой нет пропусков.
    parsed = [datetime.strptime(d, "%Y-%m-%d").date() for d in dates]
    assert parsed == sorted(parsed)
    for prev, nxt in zip(parsed, parsed[1:]):
        assert (nxt - prev).days == 1

    # routes/referrers сохраняются как есть.
    assert summary.routes[0].route == "/km"
    assert summary.referrers[0].referrer_domain == "direct"


async def test_get_summary_without_data_returns_dates_only():
    repo = FakeAnalyticsRepo(
        AnalyticsSummary(
            total_views=0,
            total_sessions=0,
            total_unique_visitors=0,
        )
    )

    summary = await get_analytics_summary(repo, days=7)

    assert summary.daily == []
    assert summary.start_date
    assert summary.end_date
    assert summary.total_views == 0