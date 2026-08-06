"""FastAPI application factory for the AI Agent microservice."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.routers import chat, health, models


def create_app() -> FastAPI:
    logging.basicConfig(level=settings.log_level.upper())

    app = FastAPI(
        title="AI Agent Microservice",
        description=(
            "OpenAI-compatible chat gateway. Forwards /v1/chat/completions to "
            "configured providers (LM Studio, DeepSeek, ...) and streams replies."
        ),
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(models.router)
    app.include_router(chat.router)

    return app


app = create_app()
