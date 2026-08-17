"""
Layer: Frameworks & Drivers — Infrastructure
Package: infrastructure.ai_gateway.ai_gateway_client
Responsibility: HTTP-клиент к AI Agent микросервису (OpenAI-совместимый шлюз).

Принадлежит слою Infrastructure: использует httpx для обращения к внешнему
сервису. Возвращает поток SSE-чанков и собранный usage в OpenAI-формате.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator, List, Optional

import httpx

logger = logging.getLogger(__name__)


class AIUsageData:
    """Разобранный usage из ответа провайдера (OpenAI-формат)."""

    def __init__(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        cached_tokens: Optional[int] = None,
        tool_tokens: int = 0,
    ):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        self.cached_tokens = cached_tokens
        self.tool_tokens = tool_tokens


class AIGatewayError(Exception):
    """Ошибка обращения к AI-шлюзу."""


class AIGatewayClient:
    """Тонкий клиент к OpenAI-совместимому шлюзу (порт 50059)."""

    def __init__(self, base_url: str = "http://127.0.0.1:50059", timeout: float = 300.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout, connect=15.0, read=timeout)

    async def stream_chat_completions(
        self,
        messages: List[dict],
        model: str,
        signal=None,
    ) -> AsyncIterator[str]:
        """Стримит SSE-чанки ответа. Возвращает только строки ``data:``.

        Генератор — вызывающий код сам разбирает usage из финальных чанков.
        """
        payload = {
            "model": model or None,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/v1/chat/completions",
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")[:500]
                        raise AIGatewayError(
                            f"AI gateway HTTP {response.status_code}: {body}"
                        )
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if line.startswith("data:"):
                            data = line[len("data:"):].strip()
                            if data:
                                yield data
        except httpx.HTTPError as exc:
            raise AIGatewayError(f"AI gateway unreachable: {exc}") from exc
