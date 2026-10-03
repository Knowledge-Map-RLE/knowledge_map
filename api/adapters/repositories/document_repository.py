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
import time
from datetime import datetime, timezone
from typing import Optional, List, Tuple

from neomodel import DoesNotExist, db

from infrastructure.neo4j.orm_models import Document as OrmDocument
from domain.models.document import Document
from domain.exceptions import NotFoundError

logger = logging.getLogger(__name__)

# Верхний предел кандидатов из fulltext-индекса за один вызов queryNodes.
# Индекс покрывает ~9.8M узлов; без лимита OR-запросы дают миллионы совпадений
# и превышают 30-секундный таймаут роутера. При AND-семантике top-20000
# результатов достаточно для страниц любой разумной глубины.
_FT_BUDGET = 20000

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


def _build_ft_query(q: str) -> str:
    """Строит Lucene-запрос для fulltext-индекса.

    - Убирает стоп-слова и символы пунктуации
    - Объединяет значимые токены через AND: документ должен содержать все слова запроса.
    Это резко сужает результат (против OR по умолчанию в Lucene) и делает
    запрос быстрым даже при миллионах узлов в индексе.
    """
    tokens = [
        t
        for t in re.findall(r"[^\W_]+", q, flags=re.UNICODE)
        if t.lower() not in _STOP_WORDS and (len(t) >= 2 or t.isdigit())
    ]
    if not tokens:
        return q
    return " AND ".join(tokens)


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
        is_gold_standard=orm_doc.is_gold_standard or False,
        gold_standard_source_pmc_id=orm_doc.gold_standard_source_pmc_id,
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
    orm_doc.is_gold_standard = doc.is_gold_standard
    orm_doc.gold_standard_source_pmc_id = doc.gold_standard_source_pmc_id
    orm_doc.is_processed = doc.is_processed
    orm_doc.processing_status = doc.processing_status
    orm_doc.error_message = doc.error_message
    orm_doc.has_full_text = doc.has_full_text
    return orm_doc


def _row_to_domain(
    row, activity_index: Optional[int] = None, include_gold_fields: bool = True
) -> Document:
    """Собирает Document из кортежа результатов Cypher-запроса (порядок как в list_all).

    Порядок полей (0-based):
    0=uid, 1=original_filename, 2=title, 3=processing_status, 4=is_processed,
    5=source, 6=s3_key, 7=s3_bucket, 8=file_size, 9=upload_date,
    10=docling_raw_md_s3_key, 11=user_md_s3_key,
    12=pubmed_id, 13=pmc_id, 14=is_open_access, 15=error_message, 16=md5_hash,
    17=is_gold_standard, 18=gold_standard_source_pmc_id
    """
    def _val(v):
        return v if v is not None else None

    activity_at = (
        _val(row[activity_index])
        if activity_index is not None and len(row) > activity_index else None
    )
    activity_at = _to_datetime(activity_at)

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
        upload_date=_to_datetime(_val(row[9])),
        docling_raw_md_s3_key=_val(row[10]),
        user_md_s3_key=_val(row[11]),
        pubmed_id=_val(row[12]),
        pmc_id=_val(row[13]),
        is_open_access=bool(_val(row[14])) if _val(row[14]) is not None else False,
        error_message=_val(row[15]),
        md5_hash=_val(row[16]),
        is_gold_standard=(
            bool(_val(row[17]))
            if include_gold_fields and len(row) > 17 and _val(row[17]) is not None else False
        ),
        gold_standard_source_pmc_id=(
            _val(row[18]) if include_gold_fields and len(row) > 18 else None
        ),
        current_user_last_edited_at=activity_at,
    )


def _to_datetime(value) -> Optional[datetime]:
    """Нормализует значения Neo4j и epoch-время в доменный datetime."""
    if value is None:
        return None
    to_native = getattr(value, "to_native", None)
    if callable(to_native):
        value = to_native()
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    return None


