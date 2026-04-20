"""
Layer: Interface Adapters — Controller (Web)
Package: web.routers.data_download
Responsibility: REST API endpoints для управления загрузкой данных.

Allowed imports: fastapi, services.data_download_service
Forbidden imports: application (напрямую)
"""
import logging
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.data_download_service import (
    get_data_download_service,
    DATA_SOURCES,
    DataDownloadService,
)
from web.routers.data_download_ws import notify_progress

logger = logging.getLogger(__name__)

router = APIRouter(tags=["data-download"])


class DataSourceStatus(BaseModel):
    name: str
    ftp_url: str
    description: Optional[str] = None
    total_files: int = 0
    downloaded_files: int = 0
    progress_percent: float = 0.0
    status: str = "idle"
    current_file: Optional[str] = ""
    error_message: Optional[str] = None
    last_updated: Optional[str] = None


class DownloadAction(BaseModel):
    source: str


@router.get("/sources", response_model=List[DataSourceStatus])
async def get_all_sources():
    """Получить статус всех источников данных."""
    service = get_data_download_service()
    sources = service.get_all_sources()
    return [
        DataSourceStatus(
            name=s["name"],
            ftp_url=s.get("ftp_url", ""),
            description=s.get("description"),
            total_files=s.get("total_files", 0),
            downloaded_files=s.get("downloaded_files", 0),
            progress_percent=s.get("progress_percent", 0.0),
            status=s.get("status", "idle"),
            error_message=s.get("error_message"),
            last_updated=str(s.get("last_updated")) if s.get("last_updated") else None,
        )
        for s in sources
    ]


@router.get("/sources/{source_name}", response_model=DataSourceStatus)
async def get_source_status(source_name: str):
    """Получить статус конкретного источника."""
    service = get_data_download_service()
    source = service.get_source_status(source_name)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return DataSourceStatus(
        name=source["name"],
        ftp_url=source.get("ftp_url", ""),
        total_files=source.get("total_files", 0),
        downloaded_files=source.get("downloaded_files", 0),
        progress_percent=source.get("progress_percent", 0.0),
        status=source.get("status", "idle"),
        error_message=source.get("error_message"),
        last_updated=str(source.get("last_updated")) if source.get("last_updated") else None,
    )


@router.post("/start")
async def start_download(action: DownloadAction):
    """Запустить загрузку для источника."""
    if action.source not in DATA_SOURCES:
        raise HTTPException(status_code=400, detail="Unknown source")
    service = get_data_download_service()
    service.set_command(action.source, "start")
    return {"status": "ok", "message": f"Start download for {action.source}"}


@router.post("/pause")
async def pause_download(action: DownloadAction):
    """Приостановить загрузку для источника."""
    if action.source not in DATA_SOURCES:
        raise HTTPException(status_code=400, detail="Unknown source")
    service = get_data_download_service()
    service.set_command(action.source, "pause")
    return {"status": "ok", "message": f"Pause download for {action.source}"}


@router.post("/reset")
async def reset_download(action: DownloadAction):
    """Сбросить прогресс загрузки."""
    if action.source not in DATA_SOURCES:
        raise HTTPException(status_code=400, detail="Unknown source")
    service = get_data_download_service()
    service.set_command(action.source, "reset")
    return {"status": "ok", "message": f"Reset download for {action.source}"}


@router.post("/initialize")
async def initialize_sources():
    """Инициализировать источники данных в базе."""
    service = get_data_download_service()
    service.initialize_sources()
    return {"status": "ok", "message": "Sources initialized"}


class ProgressUpdate(BaseModel):
    source: str
    downloaded: int
    total: int
    percent: float
    status: str
    current_file: Optional[str] = ""


@router.post("/progress")
async def update_progress(progress: ProgressUpdate):
    """Обновляет прогресс от воркера."""
    service = get_data_download_service()
    service.update_progress(
        name=progress.source,
        downloaded_files=progress.downloaded,
        total_files=progress.total,
        status=progress.status,
        error_message=progress.current_file,
    )
    await notify_progress(
        source=progress.source,
        downloaded=progress.downloaded,
        total=progress.total,
        percent=progress.percent,
        status=progress.status,
    )
    return {"status": "ok"}