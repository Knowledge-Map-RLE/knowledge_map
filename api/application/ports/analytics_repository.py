"""
Layer: Application (Use Cases)
Package: application.ports.analytics_repository
 Responsibility: Protocol для репозитория аналитики посещаемости.

Принадлежит слою Application — зависит только от domain.models.
"""
from __future__ import annotations

from typing import Protocol

from domain.models.analytics import AnalyticsSummary, PageVisit


class AnalyticsRepositoryProtocol(Protocol):
    """Протокол репозитория аналитики (structural subtyping)."""

    async def record_page_view(self, visit: PageVisit) -> None: ...

    async def get_analytics_summary(
        self,
        from_ts: float,
        to_ts: float,
    ) -> AnalyticsSummary: ...