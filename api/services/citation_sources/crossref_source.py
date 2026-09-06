"""
Layer: Infrastructure — External API / Bulk Data
Package: services.citation_sources.crossref_source
Responsibility: Сбор данных о цитированиях из Crossref.

Bulk: Annual public data file (~208 GB tar/jsonl) через S3 Requester Pays.
API: REST API (https://api.crossref.org) с Polite pool.

Rate limit: Polite pool 10 req/s single, 3 req/s lists.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import tarfile
import time
from pathlib import Path
from typing import Callable, Optional

import httpx

from .base import BulkLoadOptions, CitationEdge, CitationSource, TestEstimate

logger = logging.getLogger(__name__)

API_BASE = "https://api.crossref.org"
S3_BUCKET = "api-snapshots-reqpays-crossref"

_TEST_DOIS = [
    "10.1038/s41586-020-2649-2",
    "10.1126/science.169.3946.635",
    "10.1038/nature12373",
    "10.1016/j.cell.2018.01.029",
    "10.1146/annurev-neuro-070918-020431",
    "10.1038/s41588-020-0277-y",
    "10.1038/s41591-020-1142-7",
    "10.1016/j.cell.2019.11.015",
    "10.1126/science.aau9490",
    "10.1038/s41587-020-0441-2",
]


class CrossrefSource(CitationSource):

    def __init__(self) -> None:
        self._mailto = os.getenv("CROSSREF_MAILTO", "")

    @property
    def name(self) -> str:
        return "crossref"

    @property
    def display_name(self) -> str:
        return "Crossref"

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self._mailto:
            h["User-Agent"] = f"KnowledgeMap/1.0 (mailto:{self._mailto})"
        return h

    def _params(self) -> dict[str, str]:
        if self._mailto:
            return {"mailto": self._mailto}
        return {}

    async def _api_get(self, url: str, timeout: float = 30.0) -> httpx.Response:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            return await client.get(url, params=self._params(), headers=self._headers())

    # ── API ────────────────────────────────────────────────────────────────

    async def _fetch_references(self, doi: str) -> list[CitationEdge]:
        url = f"{API_BASE}/works/{doi}"
        try:
            resp = await self._api_get(url)
            resp.raise_for_status()
            message = resp.json().get("message", {})
        except Exception as e:
            logger.warning("Crossref fetch references failed for %s: %s", doi, e)
            return []

        title = ""
        titles = message.get("title", [])
        if titles:
            title = titles[0]

        edges: list[CitationEdge] = []
        for ref in message.get("reference", []):
            ref_doi = (ref.get("DOI") or "").lower()
            if ref_doi:
                edges.append(CitationEdge(
                    citing_doi=doi.lower(),
                    cited_doi=ref_doi,
                    source=self.name,
                    title_citing=title,
                ))
        return edges

    async def get_one(self, doi: str) -> list[CitationEdge]:
        """Crossref API даёт references (cited), но NE даёт список citing напрямую.

        Для incoming citations используем Crossref как补充 к OpenCitations.
        """
        return await self._fetch_references(doi)

    # ── Bulk ───────────────────────────────────────────────────────────────

    async def get_all(
        self,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        options: Optional[BulkLoadOptions] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[CitationEdge]:
        """Парсит Crossref annual dump (tar+jsonl) для извлечения reference edges.

        Требует локально скачанный дамп в data/crossref-dump.tar

        При options.max_files ограничивается число обработанных tar-members,
        при options.max_records — число записей (works). Чекпоинт при лимите
        не перезаписывается.
        """
        dump_path = Path("data/crossref-dump.tar")
        if not dump_path.exists():
            logger.error(
                "Crossref dump not found at %s. "
                "Download from: s3://api-snapshots-reqpays-crossref (Requester Pays) "
                "or: https://doi.org/10.13003/nggf-vt1j (torrent)",
                dump_path,
            )
            return

        checkpoint_file = Path("data/citation_crossref_checkpoint.txt")
        checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        processed_bytes = 0
        if checkpoint_file.exists():
            processed_bytes = int(checkpoint_file.read_text().strip() or "0")

        total_size = dump_path.stat().st_size
        bytes_read = 0
        limited = options is not None and options.is_limited()
        records_read = 0
        members_processed = 0

        try:
            with tarfile.open(dump_path, "r:") as tar:
                for member in tar.getmembers():
                    if cancel_callback is not None and cancel_callback():
                        logger.info("Crossref bulk canceled")
                        return
                    if not member.isfile():
                        continue
                    if member.size == 0:
                        continue
                    if bytes_read + member.size < processed_bytes:
                        bytes_read += member.size
                        continue

                    if options is not None and options.max_files is not None and members_processed >= options.max_files:
                        break
                    members_processed += 1

                    logger.info("Processing Crossref member: %s (%d bytes)", member.name, member.size)
                    f = tar.extractfile(member)
                    if f is None:
                        continue

                    for line_bytes in f:
                        try:
                            line = line_bytes.decode("utf-8", errors="replace").strip()
                            if not line:
                                continue
                            work = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        citing_doi = (work.get("DOI") or "").lower()
                        if not citing_doi:
                            continue
                        records_read += 1
                        if options is not None and options.max_records is not None and records_read > options.max_records:
                            return

                        for ref in work.get("reference", []):
                            ref_doi = (ref.get("DOI") or "").lower()
                            if ref_doi:
                                yield CitationEdge(
                                    citing_doi=citing_doi,
                                    cited_doi=ref_doi,
                                    source=self.name,
                                )

                    bytes_read += member.size
                    if not limited:
                        checkpoint_file.write_text(str(bytes_read))
                    if progress_callback:
                        progress_callback(bytes_read, total_size, member.name)

        except Exception as e:
            logger.error("Crossref bulk processing error: %s", e)

        logger.info("Crossref bulk: processed %d bytes", bytes_read)

    # ── Test ───────────────────────────────────────────────────────────────

    async def test_estimate(self, sample_size: int = 10) -> TestEstimate:
        test_dois = _TEST_DOIS[:sample_size]
        total_elapsed = 0.0
        total_edges = 0
        errors: list[str] = []

        for doi in test_dois:
            try:
                elapsed, edges = await self._test_get_one_timing(doi)
                total_elapsed += elapsed
                total_edges += len(edges)
                await _asyncio_sleep(0.3)
            except Exception as e:
                errors.append(f"{doi}: {e}")

        avg_time = total_elapsed / max(len(test_dois) - len(errors), 1)
        return TestEstimate(
            source_name=self.name,
            sample_size=sample_size,
            elapsed_seconds=round(total_elapsed, 2),
            edges_found=total_edges,
            estimated_total_edges=180_000_000,
            estimated_time_seconds=round(avg_time * 180_000_000 / max(total_edges, 1), 0) if total_edges else None,
            errors=errors,
            success=len(errors) < sample_size,
        )


async def _asyncio_sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)
