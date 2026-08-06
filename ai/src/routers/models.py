"""OpenAI-compatible ``GET /v1/models`` endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from src.providers import catalog
from src.config import settings

router = APIRouter(tags=["Models"])


@router.get("/v1/models", summary="List available models")
async def list_models() -> dict:
    models = await catalog.list_models()
    return {
        "object": "list",
        "data": [
            {
                "id": entry.id,
                "provider": entry.provider,
                "configured": entry.configured,
                "context_length": entry.context_length or settings.default_context_length,
            }
            for entry in models
        ],
    }
