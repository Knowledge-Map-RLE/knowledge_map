"""OpenAI-compatible ``POST /v1/chat/completions`` endpoint.

Supports both streaming (SSE) and non-streaming responses. The upstream provider
reply is passed through unchanged so that any OpenAI-compatible client works
against this service directly.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

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

    stream_requested = bool(payload.get("stream"))

    if not stream_requested:
        try:
            data = await client.generate(resolved_model, payload)
        except ProviderError as exc:
            logger.error("Upstream chat failed: %s", exc)
            return _error_response(502, str(exc))
        return JSONResponse(content=data)

    async def _stream():
        async for frame in client.stream(resolved_model, payload):
            yield frame
        yield b"data: [DONE]\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
