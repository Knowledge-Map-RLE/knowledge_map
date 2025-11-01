"""Middleware для FastAPI приложения"""
import logging
from typing import Callable

from fastapi import Request, Response

logger = logging.getLogger(__name__)

# Настройка CORS
ORIGINS = [
    "http://localhost:5173",  # Vite dev server
    "http://127.0.0.1:5173",
    "http://localhost:5174",  # Vite dev server (альтернативный порт)
    "http://127.0.0.1:5174",
    "http://localhost:5175",  # Vite dev server (альтернативный порт 2)
    "http://127.0.0.1:5175",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


async def log_requests(request: Request, call_next: Callable) -> Response:
    """Middleware для логирования запросов"""
    logger.info(f"Request: {request.method} {request.url}")
    logger.info(f"Headers: {dict(request.headers)}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response


async def add_cors_headers(request: Request, call_next: Callable) -> Response:
    """Middleware для добавления CORS заголовков"""
    response = await call_next(request)
    if request.headers.get("origin") in ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = request.headers["origin"]
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "*"
    return response
