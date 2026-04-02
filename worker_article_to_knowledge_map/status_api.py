"""
FastAPI status server for the worker (port 8004).

Endpoints:
  GET /status         — summary stats
  GET /status/details — per-article progress list
  GET /status/logs    — recent log lines
"""
import logging

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

# This module is imported by main.py which sets this before calling build_app()
_store = None


def set_store(store) -> None:
    global _store
    _store = store


def build_app() -> FastAPI:
    app = FastAPI(title="Knowledge Map Worker Status API", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/status")
    async def get_status():
        if _store is None:
            return {"error": "store not initialised"}
        return await _store.get_summary()

    @app.get("/status/details")
    async def get_details(
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ):
        if _store is None:
            return {"articles": [], "total": 0}
        articles = await _store.get_details(limit=limit, offset=offset)
        summary = await _store.get_summary()
        return {"articles": articles, "total": summary.get("total", 0)}

    @app.get("/status/logs")
    async def get_logs(n: int = Query(default=100, ge=1, le=500)):
        if _store is None:
            return {"logs": []}
        logs = list(_store.log_buffer)
        return {"logs": logs[-n:]}

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "worker_status_api"}

    return app
