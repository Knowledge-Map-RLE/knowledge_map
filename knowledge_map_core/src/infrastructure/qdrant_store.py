from __future__ import annotations

import logging

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointIdsList,
    VectorParams,
)

from src.domain.uniqueness import CandidateMatch

logger = logging.getLogger(__name__)


class QdrantVectorStore:
    """
    Qdrant vector store для семантического поиска утверждений.

    Использует HNSW индекс для ANN-поиска.
    Complexity: O(log N) для поиска, O(1) для upsert/delete.
    """

    def __init__(
        self,
        url: str = "http://localhost:6333",
        collection: str = "statement_embeddings",
        embedding_dimension: int = 384,
    ):
        self._url = url
        self._collection = collection
        self._dimension = embedding_dimension
        self._client: AsyncQdrantClient | None = None

    async def connect(self) -> None:
        if self._client is not None:
            return
        self._client = AsyncQdrantClient(url=self._url)
        await self._ensure_collection()

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    async def _ensure_collection(self) -> None:
        assert self._client is not None
        collections = await self._client.get_collections()
        existing = {c.name for c in collections.collections}

        if self._collection in existing:
            logger.info("Qdrant collection '%s' already exists", self._collection)
            return

        await self._client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(
                size=self._dimension,
                distance=Distance.COSINE,
            ),
        )
        logger.info(
            "Created Qdrant collection '%s' (dim=%d, COSINE)",
            self._collection,
            self._dimension,
        )

    async def upsert(
        self,
        id: str,
        vector: list[float],
        metadata: dict | None = None,
    ) -> None:
        assert self._client is not None
        from qdrant_client.models import PointStruct

        payload = metadata or {}
        point = PointStruct(
            id=hash(id) % (2**63),
            vector=vector,
            payload={"statement_id": id, **payload},
        )
        await self._client.upsert(
            collection_name=self._collection,
            points=[point],
        )

    async def search(
        self,
        vector: list[float],
        top_k: int = 20,
        score_threshold: float | None = None,
    ) -> list[CandidateMatch]:
        assert self._client is not None

        results = await self._client.query_points(
            collection_name=self._collection,
            query=vector,
            limit=top_k,
            score_threshold=score_threshold,
        )

        matches: list[CandidateMatch] = []
        for hit in results.points:
            payload = hit.payload or {}
            stmt_id = payload.get("statement_id", "")
            if not stmt_id:
                continue

            matches.append(CandidateMatch(
                statement_id=stmt_id,
                similarity=hit.score,
                subject_text=payload.get("subject_text", ""),
                predicate=payload.get("predicate", ""),
                object_text=payload.get("object_text", ""),
            ))

        return matches

    async def delete(self, id: str) -> None:
        assert self._client is not None
        point_id = hash(id) % (2**63)
        await self._client.delete(
            collection_name=self._collection,
            points_selector=PointIdsList(points=[point_id]),
        )

    async def count(self) -> int:
        assert self._client is not None
        info = await self._client.get_collection(self._collection)
        return info.points_count or 0
