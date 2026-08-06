"""Паттерны доказательственных карт (EvidenceMap): генерация, хранение,
алгоритмический майнинг частотных подграфов и матчинг новой статьи.

Эндпоинты:
  * POST /article_editor/patterns/generate   — LLM-генерация карты по тексту статьи
  * PUT  /article_editor/articles/{doc_id}/evidence-map — сохранение карты
  * GET  /article_editor/articles/{doc_id}/evidence-map — загрузка карты
  * DELETE /article_editor/articles/{doc_id}/evidence-map — удаление
  * GET  /article_editor/patterns/maps       — список сохранённых карт
  * POST /article_editor/patterns/mine       — майнинг частотных подграфов
  * POST /article_editor/articles/{doc_id}/evidence-map/match — матчинг статьи
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.evidence_map_service import DEFAULT_MODEL, get_evidence_map_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["article_editor"])
service = get_evidence_map_service()


class GenerateMapRequest(BaseModel):
    model_id: str = DEFAULT_MODEL
    temperature: float = 0.2


class SaveMapRequest(BaseModel):
    map: Dict[str, Any]


class MineRequest(BaseModel):
    doc_ids: Optional[List[str]] = None
    min_support: float = 0.6
    min_size: int = 2
    max_size: int = 4
    limit: int = 2000


class MatchRequest(BaseModel):
    patterns: Optional[List[Dict[str, Any]]] = None
    min_support: float = 1.0
    min_size: int = 2
    max_size: int = 4
    limit: int = 2000


@router.post("/article_editor/patterns/generate")
async def generate_map(doc_id: str, req: GenerateMapRequest):
    result = await service.generate_map(
        doc_id, model_id=req.model_id, temperature=req.temperature
    )
    if not result.get("success"):
        raise HTTPException(status_code=422, detail=result.get("message", "Ошибка генерации"))
    return result


@router.put("/article_editor/articles/{doc_id}/evidence-map")
async def save_map(doc_id: str, req: SaveMapRequest):
    result = await service.save_map(doc_id, req.map)
    return result


@router.get("/article_editor/articles/{doc_id}/evidence-map")
async def get_map(doc_id: str):
    m = await service.get_map(doc_id)
    if m is None:
        raise HTTPException(status_code=404, detail="EvidenceMap не найдена")
    return {"map": m, "success": True}


@router.delete("/article_editor/articles/{doc_id}/evidence-map")
async def delete_map(doc_id: str):
    await service.delete_map(doc_id)
    return {"success": True}


@router.get("/article_editor/patterns/maps")
async def list_maps():
    return {"maps": await service.list_maps(), "success": True}


@router.post("/article_editor/patterns/mine")
async def mine(req: MineRequest):
    result = await service.mine(
        doc_ids=req.doc_ids,
        min_support=req.min_support,
        min_size=req.min_size,
        max_size=req.max_size,
        limit=req.limit,
    )
    return result


@router.post("/article_editor/articles/{doc_id}/evidence-map/match")
async def match(doc_id: str, req: MatchRequest):
    result = await service.match(
        doc_id,
        patterns=req.patterns,
        min_support=req.min_support,
        min_size=req.min_size,
        max_size=req.max_size,
        limit=req.limit,
    )
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("message", "Нет карты"))
    return result
