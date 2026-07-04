import asyncio
import logging
import re
from typing import Any, Callable

import grpc
from grpc import aio
from utils.generated import knowledge_language_pb2, knowledge_language_pb2_grpc

logger = logging.getLogger(__name__)


def split_sentences(text: str) -> list[str]:
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\[\d+\](?:\s*\[\d+\])*', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    raw = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'(])', text)
    return [s.strip() for s in raw if s.strip()]


class KnowledgeLanguageGrpcClient:
    def __init__(self, host: str = None, port: int = None):
        import os
        self.host = host or os.getenv("KL_SERVICE_HOST", "127.0.0.1")
        self.port = port or int(os.getenv("KL_SERVICE_PORT", "50056"))
        self.channel = None
        self.stub = None
        self._connected = False

    async def connect(self):
        if self._connected:
            return
        try:
            options = [
                ("grpc.max_send_message_length", 256 * 1024 * 1024),
                ("grpc.max_receive_message_length", 256 * 1024 * 1024),
            ]
            self.channel = aio.insecure_channel(f"{self.host}:{self.port}", options=options)
            self.stub = knowledge_language_pb2_grpc.KnowledgeLanguageServiceStub(self.channel)
            self._connected = True
            logger.info(f"[kl_grpc] Connected to {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"[kl_grpc] Connection failed: {e}")
            raise

    async def disconnect(self):
        if self.channel:
            await self.channel.close()
            self._connected = False

    def _grpc_response_to_dict(self, response, doc_id: str) -> dict[str, Any]:
        statements = []
        for s in response.statements:
            statements.append({
                "id": s.id,
                "type": "FACT" if s.type == 1 else "META" if s.type == 2 else "UNSPECIFIED",
                "subject_id": s.subject_id,
                "subject_type": "concept" if s.subject_type == 1 else "statement",
                "predicate": s.predicate,
                "object_id": s.object_id,
                "object_type": "concept" if s.object_type == 1 else "statement" if s.object_type == 2 else "literal",
                "literal_value": s.literal_value,
                "confidence": s.confidence,
                "sentence_text": s.sentence_text,
                "created_at": s.created_at,
            })
        concepts = []
        for c in response.concepts:
            concepts.append({
                "id": c.id,
                "text": c.text,
                "normalized_text": c.normalized_text,
            })
        concept_map = {c["id"]: c["text"] for c in concepts}
        for stmt in statements:
            subj_id = stmt.get("subject_id", "")
            obj_id = stmt.get("object_id", "")
            subj_type = stmt.get("subject_type", "concept")
            obj_type = stmt.get("object_type", "concept")
            stmt["subject_text"] = concept_map.get(subj_id, "")
            stmt["object_text"] = concept_map.get(obj_id, "")
            # For Statement-typed subject/object, use UUID as fallback text
            if not stmt["subject_text"] and subj_type == "statement":
                stmt["subject_text"] = subj_id  # UUID of the referenced statement
            if not stmt["object_text"] and obj_type == "statement":
                stmt["object_text"] = obj_id  # UUID of the referenced statement
        return {
            "success": response.success,
            "statements": statements,
            "concepts": concepts,
            "total_statements": response.total_statements,
            "total_concepts": response.total_concepts,
            "message": response.message,
            "doc_id": doc_id,
        }

    async def process_text(self, text: str, doc_id: str = "", use_llm: bool = False, timeout: int = 600) -> dict[str, Any]:
        await self.connect()
        try:
            request = knowledge_language_pb2.ProcessTextRequest(
                text=text, doc_id=doc_id, use_llm=use_llm,
            )
            response = await self.stub.ProcessText(request, timeout=timeout)
            return self._grpc_response_to_dict(response, doc_id)
        except Exception as e:
            logger.exception("[kl_grpc] process_text failed")
            return {
                "success": False, "statements": [], "concepts": [],
                "total_statements": 0, "total_concepts": 0,
                "message": str(e), "doc_id": doc_id,
            }

    async def _call_sentence_grpc(self, sentence: str, doc_id: str, timeout: int) -> dict[str, Any]:
        request = knowledge_language_pb2.ProcessTextRequest(
            text=sentence, doc_id=doc_id, use_llm=False,
        )
        response = await self.stub.ProcessText(request, timeout=timeout)
        return self._grpc_response_to_dict(response, doc_id)

    async def process_text_parallel(
        self, text: str, doc_id: str = "",
        batch_size: int = 10, timeout_per_sentence: int = 60,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        await self.connect()
        sentences = split_sentences(text)
        if not sentences:
            return {
                "success": True, "statements": [], "concepts": [],
                "total_statements": 0, "total_concepts": 0,
                "message": "No sentences found", "doc_id": doc_id,
            }

        all_statements: list[dict] = []
        concept_map: dict[str, dict] = {}
        total = len(sentences)
        processed = 0
        failed = 0

        for i in range(0, total, batch_size):
            batch = sentences[i:i + batch_size]
            tasks = [
                self._call_sentence_grpc(s, doc_id, timeout_per_sentence)
                for s in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.warning("[kl_grpc] Sentence failed: %s", result)
                    failed += 1
                    continue
                if result.get("success"):
                    for stmt in result.get("statements", []):
                        all_statements.append(stmt)
                    for c in result.get("concepts", []):
                        concept_map[c["id"]] = c

            processed += len(batch)
            if progress_callback:
                progress_callback(processed, total)

        for stmt in all_statements:
            subj = concept_map.get(stmt.get("subject_id", ""))
            obj = concept_map.get(stmt.get("object_id", ""))
            if subj and not stmt.get("subject_text"):
                stmt["subject_text"] = subj.get("text", "")
            if obj and not stmt.get("object_text"):
                stmt["object_text"] = obj.get("text", "")

        logger.info("[kl_grpc] Parallel: %d/%d sentences OK, %d failed → %d statements",
                     total - failed, total, failed, len(all_statements))
        return {
            "success": True,
            "statements": all_statements,
            "concepts": list(concept_map.values()),
            "total_statements": len(all_statements),
            "total_concepts": len(concept_map),
            "message": f"Processed {processed} sentences, {failed} failed",
            "doc_id": doc_id,
        }

    async def health_check(self) -> dict[str, str]:
        await self.connect()
        try:
            request = knowledge_language_pb2.HealthCheckRequest()
            response = await self.stub.HealthCheck(request)
            return {
                "status": response.status,
                "service": response.service,
                "details": response.details,
                "timestamp": response.timestamp,
            }
        except Exception as e:
            return {"status": "UNKNOWN", "service": "knowledge_language", "details": str(e), "timestamp": ""}


_kl_client: KnowledgeLanguageGrpcClient | None = None


def get_kl_grpc_client() -> KnowledgeLanguageGrpcClient:
    global _kl_client
    if _kl_client is None:
        _kl_client = KnowledgeLanguageGrpcClient()
    return _kl_client
