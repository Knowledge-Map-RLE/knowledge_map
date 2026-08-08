"""
Layer: Interface Adapters — Repository
Package: adapters.repositories.annotation_repository
Responsibility: neomodel-реализация AnnotationRepositoryProtocol.

Allowed imports: neomodel, infrastructure.neo4j.orm_models, domain.models.annotation, domain.exceptions
Forbidden imports: fastapi, web
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional, List, Tuple

from neomodel import db, DoesNotExist

from infrastructure.neo4j.orm_models import (
    MarkdownAnnotation as OrmAnnotation,
    Document as OrmDocument,
)
from domain.models.annotation import MarkdownAnnotation, AnnotationRelation
from domain.exceptions import NotFoundError

logger = logging.getLogger(__name__)

# Список полей, читаемых из MarkdownAnnotation напрямую через raw Cypher.
# RAW-чтение вместо OrmAnnotation.nodes.get(...) необходимо, потому что neomodel
# DateTimeProperty умеет инфлейтить только float (epoch), а аннотации, созданные
# через прямые Cypher-запросы (напр. spaCy-пайплайн), хранят created_date как
# neo4j.time.DateTime — чтение таких узлов через inflate падает с InflateError.
_ANNOTATION_FIELDS = (
    "ann.uid, ann.text, ann.annotation_type, "
    "ann.start_offset, ann.end_offset, ann.color, "
    "ann.metadata, ann.confidence, ann.created_date, "
    "ann.source, ann.processor_version"
)


def _row_to_annotation(row: list) -> MarkdownAnnotation:
    return MarkdownAnnotation(
        uid=row[0],
        text=row[1],
        annotation_type=row[2],
        start_offset=row[3],
        end_offset=row[4],
        color=row[5] or "#ffeb3b",
        metadata=row[6],
        confidence=row[7],
        created_date=row[8],
        source=row[9] or "user",
        processor_version=row[10],
    )

def _orm_to_domain(orm_ann: OrmAnnotation) -> MarkdownAnnotation:
    return MarkdownAnnotation(
        uid=orm_ann.uid,
        text=orm_ann.text,
        annotation_type=orm_ann.annotation_type,
        start_offset=orm_ann.start_offset,
        end_offset=orm_ann.end_offset,
        color=orm_ann.color or "#ffeb3b",
        metadata=orm_ann.metadata,
        confidence=orm_ann.confidence,
        created_date=orm_ann.created_date,
        source=orm_ann.source or "user",
        processor_version=orm_ann.processor_version,
    )


class AnnotationRepository:
    """
    neomodel-реализация репозитория Markdown-аннотаций.
    Удовлетворяет AnnotationRepositoryProtocol (structural subtyping).
    """

    def create(self, annotation: MarkdownAnnotation, doc_id: str) -> MarkdownAnnotation:
        try:
            orm_doc = OrmDocument.nodes.get(uid=doc_id)
        except DoesNotExist:
            raise NotFoundError("Document", doc_id)

        orm_ann = OrmAnnotation(
            text=annotation.text,
            annotation_type=annotation.annotation_type,
            start_offset=annotation.start_offset,
            end_offset=annotation.end_offset,
            color=annotation.color,
            metadata=annotation.metadata,
            confidence=annotation.confidence,
            source=annotation.source,
            processor_version=annotation.processor_version,
        ).save()
        orm_doc.markdown_annotations.connect(orm_ann)
        return _orm_to_domain(orm_ann)

    def get_by_id(self, uid: str) -> Optional[MarkdownAnnotation]:
        result, _ = db.cypher_query(
            f"MATCH (ann:MarkdownAnnotation {{uid: $uid}}) RETURN {_ANNOTATION_FIELDS}",
            {"uid": uid},
        )
        if not result:
            return None
        return _row_to_annotation(result[0])

    def get_by_document(
        self,
        doc_id: str,
        skip: int = 0,
        limit: Optional[int] = None,
        annotation_types: Optional[List[str]] = None,
        source: Optional[str] = None,
    ) -> Tuple[List[MarkdownAnnotation], int]:
        params: dict = {"doc_id": doc_id}

        # Дополнительные фильтры
        extra_where = ""
        if annotation_types:
            extra_where += " AND ann.annotation_type IN $types"
            params["types"] = annotation_types
        if source:
            extra_where += " AND ann.source = $source"
            params["source"] = source

        # Запрос total (без SKIP/LIMIT)
        count_query = f"""
        MATCH (doc:Document {{uid: $doc_id}})-[:HAS_MARKDOWN_ANNOTATION]->(ann:MarkdownAnnotation)
        WHERE 1=1{extra_where}
        RETURN count(ann)
        """
        count_result, _ = db.cypher_query(count_query, params)
        total: int = count_result[0][0] if count_result else 0

        if total == 0:
            return [], 0

        # Запрос данных — свойства напрямую, без inflate()
        fetch_query = f"""
        MATCH (doc:Document {{uid: $doc_id}})-[:HAS_MARKDOWN_ANNOTATION]->(ann:MarkdownAnnotation)
        WHERE 1=1{extra_where}
        RETURN ann.uid, ann.text, ann.annotation_type,
               ann.start_offset, ann.end_offset, ann.color,
               ann.metadata, ann.confidence, ann.created_date,
               ann.source, ann.processor_version
        ORDER BY ann.start_offset
        SKIP $skip
        {f"LIMIT $limit" if limit is not None else ""}
        """
        fetch_params = {**params, "skip": skip}
        if limit is not None:
            fetch_params["limit"] = limit

        result, _ = db.cypher_query(fetch_query, fetch_params)
        annotations = []
        for row in result:
            try:
                annotations.append(MarkdownAnnotation(
                    uid=row[0],
                    text=row[1],
                    annotation_type=row[2],
                    start_offset=row[3],
                    end_offset=row[4],
                    color=row[5] or "#ffeb3b",
                    metadata=row[6],
                    confidence=row[7],
                    created_date=row[8],
                    source=row[9] or "user",
                    processor_version=row[10],
                ))
            except Exception as e:
                logger.warning(f"Не удалось разобрать аннотацию: {e}")
        return annotations, total

    def save(self, annotation: MarkdownAnnotation) -> MarkdownAnnotation:
        result, _ = db.cypher_query(
            """
            MATCH (ann:MarkdownAnnotation {uid: $uid})
            SET ann.text = $text,
                ann.annotation_type = $annotation_type,
                ann.start_offset = $start_offset,
                ann.end_offset = $end_offset,
                ann.color = $color,
                ann.metadata = $metadata,
                ann.confidence = $confidence
            RETURN count(ann)
            """,
            {
                "uid": annotation.uid,
                "text": annotation.text,
                "annotation_type": annotation.annotation_type,
                "start_offset": annotation.start_offset,
                "end_offset": annotation.end_offset,
                "color": annotation.color,
                "metadata": annotation.metadata,
                "confidence": annotation.confidence,
            },
        )
        if not result or result[0][0] == 0:
            raise NotFoundError("MarkdownAnnotation", annotation.uid)
        return annotation

    def delete(self, uid: str) -> None:
        result, _ = db.cypher_query(
            "MATCH (ann:MarkdownAnnotation {uid: $uid}) RETURN count(ann)",
            {"uid": uid},
        )
        if not result or result[0][0] == 0:
            raise NotFoundError("MarkdownAnnotation", uid)
        db.cypher_query(
            "MATCH (ann:MarkdownAnnotation {uid: $uid}) DETACH DELETE ann",
            {"uid": uid},
        )

    def delete_all_for_document(self, doc_id: str) -> int:
        result, _ = db.cypher_query(
            """
            MATCH (doc:Document {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(ann:MarkdownAnnotation)
            DETACH DELETE ann
            RETURN count(ann) as deleted
            """,
            {"doc_id": doc_id},
        )
        return result[0][0] if result else 0

    def count_for_document(self, doc_id: str) -> int:
        result, _ = db.cypher_query(
            "MATCH (doc:Document {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(ann) RETURN count(ann)",
            {"doc_id": doc_id},
        )
        return result[0][0] if result else 0

    def create_relation(
        self,
        source_uid: str,
        target_uid: str,
        relation_type: str,
        metadata: Optional[dict] = None,
    ) -> AnnotationRelation:
        for uid in (source_uid, target_uid):
            result, _ = db.cypher_query(
                "MATCH (ann:MarkdownAnnotation {uid: $uid}) RETURN count(ann)",
                {"uid": uid},
            )
            if not result or result[0][0] == 0:
                raise NotFoundError("MarkdownAnnotation", uid)

        rel_uid = uuid.uuid4().hex
        result, _ = db.cypher_query(
            """
            MATCH (s:MarkdownAnnotation {uid: $src}), (t:MarkdownAnnotation {uid: $tgt})
            CREATE (s)-[r:RELATES_TO {uid: $rel_uid, relation_type: $relation_type,
                                      created_date: datetime(), metadata: $metadata}]->(t)
            RETURN r.uid
            """,
            {
                "src": source_uid,
                "tgt": target_uid,
                "rel_uid": rel_uid,
                "relation_type": relation_type,
                "metadata": metadata or {},
            },
        )
        return AnnotationRelation(
            uid=result[0][0] if result else rel_uid,
            source_uid=source_uid,
            target_uid=target_uid,
            relation_type=relation_type,
            created_date=datetime.utcnow(),
            metadata=metadata or {},
        )

    def delete_relation(self, source_uid: str, target_uid: str) -> None:
        db.cypher_query(
            """
            MATCH (s:MarkdownAnnotation {uid: $src})-[r:RELATES_TO]->(t:MarkdownAnnotation {uid: $tgt})
            DELETE r
            """,
            {"src": source_uid, "tgt": target_uid},
        )

    def get_relations_for_document(self, doc_id: str) -> List[AnnotationRelation]:
        result, _ = db.cypher_query(
            """
            MATCH (doc:Document {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(s:MarkdownAnnotation)
            -[r:RELATES_TO]->(t:MarkdownAnnotation)
            RETURN s.uid as source_uid, t.uid as target_uid,
                   r.uid as rel_uid, r.relation_type as rel_type,
                   r.created_date as created_date, r.metadata as metadata
            """,
            {"doc_id": doc_id},
        )
        return [
            AnnotationRelation(
                uid=str(row[2]) if row[2] else "",
                source_uid=str(row[0]),
                target_uid=str(row[1]),
                relation_type=str(row[3]),
                created_date=row[4],
                metadata=row[5],
            )
            for row in result
        ]

    def batch_update_offsets(self, updates: List[dict]) -> Tuple[int, List[str]]:
        """
        Массово обновляет start_offset / end_offset одним UNWIND-запросом к Neo4j.
        updates: [{"annotation_id": str, "start_offset": int, "end_offset": int}, ...]
        """
        if not updates:
            return 0, []

        params = [
            {
                "annotation_id": upd.get("annotation_id", ""),
                "start_offset": upd["start_offset"],
                "end_offset": upd["end_offset"],
            }
            for upd in updates
        ]

        try:
            result, _ = db.cypher_query(
                """
                UNWIND $updates AS u
                MATCH (ann:MarkdownAnnotation {uid: u.annotation_id})
                SET ann.start_offset = u.start_offset, ann.end_offset = u.end_offset
                RETURN count(ann) AS updated
                """,
                {"updates": params},
            )
            updated = result[0][0] if result else 0
            errors = []
            # Если часть аннотаций не найдена — сообщаем об этом
            if updated < len(updates):
                errors.append(
                    f"Обновлено {updated} из {len(updates)}: часть аннотаций не найдена"
                )
            return updated, errors
        except Exception as e:
            logger.error(f"batch_update_offsets error: {e}")
            return 0, [f"Ошибка массового обновления: {e}"]
