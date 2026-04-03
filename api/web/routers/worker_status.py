"""
Layer: Interface Adapters — Controller (Web)
Package: web.routers.worker_status
Responsibility: Проксирует запрос статуса к worker_article_to_knowledge_map (порт 8004).
При недоступности воркера возвращает 200 с available=false вместо 502/500.
"""
import logging

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/worker", tags=["worker"])

WORKER_URL = "http://localhost:8004"
WORKER_TIMEOUT = 2.0


@router.get("/status")
async def get_worker_status() -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=WORKER_TIMEOUT) as client:
            resp = await client.get(f"{WORKER_URL}/status")
            resp.raise_for_status()
            return JSONResponse(content={"available": True, **resp.json()})
    except Exception:
        return JSONResponse(content={"available": False})


@router.get("/status/details")
async def get_worker_status_details() -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=WORKER_TIMEOUT) as client:
            resp = await client.get(f"{WORKER_URL}/status/details")
            resp.raise_for_status()
            return JSONResponse(content=resp.json())
    except Exception:
        return JSONResponse(content={"available": False, "items": []})


@router.get("/status/logs")
async def get_worker_status_logs() -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=WORKER_TIMEOUT) as client:
            resp = await client.get(f"{WORKER_URL}/status/logs")
            resp.raise_for_status()
            return JSONResponse(content=resp.json())
    except Exception:
        return JSONResponse(content={"available": False, "logs": []})
