"""
Layer: Interface Adapters — Repository
Package: adapters.repositories.document_repository
Responsibility: neomodel-реализация DocumentRepositoryProtocol.

Allowed imports: neomodel, infrastructure.neo4j.orm_models, domain.models.document, domain.exceptions
Forbidden imports: fastapi, web, grpc, aioboto3
"""
from __future__ import annotations

import logging
import re
from typing import Optional, List, Tuple

from neomodel import DoesNotExist, db

from infrastructure.neo4j.orm_models import Document as OrmDocument
from domain.models.document import Document
from domain.exceptions import NotFoundError

logger = logging.getLogger(__name__)

_STOP_WORDS = frozenset({
    "a", "an", "the", "of", "and", "or", "in", "on", "at", "to", "for",
    "is", "are", "was", "were", "be", "been", "being",
    "by", "with", "from", "as", "into", "that", "this", "it",
    "not", "but", "if", "than", "then", "so", "no", "nor",
    "its", "their", "our", "your", "his", "her",
    "also", "may", "can", "will", "would", "could", "should",
    "has", "have", "had", "do", "does", "did",
    "about", "between", "through", "during", "before", "after",
})


def _strip_stop_words(q: str) -> str:
    words = q.split()
    stripped = [w for w in words if w.lower() not in _STOP_WORDS]
    return " ".join(stripped) if stripped else q


def _orm_to_domain(orm_doc: OrmDocument) -> Document:
    """Транслирует ORM-объект Document в доменный dataclass."""
    return Document(
        uid=orm_doc.uid,
        original_filename=orm_doc.original_filename,
        md5_hash=orm_doc.md5_hash,
        s3_bucket=orm_doc.s3_bucket or "knowledge-map-data",
        s3_key=orm_doc.s3_key,
        file_size=orm_doc.file_size,
        upload_date=orm_doc.upload_date,
        title=orm_doc.title,
        authors=orm_doc.authors,
        abstract=orm_doc.abstract,
        keywords=orm_doc.keywords,
        publication_date=orm_doc.publication_date,
        journal=orm_doc.journal,
        doi=orm_doc.doi,
        docling_raw_md_s3_key=orm_doc.docling_raw_md_s3_key,
        formatted_md_s3_key=orm_doc.formatted_md_s3_key,
        user_md_s3_key=orm_doc.user_md_s3_key,
        source=orm_doc.source or "upload",
        pubmed_id=orm_doc.pubmed_id,
        pmc_id=orm_doc.pmc_id,
        is_open_access=orm_doc.is_open_access or False,
        is_processed=orm_doc.is_processed or False,
        processing_status=orm_doc.processing_status or "uploaded",
        error_message=orm_doc.error_message,
    )


def _domain_to_orm(doc: Document, orm_doc: Optional[OrmDocument] = None) -> OrmDocument:
    """Заполняет ORM-объект из доменного dataclass."""
    if orm_doc is None:
        orm_doc = OrmDocument(
            uid=doc.uid,
            original_filename=doc.original_filename,
            md5_hash=doc.md5_hash,
            s3_bucket=doc.s3_bucket,
            s3_key=doc.s3_key,
        )
    orm_doc.original_filename = doc.original_filename
    orm_doc.md5_hash = doc.md5_hash
    orm_doc.s3_bucket = doc.s3_bucket
    orm_doc.s3_key = doc.s3_key
    orm_doc.file_size = doc.file_size
    orm_doc.title = doc.title
    orm_doc.authors = doc.authors
    orm_doc.abstract = doc.abstract
    orm_doc.keywords = doc.keywords
    orm_doc.publication_date = doc.publication_date
    orm_doc.journal = doc.journal
    orm_doc.doi = doc.doi
    orm_doc.docling_raw_md_s3_key = doc.docling_raw_md_s3_key
    orm_doc.formatted_md_s3_key = doc.formatted_md_s3_key
    orm_doc.user_md_s3_key = doc.user_md_s3_key
    orm_doc.source = doc.source
    orm_doc.pubmed_id = doc.pubmed_id
    orm_doc.pmc_id = doc.pmc_id
    orm_doc.is_open_access = doc.is_open_access
    orm_doc.is_processed = doc.is_processed
    orm_doc.processing_status = doc.processing_status
    orm_doc.error_message = doc.error_message
    return orm_doc


