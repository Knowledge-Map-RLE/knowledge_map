from __future__ import annotations

import json
import logging

import grpc

from src.config import settings

logger = logging.getLogger(__name__)


class AIClient:
    def __init__(self, host: str | None = None, port: int | None = None):
        self._host = host or settings.ai_grpc_host
        self._port = port or settings.ai_grpc_port
        self._channel: grpc.aio.Channel | None = None

    async def __aenter__(self) -> AIClient:
        self._channel = grpc.aio.insecure_channel(
            f"{self._host}:{self._port}",
            options=[
                ("grpc.max_send_message_length", 256 * 1024 * 1024),
                ("grpc.max_receive_message_length", 256 * 1024 * 1024),
            ],
        )
        return self

    async def __aexit__(self, *args) -> None:
        if self._channel:
            await self._channel.close()

    async def suggest_meta_statements(
        self,
        sentence: str,
        existing_statements: list[dict],
        model_id: str | None = None,
    ) -> list[dict]:
        from src.llm import ai_model_pb2_grpc, ai_model_pb2

        stub = ai_model_pb2_grpc.AIModelServiceStub(self._channel)

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

        request = ai_model_pb2.GenerateTextRequest(
            model_id=model_id or settings.default_llm_model,
            prompt=prompt,
            max_tokens=512,
            temperature=0.1,
        )

        try:
            response = await stub.GenerateText(request)
        except grpc.RpcError as e:
            logger.error("AI gRPC call failed: %s", e)
            return []

        if not response.success:
            logger.warning("AI generation unsuccessful: %s", response.message)
            return []

        return self._parse_response(response.generated_text)

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
