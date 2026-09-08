"""
Layer: Interface Adapters — Controller (Web)
Package: web.routers.knowledge_triples
Responsibility: HTTP-эндпоинты для DAG-карты триплетов знаний (KnowledgeStatement).
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from services.knowledge_triples_service import KnowledgeTriplesService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/layout", tags=["knowledge-triples"])

_service = KnowledgeTriplesService()


@router.get("/knowledge_triples")
async def get_knowledge_triples(
    isolated_limit: int = Query(200, ge=0, le=1000, description="Лимит изолированных триплетов в начальной выдаче"),
) -> Dict[str, Any]:
    """Возвращает DAG-карту триплетов и начальный список изолированных."""
    return await _service.get_knowledge_triples(isolated_limit=isolated_limit)


@router.get("/knowledge_triples/isolated")
async def search_isolated_triples(
    q: str = Query("", description="Поиск по содержимому триплета (с 3 символов)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    """Поиск по изолированным триплетам с пагинацией."""
    return await _service.search_isolated_triples(q=q, skip=skip, limit=limit)
