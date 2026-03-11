"""Роутер для поиска и загрузки статей из PubMed и PubMed Central"""
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from services.pubmed_service import PubMedService
from src.schemas.api import PubMedIngestRequest, PubMedIngestResponse, PubMedSearchResponse, PubMedSearchResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pubmed", tags=["pubmed"])

_pubmed_service = None


def get_pubmed_service() -> PubMedService:
    global _pubmed_service
    if _pubmed_service is None:
        _pubmed_service = PubMedService()
    return _pubmed_service


@router.get("/search", response_model=PubMedSearchResponse)
async def search_pubmed(
    query: str = Query(..., min_length=3, description="Поисковый запрос (минимум 3 символа)"),
    limit: int = Query(10, ge=1, le=50, description="Максимальное число результатов"),
):
    """Единый поиск в PubMed и PMC одновременно.

    - Параллельно ищет в обоих источниках, дедуплицирует по PMID
    - OA-статьи с полным текстом идут первыми
    - Минимум 3 символа в запросе, до 10 результатов
    """
    try:
        service = get_pubmed_service()
        results = await service.search(query=query, retmax=limit)
        return PubMedSearchResponse(
            success=True,
            results=results,
            total=len(results),
            query=query,
            db="pubmed+pmc",
        )
    except Exception as e:
        logger.error(f"[pubmed/search] Ошибка поиска '{query}': {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка поиска: {str(e)}")


@router.get("/by-id", response_model=PubMedSearchResponse)
async def get_by_id(
    id: str = Query(..., description="PMID (число) или PMCID (PMC + число)"),
):
    """Получить статью напрямую по PMID или PMCID.

    Автоматически определяет тип ID:
    - Начинается с 'PMC' → ищет в PMC
    - Иначе → ищет в PubMed как PMID
    """
    try:
        service = get_pubmed_service()
        result = await service.fetch_by_id(id.strip())
        if result is None:
            return PubMedSearchResponse(success=True, results=[], total=0, query=id, db="pubmed")
        return PubMedSearchResponse(
            success=True,
            results=[result],
            total=1,
            query=id,
            db="pmc" if id.strip().upper().startswith("PMC") else "pubmed",
        )
    except Exception as e:
        logger.error(f"[pubmed/by-id] Ошибка получения по ID '{id}': {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")


@router.post("/ingest", response_model=PubMedIngestResponse)
async def ingest_pubmed_article(
    request: PubMedIngestRequest,
    background_tasks: BackgroundTasks,
):
    """Загрузка статьи из PubMed/PMC в систему.

    Логика в зависимости от источника и OA статуса:
    - PMC OA: скачивает tar.gz → конвертирует NLM XML → Markdown (без Docling)
    - PubMed OA с PDF: скачивает PDF → Docling pipeline
    - Не-OA: сохраняет абстракт + метаданные в Markdown

    Статья идентифицируется по PMID или PMCID.
    Дубликаты обнаруживаются и возвращают существующий doc_id.
    """
    if not request.pmid and not request.pmcid:
        raise HTTPException(status_code=400, detail="Необходимо указать pmid или pmcid")

    try:
        service = get_pubmed_service()
        result = await service.ingest_article(
            pmid=request.pmid,
            pmcid=request.pmcid,
            source=request.source,
            background_tasks=background_tasks,
        )
        return PubMedIngestResponse(
            success=result["success"],
            doc_id=result.get("doc_id"),
            message=result.get("message", ""),
            processing_status=result.get("processing_status", "pending"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[pubmed/ingest] Ошибка загрузки PMID={request.pmid}, PMCID={request.pmcid}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки статьи: {str(e)}")
