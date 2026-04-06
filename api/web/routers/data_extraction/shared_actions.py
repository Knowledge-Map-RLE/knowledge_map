"""
Layer: Interface Adapters — Controller (Web)
Package: web.routers.data_extraction.shared_actions
Responsibility: HTTP route handlers для агрегированного графа знаний.

Allowed imports: fastapi, application.*, web.dependencies
Forbidden imports: neomodel (напрямую), infrastructure (напрямую)
"""
import logging

from fastapi import APIRouter, Depends

from web.dependencies import get_action_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shared-actions", tags=["shared-actions"])


@router.post("/backfill")
def backfill_norm_keys(
    action_repo=Depends(get_action_repository),
):
    """Проставляет norm_key для Action-нод, у которых его ещё нет.
    Запускается один раз для миграции существующих данных."""
    updated = action_repo.backfill_norm_keys()
    return {"updated": updated}


@router.get("/graph")
def get_aggregated_graph(
    action_repo=Depends(get_action_repository),
):
    """Возвращает агрегированный граф знаний: по одной ноде на norm_key
    (одинаковые действия из разных статей объединены) с рёбрами LEADS_TO между ними."""
    nodes, edges = action_repo.get_aggregated_graph()
    return {"nodes": nodes, "edges": edges}
