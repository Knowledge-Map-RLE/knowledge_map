"""
Use case: Добавление знания с автоматической проверкой уникальности.

Если знание уже есть — возвращает существующий ID и ссылку.
Если новое — создаёт утверждение и связывает с источником.
"""
from __future__ import annotations

import logging

from services.knowledge_language_grpc_client import KnowledgeLanguageGrpcClient

logger = logging.getLogger(__name__)


async def add_knowledge_with_uniqueness(
    grpc_client: KnowledgeLanguageGrpcClient,
    *,
    subject_text: str,
    predicate: str,
    object_text: str,
    sentence_text: str,
    doc_id: str = "",
) -> dict:
    """
    Добавляет знание с предварительной проверкой уникальности.

    Если status=SAME → создаёт связь нового источника с существующим утверждением.
    Если status=NEW  → создаёт новое утверждение в графе.
    Если status=UNCERTAIN → помечает для ревью.
    """
    result = await grpc_client.add_statement_with_uniqueness(
        subject_text=subject_text,
        predicate=predicate,
        object_text=object_text,
        sentence_text=sentence_text,
        doc_id=doc_id,
    )

    if result.get("status") == "SAME" and result.get("existing_statement_id"):
        _link_source_to_existing(result["existing_statement_id"], doc_id)

    return result


def _link_source_to_existing(statement_id: str, doc_id: str) -> None:
    if not doc_id or not statement_id:
        return
    try:
        from neomodel import db
        db.cypher_query(
            """
            MATCH (d:Document {id: $doc_id})
            MATCH (s:Statement {id: $stmt_id})
            MERGE (d)-[:CONTAINS]->(s)
            SET s.evidence_count = COALESCE(s.evidence_count, 0) + 1
            """,
            {"doc_id": doc_id, "stmt_id": statement_id},
        )
    except Exception as e:
        logger.warning("Failed to link source: %s", e)
