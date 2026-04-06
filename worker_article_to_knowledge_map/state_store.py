"""
Neo4j-backed state store for worker progress.

Stores WorkerRun and WorkerArticleProgress nodes.
Supports resume across restarts.
"""
import asyncio
import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Optional

from neo4j import AsyncGraphDatabase

from config import Config

logger = logging.getLogger(__name__)

VALID_STATES = frozenset({
    "pending", "ingesting", "awaiting_markdown",
    "annotating", "extracting", "reviewing", "done", "failed"
})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    def __init__(self, config: Config):
        self._config = config
        self._driver = AsyncGraphDatabase.driver(
            config.neo4j_uri,
            auth=(config.neo4j_user, config.neo4j_password),
        )
        self._run_id: str = str(uuid.uuid4())
        self._log_buffer: deque = deque(maxlen=500)
        self._lock = asyncio.Lock()

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def log_buffer(self) -> deque:
        return self._log_buffer

    def log(self, message: str) -> None:
        entry = f"[{_now_iso()}] {message}"
        self._log_buffer.append(entry)
        logger.info(message)

    async def init(self) -> None:
        """Create Neo4j indexes and the WorkerRun node."""
        async with self._driver.session() as session:
            # Indexes for fast aggregation
            await session.run(
                "CREATE INDEX worker_article_run IF NOT EXISTS "
                "FOR (p:WorkerArticleProgress) ON (p.run_id)"
            )
            await session.run(
                "CREATE INDEX worker_article_state IF NOT EXISTS "
                "FOR (p:WorkerArticleProgress) ON (p.state)"
            )
            await session.run(
                "CREATE INDEX worker_run_id IF NOT EXISTS "
                "FOR (r:WorkerRun) ON (r.run_id)"
            )
            # Find or create the WorkerRun for this session
            await session.run(
                """
                MERGE (r:WorkerRun {run_id: $run_id})
                ON CREATE SET r.query = $worker_query,
                              r.total = 0,
                              r.started_at = $now,
                              r.status = 'running'
                ON MATCH SET r.status = 'running',
                             r.started_at = $now
                """,
                run_id=self._run_id,
                worker_query=self._config.query,
                now=_now_iso(),
            )
        self.log(f"StateStore initialised, run_id={self._run_id}")

    async def resume_or_start(self, query: str) -> Optional[str]:
        """
        Look for an existing incomplete WorkerRun with the same query.
        If found, reuse its run_id (resume mode). Otherwise keep the new one.
        Returns run_id being used.
        """
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (r:WorkerRun {query: $worker_query, status: 'running'})
                WHERE r.run_id <> $current_run_id AND r.total > 0
                RETURN r.run_id AS run_id, r.total AS total
                ORDER BY r.started_at DESC LIMIT 1
                """,
                worker_query=query,
                current_run_id=self._run_id,
            )
            rec = await result.single()
            if rec:
                old_run_id = rec["run_id"]
                self.log(f"Resuming existing run {old_run_id} (total={rec['total']})")
                # Delete newly created run node (we'll reuse the old one)
                await session.run(
                    "MATCH (r:WorkerRun {run_id: $rid}) DELETE r",
                    rid=self._run_id,
                )
                self._run_id = old_run_id
            else:
                # Clean up any stale empty runs for this query
                await session.run(
                    """
                    MATCH (r:WorkerRun {query: $worker_query})
                    WHERE r.run_id <> $current_run_id AND r.total = 0
                    DELETE r
                    """,
                    worker_query=query,
                    current_run_id=self._run_id,
                )
        return self._run_id

    async def set_total(self, total: int) -> None:
        async with self._driver.session() as session:
            await session.run(
                "MATCH (r:WorkerRun {run_id: $rid}) SET r.total = $total",
                rid=self._run_id, total=total,
            )

    async def add_articles(self, pmcids: list[str]) -> None:
        """Insert PENDING progress nodes for articles not already tracked."""
        async with self._driver.session() as session:
            await session.run(
                """
                UNWIND $pmcids AS pmcid
                MERGE (p:WorkerArticleProgress {pmcid: pmcid, run_id: $run_id})
                ON CREATE SET p.state = 'pending',
                              p.retry_count = 0,
                              p.doc_id = null,
                              p.error_msg = null,
                              p.updated_at = $now,
                              p.done_at = null
                """,
                pmcids=pmcids, run_id=self._run_id, now=_now_iso(),
            )

    async def get_doc_id(self, pmcid: str) -> Optional[str]:
        """Return stored doc_id for a pmcid, or None if not yet set."""
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (p:WorkerArticleProgress {pmcid: $pmcid, run_id: $run_id})
                RETURN p.doc_id AS doc_id
                """,
                pmcid=pmcid, run_id=self._run_id,
            )
            rec = await result.single()
            return rec["doc_id"] if rec else None

    async def reset_stuck_articles(self) -> int:
        """
        При старте воркера сбрасываем статьи в промежуточных состояниях
        (annotating, extracting, reviewing) назад в pending — они зависли
        при предыдущей остановке воркера.
        """
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (p:WorkerArticleProgress {run_id: $run_id})
                WHERE p.state IN ['annotating', 'extracting', 'reviewing']
                SET p.state = 'pending', p.updated_at = $now
                RETURN count(p) AS cnt
                """,
                run_id=self._run_id, now=_now_iso(),
            )
            rec = await result.single()
            return rec["cnt"] if rec else 0

    async def get_pending_pmcids(self) -> list[str]:
        """Return all PMCIDs not yet in 'done' state (excludes failed that hit max retries)."""
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (p:WorkerArticleProgress {run_id: $run_id})
                WHERE NOT (p.state IN ['done', 'failed'])
                RETURN p.pmcid AS pmcid
                """,
                run_id=self._run_id,
            )
            return [r["pmcid"] async for r in result]

    async def set_state(self, pmcid: str, state: str, doc_id: str = None) -> None:
        params = {
            "pmcid": pmcid,
            "run_id": self._run_id,
            "state": state,
            "now": _now_iso(),
        }
        set_clause = "p.state = $state, p.updated_at = $now"
        if doc_id is not None:
            set_clause += ", p.doc_id = $doc_id"
            params["doc_id"] = doc_id
        if state == "done":
            set_clause += ", p.done_at = $now"

        async with self._driver.session() as session:
            await session.run(
                f"""
                MATCH (p:WorkerArticleProgress {{pmcid: $pmcid, run_id: $run_id}})
                SET {set_clause}
                """,
                **params,
            )

    async def set_error(self, pmcid: str, error_msg: str) -> None:
        async with self._driver.session() as session:
            await session.run(
                """
                MATCH (p:WorkerArticleProgress {pmcid: $pmcid, run_id: $run_id})
                SET p.error_msg = $msg, p.updated_at = $now
                """,
                pmcid=pmcid, run_id=self._run_id,
                msg=error_msg[:500], now=_now_iso(),
            )

    async def increment_retry(self, pmcid: str) -> int:
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (p:WorkerArticleProgress {pmcid: $pmcid, run_id: $run_id})
                SET p.retry_count = coalesce(p.retry_count, 0) + 1,
                    p.state = 'pending',
                    p.updated_at = $now
                RETURN p.retry_count AS cnt
                """,
                pmcid=pmcid, run_id=self._run_id, now=_now_iso(),
            )
            rec = await result.single()
            return rec["cnt"] if rec else 0

    async def get_retry_count(self, pmcid: str) -> int:
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (p:WorkerArticleProgress {pmcid: $pmcid, run_id: $run_id})
                RETURN coalesce(p.retry_count, 0) AS cnt
                """,
                pmcid=pmcid, run_id=self._run_id,
            )
            rec = await result.single()
            return rec["cnt"] if rec else 0

    async def get_summary(self) -> dict:
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (r:WorkerRun {run_id: $run_id})
                OPTIONAL MATCH (p:WorkerArticleProgress {run_id: $run_id})
                RETURN r.status AS status,
                       r.started_at AS started_at,
                       count(p) AS total,
                       count(CASE WHEN p.state = 'done' THEN 1 END) AS done,
                       count(CASE WHEN p.state = 'failed' THEN 1 END) AS failed,
                       count(CASE WHEN p.state IN ['ingesting','awaiting_markdown','annotating','extracting','reviewing'] THEN 1 END) AS in_progress,
                       count(CASE WHEN p.state = 'pending' THEN 1 END) AS pending
                """,
                run_id=self._run_id,
            )
            rec = await result.single()
            if not rec:
                return {
                    "run_id": self._run_id,
                    "total": 0, "done": 0, "failed": 0,
                    "in_progress": 0, "pending": 0,
                    "percent": 0.0, "status": "unknown", "started_at": None,
                }
            total = rec["total"] or 0
            done = rec["done"] or 0
            return {
                "run_id": self._run_id,
                "total": total,
                "done": done,
                "failed": rec["failed"] or 0,
                "in_progress": rec["in_progress"] or 0,
                "pending": rec["pending"] or 0,
                "percent": round(done / total * 100, 1) if total else 0.0,
                "status": rec["status"] or "unknown",
                "started_at": rec["started_at"],
            }

    async def get_details(self, limit: int = 100, offset: int = 0) -> list[dict]:
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (p:WorkerArticleProgress {run_id: $run_id})
                RETURN p.pmcid AS pmcid, p.doc_id AS doc_id,
                       p.state AS state, p.retry_count AS retry_count,
                       p.error_msg AS error_msg, p.updated_at AS updated_at,
                       p.done_at AS done_at
                ORDER BY p.updated_at DESC
                SKIP $offset LIMIT $limit
                """,
                run_id=self._run_id, limit=limit, offset=offset,
            )
            return [dict(r) async for r in result]

    async def reset_all_to_pending(self) -> dict:
        """
        Сбрасывает ВСЕ статьи (включая done/failed) обратно в pending
        и удаляет их Action-ноды из Neo4j.
        Используется для полного перезапуска создания карт знаний.
        """
        async with self._driver.session() as session:
            # Собрать doc_id обработанных статей
            result = await session.run(
                """
                MATCH (p:WorkerArticleProgress {run_id: $run_id})
                WHERE p.state IN ['done', 'failed']
                RETURN p.pmcid AS pmcid, p.doc_id AS doc_id
                """,
                run_id=self._run_id,
            )
            records = [dict(r) async for r in result]

            # Сбросить состояния
            reset_result = await session.run(
                """
                MATCH (p:WorkerArticleProgress {run_id: $run_id})
                WHERE p.state IN ['done', 'failed']
                SET p.state = 'pending',
                    p.retry_count = 0,
                    p.error_msg = null,
                    p.done_at = null,
                    p.updated_at = $now
                RETURN count(p) AS cnt
                """,
                run_id=self._run_id, now=_now_iso(),
            )
            rec = await reset_result.single()
            reset_count = rec["cnt"] if rec else 0

            doc_ids = [r["doc_id"] for r in records if r.get("doc_id")]

            # Удалить Action-ноды для этих документов
            deleted_count = 0
            if doc_ids:
                del_result = await session.run(
                    """
                    UNWIND $doc_ids AS did
                    MATCH (a:Action {doc_id: did})
                    DETACH DELETE a
                    """,
                    doc_ids=doc_ids,
                )
                summary = await del_result.consume()
                deleted_count = summary.counters.nodes_deleted

        self.log(
            f"Reset {reset_count} articles to pending, "
            f"deleted {deleted_count} Action nodes from {len(doc_ids)} documents"
        )
        return {"reset_count": reset_count, "deleted_actions": deleted_count, "doc_ids": doc_ids}

    async def mark_run_done(self) -> None:
        async with self._driver.session() as session:
            await session.run(
                "MATCH (r:WorkerRun {run_id: $rid}) SET r.status = 'done'",
                rid=self._run_id,
            )

    async def close(self) -> None:
        await self._driver.close()
