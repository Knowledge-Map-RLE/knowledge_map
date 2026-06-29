from __future__ import annotations

import logging
from datetime import datetime, timezone

import grpc

from src import knowledge_language_pb2
from src.services.pipeline import Pipeline

logger = logging.getLogger(__name__)


class KnowledgeLanguageServicer:
    def __init__(self, pipeline: Pipeline | None = None):
        self._pipeline = pipeline or Pipeline()

    async def ProcessText(self, request, context):
        try:
            result = await self._pipeline.process(
                text=request.text,
                doc_id=request.doc_id,
                use_llm=request.use_llm,
                llm_model_id=request.llm_model_id or None,
            )

            response = knowledge_language_pb2.KnowledgeGraphResponse(
                success=result["success"],
                statements=result["statements"],
                concepts=result["concepts"],
                total_statements=result["total_statements"],
                total_concepts=result["total_concepts"],
                message=result["message"],
                doc_id=request.doc_id,
            )
            return response

        except Exception as e:
            logger.exception("ProcessText failed")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return knowledge_language_pb2.KnowledgeGraphResponse(
                success=False,
                message=str(e),
            )

    async def HealthCheck(self, request, context):
        return knowledge_language_pb2.HealthCheckResponse(
            status="SERVING",
            service="knowledge_language",
            details="Knowledge Language Parser running",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
        )
