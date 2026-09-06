"""
Layer: Interface Adapters — Controller (Web)
Package: web.routers.citation_graph
Responsibility: REST API endpoints для управления загрузкой цитатного графа.

Allowed imports: fastapi, services.citation_graph_service
Forbidden imports: application (напрямую)
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.citation_graph_service import (
    get_citation_graph_service,
    CITATION_SOURCES_CONFIG,
    CitationGraphService,
)
from services.citation_sources.base import BulkLoadOptions
from web.routers.data_download_ws import notify_progress, notify_status_change, notify_error

logger = logging.getLogger(__name__)

router = APIRouter(tags=["citation-graph"])


# ── Pydantic Models ──────────────────────────────────────────────────────

class CitationSourceStatus(BaseModel):
    key: str
    name: str
    url: str
    source_type: str
    description: Optional[str] = None
    total_edges: int = 0
    downloaded_edges: int = 0
    progress_percent: float = 0.0
    status: str = "idle"
    error_message: Optional[str] = None
    last_updated: Optional[str] = None


class CitationAction(BaseModel):
    source: str


class SingleDoiRequest(BaseModel):
    doi: str


class TestResult(BaseModel):
    source_name: str
    sample_size: int
    elapsed_seconds: float
    edges_found: int
    estimated_total_edges: Optional[int] = None
    estimated_time_seconds: Optional[float] = None
    errors: List[str] = []
    success: bool = True


class CitationStats(BaseModel):
    document_count: int
    edge_count: int
    source_breakdown: Dict[str, int] = {}


class LoadAllResponse(BaseModel):
    status: str
    message: str


# ── Endpoints ────────────────────────────────────────────────────────────

@router.get("/sources", response_model=List[CitationSourceStatus])
async def get_all_sources():
    service = get_citation_graph_service()
    sources = service.get_all_sources()
    return [
        CitationSourceStatus(
            key=s["key"],
            name=s["name"],
            url=s.get("url", ""),
            source_type=s.get("source_type", "api"),
            description=s.get("description"),
            total_edges=s.get("total_edges", 0),
            downloaded_edges=s.get("downloaded_edges", 0),
            progress_percent=s.get("progress_percent", 0.0),
            status=s.get("status", "idle"),
            error_message=s.get("error_message"),
            last_updated=str(s.get("last_updated")) if s.get("last_updated") else None,
        )
        for s in sources
    ]


@router.get("/sources/{source_key}", response_model=CitationSourceStatus)
async def get_source_status(source_key: str):
    service = get_citation_graph_service()
    sources = service.get_all_sources()
    source = next((s for s in sources if s["key"] == source_key), None)
    if not source:
        raise HTTPException(status_code=404, detail="Citation source not found")
    return CitationSourceStatus(
        key=source["key"],
        name=source["name"],
        url=source.get("url", ""),
        source_type=source.get("source_type", "api"),
        description=source.get("description"),
        total_edges=source.get("total_edges", 0),
        downloaded_edges=source.get("downloaded_edges", 0),
        progress_percent=source.get("progress_percent", 0.0),
        status=source.get("status", "idle"),
        error_message=source.get("error_message"),
        last_updated=str(source.get("last_updated")) if source.get("last_updated") else None,
    )


@router.post("/initialize")
async def initialize_sources():
    service = get_citation_graph_service()
    service.initialize_sources()
    return {"status": "ok", "message": "Citation sources initialized"}


@router.post("/test/{source_key}", response_model=TestResult)
async def test_source(source_key: str, sample_size: int = 10):
    if source_key not in CITATION_SOURCES_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source_key}")
    service = get_citation_graph_service()
    try:
        result = await service.test_source(source_key, sample_size)
        return TestResult(
            source_name=result.source_name,
            sample_size=result.sample_size,
            elapsed_seconds=result.elapsed_seconds,
            edges_found=result.edges_found,
            estimated_total_edges=result.estimated_total_edges,
            estimated_time_seconds=result.estimated_time_seconds,
            errors=result.errors,
            success=result.success,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/load/{source_key}")
async def load_source(source_key: str, max_files: Optional[int] = None, max_records: Optional[int] = None):
    if source_key not in CITATION_SOURCES_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source_key}")
    service = get_citation_graph_service()
    try:
        options = BulkLoadOptions(max_files=max_files, max_records=max_records)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        _schedule_load(service, source_key, options)
        return {"status": "ok", "message": f"Load started for {source_key}"}
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/load_all")
async def load_all_sources():
    service = get_citation_graph_service()
    for key in CITATION_SOURCES_CONFIG:
        try:
            asyncio.create_task(_run_load(service, key))
        except Exception as e:
            logger.warning("Could not start load for %s: %s", key, e)
    return {"status": "ok", "message": "Load started for all available sources"}


@router.post("/load_one")
async def load_single_doi(req: SingleDoiRequest):
    service = get_citation_graph_service()
    try:
        result = await service.load_single_doi(req.doi)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=CitationStats)
async def get_stats():
    service = get_citation_graph_service()
    loop = asyncio.get_running_loop()
    stats = await loop.run_in_executor(None, service.get_stats)
    return CitationStats(**stats)


@router.post("/relayout")
async def recalculate_layout() -> Dict[str, Any]:
    """Пересчитывает координаты (layer, level, x, y) цитатного графа и сохраняет их в Neo4j.

    Только переукладка: граф и данные не перезагружаются. Выполняется в executor,
    так как укладка не должна блокировать event loop API-сервера.
    """
    service = get_citation_graph_service()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: asyncio.run(service.layout_citation_graph()))


@router.post("/enrich_fields")
async def enrich_document_fields() -> Dict[str, Any]:
    """Запускает в фоне обогащение уже загруженных Document-узлов тематикой
    (primary_field, fields) из локального OpenAlex-дампа. Прогресс — через
    GET /enrich_fields_status.
    """
    service = get_citation_graph_service()
    return await service.start_enrich_document_fields()


@router.get("/enrich_fields_status")
async def enrich_document_fields_status() -> Dict[str, Any]:
    """Текущий прогресс фонового обогащения Document-узлов тематикой."""
    service = get_citation_graph_service()
    return await service.enrich_document_fields_status()


@router.post("/pause/{source_key}")
async def pause_source(source_key: str):
    if source_key not in CITATION_SOURCES_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source_key}")
    service = get_citation_graph_service()
    await service.pause_load(source_key)
    await notify_status_change(f"citation_{source_key}", "paused", f"Paused bulk load for {source_key}")
    return {"status": "ok", "message": f"Paused {source_key}"}


@router.post("/resume/{source_key}")
async def resume_source(source_key: str):
    if source_key not in CITATION_SOURCES_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source_key}")
    service = get_citation_graph_service()
    if service.is_source_active(source_key):
        await service.resume_load(source_key)
        await notify_status_change(f"citation_{source_key}", "downloading", f"Resumed bulk load for {source_key}")
        return {"status": "ok", "message": f"Resumed {source_key}"}
    # Worker не жив (перезапуск API, падение). Возобновляем новым прогоном:
    # полная загрузка продолжит с чекпоинта, повторно ничего не скачается.
    _schedule_load(service, source_key)
    return {"status": "ok", "message": f"Load continued for {source_key}"}


@router.post("/reset/{source_key}")
async def reset_source(source_key: str):
    if source_key not in CITATION_SOURCES_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source_key}")
    service = get_citation_graph_service()
    await service.reset_load(source_key)
    await notify_status_change(f"citation_{source_key}", "idle", f"Reset {source_key}")
    return {"status": "ok", "message": f"Reset {source_key}"}


def _schedule_load(service: CitationGraphService, key: str, options: Optional[BulkLoadOptions] = None) -> None:
    """Запускает фоновую задачу загрузки (обёртка над _run_load)."""
    asyncio.create_task(_run_load(service, key, options))


async def _run_load(service: CitationGraphService, key: str, options: Optional[BulkLoadOptions] = None) -> None:
    """Фоновая задача загрузки с уведомлениями через WebSocket.

    Сам процесс загрузки выполняется в worker-потоке сервиса; уведомления
    возвращаются в этот event loop через run_coroutine_threadsafe.
    """
    loop = asyncio.get_running_loop()

    def _on_status(status: str, message: str) -> None:
        asyncio.run_coroutine_threadsafe(
            notify_status_change(f"citation_{key}", status, message), loop
        )

    def _on_progress(downloaded: int, total: int, percent: float, filename: str) -> None:
        asyncio.run_coroutine_threadsafe(
            notify_progress(
                f"citation_{key}",
                downloaded=downloaded,
                total=total,
                percent=percent,
                current_file=filename,
            ),
            loop,
        )

    try:
        await service.load_source_bulk(
            key, options, on_progress=_on_progress, on_status=_on_status
        )
    except Exception as e:
        logger.error("Load task failed for %s: %s", key, e)
        await notify_error(f"citation_{key}", str(e))
