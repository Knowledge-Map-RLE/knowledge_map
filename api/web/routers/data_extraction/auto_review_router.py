"""
Layer: Interface Adapters — Controller (Web)
Package: web.routers.data_extraction.auto_review_router
Responsibility: HTTP endpoint для автоматического ревью рёбер LEADS_TO.

Оборачивает api/auto_review.run() в async HTTP endpoint.
"""
import asyncio
import logging
import os
import sys

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents/{doc_id}", tags=["auto-review"])


class AutoReviewResponse(BaseModel):
    success: bool
    doc_id: str
    confirmed: int
    rejected: int


@router.post("/auto-review", response_model=AutoReviewResponse)
async def auto_review_document(doc_id: str, dry_run: bool = False):
    """
    Автоматически подтверждает/отклоняет рёбра LEADS_TO для документа.

    Применяет эвристики на основе биомедицинских глаголов и типов связей.
    Подтверждённые рёбра становятся видны в "Карте статьи".
    """
    # auto_review.py находится в корне api/ — нужно добавить в sys.path
    api_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    if api_dir not in sys.path:
        sys.path.insert(0, api_dir)

    try:
        from auto_review import run as ar_run
    except ImportError as e:
        logger.error(f"Cannot import auto_review: {e}")
        raise HTTPException(status_code=500, detail=f"auto_review module not available: {e}")

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, ar_run, doc_id, dry_run)
        return AutoReviewResponse(
            success=True,
            doc_id=doc_id,
            confirmed=result.get("confirmed", 0),
            rejected=result.get("rejected", 0),
        )
    except Exception as e:
        logger.error(f"auto_review failed for doc {doc_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
