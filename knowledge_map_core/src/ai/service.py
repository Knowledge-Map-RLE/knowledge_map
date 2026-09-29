"""Local LLM extraction service — fallback when rule-based extraction yields no results."""

from __future__ import annotations

import logging
from typing import Any

import grpc

from src.ai.prompts import get_prompt
from src.config import model_registry, settings
from src.llm import ai_model_pb2_grpc, ai_model_pb2
from src.domain.models import Statement, StatementType, StatementID, Concept
from src.extractor.context import ExtractionContext

logger = logging.getLogger(__name__)


def _extract_dsl(text: str) -> list[dict[str, str]]:
    """Parse direct relation DSL without accepting JSON or Markdown fallbacks."""
    triplets: list[dict[str, str]] = []
    for line in text.splitlines():
        parts = [part.strip() for part in line.split("|")]
        if not parts or parts[0] != "R":
            continue
        fields = dict(part.split("=", 1) for part in parts[1:] if "=" in part)
        if {"sub", "pred", "obj"} <= fields.keys():
            triplets.append({"subject": fields["sub"], "predicate": fields["pred"], "object": fields["obj"]})
    return triplets


class LocalAIExtractor:
    """Extract triplets via the local AI gRPC service (port 50059)."""

    def __init__(self, host: str = "localhost", port: int = 50059):
        self._host = host
        self._port = port
        self._default_model = model_registry.profile(role="knowledge_core").profile_name

    async def extract(
        self,
        sentence: str,
        ctx: ExtractionContext,
        task_type: str = "general",
        model_id: str | None = None,
    ) -> list[Statement]:
        """Run LLM extraction and return Statement objects."""
        prompt = get_prompt(task_type, sentence)
        model = model_id or self._default_model

        try:
            async with grpc.aio.insecure_channel(
                f"{self._host}:{self._port}",
                options=[
                    ("grpc.max_send_message_length", 256 * 1024 * 1024),
                    ("grpc.max_receive_message_length", 256 * 1024 * 1024),
                ],
            ) as channel:
                stub = ai_model_pb2_grpc.AIModelServiceStub(channel)
                request = ai_model_pb2.GenerateTextRequest(
                    model_id=model,
                    prompt=prompt,
                    max_tokens=512,
                    temperature=0.1,
                    top_p=0.9,
                    top_k=50,
                )
                response = await stub.GenerateText(request)
        except grpc.RpcError as e:
            logger.warning("Local AI gRPC call failed: %s", e)
            return []

        if not response.success:
            logger.warning("Local AI generation failed: %s", response.message)
            return []

        raw = response.generated_text
        logger.debug("LLM raw output: %s", raw[:200])

        triplets = _extract_dsl(raw)
        if not triplets:
            logger.info("LLM returned no parseable triplets for: %s", sentence[:60])
            return []

        statements: list[Statement] = []
        for item in triplets:
            subj_text = (item.get("subject") or "").strip()
            pred_text = (item.get("predicate") or "").strip().lower()
            obj_text = (item.get("object") or "").strip()
            if not subj_text or not pred_text or not obj_text:
                continue
            subject = ctx.get_or_create_concept(subj_text)
            obj = ctx.get_or_create_concept(obj_text)
            statements.append(Statement(
                id=StatementID.new(),
                type=StatementType.FACT,
                subject=subject,
                predicate=pred_text,
                object=obj,
                sentence_text=ctx.sentence_text,
            ))

        if statements:
            logger.info("LLM extracted %d triplet(s) for: %s", len(statements), sentence[:60])
        return statements
