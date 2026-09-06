"""
Layer: Application — Service
Package: services.citation_graph_service
Responsibility: Запись цитатного графа в Neo4j + статистика + управление загрузкой.

Работает через neo4j.GraphDatabase.driver (прямой Cypher), как data_download_service.
Создаёт Document узлы с doi + title и BIBLIOGRAPHIC_LINK рёбра между ними.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from services.layout_client import get_layout_client, LayoutOptions  # noqa: F401
from neo4j import GraphDatabase

from .citation_sources import ALL_SOURCES
from .citation_sources.base import BulkLoadOptions, CitationEdge, CitationSource, TestEstimate
from .citation_merge_service import CitationMergeService

logger = logging.getLogger(__name__)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# Множитель расстояния по оси X между блоками карты цитат.
# Координаты x, вычисленные layout-сервисом, при записи в Neo4j умножаются на этот
# коэффициент, что делает горизонтальные расстояния в exactly 10 раз больше
# (согласовано с fallback-константой LAYER_SPACING = 2400 в layout_service).
X_SPACING_MULTIPLIER = 10

CITATION_SOURCES_CONFIG = {
    "opencitations": {
        "name": "OpenCitations COCI",
        "url": "https://download.opencitations.net",
        "source_type": "api+bulk",
        "description": "Индекс COCI: 2.5+ млрд DOI-to-DOI цитат (CSV dump ~40 GB + REST API v2)",
    },
    "openalex": {
        "name": "OpenAlex",
        "url": "s3://openalex/data/jsonl/works",
        "source_type": "s3+api",
        "description": "264M+ работ: references, citations, metadata (JSONL dump ~330 GB + REST API)",
    },
    "crossref": {
        "name": "Crossref",
        "url": "s3://api-snapshots-reqpays-crossref",
        "source_type": "s3+api",
        "description": "180M+ DOI с reference списками (annual dump ~208 GB + REST API)",
    },
    "datacite": {
        "name": "DataCite",
        "url": "https://datafiles.datacite.org",
        "source_type": "api+bulk",
        "description": "108M DOI с relatedIdentifiers (public dump ~33 GB + REST API)",
    },
}

BATCH_SIZE = 500
CHECKPOINT_DIR = Path("data/citation_graph_checkpoints")


class CitationGraphService:
    """Управление цитатным графом: загрузка, запись в Neo4j, статистика."""

    def __init__(self) -> None:
        self.driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            max_connection_pool_size=10,
        )
        self._merge_service = CitationMergeService()
        self._sources: dict[str, CitationSource] = {}
        for key, cls in ALL_SOURCES.items():
            try:
                self._sources[key] = cls()
            except Exception as e:
                logger.warning("Failed to init source %s: %s", key, e)
        self._active_loads: dict[str, bool] = {}
        self._pause_events: dict[str, threading.Event] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._load_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="citation-load")
        self._enrich_task: Optional[asyncio.Future] = None
        self._enrich_state: Dict[str, Any] = {
            "running": False,
            "total_files": 0,
            "processed_files": 0,
            "processed_dois": 0,
            "matched_documents": 0,
            "last_file": None,
            "error": None,
        }
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        self.driver.close()

    def _run_query(self, query: str, **params: Any) -> Any:
        with self.driver.session() as session:
            return session.run(query, **params)

    def _run_write(self, query: str, **params: Any) -> Any:
        with self.driver.session() as session:
            return session.run(query, **params)

    # ── Source Status ──────────────────────────────────────────────────────

    def initialize_sources(self) -> None:
        for key, config in CITATION_SOURCES_CONFIG.items():
            self._run_query(
                """
                MERGE (s:CitationSource {key: $key})
                SET s.name = $name,
                    s.url = $url,
                    s.source_type = $source_type,
                    s.description = $description,
                    s.total_edges = 0,
                    s.downloaded_edges = 0,
                    s.progress_percent = 0.0,
                    s.status = 'idle',
                    s.command = '',
                    s.error_message = null,
                    s.last_updated = datetime()
                """,
                key=key,
                name=config["name"],
                url=config["url"],
                source_type=config["source_type"],
                description=config["description"],
            )
        known_keys = list(CITATION_SOURCES_CONFIG.keys())
        self._run_query(
            """
            MATCH (s:CitationSource)
            WHERE NOT s.key IN $keys
            DETACH DELETE s
            """,
            keys=known_keys,
        )
        logger.info("Citation sources initialized in Neo4j")

    def get_all_sources(self) -> List[Dict[str, Any]]:
        with self.driver.session() as session:
            result = session.run("""
                MATCH (s:CitationSource)
                RETURN s.key as key,
                       s.name as name,
                       s.url as url,
                       s.source_type as source_type,
                       s.description as description,
                       s.total_edges as total_edges,
                       s.downloaded_edges as downloaded_edges,
                       s.progress_percent as progress_percent,
                       s.status as status,
                       s.error_message as error_message,
                       s.last_updated as last_updated
                ORDER BY s.key
            """)
            rows = [dict(record) for record in result]
        # Статус, оставшийся в Neo4j от мёртвого worker'а (перезапуск API,
        # падение/завершение процесса), считаем недействительным: реальную
        # активность даёт флаг в памяти. Клиент увидит "idle" и сможет стартовать.
        for row in rows:
            key = row.get("key")
            if row.get("status") in ("downloading", "paused", "layouting") and key and not self._is_source_busy(key):
                self.set_status(key, "idle")
                row["status"] = "idle"
                row["error_message"] = None
        return rows

    def is_source_active(self, key: str) -> bool:
        """True, если для источника реально выполняется фоновый worker."""
        return self._is_source_busy(key)

    def update_progress(self, key: str, downloaded: int, total: int, status: str, error: Optional[str] = None) -> None:
        progress = (downloaded / total * 100) if total > 0 else 0
        self._run_query(
            """
            MATCH (s:CitationSource {key: $key})
            SET s.downloaded_edges = $downloaded,
                s.total_edges = $total,
                s.progress_percent = $progress,
                s.status = $status,
                s.error_message = $error,
                s.last_updated = datetime()
            """,
            key=key, downloaded=downloaded, total=total,
            progress=round(progress, 2), status=status, error=error,
        )

    def set_status(self, key: str, status: str, error: Optional[str] = None) -> None:
        self._run_query(
            """
            MATCH (s:CitationSource {key: $key})
            SET s.status = $status,
                s.error_message = $error,
                s.last_updated = datetime()
            """,
            key=key, status=status, error=error,
        )

    def set_command(self, key: str, command: str) -> None:
        self._run_query(
            """
            MATCH (s:CitationSource {key: $key})
            SET s.command = $command,
                s.last_updated = datetime()
            """,
            key=key, command=command,
        )

    # ── Neo4j Write ────────────────────────────────────────────────────────

    def write_edges_batch(self, edges: List[CitationEdge]) -> int:
        """Записывает пакет edges в Neo4j через UNWIND. Возвращает кол-во записанных."""
        if not edges:
            return 0
        batch = [
            {
                "citing_doi": e.citing_doi,
                "cited_doi": e.cited_doi,
                "source": e.source,
                "title_citing": e.title_citing or "",
                "title_cited": e.title_cited or "",
                "primary_field_citing": e.primary_field_citing,
                "fields_citing": e.fields_citing,
                "primary_field_cited": e.primary_field_cited,
                "fields_cited": e.fields_cited,
            }
            for e in edges
        ]
        query = """
        UNWIND $batch AS edge
        MERGE (citing:Document {doi: edge.citing_doi})
          ON CREATE SET citing.title = CASE WHEN edge.title_citing <> '' THEN edge.title_citing ELSE null END,
                        citing.source = 'citation_import',
                        citing.created_at = datetime()
        SET citing.uid = citing.doi
        FOREACH (_ IN CASE WHEN edge.fields_citing IS NOT NULL THEN [1] ELSE [] END |
            SET citing.primary_field = edge.primary_field_citing,
                citing.fields = edge.fields_citing
        )
        MERGE (cited:Document {doi: edge.cited_doi})
          ON CREATE SET cited.title = CASE WHEN edge.title_cited <> '' THEN edge.title_cited ELSE null END,
                        cited.source = 'citation_import',
                        cited.created_at = datetime()
        SET cited.uid = cited.doi
        FOREACH (_ IN CASE WHEN edge.fields_cited IS NOT NULL THEN [1] ELSE [] END |
            SET cited.primary_field = edge.primary_field_cited,
                cited.fields = edge.fields_cited
        )
        MERGE (citing)-[r:BIBLIOGRAPHIC_LINK]->(cited)
        ON CREATE SET r.source = edge.source,
                      r.created_at = datetime()
        ON MATCH SET r.source = CASE
            WHEN NOT edge.source IN split(r.source, '|')
            THEN r.source + '|' + edge.source
            ELSE r.source END
        """
        result = self._run_write(query, batch=batch)
        summary = result.consume()
        counters = summary.counters
        return counters.nodes_created + counters.relationships_created + counters.properties_set

    async def write_edges_async(
        self,
        edges: List[CitationEdge],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> int:
        """Асинхронная запись edges пакетами."""
        import concurrent.futures
        total = len(edges)
        written = 0
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            for i in range(0, total, BATCH_SIZE):
                batch = edges[i : i + BATCH_SIZE]
                written += await loop.run_in_executor(executor, self.write_edges_batch, batch)
                if progress_callback:
                    progress_callback(min(i + BATCH_SIZE, total), total)

        logger.info("Written %d edge operations for %d edges", written, total)
        return written

    # ── Layout ──────────────────────────────────────────────────────────────

    async def layout_citation_graph(self) -> Dict[str, Any]:
        """Вычисляет координаты (layer, level, x, y) для цитатного графа через layout-сервис.

        Читает узлы и рёбра из Neo4j, отправляет в layout_client.calculate_layout(),
        записывает вычисленные координаты обратно в Neo4j (пакетами UNWIND).

        Метод вызывается из worker-потока массовой загрузки и не должен выполняться
        в event loop API-сервера.
        """
        from infrastructure.graph_layout_client import get_graph_layout_client

        logger.info("Starting citation graph layout calculation")
        self._ensure_document_indexes()

        # Вычисляем слабо связную компоненту графа цитирований, «затравленную»
        # узлами, импортированными как citation_import. Двигаемся по
        # BIBLIOGRAPHIC_LINK в обе стороны, чтобы в укладку попали и смежные
        # узлы других источников (pmc/pubmed), а не только помеченные
        # citation_import. Ограничение защищает от расползания на весь корпус.
        with self.driver.session() as session:
            seed_result = session.run(
                "MATCH (n:Document {source: 'citation_import'}) RETURN n.uid LIMIT 50000"
            ).values()
        seed_ids = {str(row[0]) for row in seed_result if row and row[0] is not None}
        if not seed_ids:
            return self._empty_layout_result()

        node_ids: set[str] = {uid for uid in seed_ids if uid != "None"}
        frontier = list(seed_ids)
        component_cap = 50_000
        while frontier and len(node_ids) < component_cap:
            with self.driver.session() as session:
                neighbors_rows = session.run(
                    """
                    MATCH (a:Document)-[r:BIBLIOGRAPHIC_LINK]-(b:Document)
                    WHERE a.uid IN $ids
                    RETURN b.uid AS uid
                    """,
                    ids=list(frontier),
                ).values()
            new_ids = {
                str(row[0]) for row in neighbors_rows
                if row and row[0] is not None and str(row[0]) != "None" and str(row[0]) not in node_ids
            }
            if not new_ids:
                break
            node_ids |= new_ids
            frontier = list(new_ids)

        if not node_ids:
            logger.warning("No citation nodes found for layout")
            return self._empty_layout_result()

        cleanup_stats = self.cleanup_antiparallel_edges()
        if cleanup_stats["removed"]:
            logger.info("Layout: cleaned %d spurious antiparallel edges", cleanup_stats["removed"])

        links_query = """
        MATCH (s:Document)-[r:BIBLIOGRAPHIC_LINK]->(t:Document)
        WHERE s.uid IN $ids AND t.uid IN $ids
        RETURN s.uid AS source_id, t.uid AS target_id
        """
        with self.driver.session() as session:
            link_rows = session.run(links_query, ids=list(node_ids)).values()
        # В БД BIBLIOGRAPHIC_LINK направлено citing -> cited (новая -> старая).
        # Используем это направление как есть: целевой узел (cited) двигатель
        # укладывает на следующий слой после исходного (citing), что соответствует
        # текущей семантике графа.
        links = [{"source_id": str(row[0]), "target_id": str(row[1])} for row in link_rows]

        logger.info("Layout input: %d nodes, %d links", len(node_ids), len(links))

        layout_client = get_graph_layout_client()
        positions = await layout_client.compute_layout(
            edges=links,
            block_width=200.0,
            block_height=100.0,
            horizontal_gap=60.0,
            vertical_gap=50.0,
            reduce_crossings=True,
            convert_to_dag=True,
        )

        logger.info("Layout output: computed positions for %d nodes", len(positions))

        items = [
            {
                "uid": uid,
                "x": pos.x * X_SPACING_MULTIPLIER,
                "y": pos.y,
                "layer": pos.layer,
                "level": pos.level,
            }
            for uid, pos in positions.items()
        ]
        position_batch = 1000
        for i in range(0, len(items), position_batch):
            with self.driver.session() as session:
                session.run(
                    """
                    UNWIND $items AS it
                    MATCH (n:Document {uid: it.uid})
                    SET n.x = it.x, n.y = it.y, n.layer = it.layer,
                        n.level = it.level, n.layout_status = 'placed'
                    """,
                    items=items[i:i + position_batch],
                )

        updated = len(items)
        logger.info("Layout complete: updated %d nodes' coordinates", updated)
        return {
            "success": True,
            "updated": updated,
            "nodes": len(node_ids),
            "links": len(links),
            "layers": max((p.layer for p in positions.values()), default=0) + 1,
            "levels": max((p.level for p in positions.values()), default=0) + 1,
        }

    def _empty_layout_result(self) -> Dict[str, Any]:
        return {"success": True, "updated": 0, "nodes": 0, "links": 0, "layers": 0, "levels": 0}

    def _cleanup_placeholder_openalex_nodes(self) -> int:
        """Удаляет узлы-плейсхолдеры, созданные старым bulk-кодом OpenAlex.

        Раньше ссылки на работы без известного DOI записывались как узлы с
        doi вида "W123456789" (OpenAlex ID). Такие узлы не являются реальными
        публикациями и должны быть удалены, чтобы на графе не появлялись
        надписи "w[number]".
        """
        try:
            summary = self._run_query(
                "MATCH (n:Document) WHERE n.doi =~ '(?i)^w[0-9]+$' DETACH DELETE n"
            ).consume()
            removed = summary.counters.nodes_deleted
            if removed:
                logger.info("Removed %d placeholder OpenAlex nodes (doi like W[number])", removed)
            return removed
        except Exception as e:
            logger.warning("Placeholder OpenAlex cleanup failed: %s", e)
            return 0

    def _ensure_document_indexes(self) -> None:
        """Гарантирует наличие индексов, ускоряющих layout-запросы."""
        for cypher in (
            "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.uid)",
            "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.doi)",
        ):
            try:
                self._run_query(cypher)
            except Exception as e:
                logger.warning("Index creation failed (%s): %s", cypher, e)

    @staticmethod
    def _source_count(source_str: Optional[str]) -> int:
        """Число уникальных источников, поддержавших направленное ребро."""
        if not source_str:
            return 0
        return len({s for s in source_str.split("|") if s})

    def cleanup_antiparallel_edges(self) -> Dict[str, Any]:
        """Удаляет спуриозные антипараллельные рёбра BIBLIOGRAPHIC_LINK.

        Для каждой неупорядоченной пары {a, b}, у которой существуют ОБА
        направления (взаимная «цитата» из-за противоречивых записей источников),
        оставляем только направление с большей уверенностью (числом уникальных
        источников). Слабое направление удаляется. Это исключает неоднозначность
        укладки (произвольный разворот одного ребра в feedback arc set).
        Направления с равной уверенностью не трогаем.
        """
        removed: List[tuple] = []
        with self.driver.session() as session:
            result = session.run("""
                MATCH (a:Document)-[ra:BIBLIOGRAPHIC_LINK]->(b:Document),
                      (b:Document)-[rb:BIBLIOGRAPHIC_LINK]->(a:Document)
                RETURN a.uid AS a_uid, ra.source AS a_src,
                       b.uid AS b_uid, rb.source AS b_src
            """)
            # key: каноническая пара (lo_uid, hi_uid); value: {u: вес направления u->v}
            best: Dict[tuple, Dict[str, int]] = {}
            for rec in result:
                a = rec["a_uid"]
                b = rec["b_uid"]
                if a is None or b is None:
                    continue
                w_ab = self._source_count(rec["a_src"])  # a -> b
                w_ba = self._source_count(rec["b_src"])  # b -> a
                lo, hi = (a, b) if a < b else (b, a)
                d = best.setdefault((lo, hi), {})
                d[a] = max(d.get(a, 0), w_ab)
                d[b] = max(d.get(b, 0), w_ba)

            for (lo, hi), d in best.items():
                if len(d) < 2:
                    continue
                w_ab = d.get(lo, 0)  # lo -> hi
                w_ba = d.get(hi, 0)  # hi -> lo
                if w_ab == w_ba:
                    continue  # равная уверенность — оставляем как есть
                loser_src, loser_tgt = (lo, hi) if w_ab < w_ba else (hi, lo)
                session.run(
                    """
                    MATCH (x:Document {uid: $from_uid})-[r:BIBLIOGRAPHIC_LINK]->(y:Document {uid: $to_uid})
                    DETACH DELETE r
                    """,
                    {"from_uid": loser_src, "to_uid": loser_tgt},
                )
                removed.append((loser_src, loser_tgt))

        if removed:
            logger.info("Cleanup antiparallel edges: removed %d", len(removed))
            for src, tgt in removed[:20]:
                logger.info("  removed %s -> %s", src, tgt)
        return {"removed": len(removed), "pairs_checked": len(best)}

    # ── Statistics ─────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        with self.driver.session() as session:
            result = session.run("""
                MATCH (d:Document)
                WHERE d.doi IS NOT NULL
                WITH count(d) AS doc_count
                MATCH (d1:Document)-[r:BIBLIOGRAPHIC_LINK]->(d2:Document)
                WITH doc_count, count(r) AS edge_count
                MATCH (d1:Document)-[r:BIBLIOGRAPHIC_LINK]->(d2:Document)
                UNWIND split(r.source, '|') AS src
                WITH doc_count, edge_count, src, count(*) AS cnt
                RETURN doc_count, edge_count, src, cnt
                ORDER BY cnt DESC
            """)
            source_stats = {}
            doc_count = 0
            edge_count = 0
            for record in result:
                doc_count = record["doc_count"]
                edge_count = record["edge_count"]
                source_stats[record["src"]] = record["cnt"]
            return {
                "document_count": doc_count,
                "edge_count": edge_count,
                "source_breakdown": source_stats,
            }

    # ── Loading Orchestration ──────────────────────────────────────────────

    def _is_source_busy(self, key: str) -> bool:
        with self._lock:
            return self._active_loads.get(key, False)

    def _mark_source_active(self, key: str, active: bool) -> None:
        with self._lock:
            self._active_loads[key] = active

    def _get_pause_event(self, key: str) -> threading.Event:
        with self._lock:
            ev = self._pause_events.get(key)
            if ev is None:
                ev = threading.Event()
                ev.set()
                self._pause_events[key] = ev
            return ev

    def _get_cancel_event(self, key: str) -> threading.Event:
        with self._lock:
            ev = self._cancel_events.get(key)
            if ev is None:
                ev = threading.Event()
                self._cancel_events[key] = ev
            return ev

    async def pause_load(self, key: str) -> None:
        """Кооперативная пауза массовой загрузки источника."""
        self._get_pause_event(key).clear()
        self.set_status(key, "paused")
        logger.info("Pause requested for %s", key)

    async def resume_load(self, key: str) -> None:
        """Возобновление массовой загрузки источника."""
        self._get_pause_event(key).set()
        self.set_status(key, "downloading")
        logger.info("Resume requested for %s", key)

    async def reset_load(self, key: str) -> None:
        """Сбрасывает прогресс и останавливает активную загрузку источника."""
        self._get_cancel_event(key).set()
        self._get_pause_event(key).set()
        self.update_progress(key, 0, 0, "idle")
        logger.info("Reset requested for %s", key)

    async def load_source_bulk(
        self,
        key: str,
        options: Optional[BulkLoadOptions] = None,
        *,
        on_progress: Optional[Callable[[int, int, float, str], None]] = None,
        on_status: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        """Запускает массовую загрузку source key вне event loop (в worker-потоке).

        options: ограничения частичной загрузки (первые N файлов/записей).
        on_progress: синхронный обратный вызов (downloaded, total, percent, filename),
            вызывается из worker-потока (потокобезопасно).
        on_status: синхронный обратный вызов (status, message).
        """
        if key not in self._sources:
            raise ValueError(f"Unknown source: {key}")
        if self._is_source_busy(key):
            raise RuntimeError(f"Source {key} is already loading")

        self._mark_source_active(key, True)
        pause_event = self._get_pause_event(key)
        cancel_event = self._get_cancel_event(key)
        pause_event.set()
        cancel_event.clear()
        self.set_status(key, "downloading")
        if on_status:
            on_status("downloading", f"Starting bulk load for {key}")

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                self._load_executor,
                self._bulk_worker,
                key, options, pause_event, cancel_event, on_progress, on_status,
            )
        finally:
            self._mark_source_active(key, False)

    def _bulk_worker(
        self,
        key: str,
        options: Optional[BulkLoadOptions],
        pause_event: threading.Event,
        cancel_event: threading.Event,
        on_progress: Optional[Callable[[int, int, float, str], None]],
        on_status: Optional[Callable[[str, str], None]],
    ) -> None:
        """Выполняет массовую загрузку источника в отдельном потоке со своим event loop.

        Весь тяжёлый код (парсинг файлов, запись в Neo4j, layout) выполняется в этом
        потоке, не блокируя event loop API-сервера.
        """

        async def _pipeline() -> None:
            source = self._sources[key]
            edges_batch: List[CitationEdge] = []
            total_yielded = 0
            total_written = 0

            def _progress(downloaded: int, total: int, filename: str = "") -> None:
                self.update_progress(key, downloaded, total, "downloading")
                if on_progress:
                    percent = round((downloaded / total) * 100, 1) if total > 0 else 0.0
                    on_progress(downloaded, total, percent, filename)

            write_error: Optional[Exception] = None
            try:
                async for edge in source.get_all(
                    progress_callback=_progress,
                    options=options,
                    cancel_callback=lambda: cancel_event.is_set(),
                ):
                    while not pause_event.is_set():
                        if cancel_event.is_set():
                            break
                        await asyncio.sleep(0.5)
                    if cancel_event.is_set():
                        break
                    edges_batch.append(edge)
                    total_yielded += 1

                    if len(edges_batch) >= BATCH_SIZE:
                        merged = self._merge_service.merge_edges(edges_batch)
                        edges_list = list(merged.values())
                        written = await self.write_edges_async(edges_list)
                        total_written += written
                        edges_batch.clear()

                if edges_batch:
                    merged = self._merge_service.merge_edges(edges_batch)
                    edges_list = list(merged.values())
                    written = await self.write_edges_async(edges_list)
                    total_written += written

                if key == "openalex":
                    self._cleanup_placeholder_openalex_nodes()
            except Exception as e:
                write_error = e
                logger.error("Bulk processing failed for %s: %s", key, e)

            # Укладку считаем и для частично скачанных данных: прерванный прогон
            # (отмена/ошибка) всё равно кладёт накопленные рёбра на карту
            # science_articles. Логируется отдельно, чтобы не прятать ошибку записи.
            layout_result: Dict[str, Any] = {}
            try:
                self.set_status(key, "layouting")
                if on_status:
                    on_status("layouting", "Calculating graph layout")
                layout_result = await self.layout_citation_graph()
                logger.info("Layout after bulk load for %s: %s", key, layout_result)
            except Exception as e:
                logger.error("Layout failed for %s: %s", key, e)

            self.update_progress(key, total_yielded, total_yielded, "completed")
            logger.info(
                "Bulk load for %s complete: %d edges, %d written",
                key, total_yielded, total_written,
            )
            if on_status:
                on_status("completed", f"Bulk load for {key} complete")

            if write_error is not None:
                self.set_status(key, "error", str(write_error))
                if on_status:
                    on_status("error", str(write_error))

        try:
            asyncio.run(_pipeline())
        except Exception as e:
            logger.error("Bulk load failed for %s: %s", key, e)
            self.set_status(key, "error", str(e))
            if on_status:
                on_status("error", str(e))

    async def load_single_doi(self, doi: str) -> Dict[str, Any]:
        """Загружает цитаты для одного DOI через все источники."""
        logger.info("load_single_doi: fetching citations for DOI %s", doi)
        all_edges: List[CitationEdge] = []
        source_results: Dict[str, Any] = {}

        for key, source in self._sources.items():
            try:
                edges = await source.get_one(doi)
                all_edges.extend(edges)
                source_results[key] = {"edges": len(edges), "status": "ok"}
                logger.info("load_single_doi: %s returned %d edges", key, len(edges))
            except Exception as e:
                source_results[key] = {"edges": 0, "status": "error", "error": str(e)}
                logger.warning("load_single_doi: %s failed: %s", key, e)

        merged = self._merge_service.merge_edges(all_edges)
        edges_list = list(merged.values())
        written = await self.write_edges_async(edges_list)
        logger.info("load_single_doi: wrote %d merged edges", len(edges_list))

        layout_result = await self.layout_citation_graph()

        return {
            "doi": doi,
            "total_edges_raw": len(all_edges),
            "unique_edges": len(edges_list),
            "written_ops": written,
            "sources": source_results,
            "layout": layout_result,
        }

    async def enrich_document_fields_status(self) -> Dict[str, Any]:
        """Прогресс фонового обогащения Document-узлов тематикой."""
        return dict(self._enrich_state)

    async def start_enrich_document_fields(self) -> Dict[str, Any]:
        """Запускает одноразовое обогащение Document-узлов тематикой в фоне.

        Проставляет на узлы (по DOI) свойства primary_field и fields
        (список field.display_name из primary_topic/topics) для данных, уже
        загруженных в БД до внедрения тематики. Идемпотентно. Работает в
        потоке исполнителя (блокирующий neo4j driver), HTTP-ответ возвращается
        сразу, прогресс доступен через enrich_document_fields_status().
        """
        if self._enrich_state.get("running"):
            return {"success": False, "error": "enrichment already running"}
        self._enrich_state.update({
            "running": True,
            "total_files": 0,
            "processed_files": 0,
            "processed_dois": 0,
            "matched_documents": 0,
            "last_file": None,
            "error": None,
        })
        try:
            self._enrich_task = asyncio.get_running_loop().run_in_executor(
                self._load_executor, self._enrich_blocking
            )
        except Exception as e:
            logger.error("Failed to start enrichment: %s", e)
            self._enrich_state.update({"running": False, "error": str(e)})
            return {"success": False, "error": str(e)}
        return {"success": True}

    def _enrich_blocking(self) -> None:
        """Блокирующая часть обогащения: читает локальный дамп и пишет в Neo4j."""
        state = self._enrich_state
        openalex = self._sources.get("openalex")
        total_dois = 0
        matched = 0
        if openalex is None:
            state.update({"running": False, "error": "openalex source unavailable"})
            return
        try:
            files = openalex.list_local_dump_files()
            state["total_files"] = len(files)
            batch: list[dict] = []

            def flush() -> int:
                nonlocal batch
                if not batch:
                    return 0
                query = """
                UNWIND $batch AS item
                MATCH (n:Document {doi: item.doi})
                SET n.primary_field = item.primary_field,
                    n.fields = item.fields
                RETURN count(n) AS matched
                """
                with self.driver.session() as session:
                    values = session.run(query, batch=batch, timeout=120).values()
                batch = []
                return int(values[0][0]) if values else 0

            for path in files:
                for doi, primary_field, fields in openalex.iter_file_topics(path):
                    total_dois += 1
                    batch.append({
                        "doi": doi,
                        "primary_field": primary_field,
                        "fields": list(fields) if fields else None,
                    })
                    if len(batch) >= 5000:
                        matched += flush()
                state.update({
                    "processed_files": state.get("processed_files", 0) + 1,
                    "last_file": str(path),
                    "processed_dois": total_dois,
                    "matched_documents": matched,
                })
                logger.info(
                    "Enrich progress: %d/%d files, %d DOIs, %d matched",
                    state["processed_files"], state["total_files"],
                    total_dois, matched,
                )
            matched += flush()
        except Exception as e:
            logger.error("Enrich failed: %s", e)
            state["error"] = str(e)
        finally:
            state.update({
                "running": False,
                "processed_dois": total_dois,
                "matched_documents": matched,
            })
            logger.info("Enriched %d/%d DOIs with topics", matched, total_dois)

    async def test_source(self, key: str, sample_size: int = 10) -> TestEstimate:
        """Тестовый прогон source через API для оценки времени."""
        if key not in self._sources:
            raise ValueError(f"Unknown source: {key}")
        return await self._sources[key].test_estimate(sample_size)


_service_instance: Optional[CitationGraphService] = None


def get_citation_graph_service() -> CitationGraphService:
    global _service_instance
    if _service_instance is None:
        _service_instance = CitationGraphService()
    return _service_instance
