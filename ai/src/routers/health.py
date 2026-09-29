"""Health endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from src.config import model_registry, settings
from src.providers import catalog

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Service health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "ai-agent",
        "active_profile": model_registry.active_profile_name,
        "active_provider": catalog.default_provider().name,
        "active_model": catalog.default_provider().default_model,
        "providers": [provider.name for provider in catalog.providers],
    }