def _row_to_domain(row) -> Document:
    """Собирает Document из кортежа результатов Cypher-запроса (порядок как в list_all).

    Порядок полей (0-based):
    0=uid, 1=original_filename, 2=title, 3=processing_status, 4=is_processed,
    5=source, 6=s3_key, 7=s3_bucket, 8=file_size, 9=upload_date,
    10=docling_raw_md_s3_key, 11=formatted_md_s3_key, 12=user_md_s3_key,
    13=pubmed_id, 14=pmc_id, 15=is_open_access, 16=error_message, 17=md5_hash
    """
    def _val(v):
        return v if v is not None else None

    return Document(
        uid=_val(row[0]),
        original_filename=_val(row[1]) or "",
        title=_val(row[2]),
        processing_status=_val(row[3]) or "uploaded",
        is_processed=bool(_val(row[4])) if _val(row[4]) is not None else False,
        source=_val(row[5]) or "upload",
        s3_key=_val(row[6]),
        s3_bucket=_val(row[7]) or "knowledge-map-data",
        file_size=_val(row[8]),
        upload_date=_val(row[9]),
        docling_raw_md_s3_key=_val(row[10]),
        formatted_md_s3_key=_val(row[11]),
        user_md_s3_key=_val(row[12]),
        pubmed_id=_val(row[13]),
        pmc_id=_val(row[14]),
        is_open_access=bool(_val(row[15])) if _val(row[15]) is not None else False,
        error_message=_val(row[16]),
        md5_hash=_val(row[17]),
    )


