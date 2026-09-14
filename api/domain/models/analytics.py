"""
Layer: Domain (Entities)
Package: domain.models.analytics
 Responsibility: Dataclass-ы серверной аналитики посещаемости.

Принадлежит слою Domain — чистые dataclass-ы без зависимостей от инфраструктуры.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PageVisit:
    """Один просмотр страницы, пришедший с клиента."""
    uid: str
    session_id: str
    route: str
    referrer_domain: str = "direct"
    ip_address: str = ""
    authenticated: bool = False
    user_uid: str = ""
    visited_at: float = 0.0


@dataclass(frozen=True)
class RouteStats:
    """Статистика по маршруту SPA."""
    route: str = ""
    views: int = 0
    sessions: int = 0


@dataclass(frozen=True)
class ReferrerStats:
    """Статистика по источнику перехода."""
    referrer_domain: str = ""
    views: int = 0
    sessions: int = 0


@dataclass(frozen=True)
class DailyStats:
    """Статистика за календарный день (UTC, дата в формате YYYY-MM-DD)."""
    date: str = ""
    views: int = 0
    sessions: int = 0
    unique_visitors: int = 0


@dataclass(frozen=True)
class AnalyticsSummary:
    """Сводка посещаемости за период."""
    total_views: int = 0
    total_sessions: int = 0
    total_unique_visitors: int = 0
    start_date: str = ""
    end_date: str = ""
    daily: list[DailyStats] = field(default_factory=list)
    routes: list[RouteStats] = field(default_factory=list)
    referrers: list[ReferrerStats] = field(default_factory=list)