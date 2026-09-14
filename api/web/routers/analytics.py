"""
Layer: Frameworks & Drivers — Web
Package: web.routers.analytics
 Responsibility: HTTP-контроллеры серверной аналитики посещаемости.

Принадлежит слою Web — тонкий контроллер, вызывает use cases через DI.
Не содержит бизнес-логики.

POST /api/analytics/page-view — публичный приём просмотра страницы (fire-and-forget
с клиента). Аутентифицированный пользователь определяется по Bearer-токену
(get_optional_user) — сервер доверяет только токену, а не полю из тела запроса.
Сессия берётся только из заголовка X-Client-Session-ID.

GET /api/analytics/summary — сводка для администратора (get_current_admin).

Allowed imports: fastapi, web.dependencies, adapters.repositories.analytics_repository,
                 application.analytics.*, domain.models.analytics, src.schemas.schemas
Forbidden imports: neomodel (напрямую), services
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Request

from adapters.repositories.analytics_repository import AnalyticsRepository
from application.analytics.get_summary import get_analytics_summary
from application.analytics.record_page_view import record_page_view
from domain.models.analytics import PageVisit
from src.schemas.schemas import (
    AnalyticsSummaryResponse,
    DailyStatsItem,
    PageViewRequest,
    PageViewResponse,
    ReferrerStatsItem,
    RouteStatsItem,
)
from src.uuid8 import uuid8_str
from web.dependencies import (
    get_analytics_repository,
    get_current_admin,
    get_optional_user,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _client_ip(request: Request) -> str:
    """IP клиента: приоритет у X-Forwarded-For (за nginx/docker)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


@router.post("/page-view", response_model=PageViewResponse)
async def log_page_view(
    payload: PageViewRequest,
    request: Request,
    session_id: Optional[str] = Header(None, alias="X-Client-Session-ID"),
    user: Optional[dict] = Depends(get_optional_user),
    repo: AnalyticsRepository = Depends(get_analytics_repository),
):
    """Сохранить просмотр страницы (вызывается из SPA при смене маршрута)."""
    referrer = (payload.referrer or "").strip()
    visit = PageVisit(
        uid=uuid8_str(),
        session_id=(session_id or "unknown").strip()[:200],
        route=payload.route,
        referrer_domain=referrer if referrer else "direct",
        ip_address=_client_ip(request),
        authenticated=bool(user),
        user_uid=str(user.get("uid", "")) if user else "",
        visited_at=time.time(),
    )
    await record_page_view(repo, visit)
    return PageViewResponse(success=True)


@router.get("/summary", response_model=AnalyticsSummaryResponse)
async def analytics_summary(
    days: int = Query(default=30, ge=1, le=365),
    admin: dict = Depends(get_current_admin),
    repo: AnalyticsRepository = Depends(get_analytics_repository),
):
    """Сводка посещаемости за последние N дней (только для администратора)."""
    summary = await get_analytics_summary(repo, days=days)
    return AnalyticsSummaryResponse(
        total_views=summary.total_views,
        total_sessions=summary.total_sessions,
        total_unique_visitors=summary.total_unique_visitors,
        start_date=summary.start_date,
        end_date=summary.end_date,
        routes=[
            RouteStatsItem(route=r.route, views=r.views, sessions=r.sessions)
            for r in summary.routes
        ],
        referrers=[
            ReferrerStatsItem(
                referrer_domain=r.referrer_domain,
                views=r.views,
                sessions=r.sessions,
            )
            for r in summary.referrers
        ],
        daily=[
            DailyStatsItem(
                date=d.date,
                views=d.views,
                sessions=d.sessions,
                unique_visitors=d.unique_visitors,
            )
            for d in summary.daily
        ],
    )