class DocumentRepository:
    """
    neomodel-реализация репозитория документов.
    Удовлетворяет DocumentRepositoryProtocol (structural subtyping).
    """

    _full_text_count_cache: Optional[Tuple[int, float]] = None
    _all_count_cache: Optional[Tuple[int, float]] = None
    _sources_count_cache: Optional[Tuple[int, float]] = None
    _CACHE_TTL = 300.0

    def __init__(self) -> None:
        pass

    def record_user_edit(self, user_uid: str, doc_uid: str) -> bool:
        """Создаёт или обновляет пользовательскую активность документа."""
        if not user_uid or not doc_uid:
            logger.warning("Не удалось записать активность документа: отсутствует uid пользователя или документа")
            return False

        results, _ = db.cypher_query(
            "MERGE (u:User {uid: $user_uid}) "
            "ON CREATE SET u.data = '{}' "
            "WITH u MATCH (d:Document {uid: $doc_uid}) "
            "MERGE (u)-[activity:RECENTLY_EDITED]->(d) "
            "SET activity.last_edited_at = datetime() "
            "RETURN activity.last_edited_at",
            {"user_uid": user_uid, "doc_uid": doc_uid},
        )
        if not results:
            logger.warning(
                "Не удалось записать активность: пользователь или документ не найден (user_uid=%s, doc_uid=%s)",
                user_uid,
                doc_uid,
            )
            return False
        type(self)._full_text_count_cache = None
        return True

    _LIST_FIELDS = """
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
               d.user_md_s3_key as user_md_s3_key,
               d.pubmed_id as pubmed_id,
               d.pmc_id as pmc_id,
               d.is_open_access as is_open_access,
               d.error_message as error_message,
               d.md5_hash as md5_hash,
               d.is_gold_standard as is_gold_standard,
               d.gold_standard_source_pmc_id as gold_standard_source_pmc_id
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
        full_text_only: bool = False,
        gold_standard_only: bool = False,
        user_uid: Optional[str] = None,
    ) -> List[Document]:
        t0 = time.monotonic()
        try:
            if limit is not None and limit <= 0:
                return []

            eff_limit = limit or 100
            source_filter = (
                "" if full_text_only else " AND d.source IN ['upload', 'pubmed', 'pmc']"
            )
            gold_filter = " AND d.is_gold_standard = true" if gold_standard_only else ""
            personal_docs: List[Document] = []

            if user_uid:
                # Начинаем выборку недавних документов с узла пользователя и его
                # отношений. Так Neo4j не проверяет персональную активность для
                # каждого документа в многомиллионном каталоге.
                activity_query = f"""
                    MATCH (:User {{uid: $user_uid}})-[activity:RECENTLY_EDITED]->(d:Document)
                    WITH d, max(activity.last_edited_at) AS user_last_edited_at
                    WHERE user_last_edited_at IS NOT NULL{source_filter}{gold_filter}
                    RETURN {self._LIST_FIELDS}, user_last_edited_at
                    ORDER BY user_last_edited_at DESC, is_processed DESC, uid ASC
                """
                activity_rows, _ = db.cypher_query(activity_query, {"user_uid": user_uid})
                personal_docs.extend(
                    _row_to_domain(row, activity_index=19) for row in activity_rows
                )

                # Для статей, созданных до появления RECENTLY_EDITED, доступна
                # дата создания и владелец. Берём только авторские документы без
                # персонального отношения; created_by_uid индексирован.
                created_query = f"""
                    MATCH (d:Document {{created_by_uid: $user_uid}})
                    OPTIONAL MATCH (:User {{uid: $user_uid}})-[activity:RECENTLY_EDITED]->(d)
                    WITH d, max(activity.last_edited_at) AS user_last_edited_at
                    WHERE user_last_edited_at IS NULL{source_filter}{gold_filter}
                    RETURN {self._LIST_FIELDS}, d.upload_date
                    ORDER BY d.upload_date DESC, is_processed DESC, uid ASC
                """
                created_rows, _ = db.cypher_query(created_query, {"user_uid": user_uid})
                personal_docs.extend(
                    _row_to_domain(row, activity_index=19) for row in created_rows
                )

                # Дедупликация и общий порядок персональных документов.
                by_uid: dict[str, Document] = {}
                for doc in personal_docs:
                    by_uid.setdefault(doc.uid, doc)
                personal_docs = list(by_uid.values())
                personal_docs.sort(key=lambda doc: doc.uid or "")
                personal_docs.sort(key=lambda doc: doc.is_processed, reverse=True)
                personal_docs.sort(
                    key=lambda doc: (
                        doc.current_user_last_edited_at.timestamp()
                        if doc.current_user_last_edited_at else float("-inf")
                    ),
                    reverse=True,
                )

            personal_uids = [doc.uid for doc in personal_docs]
            personal_page = personal_docs[skip:skip + eff_limit]
            regular_skip = max(0, skip - len(personal_docs))
            regular_limit = eff_limit - len(personal_page)
            if regular_limit <= 0:
                docs = personal_page
            else:
                personal_exclusion = (
                    " AND NOT (d.uid IN $personal_uids)" if personal_uids else ""
                )
                regular_where = (
                    "d.has_full_text = true" if full_text_only
                    else "d.source IN ['upload', 'pubmed', 'pmc']"
                )
                if gold_standard_only:
                    regular_where += " AND d.is_gold_standard = true"
                regular_query = f"""
                    MATCH (d:Document)
                    WHERE {regular_where}{personal_exclusion}
                    RETURN {self._LIST_FIELDS}, null AS current_user_last_edited_at
                    ORDER BY is_processed DESC, uid ASC
                    SKIP $skip
                    LIMIT $limit
                """
                regular_params: dict = {"skip": regular_skip, "limit": regular_limit}
                if personal_uids:
                    regular_params["personal_uids"] = personal_uids
                regular_rows, _ = db.cypher_query(regular_query, regular_params)
                docs = personal_page + [
                    _row_to_domain(row, activity_index=19) for row in regular_rows
                ]

            elapsed = time.monotonic() - t0
            if elapsed > 2:
                logger.warning(
                    "list_all took %.1fs for %d docs (skip=%d, limit=%d, "
                    "full_text_only=%s, gold_standard_only=%s)",
                    elapsed, len(docs), skip, eff_limit, full_text_only, gold_standard_only,
                )
            return docs
        except Exception as e:
            elapsed = time.monotonic() - t0
            logger.error(f"list_all failed after {elapsed:.1f}s: {e}")
            return []

    def count_all(self) -> int:
        """Общее количество документов. Кэшируется на 5 минут."""
        now = time.monotonic()
        if self._all_count_cache is not None:
            cached_count, cached_at = self._all_count_cache
            if now - cached_at < self._CACHE_TTL:
                return cached_count
        t0 = now
        try:
            results, _ = db.cypher_query(
                "MATCH (d:Document) RETURN count(d) as total"
            )
            elapsed = time.monotonic() - t0
            if elapsed > 2:
                logger.warning(f"count_all took {elapsed:.1f}s")
            count = results[0][0] if results else 0
            self._all_count_cache = (count, time.monotonic())
            return count
        except Exception as e:
            elapsed = time.monotonic() - t0
            logger.error(f"count_all failed after {elapsed:.1f}s: {e}")
            return 0

    def count_full_text(
        self, gold_standard_only: bool = False, user_uid: Optional[str] = None
    ) -> int:
        """Количество документов с полным текстом. Кэшируется на 5 минут."""
        if user_uid is not None:
            try:
                gold_filter = "AND d.is_gold_standard = true" if gold_standard_only else ""
                full_text_count = self.count_full_text(
                    gold_standard_only=gold_standard_only,
                )
                results, _ = db.cypher_query(
                    "CALL { "
                    "MATCH (:User {uid: $user_uid})-[:RECENTLY_EDITED]->(d:Document) "
                    "WHERE coalesce(d.has_full_text, false) = false "
                    f"{gold_filter} RETURN d "
                    "UNION "
                    "MATCH (d:Document {created_by_uid: $user_uid}) "
                    "WHERE coalesce(d.has_full_text, false) = false "
                    f"{gold_filter} "
                    "OPTIONAL MATCH (:User {uid: $user_uid})-[activity:RECENTLY_EDITED]->(d) "
                    "WITH d, count(activity) AS matched_activity "
                    "WHERE matched_activity = 0 RETURN d "
                    "} RETURN count(DISTINCT d) AS cnt",
                    {"user_uid": user_uid},
                )
                personal_without_full_text = results[0][0] if results else 0
                return full_text_count + personal_without_full_text
            except Exception as e:
                logger.error("count_full_text for user failed (user_uid=%s): %s", user_uid, e)
                return 0
        if gold_standard_only:
            try:
                results, _ = db.cypher_query(
                    "MATCH (d:Document) WHERE d.has_full_text = true "
                    "AND d.is_gold_standard = true RETURN count(d) AS cnt"
                )
                return results[0][0] if results else 0
            except Exception as e:
                logger.error(f"count_full_text(gold_standard_only=True) failed: {e}")
                return 0
        now = time.monotonic()
        if self._full_text_count_cache is not None:
            cached_count, cached_at = self._full_text_count_cache
            if now - cached_at < self._CACHE_TTL:
                return cached_count
        t0 = now
        try:
            results, _ = db.cypher_query(
                "MATCH (d:Document) WHERE d.has_full_text = true "
                "RETURN count(d) AS cnt"
            )
            elapsed = time.monotonic() - t0
            if elapsed > 2:
                logger.warning(f"count_full_text took {elapsed:.1f}s")
            count = results[0][0] if results else 0
            self._full_text_count_cache = (count, time.monotonic())
            return count
        except Exception as e:
            elapsed = time.monotonic() - t0
            logger.error(f"count_full_text failed after {elapsed:.1f}s: {e}")
            if self._full_text_count_cache is not None:
                return self._full_text_count_cache[0]
            return 0

    def count_by_sources(self) -> int:
        """Количество документов из основных source (upload, pubmed, pmc). Кэшируется."""
        now = time.monotonic()
        if self._sources_count_cache is not None:
            cached_count, cached_at = self._sources_count_cache
            if now - cached_at < self._CACHE_TTL:
                return cached_count
        t0 = now
        try:
            results, _ = db.cypher_query(
                "MATCH (d:Document) WHERE d.source IN ['upload', 'pubmed', 'pmc'] "
                "RETURN count(d) AS cnt"
            )
            elapsed = time.monotonic() - t0
            if elapsed > 2:
                logger.warning(f"count_by_sources took {elapsed:.1f}s")
            count = results[0][0] if results else 0
            DocumentRepository._sources_count_cache = (count, time.monotonic())
            return count
        except Exception as e:
            elapsed = time.monotonic() - t0
            logger.error(f"count_by_sources failed after {elapsed:.1f}s: {e}")
            if self._sources_count_cache is not None:
                return self._sources_count_cache[0]
            return 0

    def list_all_with_count(
        self,
        skip: int = 0,
        limit: Optional[int] = None,
        full_text_only: bool = False,
    ) -> Tuple[List[Document], int]:
        """Документы + общее количество за два запроса."""
        try:
            docs = self.list_all(skip=skip, limit=limit, full_text_only=full_text_only)
            total = self.count_full_text() if full_text_only else self.count_by_sources()
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
        full_text_only: bool = False,
        user_uid: Optional[str] = None,
    ) -> Tuple[List[Document], int]:
        ft_filter = (
            "(d.has_full_text = true OR user_last_edited_at IS NOT NULL "
            "OR ($user_uid IS NOT NULL AND d.created_by_uid = $user_uid))"
            if full_text_only else "true"
        )
        cypher = f"""
            MATCH (d:Document) WHERE d.{field} = $val
            OPTIONAL MATCH (:User {{uid: $user_uid}})-[activity:RECENTLY_EDITED]->(d)
            WITH d, max(activity.last_edited_at) AS user_last_edited_at
            WHERE {ft_filter}
            WITH d, coalesce(
                user_last_edited_at,
                CASE WHEN $user_uid IS NOT NULL AND d.created_by_uid = $user_uid
                     THEN d.upload_date ELSE null END
            ) AS current_user_last_edited_at
            RETURN {self._SEARCH_FIELDS}, current_user_last_edited_at
            ORDER BY
                CASE WHEN current_user_last_edited_at IS NULL THEN 1 ELSE 0 END ASC,
                current_user_last_edited_at DESC,
                is_processed DESC,
                uid ASC
            SKIP $skip
            LIMIT $limit
        """
        params = {"val": value, "skip": skip, "limit": limit, "user_uid": user_uid}
        results, _ = db.cypher_query(cypher, params)
        count_cypher = f"""
            MATCH (d:Document) WHERE d.{field} = $val
            OPTIONAL MATCH (:User {{uid: $user_uid}})-[activity:RECENTLY_EDITED]->(d)
            WITH d, max(activity.last_edited_at) AS user_last_edited_at
            WHERE {ft_filter}
            RETURN count(d)
        """
        cnt, _ = db.cypher_query(count_cypher, {"val": value, "user_uid": user_uid})
        total = cnt[0][0] if cnt else 0
        return [
            _row_to_domain(row, activity_index=17, include_gold_fields=False)
            for row in results
        ], total

    def search(
        self,
        q: str,
        skip: int = 0,
        limit: int = 100,
        full_text_only: bool = False,
        user_uid: Optional[str] = None,
    ) -> Tuple[List[Document], int]:
        t0 = time.monotonic()
        try:
            if not q.strip():
                return (
                    self.list_all(
                        skip=skip, limit=limit, full_text_only=full_text_only, user_uid=user_uid,
                    ),
                    self.count_full_text(user_uid=user_uid) if full_text_only else self.count_by_sources(),
                )

            query = q.strip()

            if self._is_doi(query):
                results, total = self._search_by_exact_field(
                    "doi", query, skip, limit, full_text_only, user_uid,
                )
                elapsed = time.monotonic() - t0
                if elapsed > 3:
                    logger.warning(f"DOI search took {elapsed:.1f}s for doi={query}")
                return results, total

            if query.isdigit():
                results, total = self._search_by_exact_field(
                    "pubmed_id", query, skip, limit, full_text_only, user_uid,
                )
                elapsed = time.monotonic() - t0
                if elapsed > 3:
                    logger.warning(f"PMID search took {elapsed:.1f}s for pmid={query}")
                return results, total

            if query.upper().startswith("PMC") and query[3:].isdigit():
                results, total = self._search_by_exact_field(
                    "pmc_id", query.upper(), skip, limit, full_text_only, user_uid,
                )
                elapsed = time.monotonic() - t0
                if elapsed > 3:
                    logger.warning(f"PMCID search took {elapsed:.1f}s for pmcid={query}")
                return results, total

            ft_query = _build_ft_query(query)

            personal_filter = """
                d.has_full_text = true OR user_last_edited_at IS NOT NULL
                OR ($user_uid IS NOT NULL AND d.created_by_uid = $user_uid)
            """ if full_text_only else "true"
            documents_cypher = f"""
                CALL db.index.fulltext.queryNodes('doc_fulltext', $q, {{limit: $budget}})
                YIELD node as d, score
                WHERE score > 0.1
                OPTIONAL MATCH (:User {{uid: $user_uid}})-[activity:RECENTLY_EDITED]->(d)
                WITH d, score, max(activity.last_edited_at) AS user_last_edited_at
                WHERE {personal_filter}
                WITH d, score, coalesce(
                    user_last_edited_at,
                    CASE WHEN $user_uid IS NOT NULL AND d.created_by_uid = $user_uid
                         THEN d.upload_date ELSE null END
                ) AS current_user_last_edited_at
                RETURN {self._SEARCH_FIELDS}, current_user_last_edited_at, score
                ORDER BY
                    CASE WHEN current_user_last_edited_at IS NULL THEN 1 ELSE 0 END ASC,
                    current_user_last_edited_at DESC,
                    score DESC,
                    is_processed DESC,
                    uid ASC
                SKIP $skip
                LIMIT $limit
            """
            query_params = {
                "q": ft_query,
                "budget": _FT_BUDGET,
                "skip": skip,
                "limit": limit,
                "user_uid": user_uid,
            }
            results, _ = db.cypher_query(documents_cypher, query_params)

            count_cypher = f"""
                CALL db.index.fulltext.queryNodes('doc_fulltext', $q, {{limit: $budget}})
                YIELD node as d, score
                WHERE score > 0.1
                OPTIONAL MATCH (:User {{uid: $user_uid}})-[activity:RECENTLY_EDITED]->(d)
                WITH d, max(activity.last_edited_at) AS user_last_edited_at
                WHERE {personal_filter}
                RETURN count(d) AS total
            """
            cnt, _ = db.cypher_query(
                count_cypher,
                {"q": ft_query, "budget": _FT_BUDGET, "user_uid": user_uid},
            )
            total = cnt[0][0] if cnt else 0

            elapsed = time.monotonic() - t0
            if elapsed > 3:
                logger.warning(f"fulltext search took {elapsed:.1f}s for q={query!r}, rows={len(results)}")
            return [
                _row_to_domain(row, activity_index=17, include_gold_fields=False)
                for row in results
            ], total
        except Exception as e:
            elapsed = time.monotonic() - t0
            logger.error(f"search failed after {elapsed:.1f}s: {e}")
            return [], 0
