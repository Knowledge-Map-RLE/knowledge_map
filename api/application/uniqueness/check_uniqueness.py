"""
Use case: Проверка уникальности одного утверждения.

Вызывается при попытке добавить знание-кандидата.
ВозвращаетSAME/UNCERTAIN/DIFFERENT/NEW с ссылкой на существующее утверждение.
"""
from __future__ import annotations

import logging

from services.knowledge_language_grpc_client import KnowledgeLanguageGrpcClient

logger = logging.getLogger(__name__)


async def check_knowledge_uniqueness(
    grpc_client: KnowledgeLanguageGrpcClient,
    *,
    subject_text: str,
    predicate: str,
    object_text: str,
    sentence_text: str,
) -> dict:
    """
    Проверяет уникальность знания-кандидата в графе утверждений.

    Алгоритм:
    1. Fingerprint (SHA256) — O(1) Neo4j lookup
    2. Embedding + Qdrant vector search — O(log N)
    3. Cosine similarity threshold — O(K) where K=top_k
    """
    return await grpc_client.check_uniqueness(
        subject_text=subject_text,
        predicate=predicate,
        object_text=object_text,
        sentence_text=sentence_text,
    )
