from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncGraphDatabase, async_transaction

from src.config import settings
from src.domain.models import Statement, StatementType, Concept, Literal

logger = logging.getLogger(__name__)


class Neo4jWriter:
    def __init__(self, uri: str | None = None, user: str | None = None, password: str | None = None):
        self._uri = uri or settings.neo4j_uri
        self._user = user or settings.neo4j_user
        self._password = password or settings.neo4j_password
        self._driver = None

    async def __aenter__(self) -> Neo4jWriter:
        self._driver = AsyncGraphDatabase.driver(
            self._uri,
            auth=(self._user, self._password),
        )
        return self

    async def __aexit__(self, *args) -> None:
        if self._driver:
            await self._driver.close()

    async def write_graph(self, statements: list[Statement], doc_id: str = "") -> dict[str, Any]:
        if not self._driver:
            raise RuntimeError("Not connected. Use async with.")

        result = {"statements_written": 0, "concepts_written": 0, "errors": []}

        async with self._driver.session() as session:
            for stmt in statements:
                try:
                    await session.execute_write(self._write_statement, stmt, doc_id)
                    result["statements_written"] += 1
                except Exception as e:
                    logger.exception("Failed to write statement %s", stmt.id)
                    result["errors"].append(str(e))

        return result

    async def _write_statement(self, tx, stmt: Statement, doc_id: str) -> None:
        if doc_id:
            await tx.run(
                """
                MERGE (d:Document {id: $doc_id})
                """,
                doc_id=doc_id,
            )

        if isinstance(stmt.subject, Concept):
            await self._merge_concept(tx, stmt.subject, doc_id)

        if isinstance(stmt.object, Concept):
            await self._merge_concept(tx, stmt.object, doc_id)

        stmt_type = "Fact" if stmt.type == StatementType.FACT else "Meta"
        await tx.run(
            """
            MERGE (s:Statement {id: $id})
            SET s.type = $type,
                s.predicate = $predicate,
                s.confidence = $confidence,
                s.sentence = $sentence,
                s.created_at = $created_at
            """,
            id=str(stmt.id),
            type=stmt_type,
            predicate=stmt.predicate,
            confidence=stmt.confidence,
            sentence=stmt.sentence_text,
            created_at=int(stmt.created_at.timestamp()),
        )

        if doc_id:
            await tx.run(
                """
                MATCH (d:Document {id: $doc_id})
                MATCH (s:Statement {id: $stmt_id})
                MERGE (d)-[:CONTAINS]->(s)
                """,
                doc_id=doc_id,
                stmt_id=str(stmt.id),
            )

        subject_clause = self._entity_clause(stmt.subject, "subject")
        object_clause = self._entity_clause(stmt.object, "object")

        await tx.run(
            f"""
            MATCH (s:Statement {{id: $id}})
            MATCH {subject_clause}
            MATCH {object_clause}
            MERGE (subj)-[r:RELATES_TO {{predicate: $predicate}}]->(obj)
            SET r.statement_id = $id
            """,
            id=str(stmt.id),
            predicate=stmt.predicate,
        )

    async def _merge_concept(self, tx, concept: Concept, doc_id: str) -> None:
        await tx.run(
            """
            MERGE (c:Concept {id: $id})
            SET c.text = $text,
                c.normalized_text = $normalized_text
            """,
            id=concept.id,
            text=concept.text,
            normalized_text=concept.normalized_text or concept.text,
        )

        if doc_id:
            await tx.run(
                """
                MATCH (d:Document {id: $doc_id})
                MATCH (c:Concept {id: $concept_id})
                MERGE (d)-[:CONTAINS]->(c)
                """,
                doc_id=doc_id,
                concept_id=concept.id,
            )

    def _entity_clause(self, entity, alias: str) -> str:
        if isinstance(entity, Concept):
            return f"({alias}:Concept {{id: '{entity.id}'}})"
        if isinstance(entity, Statement):
            return f"({alias}:Statement {{id: '{entity.id}'}})"
        if isinstance(entity, Literal):
            escaped = entity.value.replace("'", "\\'")
            return f"({alias}:Literal {{value: '{escaped}', type: '{entity.type}'}})"
        return f"({alias}:Literal {{value: 'unknown'}})"
