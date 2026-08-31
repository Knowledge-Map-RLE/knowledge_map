"""Роутер золотых эталонов LLM-экстракции (eval/gold).

Чтение кейсов — любой авторизованный пользователь;
создание и обновление — только администраторы (get_current_admin).
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.gold_case_service import (
    GoldCaseConflict,
    GoldCaseError,
    GoldCaseNotFound,
    GoldCaseService,
    GoldCaseValidationError,
)
from web.dependencies import get_current_admin, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["article_editor"])


def get_gold_service() -> GoldCaseService:
    return GoldCaseService()


class CreateGoldCaseRequest(BaseModel):
    doc_id: str = Field(min_length=1)
    blocks: Optional[List[Dict[str, Any]]] = None


class UpdateGoldCaseRequest(BaseModel):
    blocks: List[Dict[str, Any]]


def _to_http_error(exc: GoldCaseError) -> HTTPException:
    if isinstance(exc, GoldCaseNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, GoldCaseConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, GoldCaseValidationError):
        return HTTPException(status_code=422, detail={"message": str(exc), "errors": exc.errors})
    logger.exception("Ошибка золотых эталонов")
    return HTTPException(status_code=500, detail=str(exc))


@router.get("/article_editor/gold/cases")
async def list_gold_cases(
    service: GoldCaseService = Depends(get_gold_service),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Список эталонных кейсов и индекс doc_id -> slug (для бейджей в UI)."""
    cases = service.list_cases()
    return {
        "success": True,
        "cases": cases,
        "by_doc_id": {doc_id: info["slug"] for doc_id, info in service.doc_id_index().items()},
    }


@router.get("/article_editor/gold/cases/{slug}")
async def get_gold_case(
    slug: str,
    service: GoldCaseService = Depends(get_gold_service),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Полный эталонный кейс: мета, снапшот статьи и структурные строки."""
    try:
        return await _get_case(service, slug)
    except GoldCaseError as exc:
        raise _to_http_error(exc) from exc


async def _get_case(service: GoldCaseService, slug: str) -> Dict[str, Any]:
    return service.get_case(slug)


@router.post("/article_editor/gold/cases", status_code=201)
async def create_gold_case(
    req: CreateGoldCaseRequest,
    service: GoldCaseService = Depends(get_gold_service),
    user: dict = Depends(get_current_admin),
) -> Dict[str, Any]:
    """Создаёт эталон из текущих строк статьи редактора (admin)."""
    annotator = user.get("nickname") or user.get("login") or user.get("uid", "")
    try:
        return await service.create_case_from_article(req.doc_id, annotator, req.blocks)
    except GoldCaseError as exc:
        raise _to_http_error(exc) from exc


@router.put("/article_editor/gold/cases/{slug}")
async def update_gold_case(
    slug: str,
    req: UpdateGoldCaseRequest,
    service: GoldCaseService = Depends(get_gold_service),
    user: dict = Depends(get_current_admin),
) -> Dict[str, Any]:
    """Перезаписывает структурные строки эталона выверенными блоками (admin)."""
    annotator = user.get("nickname") or user.get("login") or user.get("uid", "")
    try:
        return await service.update_case_blocks(slug, annotator, req.blocks)
    except GoldCaseError as exc:
        raise _to_http_error(exc) from exc
