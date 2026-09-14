"""
Layer: Application (Use Cases)
Package: application.analytics.get_summary
Responsibility: Возвращает сводку посещаемости за период с заполнением пустых дней.

All даты в часовом поясе UTC: и bucketing в Neo4j (date(datetime({epochSeconds})),
и gap-fill здесь используют одинаковый подход, поэтому series согласованы.

Allowed imports: application.ports.analytics_repository, domain.models.analytics,
                 стандартная библиотека (datetime, dataclasses, time)
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from application.ports.analytics_repository import AnalyticsRepositoryProtocol
from domain.models.analytics import AnalyticsSummary, DailyStats


async def get_analytics_summary(
    repo: AnalyticsRepositoryProtocol,
    days: int,
) -> AnalyticsSummary:
    """Сводка за последние `days` календарных дней (UTC), включая сегодня."""
    now = time.time()
    from_ts = now - days * 86400.0

    raw = await repo.get_analytics_summary(from_ts=from_ts, to_ts=now)
    if not raw.daily:
        return replace(
            raw,
            start_date=_utc_date(from_ts),
            end_date=_utc_date(now),
        )

    by_date = {d.date: d for d in raw.daily}
    start = _utc_date(from_ts)
    end = _utc_date(now)

    filled: list[DailyStats] = []
    cursor = datetime.strptime(start, "%Y-%m-%d").date()
    last = datetime.strptime(end, "%Y-%m-%d").date()
    while cursor <= last:
        key = cursor.isoformat()
        day = by_date.get(key)
        filled.append(day if day else DailyStats(date=key))
        cursor += timedelta(days=1)

    return replace(raw, start_date=start, end_date=end, daily=filled)


def _utc_date(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")