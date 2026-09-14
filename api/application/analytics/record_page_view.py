"""
Layer: Application (Use Cases)
Package: application.analytics.record_page_view
Responsibility: Сохраняет единичный просмотр страницы в хранилище.

Allowed imports: application.ports.analytics_repository, domain.models.analytics
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

from application.ports.analytics_repository import AnalyticsRepositoryProtocol
from domain.models.analytics import PageVisit


async def record_page_view(repo: AnalyticsRepositoryProtocol, visit: PageVisit) -> None:
    """Персистентно сохраняет просмотр. Идемпотентность не требуется —
    событие трактуется как факт, в отличие от уникальных посетителей."""
    await repo.record_page_view(visit)