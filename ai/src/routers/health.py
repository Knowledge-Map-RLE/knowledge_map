"""Health endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from src.config import settings
from src.providers import catalog

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Service health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "ai-agent",
        "default_provider": settings.default_provider,
        "default_model": settings.default_model,
        "providers": [provider.name for provider in catalog.providers],
    }
