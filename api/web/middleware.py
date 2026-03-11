"""
Layer: Frameworks & Drivers — Web
Package: web.middleware
Responsibility: CORS-конфигурация и middleware для логирования запросов.

Перемещено из src/middleware.py без изменений.

Allowed imports: fastapi, os, стандартная библиотека
Forbidden imports: domain, application, adapters, infrastructure, neomodel
"""
import logging
import os
from typing import Callable

from fastapi import Request, Response

logger = logging.getLogger(__name__)

_extra_origins = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
]
ORIGINS = _extra_origins + [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5555",
    "http://127.0.0.1:5555",
]


async def log_requests(request: Request, call_next: Callable) -> Response:
    logger.debug(f"{request.method} {request.url}")
    response = await call_next(request)
    if response.status_code >= 400:
        logger.warning(f"{request.method} {request.url} → {response.status_code}")
    return response


async def add_cors_headers(request: Request, call_next: Callable) -> Response:
    response = await call_next(request)
    if request.headers.get("origin") in ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = request.headers["origin"]
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "*"
    return response
