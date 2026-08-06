"""OpenAI-compatible ``POST /v1/chat/completions`` endpoint.

Supports both streaming (SSE) and non-streaming responses. The upstream provider
reply is passed through unchanged so that any OpenAI-compatible client works
against this service directly.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from src.config import settings
from src.providers import ProviderError, catalog
from src.schemas import ChatCompletionRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat"])


def _error_response(status: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": "invalid_request_error"}},
    )


def _inject_system_prompt(messages: list[dict]) -> list[dict]:
    """Prepend the configured persona when the client did not send a system message."""
    if not settings.system_prompt:
        return messages
    for message in messages:
        if message.get("role") == "system":
            return messages
    return [{"role": "system", "content": settings.system_prompt}, *messages]


@router.post(
    "/v1/chat/completions",
    summary="Chat completion (OpenAI-compatible)",
    response_model=None,
)
async def chat_completions(body: ChatCompletionRequest):
    payload = body.model_dump(exclude_none=True)
    payload["messages"] = _inject_system_prompt(
        [message.model_dump() for message in body.messages]
    )

    try:
        client, resolved_model = catalog.resolve(body.model)
    except ProviderError as exc:
        return _error_response(400, str(exc))
    payload["model"] = resolved_model

    try:
        response, _ = await client.chat_completions(resolved_model, payload)
    except ProviderError as exc:
        logger.error("Upstream chat failed: %s", exc)
        return _error_response(502, str(exc))

    if body.stream:
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
        return JSONResponse(content=json.loads(content))
    except json.JSONDecodeError:
        return _error_response(502, "Upstream provider returned a non-JSON response")
