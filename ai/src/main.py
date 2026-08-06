"""Entry point for the AI Agent microservice.

Run with: poetry run python src/main.py
"""

from __future__ import annotations

import uvicorn

from src.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "src.app:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
