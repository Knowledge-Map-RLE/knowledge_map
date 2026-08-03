import json
import logging
import mimetypes
import os
from datetime import datetime, timezone

from src.uuid8 import uuid8_str
from typing import Any

from neomodel import db
from infrastructure.neo4j.orm_models import Document
from . import settings, get_s3_client

logger = logging.getLogger(__name__)


def _chunks(lst: list, n: int):
    """Разбивает список на батчи по n элементов."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


class ArticleEditorService:
    async def create_article(self, title: str = "New Article") -> dict[str, Any]:
        article_uid = uuid8_str()
        doc = Document(
            uid=article_uid,
            original_filename=title or "New Article",
            md5_hash=article_uid,
            s3_key="",
            title=title or "New Article",
            processing_status="ready_for_annotation",
            is_processed=False,
        ).save()
        return {
            "uid": doc.uid,
            "title": doc.title,
            "original_filename": doc.original_filename,
            "processing_status": doc.processing_status,
            "is_processed": doc.is_processed,
            "created_at": doc.upload_date.isoformat() if doc.upload_date else "",
        }

    async def get_article(self, doc_id: str) -> dict[str, Any] | None:
        doc = Document.nodes.get_or_none(uid=doc_id)
        if not doc:
            return None
        article: dict[str, Any] = {
            "uid": doc.uid,
            "title": doc.title or doc.original_filename,
            "original_filename": doc.original_filename,
            "processing_status": doc.processing_status or "",
            "is_processed": doc.is_processed or False,
            "created_at": doc.upload_date.isoformat() if doc.upload_date else "",
            "updated_at": doc.edit_date.isoformat() if getattr(doc, 'edit_date', None) else "",
        }

        statements, _ = db.cypher_query(
            "MATCH (d:Document {uid: $uid})-[:HAS_STATEMENT]->(s:KnowledgeStatement) "
            "RETURN s ORDER BY s.sort_order",
            {"uid": doc_id},
        )
        article["statements"] = [
            {
                "id": s[0].get("uid", ""),
                "subject_text": s[0].get("subject_text", ""),
                "predicate": s[0].get("predicate", ""),
                "object_text": s[0].get("object_text", ""),
                "subject_type": s[0].get("subject_type", "concept"),
                "object_type": s[0].get("object_type", "concept"),
                "type": s[0].get("type", "FACT"),
                "confidence": s[0].get("confidence", 1.0),
                "sentence_text": s[0].get("sentence_text", ""),
                "sort_order": s[0].get("sort_order", 0),
            }
            for s in statements
        ] if statements else []

        return article

    async def get_document_status(self, doc_id: str) -> str | None:
        results, _ = db.cypher_query(
            "MATCH (d:Document {uid: $uid}) RETURN d.processing_status",
            {"uid": doc_id},
        )
        return results[0][0] if results else None

    def _is_editable_status(self, status: str | None) -> bool:
        """Только документы в финальном статусе можно редактировать."""
        if not status:
            return False
        blocked = {"uploaded", "uploading", "pdf_to_markdown", "processing", "error"}
        return status not in blocked

    async def save_article_text(self, doc_id: str, text: str) -> dict[str, Any]:
        status = await self.get_document_status(doc_id)
        if not self._is_editable_status(status):
            return {"success": False, "uid": doc_id, "error": "not_annotated",
                    "message": "Редактирование доступно только для аннотированных документов. Перейдите в data_extraction редактор для приведения текста в каноничный вид."}
        now = datetime.now(timezone.utc).isoformat()
        bucket = settings.S3_BUCKET_NAME
        md_key = f"markdown/{doc_id}.md"
        s3_client = get_s3_client()
        ok = await s3_client.upload_bytes(
            text.encode("utf-8"),
            bucket,
            md_key,
            content_type="text/markdown; charset=utf-8",
        )
        if not ok:
            return {"success": False, "uid": doc_id, "error": "S3 upload failed"}
        db.cypher_query(
            "MATCH (d:Document {uid: $uid}) "
            "SET d.user_md_s3_key = $key, d.edit_date = datetime($now)",
            {"uid": doc_id, "key": md_key, "now": now},
        )
        return {"success": True, "uid": doc_id, "text_length": len(text)}

    async def get_article_text(self, doc_id: str) -> dict[str, Any]:
        status = await self.get_document_status(doc_id)
        if not self._is_editable_status(status):
            return {"text": "", "not_annotated": True,
                    "message": "Редактирование доступно только для аннотированных документов. Перейдите в data_extraction редактор для приведения текста в каноничный вид."}
        results, _ = db.cypher_query(
            "MATCH (d:Document {uid: $uid}) RETURN "
            "d.user_md_s3_key, d.formatted_md_s3_key, d.docling_raw_md_s3_key",
            {"uid": doc_id},
        )
        if not results:
            return {"text": ""}
        md_key = results[0][0] or results[0][1] or results[0][2]
        if not md_key:
            return {"text": ""}
        bucket = settings.S3_BUCKET_NAME
        s3_client = get_s3_client()
        exists = await s3_client.object_exists(bucket, md_key)
        if not exists:
            return {"text": ""}
        text = await s3_client.download_text(bucket, md_key)
        return {"text": text or ""}

    async def save_statements(
        self, doc_id: str, statements: list[dict[str, Any]]
    ) -> dict[str, Any]:
        status = await self.get_document_status(doc_id)
        if not self._is_editable_status(status):
            return {"success": False, "error": "not_annotated",
                    "message": "Редактирование доступно только для аннотированных документов. Перейдите в data_extraction редактор для приведения текста в каноничный вид."}
        db.cypher_query(
            "MATCH (d:Document {uid: $uid}) OPTIONAL MATCH (d)-[r:HAS_STATEMENT]->(s:KnowledgeStatement) DELETE r, s",
            {"uid": doc_id},
        )
        content_uuids: list[str] = []
        batch: list[dict[str, Any]] = []
        for i, stmt in enumerate(statements):
            stmt_uid = stmt.get("uid") or uuid8_str()
            content_uuids.append(stmt_uid)
            batch.append({
                "uid": stmt_uid,
                "subj": stmt.get("subject_text", ""),
                "pred": stmt.get("predicate", ""),
                "obj": stmt.get("object_text", ""),
                "subj_type": stmt.get("subject_type", "concept"),
                "obj_type": stmt.get("object_type", "concept"),
                "type": stmt.get("type", "FACT"),
                "conf": stmt.get("confidence", 1.0),
                "sent": stmt.get("sentence_text", ""),
                "order": i,
            })
        for chunk in _chunks(batch, 500):
            db.cypher_query(
                "MATCH (d:Document {uid: $doc_id}) "
                "UNWIND $batch AS item "
                "CREATE (s:KnowledgeStatement {uid: item.uid, subject_text: item.subj, predicate: item.pred, "
                "object_text: item.obj, subject_type: item.subj_type, object_type: item.obj_type, "
                "type: item.type, confidence: item.conf, sentence_text: item.sent, sort_order: item.order}) "
                "CREATE (d)-[:HAS_STATEMENT]->(s)",
                {"batch": chunk, "doc_id": doc_id},
            )

        article_uid = uuid8_str()
        db.cypher_query(
            "CREATE (s:KnowledgeStatement {uid: $uid, subject_text: $doc_id, predicate: 'является', "
            "object_text: 'научная статья', subject_type: 'concept', object_type: 'concept', "
            "type: 'META', confidence: 1.0, sentence_text: '', sort_order: $order}) "
            "WITH s MATCH (d:Document {uid: $doc_id}) CREATE (d)-[:HAS_STATEMENT]->(s)",
            {"uid": article_uid, "doc_id": doc_id, "order": len(content_uuids)},
        )

        meta_batch: list[dict[str, Any]] = []
        for idx, stmt_uuid in enumerate(content_uuids):
            meta_batch.append({
                "uid": uuid8_str(),
                "obj": stmt_uuid,
                "order": len(content_uuids) + 1 + idx,
            })
        for chunk in _chunks(meta_batch, 500):
            db.cypher_query(
                "MATCH (d:Document {uid: $doc_id}) "
                "UNWIND $batch AS item "
                "CREATE (s:KnowledgeStatement {uid: item.uid, subject_text: $doc_id, predicate: 'содержит', "
                "object_text: item.obj, subject_type: 'concept', object_type: 'concept', "
                "type: 'META', confidence: 1.0, sentence_text: '', sort_order: item.order}) "
                "CREATE (d)-[:HAS_STATEMENT]->(s)",
                {"batch": chunk, "doc_id": doc_id},
            )

        return {"success": True, "uid": doc_id, "statements_count": len(content_uuids),
                "statement_ids": content_uuids}

    async def list_articles(self, skip: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        results, meta = db.cypher_query(
            "MATCH (d:Document) RETURN d.uid, d.title, d.original_filename, "
            "d.processing_status, d.upload_date, d.user_md_s3_key "
            "ORDER BY d.upload_date DESC SKIP $skip LIMIT $limit",
            {"skip": skip, "limit": limit},
        )
        articles = []
        for row in results:
            ts = row[4]
            articles.append({
                "uid": row[0],
                "title": row[1],
                "original_filename": row[2],
                "processing_status": row[3],
                "created_at": ts.isoformat() if ts else "",
                "has_text": bool(row[5]),
            })
        return articles

    async def get_graph_data(self, doc_id: str) -> dict[str, Any]:
        results, _ = db.cypher_query(
            "MATCH (d:Document {uid: $uid})-[:HAS_STATEMENT]->(s:KnowledgeStatement) "
            "RETURN s ORDER BY s.sort_order",
            {"uid": doc_id},
        )
        all_statements = []
        for row in results:
            s = row[0]
            pred = s.get("predicate", "")
            # Exclude noisy "related_to" meta-statements from graph
            if pred == "related_to":
                continue
            all_statements.append({
                "uid": s.get("uid", ""),
                "subject_text": s.get("subject_text", ""),
                "predicate": pred,
                "object_text": s.get("object_text", ""),
                "subject_type": s.get("subject_type", "concept"),
                "object_type": s.get("object_type", "concept"),
                "type": s.get("type", "FACT"),
            })
        seen: set[tuple[str, str]] = set()
        edges: list[dict[str, str]] = []
        for stmt in all_statements:
            for other in all_statements:
                if stmt["uid"] == other["uid"]:
                    continue
                if stmt["subject_text"] == other["object_text"]:
                    pair = (other["uid"], stmt["uid"])
                    if pair not in seen:
                        seen.add(pair)
                        edges.append({"source_id": other["uid"], "target_id": stmt["uid"]})
                if stmt["object_text"] == other["subject_text"]:
                    pair = (stmt["uid"], other["uid"])
                    if pair not in seen:
                        seen.add(pair)
                        edges.append({"source_id": stmt["uid"], "target_id": other["uid"]})
        connected_ids: set[str] = set()
        for e in edges:
            connected_ids.add(e["source_id"])
            connected_ids.add(e["target_id"])
        all_statements = [s for s in all_statements if s["uid"] in connected_ids]
        return {"statements": all_statements, "edges": edges}

    async def save_blocks(self, doc_id: str, blocks: list[dict[str, Any]]) -> dict[str, Any]:
        status = await self.get_document_status(doc_id)
        if not self._is_editable_status(status):
            return {"success": False, "error": "not_annotated",
                    "message": "Редактирование доступно только для аннотированных документов."}
        db.cypher_query(
            "MATCH (d:Document {uid: $uid}) OPTIONAL MATCH (d)-[r:HAS_BLOCK]->(b:ArticleBlock) DELETE r, b",
            {"uid": doc_id},
        )
        batch: list[dict[str, Any]] = []
        for i, block in enumerate(blocks):
            block_uid = block.get("instanceId") or uuid8_str()
            batch.append({
                "uid": block_uid,
                "bt": int(block.get("blockType", 0)),
                "data": json.dumps(block.get("data", {}), ensure_ascii=False),
                "order": int(block.get("order", i)),
            })
        for chunk in _chunks(batch, 500):
            db.cypher_query(
                "MATCH (d:Document {uid: $doc_id}) "
                "UNWIND $batch AS item "
                "CREATE (b:ArticleBlock {uid: item.uid, block_type: item.bt, data: item.data, order: item.order}) "
                "CREATE (d)-[:HAS_BLOCK]->(b)",
                {"batch": chunk, "doc_id": doc_id},
            )
        db.cypher_query(
            "MATCH (d:Document {uid: $uid}) "
            "SET d.edit_date = datetime($now)",
            {"uid": doc_id, "now": datetime.now(timezone.utc).isoformat()},
        )
        return {"success": True, "uid": doc_id, "blocks_count": len(blocks)}

    async def update_article_title(self, doc_id: str, title: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        db.cypher_query(
            "MATCH (d:Document {uid: $uid}) "
            "SET d.title = $title, d.original_filename = $title, d.edit_date = datetime($now)",
            {"uid": doc_id, "title": title, "now": now},
        )
        return {"success": True, "uid": doc_id, "title": title}

    async def get_blocks(self, doc_id: str) -> dict[str, Any]:
        results, _ = db.cypher_query(
            "MATCH (d:Document {uid: $uid})-[:HAS_BLOCK]->(b:ArticleBlock) "
            "RETURN b.uid, b.block_type, b.data, b.order ORDER BY b.order",
            {"uid": doc_id},
        )
        blocks = []
        for row in results:
            try:
                data = json.loads(row[2])
            except (json.JSONDecodeError, TypeError):
                data = {}
            blocks.append({
                "instanceId": row[0],
                "blockType": row[1],
                "data": data,
                "order": row[3],
            })
        return {"blocks": blocks, "success": True}

    _IMAGE_EXTENSIONS = {
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".tif", ".tiff",
    }

    async def upload_image(
        self, doc_id: str, filename: str, content_type: str, data: bytes
    ) -> dict[str, Any]:
        """Загружает изображение статьи в S3 и возвращает object_key."""
        status = await self.get_document_status(doc_id)
        if not self._is_editable_status(status):
            return {"success": False, "error": "not_annotated",
                    "message": "Редактирование доступно только для аннотированных документов."}
        if not data:
            return {"success": False, "error": "empty_file"}
        ext = os.path.splitext(filename or "")[1].lower()
        if ext not in self._IMAGE_EXTENSIONS:
            ext = ".png"
        object_key = f"documents/{doc_id}/images/{uuid8_str()}{ext}"
        s3_client = get_s3_client()
        ok = await s3_client.upload_bytes(
            data,
            settings.S3_BUCKET_NAME,
            object_key,
            content_type=content_type or "application/octet-stream",
        )
        if not ok:
            return {"success": False, "error": "S3 upload failed"}
        return {"success": True, "object_key": object_key}

    async def get_image(self, object_key: str) -> tuple[bytes, str] | None:
        """Возвращает содержимое изображения и content-type, либо None."""
        if ".." in object_key.split("/"):
            return None
        s3_client = get_s3_client()
        if not await s3_client.object_exists(settings.S3_BUCKET_NAME, object_key):
            return None
        data = await s3_client.download_bytes(settings.S3_BUCKET_NAME, object_key)
        if data is None:
            return None
        content_type = mimetypes.guess_type(object_key)[0] or "application/octet-stream"
        return data, content_type

    async def delete_image(self, object_key: str) -> bool:
        """Удаляет изображение из S3."""
        if ".." in object_key.split("/"):
            return False
        s3_client = get_s3_client()
        if not await s3_client.object_exists(settings.S3_BUCKET_NAME, object_key):
            return False
        return await s3_client.delete_object(settings.S3_BUCKET_NAME, object_key)
