"""OpenAI-compatible ``GET /v1/models`` endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from src.providers import catalog
from src.config import model_registry, settings

router = APIRouter(tags=["Models"])


@router.get("/v1/models", summary="List available models")
async def list_models() -> dict:
    models = await catalog.list_models()
    profiles = [
        {
            "id": profile.name,
            "model_id": profile.model_id,
            "provider": profile.provider,
            "configured": True,
            "context_length": profile.context_length,
            "display_name": profile.display_name,
        }
        for profile in model_registry.profiles
    ]
    return {
        "object": "list",
        "data": profiles + [
            {
                "id": entry.id,
                "provider": entry.provider,
                "configured": entry.configured,
                "context_length": entry.context_length or settings.default_context_length,
            }
            for entry in models
        ],
    }
