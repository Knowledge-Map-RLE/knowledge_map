"""
Layer: Interface Adapters — Repository
Package: adapters.repositories.analytics_repository
 Responsibility: neomodel-реализация AnalyticsRepositoryProtocol.

Принадлежит слою Interface Adapters: транслирует между доменными dataclass-ами
(domain.models.analytics) и ORM-моделями (infrastructure.neo4j.orm_models).
Удовлетворяет протоколу structural subtyping.

All даты группируются по UTC через date(datetime({epochSeconds})) — согласуется
с gap-fill в application.analytics.get_summary.

Allowed imports: neomodel, infrastructure.neo4j.orm_models, domain.models.analytics, src.uuid8
Forbidden imports: fastapi, web, grpc, aioboto3
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from neomodel import db

from domain.models.analytics import (
    AnalyticsSummary,
    DailyStats,
    PageVisit,
    ReferrerStats,
    RouteStats,
)
from infrastructure.neo4j.orm_models import PageVisit as OrmVisit
from src.uuid8 import uuid8_str

logger = logging.getLogger(__name__)

TOP_N = 25

_VISIT_RANGE = "v.visited_at >= $from AND v.visited_at <= $to"


def _now() -> float:
    return time.time()


class AnalyticsRepository:
    """neomodel-реализация репозитория аналитики посещаемости."""

    async def record_page_view(self, visit: PageVisit) -> None:
        orm = OrmVisit(
            uid=visit.uid or uuid8_str(),
            session_id=visit.session_id or "unknown",
            user_uid=visit.user_uid or "",
            route=visit.route,
            referrer_domain=visit.referrer_domain or "direct",
            ip_address=visit.ip_address or "",
            authenticated=bool(visit.authenticated),
            visited_at=float(visit.visited_at) or _now(),
        )
        orm.save()
        logger.info(f"Page view recorded: route={orm.route} session={orm.session_id}")

    async def get_analytics_summary(
        self,
        from_ts: float,
        to_ts: float,
    ) -> AnalyticsSummary:
        params = {"from": from_ts, "to": to_ts}

        total_views = self._scalar(
            f"MATCH (v:PageVisit) WHERE {_VISIT_RANGE} RETURN count(v)",
            params,
        )
        total_sessions = self._scalar(
            f"MATCH (v:PageVisit) WHERE {_VISIT_RANGE} "
            "RETURN count(DISTINCT v.session_id)",
            params,
        )

        daily = self._daily_stats(from_ts, to_ts)
        routes = self._route_stats(from_ts, to_ts)
        referrers = self._referrer_stats(from_ts, to_ts)

        logger.info(
            f"Analytics summary: views={total_views} sessions={total_sessions} "
            f"days={len(daily)}"
        )
        return AnalyticsSummary(
            total_views=total_views,
            total_sessions=total_sessions,
            total_unique_visitors=total_sessions,
            daily=daily,
            routes=routes,
            referrers=referrers,
        )

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _daily_stats(self, from_ts: float, to_ts: float) -> list[DailyStats]:
        result, _ = db.cypher_query(
            f"MATCH (v:PageVisit) WHERE {_VISIT_RANGE} "
            "WITH date(datetime({epochSeconds: toInteger(v.visited_at)})) AS d, "
            "v.session_id AS s, v "
            "RETURN toString(d) AS day, count(v) AS views, count(DISTINCT s) AS sessions "
            "ORDER BY day",
            {"from": from_ts, "to": to_ts},
        )
        return [
            DailyStats(
                date=str(row[0]),
                views=int(row[1] or 0),
                sessions=int(row[2] or 0),
                unique_visitors=int(row[2] or 0),
            )
            for row in result
        ]

    def _route_stats(self, from_ts: float, to_ts: float) -> list[RouteStats]:
        result, _ = db.cypher_query(
            f"MATCH (v:PageVisit) WHERE {_VISIT_RANGE} "
            "RETURN v.route AS route, count(v) AS views, "
            "count(DISTINCT v.session_id) AS sessions "
            "ORDER BY views DESC, route ASC LIMIT $limit",
            {"from": from_ts, "to": to_ts, "limit": TOP_N},
        )
        return [
            RouteStats(
                route=str(row[0]),
                views=int(row[1] or 0),
                sessions=int(row[2] or 0),
            )
            for row in result
        ]

    def _referrer_stats(self, from_ts: float, to_ts: float) -> list[ReferrerStats]:
        result, _ = db.cypher_query(
            f"MATCH (v:PageVisit) WHERE {_VISIT_RANGE} "
            "RETURN v.referrer_domain AS referrer, count(v) AS views, "
            "count(DISTINCT v.session_id) AS sessions "
            "ORDER BY views DESC, referrer ASC LIMIT $limit",
            {"from": from_ts, "to": to_ts, "limit": TOP_N},
        )
        return [
            ReferrerStats(
                referrer_domain=str(row[0]),
                views=int(row[1] or 0),
                sessions=int(row[2] or 0),
            )
            for row in result
        ]

    def _scalar(self, query: str, params: dict) -> int:
        result, _ = db.cypher_query(query, params)
        if not result or not result[0]:
            return 0
        return int(result[0][0] or 0)