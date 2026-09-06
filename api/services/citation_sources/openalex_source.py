"""
Layer: Infrastructure — External API / Bulk Data
Package: services.citation_sources.openalex_source
Responsibility: Сбор данных о цитированиях из OpenAlex.

Bulk: S3 JSONL dump (s3://openalex/data/jsonl/works/) — сотни ГБ gzip
(полный дамп на момент проверки: 2 446 файлов, ~666 GB).
API: REST API (https://api.openalex.org).

Rate limit: $1/день с бесплатным ключом, 100 req/s.
"""
from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
import time
from pathlib import Path
from typing import Callable, Iterator, Optional

import boto3
import httpx
from botocore import UNSIGNED
from botocore.config import Config

from .base import BulkLoadOptions, CitationEdge, CitationSource, TestEstimate
from infrastructure.config import settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.openalex.org"

S3_BUCKET = "openalex"
S3_PREFIX = "data/jsonl/works"
# Пути отсчитываются от корня репозитория (см. infrastructure.config): данные
# bulk-дампа живут в корневом data/ независимо от рабочей директории API.
LOCAL_WORKS_DIR = settings.openalex_works_dir
CHECKPOINT_FILE = settings.openalex_checkpoint_file

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

# Файлы больше не считаем малыми: индексируем их одним проходом,
# не держа весь файл в памяти.
_SMALL_FILE_INDEX_THRESHOLD = 64 * 1024 * 1024


class _RecordsLimitReached(Exception):
    """Сигнал о достижении BulkLoadOptions.max_records внутри генератора."""


