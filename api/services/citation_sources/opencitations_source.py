"""
Layer: Infrastructure — External API / Bulk Data
Package: services.citation_sources.opencitations_source
Responsibility: Сбор данных о цитированиях из OpenCitations COCI.

Bulk: CSV-дамп цитирований (~40 GB zip) с Figshare/Zenodo + Meta CSV для title.
API: REST API v2 Index + Meta v1 (https://api.opencitations.net).

Rate limit: 180 req/min (с токеном).
"""
from __future__ import annotations

import csv
import gzip
import io
import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional

import httpx

from .base import BulkLoadOptions, CitationEdge, CitationSource, TestEstimate

logger = logging.getLogger(__name__)

# Дампы OpenCitations (актуальные на 2026-07)
CITATION_DUMP_URL = "https://download.figshare.com/files/31353691"
META_DUMP_URL = "https://download.figshare.com/files/20965426"

# REST API v2
INDEX_API_BASE = "https://api.opencitations.net/index/v2"
META_API_BASE = "https://api.opencitations.net/meta/v1"

# Тест DOI для estimates
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


class OpenCitationsSource(CitationSource):

    def __init__(self) -> None:
        self._access_token = os.getenv("OPENCITATIONS_ACCESS_TOKEN", "")
        self._email = os.getenv("OPENCITATIONS_EMAIL", "")

    @property
    def name(self) -> str:
        return "opencitations"

    @property
    def display_name(self) -> str:
        return "OpenCitations COCI"

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Accept": "application/json"}
        if self._access_token:
            h["authorization"] = self._access_token
        return h

    # ── API ────────────────────────────────────────────────────────────────

    async def _api_get(self, url: str, timeout: float = 30.0) -> httpx.Response:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            return await client.get(url, headers=self._headers())

    async def _fetch_incoming(self, doi: str) -> list[CitationEdge]:
        url = f"{INDEX_API_BASE}/citations/doi:{doi}"
        try:
            resp = await self._api_get(url)
            resp.raise_for_status()
            items = resp.json()
        except Exception as e:
            logger.warning("OpenCitations incoming fetch failed for %s: %s", doi, e)
            return []
        edges: list[CitationEdge] = []
        for item in items:
            citing_raw = item.get("citing", "")
            cited_raw = item.get("cited", "")
            citing = self._extract_doi(citing_raw)
            cited = self._extract_doi(cited_raw)
            if citing and cited:
                edges.append(CitationEdge(citing_doi=citing, cited_doi=cited, source=self.name))
        return edges

    async def _fetch_outgoing(self, doi: str) -> list[CitationEdge]:
        url = f"{INDEX_API_BASE}/references/doi:{doi}"
        try:
            resp = await self._api_get(url)
            resp.raise_for_status()
            items = resp.json()
        except Exception as e:
            logger.warning("OpenCitations outgoing fetch failed for %s: %s", doi, e)
            return []
        edges: list[CitationEdge] = []
        for item in items:
            citing_raw = item.get("citing", "")
            cited_raw = item.get("cited", "")
            citing = self._extract_doi(citing_raw)
            cited = self._extract_doi(cited_raw)
            if citing and cited:
                edges.append(CitationEdge(citing_doi=citing, cited_doi=cited, source=self.name))
        return edges

    async def _fetch_title(self, doi: str) -> Optional[str]:
        url = f"{META_API_BASE}/metadata/doi:{doi}"
        try:
            resp = await self._api_get(url)
            resp.raise_for_status()
            items = resp.json()
            if items and isinstance(items, list):
                return items[0].get("title") or None
        except Exception:
            pass
        return None

    async def get_one(self, doi: str) -> list[CitationEdge]:
        """Получить все цитаты для DOI через API (citing + cited)."""
        incoming = await self._fetch_incoming(doi)
        outgoing = await self._fetch_outgoing(doi)
        return incoming + outgoing

    # ── Bulk ───────────────────────────────────────────────────────────────

    async def get_all(
        self,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        options: Optional[BulkLoadOptions] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[CitationEdge]:
        """Скачивает CSV-дамп цитирований и yield'ит CitationEdge.

        Формат CSV: oci,citing,cited,creation,timespan,journal_sc,author_sc
        Файлы gzip-архивы внутри zip.

        При options.max_records обрабатываются только первые N строк дампа
        (один файл — max_files неприменим). Чекпоинт при лимите не перезаписывается.
        """
        checkpoint_file = Path("data/citation_opencitations_checkpoint.txt")
        checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        processed_bytes = 0
        if checkpoint_file.exists():
            processed_bytes = int(checkpoint_file.read_text().strip() or "0")

        local_path = Path("data/opencitations_citations.csv.gz")
        local_path.parent.mkdir(parents=True, exist_ok=True)

        total_size = await self._get_dump_size(CITATION_DUMP_URL)

        if not local_path.exists() or local_path.stat().st_size < total_size * 0.99:
            logger.info("Downloading OpenCitations citation dump (~%d bytes)...", total_size)
            await self._download_file(CITATION_DUMP_URL, local_path, progress_callback, total_size)

        logger.info("Processing OpenCitations dump from byte %d...", processed_bytes)
        bytes_read = 0
        limited = options is not None and options.is_limited()
        records_read = 0
        with open(local_path, "rb") as f_raw:
            if local_path.suffix == ".gz":
                import gzip as gzip_mod
                f_text = io.TextIOWrapper(
                    gzip_mod.GzipFile(fileobj=f_raw), encoding="utf-8", errors="replace"
                )
            else:
                f_text = io.TextIOWrapper(f_raw, encoding="utf-8", errors="replace")

            reader = csv.DictReader(f_text)
            for row in reader:
                if cancel_callback is not None and cancel_callback():
                    logger.info("OpenCitations bulk canceled")
                    return
                bytes_read += 1
                if bytes_read <= processed_bytes:
                    continue
                records_read += 1
                if options is not None and options.max_records is not None and records_read > options.max_records:
                    return
                citing = (row.get("citing") or "").strip()
                cited = (row.get("cited") or "").strip()
                if citing and cited:
                    yield CitationEdge(
                        citing_doi=citing.lower(),
                        cited_doi=cited.lower(),
                        source=self.name,
                    )
                if bytes_read % 500_000 == 0:
                    if not limited:
                        checkpoint_file.write_text(str(bytes_read))
                    if progress_callback:
                        progress_callback(bytes_read, total_size, "opencitations_citations.csv.gz")

        if not limited:
            checkpoint_file.write_text(str(bytes_read))
        logger.info("OpenCitations bulk: processed %d rows", bytes_read)

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
                await asyncio_sleep(0.35)
            except Exception as e:
                errors.append(f"{doi}: {e}")

        avg_time = total_elapsed / max(len(test_dois) - len(errors), 1)
        estimated_api_edges = int(total_edges / max(len(test_dois) - len(errors), 1) * 2_500_000_000)

        return TestEstimate(
            source_name=self.name,
            sample_size=sample_size,
            elapsed_seconds=round(total_elapsed, 2),
            edges_found=total_edges,
            estimated_total_edges=estimated_api_edges,
            estimated_time_seconds=None,
            errors=errors,
            success=len(errors) < sample_size,
        )

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_doi(raw: str) -> Optional[str]:
        """Извлекает DOI из строки вида 'doi:10.1234/xxx omid:br/...'."""
        for part in raw.split():
            if part.startswith("doi:"):
                return part[4:].lower()
        return None

    async def _get_dump_size(self, url: str) -> int:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.head(url, headers=self._headers())
                cl = resp.headers.get("content-length")
                return int(cl) if cl else 0
        except Exception:
            return 0

    async def _download_file(
        self,
        url: str,
        dest: Path,
        progress_callback: Optional[Callable[[int, int, str], None]],
        total_size: int,
    ) -> None:
        downloaded = 0
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
            async with client.stream("GET", url, headers=self._headers()) as resp:
                resp.raise_for_status()
                with open(dest, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total_size, dest.name)


async def asyncio_sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)
