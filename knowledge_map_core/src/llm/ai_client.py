"""Async HTTP client for the AI Agent microservice (OpenAI-compatible gateway)."""

from __future__ import annotations

import json
import logging

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class AIClient:
    def __init__(self, host: str | None = None, port: int | None = None):
        self._host = host or settings.ai_service_host
        self._port = port or settings.ai_service_port
        self._base_url = f"http://{self._host}:{self._port}/v1"

    async def __aenter__(self) -> AIClient:
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0))
        return self

    async def __aexit__(self, *args) -> None:
        await self._client.aclose()

    async def suggest_meta_statements(
        self,
        sentence: str,
        existing_statements: list[dict],
        model_id: str | None = None,
    ) -> list[dict]:
        """Ask the AI agent for missing META statements between extracted facts."""
        facts_text = "\n".join(
            f"{s['id']}: {s['subject']} → {s['predicate']} → {s['object']}"
            for s in existing_statements
        )

        prompt = (
            f"Sentence: {sentence}\n\n"
            f"Extracted facts:\n{facts_text}\n\n"
            "Task: Identify missing meta-statements (links between facts).\n"
            "Output ONLY lines in this format (no explanations):\n"
            "M: <subject_id> → <predicate> → <object_id>\n"
            "If none, output: NONE"
        )

        payload = {
            "model": model_id or settings.default_llm_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "max_tokens": 512,
            "temperature": 0.1,
        }

        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions", json=payload
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            logger.error("AI Agent HTTP call failed: %s", exc)
            return []

        content = data["choices"][0]["message"].get("content", "")
        return self._parse_response(content)

    def _parse_response(self, text: str) -> list[dict]:
        results = []
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("M:") and "→" in line:
                parts = line[2:].split("→")
                if len(parts) == 3:
                    results.append({
                        "type": "META",
                        "subject_id": parts[0].strip(),
                        "predicate": parts[1].strip(),
                        "object_id": parts[2].strip(),
                    })
        return results