class OpenAlexSource(CitationSource):

    def __init__(self) -> None:
        self._api_key = os.getenv("OPENALEX_API_KEY", "")

    @property
    def name(self) -> str:
        return "openalex"

    @property
    def display_name(self) -> str:
        return "OpenAlex"

    def _params(self) -> dict[str, str]:
        if self._api_key:
            return {"api_key": self._api_key}
        return {}

    async def _api_get(self, url: str, timeout: float = 30.0, **extra_params: str) -> httpx.Response:
        params = {**self._params(), **extra_params}
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            return await client.get(url, params=params)

    async def _fetch_work_by_doi(self, doi: str) -> Optional[dict]:
        url = f"{API_BASE}/works/https://doi.org/{doi}"
        try:
            resp = await self._api_get(url, select="id,display_name,doi,referenced_works")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("OpenAlex fetch work failed for %s: %s", doi, e)
            return None

    async def _fetch_citing_works(self, openalex_id: str) -> list[CitationEdge]:
        url = f"{API_BASE}/works"
        edges: list[CitationEdge] = []
        cursor = "*"
        params: dict[str, str] = {"filter": f"cites:{openalex_id}", "per_page": "100", "select": "doi,display_name"}
        while cursor:
            try:
                params["cursor"] = cursor
                resp = await self._api_get(url, **params)
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])
                for w in results:
                    citing_doi = (w.get("doi") or "").replace("https://doi.org/", "").lower()
                    if citing_doi:
                        edges.append(CitationEdge(
                            citing_doi=citing_doi,
                            cited_doi=doi.lower(),
                            source=self.name,
                            title_citing=w.get("display_name") or None,
                        ))
                cursor = data.get("meta", {}).get("next_cursor")
                if not results:
                    break
            except Exception as e:
                logger.warning("OpenAlex citing fetch error: %s", e)
                break
        return edges

    async def get_one(self, doi: str) -> list[CitationEdge]:
        work = await self._fetch_work_by_doi(doi)
        if not work:
            return []
        oa_id = (work.get("id") or "").split("/")[-1]
        title = work.get("display_name")
        edges: list[CitationEdge] = []

        for ref_url in work.get("referenced_works", []):
            ref_id = ref_url.split("/")[-1] if ref_url else ""
            if ref_id:
                ref_work = None
                try:
                    resp = await self._api_get(
                        f"{API_BASE}/works/{ref_id}", select="doi,display_name"
                    )
                    if resp.status_code == 200:
                        ref_work = resp.json()
                except Exception:
                    pass
                ref_doi = ""
                if ref_work:
                    ref_doi = (ref_work.get("doi") or "").replace("https://doi.org/", "").lower()
                if ref_doi:
                    edges.append(CitationEdge(
                        citing_doi=doi.lower(),
                        cited_doi=ref_doi,
                        source=self.name,
                        title_citing=title,
                        title_cited=ref_work.get("display_name"),
                    ))

        if oa_id:
            incoming = await self._fetch_citing_works(oa_id)
            edges.extend(incoming)

        return edges

    # ── Bulk ───────────────────────────────────────────────────────────────

    @staticmethod
    def _new_s3_client():
        """Анонимный клиент S3 (дамп OpenAlex — публичные open data)."""
        return boto3.client("s3", config=Config(signature_version=UNSIGNED))

    @classmethod
    async def _list_remote_works(cls, need: int) -> tuple[list[str], list[int]]:
        """Возвращает первые `need` .gz-ключей дампа works и их размеры.

        Pagination останавливается, как только собрано достаточно ключей.
        """
        keys: list[str] = []
        sizes: list[int] = []
        token = None
        while len(keys) < need:
            page_token = token

            def _list_page(_token: Optional[str] = page_token):
                client = cls._new_s3_client()
                kwargs: dict = {"Bucket": S3_BUCKET, "Prefix": f"{S3_PREFIX}/"}
                if _token:
                    kwargs["ContinuationToken"] = _token
                return client.list_objects_v2(**kwargs)

            try:
                page = await asyncio.to_thread(_list_page)
            except Exception as e:
                logger.error("OpenAlex S3 list failed: %s", e)
                raise
            contents = page.get("Contents", [])
            for obj in contents:
                key = obj.get("Key", "")
                if key.endswith(".gz"):
                    keys.append(key)
                    sizes.append(int(obj.get("Size", 0)))
            if page.get("IsTruncated"):
                token = page.get("NextContinuationToken")
            else:
                break
        return keys[:need], sizes[:need]

    @classmethod
    async def _list_all_remote_works(cls) -> tuple[list[str], list[int]]:
        """Возвращает ВСЕ .gz-ключи дампа works и их размеры (полная пролистовка)."""
        keys: list[str] = []
        sizes: list[int] = []
        token = None
        while True:
            page_token = token

            def _list_page(_token: Optional[str] = page_token):
                client = cls._new_s3_client()
                kwargs: dict = {"Bucket": S3_BUCKET, "Prefix": f"{S3_PREFIX}/"}
                if _token:
                    kwargs["ContinuationToken"] = _token
                return client.list_objects_v2(**kwargs)

            try:
                page = await asyncio.to_thread(_list_page)
            except Exception as e:
                logger.error("OpenAlex S3 full list failed: %s", e)
                raise
            contents = page.get("Contents", [])
            if not contents:
                break
            for obj in contents:
                key = obj.get("Key", "")
                if key.endswith(".gz"):
                    keys.append(key)
                    sizes.append(int(obj.get("Size", 0)))
            if page.get("IsTruncated"):
                token = page.get("NextContinuationToken")
            else:
                break
        return keys, sizes

    @classmethod
    def _download_key(
        cls,
        key: str,
        local_path: Path,
        offset: int = 0,
        total: int = 0,
        callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> None:
        """Синхронное скачивание одного объекта S3 в локальный файл."""
        local_path.parent.mkdir(parents=True, exist_ok=True)
        client = cls._new_s3_client()
        with open(local_path, "wb") as f:
            cb = None
            if callback is not None:
                name = key.rsplit("/", 1)[-1]
                cb = lambda i: callback(offset + i, total, name)
            client.download_fileobj(S3_BUCKET, key, f, Callback=cb)

    def _checkpoint_processed_count(self) -> int:
        CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
        if CHECKPOINT_FILE.exists():
            return int(CHECKPOINT_FILE.read_text().strip() or "0")
        return 0

    async def get_all(
        self,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        options: Optional[BulkLoadOptions] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[CitationEdge]:
        """Парсит OpenAlex S3 JSONL dump для извлечения citation edges.

        Источник данных и загрузка выбираются автоматически:
        - options.max_files задан: скачиваются (при отсутствии) и обрабатываются
          первые N файлов после чекпоинта из публичного S3;
        - max_files не задан (ПОЛНАЯ загрузка): все файлы дампа после чекпоинта,
          недостающие локально .gz докачиваются из S3 и каждый файл сразу
          обрабатывается. Чекпоинт пишется после каждого файла, поэтому загрузку
          можно вести частями: прерванный/неполный прогон резюмируется.

        При любом ограничении (options) постоянный чекпоинт не перезаписывается.
        """
        processed_files_count = self._checkpoint_processed_count()
        limited = options is not None and options.is_limited()
        auto_download = options is not None and options.max_files is not None

        # План обработки: [(remote_key, local_path, expected_size)] в порядке дампа.
        if auto_download:
            need = processed_files_count + options.max_files
            remote_keys, remote_sizes = await self._list_remote_works(need)
            selected_keys = remote_keys[processed_files_count:need]
            selected_sizes = remote_sizes[processed_files_count:need]
            if not selected_keys:
                logger.info("OpenAlex: no new remote files to process (checkpoint %d)", processed_files_count)
                return
            plan = [
                (key, LOCAL_WORKS_DIR / key[len(S3_PREFIX) + 1:], int(size))
                for key, size in zip(selected_keys, selected_sizes)
            ]
            total_bytes = sum(selected_sizes)
        else:
            logger.info("OpenAlex: full dump load — listing all S3 works files")
            all_keys, all_sizes = await self._list_all_remote_works()
            by_rel = {
                key[len(S3_PREFIX) + 1:]: size for key, size in zip(all_keys, all_sizes)
            }
            if not by_rel:
                logger.info("OpenAlex: no remote works files found")
                return
            remaining_rel = list(by_rel)[processed_files_count:]
            if not remaining_rel:
                logger.info("OpenAlex: all %d dump files are already processed", processed_files_count)
                return
            local_files = sorted(LOCAL_WORKS_DIR.rglob("*.gz")) if LOCAL_WORKS_DIR.exists() else []
            local_present: set[str] = set()
            for p in local_files:
                rel = str(p.relative_to(LOCAL_WORKS_DIR)).replace("\\", "/")
                if p.stat().st_size == by_rel.get(rel):
                    local_present.add(rel)
            missing_rel = [rel for rel in remaining_rel if rel not in local_present]
            if missing_rel:
                logger.info(
                    "OpenAlex: %d/%d remaining files missing or partial locally (%.1f GB to download) — "
                    "download and process per file",
                    len(missing_rel), len(remaining_rel),
                    sum(by_rel[rel] for rel in missing_rel) / 1e9,
                )
            plan = [
                (f"{S3_PREFIX}/{rel}", LOCAL_WORKS_DIR / rel, int(by_rel[rel]))
                for rel in remaining_rel
            ]
            total_bytes = sum(by_rel[rel] for rel in remaining_rel)

        # openalex_id -> {"doi": ..., "title": ..., "primary_field": ..., "fields": [...]}
        # по всем работам, встреченным в текущем запуске (предыдущие файлы +
        # текущий файл). Используется для превращения ссылок "W123..." в настоящие
        # DOI + заголовки и для протаскивания тематики (fields) на узел.
        known_works: dict[str, dict] = {}
        state: dict[str, int] = {"records": 0}

        def _register_work(work: dict) -> None:
            oid = (work.get("id") or "").rstrip("/").rsplit("/", 1)[-1]
            if not oid or oid in known_works:
                return
            doi = (work.get("doi") or "").replace("https://doi.org/", "").strip().lower()
            primary_field, fields = self._extract_topics_static(work)
            known_works[oid] = {
                "doi": doi,
                "title": work.get("display_name") or None,
                "primary_field": primary_field,
                "fields": tuple(fields) if fields else None,
            }

        def _yield_work(work: dict, ctx: dict) -> None:
            """Регистрирует работу и выделяет её citation edges.

            ctx: mutable dict со счётчиком пропущенных ссылок для текущего файла.
            """
            _register_work(work)
            citing_doi = (work.get("doi") or "").replace("https://doi.org/", "").strip().lower()
            if not citing_doi:
                return
            state["records"] += 1
            if options is not None and options.max_records is not None and state["records"] > options.max_records:
                raise _RecordsLimitReached()
            citing_title = work.get("display_name") or None
            citing_info = known_works.get(work.get("id", "").rstrip("/").rsplit("/", 1)[-1]) or {}
            citing_primary_field = citing_info.get("primary_field")
            citing_fields = citing_info.get("fields")
            for ref_url in work.get("referenced_works", []):
                ref_id = ref_url.rstrip("/").rsplit("/", 1)[-1] if ref_url else ""
                if not ref_id:
                    continue
                info = known_works.get(ref_id)
                # Работу без DOI (или ещё не встреченную в дампе) не добавляем:
                # вместо неё нельзя подставлять идентификатор "W[number]".
                if not info or not info.get("doi"):
                    ctx["skipped"] += 1
                    continue
                yield CitationEdge(
                    citing_doi=citing_doi,
                    cited_doi=info["doi"],
                    source=self.name,
                    title_citing=citing_title,
                    title_cited=info.get("title"),
                    primary_field_citing=citing_primary_field,
                    fields_citing=citing_fields,
                    primary_field_cited=info.get("primary_field"),
                    fields_cited=info.get("fields"),
                )

        processed_bytes = 0
        for idx, (key, local_path, expected_size) in enumerate(plan):
            if cancel_callback is not None and cancel_callback():
                logger.info("OpenAlex bulk canceled (%d files processed)", processed_files_count + idx)
                return
            if not (local_path.exists() and local_path.stat().st_size == expected_size):
                logger.info(
                    "Downloading OpenAlex file %d/%d: %s",
                    idx + 1, len(plan), key,
                )
                if local_path.exists():
                    # Частичный/оборванный файл (например, диск заполнился) —
                    # удаляем, чтобы следующий запуск скачал его целиком заново.
                    try:
                        local_path.unlink()
                    except OSError:
                        pass
                try:
                    await asyncio.to_thread(
                        self._download_key, key, local_path,
                        processed_bytes, total_bytes, progress_callback,
                    )
                except Exception as e:
                    logger.error("OpenAlex download failed for %s: %s", key, e)
                    raise RuntimeError(f"OpenAlex file download failed: {key}") from e
                if not (local_path.exists() and local_path.stat().st_size == expected_size):
                    try:
                        local_path.unlink()
                    except OSError:
                        pass
                    raise RuntimeError(
                        f"OpenAlex download incomplete for {key}: "
                        f"expected {expected_size} bytes. Free disk space and run again "
                        "(checkpoint will continue)."
                    )

            logger.info("Processing OpenAlex file %d/%d: %s", idx + 1, len(plan), local_path.name)
            ctx: dict = {"skipped": 0}
            try:
                # Небольшие файлы индексируем целиком (2 прохода), чтобы резолвить
                # ссылки на работы из этого же файла; крупные — одним проходом,
                # полагаясь на уже встреченные работы (дамп упорядочен по updated_date).
                size = local_path.stat().st_size
                if size <= _SMALL_FILE_INDEX_THRESHOLD:
                    batch: list[dict] = []
                    with gzip.open(local_path, "rt", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            try:
                                batch.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
                    for work in batch:
                        _register_work(work)
                    for work in batch:
                        for edge in _yield_work(work, ctx):
                            yield edge
                else:
                    with gzip.open(local_path, "rt", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            try:
                                work = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            for edge in _yield_work(work, ctx):
                                yield edge
            except _RecordsLimitReached:
                return
            except Exception as e:
                logger.warning("Error processing %s: %s", local_path, e)

            processed_bytes += local_path.stat().st_size
            if not limited:
                CHECKPOINT_FILE.write_text(str(processed_files_count + idx + 1))
            if progress_callback:
                progress_callback(processed_bytes, total_bytes, local_path.name)
            if ctx["skipped"]:
                logger.info(
                    "OpenAlex file %s: skipped %d reference edges to works without resolvable DOI",
                    local_path.name, ctx["skipped"],
                )

        logger.info("OpenAlex bulk: processed %d files", processed_files_count + len(plan))

    # ── Enrichment ──────────────────────────────────────────────────────────

    def list_local_dump_files(self) -> list[Path]:
        """Отсортированный список локальных .gz-файлов дампа works."""
        return sorted(LOCAL_WORKS_DIR.rglob("*.gz")) if LOCAL_WORKS_DIR.exists() else []

    def iter_file_topics(
        self,
        path: Path,
    ) -> Iterator[tuple[str, Optional[str], Optional[tuple[str, ...]]]]:
        """(doi, primary_field, fields) по одному локальному файлу дампа.

        Работы без DOI пропускаются (в графе они не представлены).
        """
        try:
            with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        work = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    doi = (work.get("doi") or "").replace("https://doi.org/", "").strip().lower()
                    if not doi:
                        continue
                    primary_field, fields = self._extract_topics_static(work)
                    if not primary_field and not fields:
                        continue
                    yield doi, primary_field, (tuple(fields) if fields else None)
        except Exception as e:
            logger.warning("OpenAlex enrichment error in %s: %s", path, e)

    def iter_work_topics(
        self,
    ) -> Iterator[tuple[str, Optional[str], Optional[tuple[str, ...]]]]:
        """Синхронный генератор (doi, primary_field, fields) по всем локальным файлам.

        Читает уже скачанные .gz дампа works вне зависимости от чекпоинта загрузки
        и используется для одноразового обогащения Document-узлов тематикой.
        """
        for path in self.list_local_dump_files():
            yield from self.iter_file_topics(path)

    @staticmethod
    def _extract_topics_static(work: dict) -> tuple[Optional[str], list[str]]:
        """primary_field + уникальные field.display_name из topics работы.

        Дублирует логику из get_all (там она замыкает scope known_works),
        чтобы итерировать тематику независимо от массовой загрузки.
        """
        fields: list[str] = []
        primary_field: Optional[str] = None
        pt = work.get("primary_topic") or {}
        pf = (pt.get("field") or {}).get("display_name")
        if pf:
            primary_field = pf
            fields.append(pf)
        for topic in work.get("topics") or []:
            f = (topic.get("field") or {}).get("display_name")
            if f and f not in fields:
                fields.append(f)
        return primary_field, fields

    # ── Test ───────────────────────────────────────────────────────────────

    async def test_estimate(self, sample_size: int = 10) -> TestEstimate:
        test_dois = _TEST_DOIS[:sample_size]
        total_elapsed = 0.0
        total_edges = 0
        errors: list[str] = []

        for doi in test_dois:
            try:
                t0 = time.monotonic()
                edges = await self.get_one(doi)
                elapsed = time.monotonic() - t0
                total_elapsed += elapsed
                total_edges += len(edges)
                await _asyncio_sleep(0.1)
            except Exception as e:
                errors.append(f"{doi}: {e}")

        avg_time = total_elapsed / max(len(test_dois) - len(errors), 1)
        return TestEstimate(
            source_name=self.name,
            sample_size=sample_size,
            elapsed_seconds=round(total_elapsed, 2),
            edges_found=total_edges,
            estimated_total_edges=2_500_000_000,
            estimated_time_seconds=round(avg_time * 2_500_000_000 / max(total_edges, 1), 0) if total_edges else None,
            errors=errors,
            success=len(errors) < sample_size,
        )


async def _asyncio_sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)