class DocumentRepository:
    """
    neomodel-реализация репозитория документов.
    Удовлетворяет DocumentRepositoryProtocol (structural subtyping).
    """

    def get_by_id(self, uid: str) -> Optional[Document]:
        try:
            return _orm_to_domain(OrmDocument.nodes.get(uid=uid))
        except DoesNotExist:
            return None

    def get_by_md5(self, md5_hash: str) -> Optional[Document]:
        try:
            return _orm_to_domain(OrmDocument.nodes.get(md5_hash=md5_hash))
        except DoesNotExist:
            return None

    def save(self, doc: Document) -> Document:
        try:
            orm_doc = OrmDocument.nodes.get(uid=doc.uid) if doc.uid else None
        except DoesNotExist:
            orm_doc = None

        orm_doc = _domain_to_orm(doc, orm_doc)
        orm_doc.save()
        orm_doc.refresh()
        return _orm_to_domain(orm_doc)

    def delete(self, uid: str) -> None:
        try:
            orm_doc = OrmDocument.nodes.get(uid=uid)
        except DoesNotExist:
            raise NotFoundError("Document", uid)
        orm_doc.delete()

    def list_all(
        self,
        skip: int = 0,
        limit: Optional[int] = None,
    ) -> List[Document]:
        import time
        t0 = time.monotonic()
        try:
            if limit is not None and limit <= 0:
                return []

            eff_limit = limit or 100

            # Два быстрых запроса вместо одного медленного ORDER BY CASE:
            # 1) upload-документы (range index по source — мгновенно)
            # 2) не-upload документы с LIMIT (без сортировки по source — full scan)
            # UNION ALL сохраняет приоритет: upload наверху.
            _FIELDS = """
                       d.uid as uid,
                       d.original_filename as original_filename,
                       d.title as title,
                       d.processing_status as processing_status,
                       d.is_processed as is_processed,
                       d.source as source,
                       d.s3_key as s3_key,
                       d.s3_bucket as s3_bucket,
                       d.file_size as file_size,
                       d.upload_date as upload_date,
                       d.docling_raw_md_s3_key as docling_raw_md_s3_key,
                       d.formatted_md_s3_key as formatted_md_s3_key,
                       d.user_md_s3_key as user_md_s3_key,
                       d.pubmed_id as pubmed_id,
                       d.pmc_id as pmc_id,
                       d.is_open_access as is_open_access,
                       d.error_message as error_message,
                       d.md5_hash as md5_hash
            """
            cypher = f"""
                MATCH (d:Document) WHERE d.source = 'upload'
                RETURN {_FIELDS}
                ORDER BY d.uid ASC
                SKIP $skip
                LIMIT $limit
                UNION ALL
                MATCH (d:Document) WHERE d.source IN ['pubmed', 'pmc']
                RETURN {_FIELDS}
                SKIP $skip
                LIMIT $limit
            """
            params: dict = {"skip": skip, "limit": eff_limit}

            results, _ = db.cypher_query(cypher, params)
            elapsed = time.monotonic() - t0
            if elapsed > 2:
                logger.warning(f"list_all took {elapsed:.1f}s for {len(results)} docs (skip={skip}, limit={limit})")

            # Убираем дубли (на случай пересечения) и обрезаем до limit
            seen = set()
            docs: List[Document] = []
            for row in results:
                uid = row[0]
                if uid in seen:
                    continue
                seen.add(uid)
                docs.append(_row_to_domain(row))
                if len(docs) >= eff_limit:
                    break

            return docs
        except Exception as e:
            elapsed = time.monotonic() - t0
            logger.error(f"list_all failed after {elapsed:.1f}s: {e}")
            return []

    def count_all(self) -> int:
        import time
        t0 = time.monotonic()
        try:
            results, _ = db.cypher_query(
                "MATCH (d:Document) RETURN count(d) as total"
            )
            elapsed = time.monotonic() - t0
            if elapsed > 2:
                logger.warning(f"count_all took {elapsed:.1f}s")
            return results[0][0] if results else 0
        except Exception as e:
            elapsed = time.monotonic() - t0
            logger.error(f"count_all failed after {elapsed:.1f}s: {e}")
            return 0

    def list_all_with_count(
        self,
        skip: int = 0,
        limit: Optional[int] = None,
    ) -> Tuple[List[Document], int]:
        """Документы + общее количество за два запроса (оба используют индексы)."""
        try:
            docs = self.list_all(skip=skip, limit=limit)
            total = self.count_all()
            return docs, total
        except Exception as e:
            logger.error(f"list_all_with_count failed: {e}")
            return [], 0

    _SEARCH_FIELDS = """
        d.uid as uid,
        d.original_filename as original_filename,
        d.title as title,
        d.processing_status as processing_status,
        d.is_processed as is_processed,
        d.source as source,
        d.s3_key as s3_key,
        d.s3_bucket as s3_bucket,
        d.file_size as file_size,
        d.upload_date as upload_date,
        d.docling_raw_md_s3_key as docling_raw_md_s3_key,
        d.formatted_md_s3_key as formatted_md_s3_key,
        d.user_md_s3_key as user_md_s3_key,
        d.pubmed_id as pubmed_id,
        d.pmc_id as pmc_id,
        d.is_open_access as is_open_access,
        d.error_message as error_message,
        d.md5_hash as md5_hash
    """

    @staticmethod
    def _is_doi(q: str) -> bool:
        stripped = q.strip()
        return stripped.startswith("10.") and "/" in stripped

    def _search_by_exact_field(
        self,
        field: str,
        value: str,
        skip: int,
        limit: int,
    ) -> Tuple[List[Document], int]:
        cypher = f"""
            MATCH (d:Document) WHERE d.{field} = $val
            RETURN {self._SEARCH_FIELDS}
            SKIP $skip LIMIT $limit
        """
        results, _ = db.cypher_query(cypher, {"val": value, "skip": skip, "limit": limit})
        if results:
            count_cypher = f"MATCH (d:Document) WHERE d.{field} = $val RETURN count(d)"
            cnt, _ = db.cypher_query(count_cypher, {"val": value})
            total = cnt[0][0] if cnt else len(results)
            return [_row_to_domain(row) for row in results], total
        return [], 0

    def search(
        self,
        q: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Document], int]:
        import time
        t0 = time.monotonic()
        try:
            if not q.strip():
                return self.list_all(skip=skip, limit=limit), self.count_all()

            query = q.strip()

            if self._is_doi(query):
                results, total = self._search_by_exact_field("doi", query, skip, limit)
                elapsed = time.monotonic() - t0
                if elapsed > 3:
                    logger.warning(f"DOI search took {elapsed:.1f}s for doi={query}")
                return results, total

            if query.isdigit():
                results, total = self._search_by_exact_field("pubmed_id", query, skip, limit)
                elapsed = time.monotonic() - t0
                if elapsed > 3:
                    logger.warning(f"PMID search took {elapsed:.1f}s for pmid={query}")
                return results, total

            if query.upper().startswith("PMC") and query[3:].isdigit():
                results, total = self._search_by_exact_field("pmc_id", query.upper(), skip, limit)
                elapsed = time.monotonic() - t0
                if elapsed > 3:
                    logger.warning(f"PMCID search took {elapsed:.1f}s for pmcid={query}")
                return results, total

            ft_query = _strip_stop_words(query)

            uid_cypher = """
                CALL db.index.fulltext.queryNodes('doc_fulltext', $q)
                YIELD node as d, score
                WITH d.uid AS uid, d.source AS source, score
                WHERE score > 0.1
                WITH uid, source, score,
                     CASE WHEN source = 'upload' THEN 1000 ELSE 0 END AS upload_bonus
                ORDER BY upload_bonus DESC, score DESC
                SKIP $skip
                LIMIT $limit
                RETURN uid
            """
            uid_results, _ = db.cypher_query(uid_cypher, {"q": ft_query, "skip": skip, "limit": limit})
            uids = [row[0] for row in uid_results if row[0]]
            elapsed_ft = time.monotonic() - t0
            if elapsed_ft > 2:
                logger.warning(f"fulltext UIDs phase took {elapsed_ft:.1f}s for q={query!r}, uids={len(uids)}")

            if not uids:
                return [], 0

            fetch_cypher = f"""
                MATCH (d:Document) WHERE d.uid IN $uids
                RETURN {self._SEARCH_FIELDS}
            """
            fetch_results, _ = db.cypher_query(fetch_cypher, {"uids": uids})
            uid_order = {uid: i for i, uid in enumerate(uids)}
            sorted_rows = sorted(fetch_results, key=lambda row: uid_order.get(row[0], 999))

            total = len(uid_results) if len(uid_results) < limit else len(uid_results) + skip
            elapsed = time.monotonic() - t0
            if elapsed > 3:
                logger.warning(f"fulltext search took {elapsed:.1f}s for q={query!r}, rows={len(sorted_rows)}")
            return [_row_to_domain(row) for row in sorted_rows], total
        except Exception as e:
            elapsed = time.monotonic() - t0
            logger.error(f"search failed after {elapsed:.1f}s: {e}")
            return [], 0
