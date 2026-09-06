"""
Layer: Infrastructure — External API / Bulk Data
Package: services.citation_sources.datacite_source
Responsibility: Сбор данных о цитированиях из DataCite.

Bulk: Public data file (~33 GB tar.gz/jsonl) с https://datafiles.datacite.org.
API: REST API (https://api.datacite.org).

Rate limit: 1000 req/5min (identified), 500 req/5min (unidentified).
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

API_BASE = "https://api.datacite.org"
DUMP_URL = "https://datafiles.datacite.org/datafiles/public-2025"

_TEST_DOIS = [
    "10.14454/qdd3-ps68",
    "10.5061/dryad.qjq2bvqhq",
    "10.5281/zenodo.3235814",
    "10.5281/zenodo.2656253",
    "10.14454/t5qb-d995",
    "10.5281/zenodo.4903623",
    "10.5281/zenodo.5763970",
    "10.5281/zenodo.6346548",
    "10.5281/zenodo.7058132",
    "10.5281/zenodo.8244657",
]


class DataCiteSource(CitationSource):

    def __init__(self) -> None:
        self._email = os.getenv("DATACITE_EMAIL", "")

    @property
    def name(self) -> str:
        return "datacite"

    @property
    def display_name(self) -> str:
        return "DataCite"

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Accept": "application/json"}
        if self._email:
            h["User-Agent"] = f"KnowledgeMap/1.0 ({self._email})"
        return h

    async def _api_get(self, url: str, timeout: float = 30.0, **extra_params: str) -> httpx.Response:
        params: dict[str, str] = {}
        if self._email:
            params["mailto"] = self._email
        params.update(extra_params)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            return await client.get(url, params=params, headers=self._headers())

    # ── API ────────────────────────────────────────────────────────────────

    async def _fetch_doi_data(self, doi: str) -> Optional[dict]:
        url = f"{API_BASE}/dois/{doi}"
        try:
            resp = await self._api_get(url, detail="true")
            resp.raise_for_status()
            return resp.json().get("data", {})
        except Exception as e:
            logger.warning("DataCite fetch DOI failed for %s: %s", doi, e)
            return None

    def _extract_edges_from_data(self, doi: str, data: dict) -> list[CitationEdge]:
        attrs = data.get("attributes", {})
        title = ""
        titles = attrs.get("titles", [])
        if titles:
            title = titles[0].get("title", "")

        edges: list[CitationEdge] = []

        for rel in attrs.get("relatedIdentifiers", []):
            rel_type = (rel.get("relationType") or "").lower()
            rel_doi = (rel.get("relatedIdentifier") or "").lower()
            rel_type_id = (rel.get("relatedIdentifierType") or "").upper()

            if not rel_doi or rel_type_id != "DOI":
                continue

            if rel_type in ("iscitedby", "isreferencedby", "issupplementto"):
                edges.append(CitationEdge(
                    citing_doi=rel_doi,
                    cited_doi=doi.lower(),
                    source=self.name,
                    title_cited=title,
                ))
            elif rel_type in ("cites", "references", "issupplementedby"):
                edges.append(CitationEdge(
                    citing_doi=doi.lower(),
                    cited_doi=rel_doi,
                    source=self.name,
                    title_citing=title,
                ))

        relationships = data.get("relationships", {})
        for rel_key in ("citations", "references"):
            rel_data = relationships.get(rel_key, {}).get("data", [])
            for rel_item in rel_data:
                rel_doi = (rel_item.get("id") or "").lower()
                if not rel_doi:
                    continue
                if rel_key == "citations":
                    edges.append(CitationEdge(
                        citing_doi=rel_doi,
                        cited_doi=doi.lower(),
                        source=self.name,
                    ))
                else:
                    edges.append(CitationEdge(
                        citing_doi=doi.lower(),
                        cited_doi=rel_doi,
                        source=self.name,
                    ))

        return edges

    async def get_one(self, doi: str) -> list[CitationEdge]:
        data = await self._fetch_doi_data(doi)
        if not data:
            return []
        return self._extract_edges_from_data(doi, data)

    # ── Bulk ───────────────────────────────────────────────────────────────

    async def get_all(
        self,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        options: Optional[BulkLoadOptions] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[CitationEdge]:
        """Парсит DataCite public dump (tar.gz + jsonl) для relatedIdentifiers.

        Требует локально скачанный дамп в data/datacite-dump/

        При заданных options (max_files/max_records) загружается только часть
        дампа, а постоянный чекпоинт не перезаписывается.
        """
        dump_dir = Path("data/datacite-dump")
        if not dump_dir.exists():
            logger.error(
                "DataCite dump not found at %s. "
                "Download from: %s (enter email to get link)",
                dump_dir,
                DUMP_URL,
            )
            return

        checkpoint_file = Path("data/citation_datacite_checkpoint.txt")
        checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        processed_files_count = 0
        if checkpoint_file.exists():
            processed_files_count = int(checkpoint_file.read_text().strip() or "0")

        jsonl_files = sorted(dump_dir.rglob("*.jsonl.gz"))

        selected_files: list[Path] = []
        for idx, gz_path in enumerate(jsonl_files):
            if idx < processed_files_count:
                continue
            selected_files.append(gz_path)
            if options is not None and options.max_files is not None and len(selected_files) >= options.max_files:
                break

        total_files = len(selected_files)
        total_bytes = sum(f.stat().st_size for f in selected_files)
        bytes_read = 0
        limited = options is not None and options.is_limited()
        records_read = 0

        for idx, gz_path in enumerate(selected_files):
            if cancel_callback is not None and cancel_callback():
                logger.info("DataCite bulk canceled")
                return
            logger.info("Processing DataCite file %d/%d: %s", idx + 1, total_files, gz_path.name)
            try:
                with gzip.open(gz_path, "rt", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        records_read += 1
                        if options is not None and options.max_records is not None and records_read > options.max_records:
                            return
                        doi = (record.get("doi") or "").lower()
                        if not doi:
                            continue
                        edges = self._extract_edges_from_data(doi, record)
                        for edge in edges:
                            yield edge
            except Exception as e:
                logger.warning("Error processing %s: %s", gz_path, e)

            bytes_read += gz_path.stat().st_size
            if not limited:
                checkpoint_file.write_text(str(processed_files_count + idx + 1))
            if progress_callback:
                progress_callback(bytes_read, total_bytes, gz_path.name)

        logger.info("DataCite bulk: processed %d files", processed_files_count + len(selected_files))

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
                await _asyncio_sleep(0.5)
            except Exception as e:
                errors.append(f"{doi}: {e}")

        avg_time = total_elapsed / max(len(test_dois) - len(errors), 1)
        return TestEstimate(
            source_name=self.name,
            sample_size=sample_size,
            elapsed_seconds=round(total_elapsed, 2),
            edges_found=total_edges,
            estimated_total_edges=108_000_000,
            estimated_time_seconds=round(avg_time * 108_000_000 / max(total_edges, 1), 0) if total_edges else None,
            errors=errors,
            success=len(errors) < sample_size,
        )


async def _asyncio_sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)
