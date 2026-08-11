"""Reverse proxy: ``/ai/*`` -> AI Agent microservice (OpenAI-compatible gateway).

Фронтенд обращается к микросервису через единую точку входа API (порт 8000),
а не напрямую: ``VITE_API_BASE_URL`` указывает на API. Этот роутер пробрасывает
``GET /ai/v1/models`` и ``POST /ai/v1/chat/completions`` на микросервис
(``ai/``, порт 50054), сохраняя SSE-стриминг для chat completions.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from web.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI Proxy"])

MICROSERVICE_ROOT = "http://127.0.0.1:50054"

_TIMEOUT = httpx.Timeout(300.0, connect=5.0, read=300.0)

_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=_TIMEOUT)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _headers(request: Request) -> dict:
    content_type = request.headers.get("content-type")
    headers = {}
    if content_type:
        headers["content-type"] = content_type
    return headers


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": "proxy_error"}},
    )


async def _unavailable(exc: Exception) -> JSONResponse:
    logger.error("AI Agent microservice unavailable: %s", exc)
    return _error(502, f"AI Agent service unavailable: {exc}")


@router.get("/v1/models", response_model=None)
async def list_models(request: Request) -> JSONResponse:
    client = get_client()
    try:
        response = await client.get(
            f"{MICROSERVICE_ROOT}/v1/models", params=request.query_params
        )
    except httpx.HTTPError as exc:
        return await _unavailable(exc)
    content = response.json() if response.content else {}
    return JSONResponse(status_code=response.status_code, content=content)


@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: Request, user: dict = Depends(get_current_user)
) -> StreamingResponse | JSONResponse:
    client = get_client()
    try:
        body = await request.body()
    except Exception as exc:
        logger.error("Failed to read request body: %s", exc)
        return _error(400, f"Invalid request body: {exc}")

    stream = False
    if body:
        try:
            stream = bool(json.loads(body).get("stream", False))
        except Exception:
            pass

    url = f"{MICROSERVICE_ROOT}/v1/chat/completions"
    try:
        req = client.build_request(
            "POST",
            url,
            params=request.query_params,
            content=body,
            headers=_headers(request),
        )
        response = await client.send(req, stream=True)
    except httpx.HTTPError as exc:
        return await _unavailable(exc)

    if response.status_code >= 400:
        error_content = await response.aread()
        await response.aclose()
        try:
            payload = json.loads(error_content) if error_content else {}
        except Exception:
            payload = {"error": {"message": error_content.decode("utf-8", "replace")}}
        return JSONResponse(status_code=response.status_code, content=payload)

    if stream:
        return StreamingResponse(
            response.aiter_bytes(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
            background=BackgroundTask(response.aclose),
        )

    content = await response.aread()
    await response.aclose()
    try:
        payload = json.loads(content) if content else {}
    except Exception:
        payload = {"error": {"message": content.decode("utf-8", "replace")[:500]}}
    return JSONResponse(status_code=response.status_code, content=payload)
