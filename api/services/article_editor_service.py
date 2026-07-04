import logging
from datetime import datetime, timezone

from src.uuid8 import uuid8_str
from typing import Any

from neomodel import db
from infrastructure.neo4j.orm_models import Document
from . import settings, get_s3_client

logger = logging.getLogger(__name__)


class ArticleEditorService:
    async def create_article(self, title: str = "New Article") -> dict[str, Any]:
        doc = Document(
            original_filename=title or "New Article",
            md5_hash=uuid8_str(),
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

    async def save_article_text(self, doc_id: str, text: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        db.cypher_query(
            "MATCH (d:Document {uid: $uid}) "
            "SET d.kl_text = $text, d.edit_date = datetime($now)",
            {"uid": doc_id, "text": text, "now": now},
        )
        return {"success": True, "uid": doc_id, "text_length": len(text)}

    async def get_article_text(self, doc_id: str) -> str:
        results, _ = db.cypher_query(
            "MATCH (d:Document {uid: $uid}) RETURN d.kl_text, "
            "d.user_md_s3_key, d.formatted_md_s3_key, d.docling_raw_md_s3_key",
            {"uid": doc_id},
        )
        if results and results[0][0]:
            return results[0][0]

        # Fallback: load from S3 and cache as kl_text
        if results:
            md_key = results[0][1] or results[0][2] or results[0][3]
            if md_key:
                bucket = settings.S3_BUCKET_NAME
                s3_client = get_s3_client()
                exists = await s3_client.object_exists(bucket, md_key)
                if exists:
                    text = await s3_client.download_text(bucket, md_key)
                    if text:
                        db.cypher_query(
                            "MATCH (d:Document {uid: $uid}) SET d.kl_text = $text",
                            {"uid": doc_id, "text": text},
                        )
                    return text or ""
        return ""

    async def save_statements(
        self, doc_id: str, statements: list[dict[str, Any]]
    ) -> dict[str, Any]:
        db.cypher_query(
            "MATCH (d:Document {uid: $uid}) OPTIONAL MATCH (d)-[r:HAS_STATEMENT]->(s:KnowledgeStatement) DELETE r, s",
            {"uid": doc_id},
        )
        for i, stmt in enumerate(statements):
            stmt_uid = stmt.get("id") or uuid8_str()
            db.cypher_query(
                "CREATE (s:KnowledgeStatement {uid: $uid, subject_text: $subj, predicate: $pred, "
                "object_text: $obj, subject_type: $subj_type, object_type: $obj_type, "
                "type: $type, confidence: $conf, sentence_text: $sent, sort_order: $order}) "
                "WITH s MATCH (d:Document {uid: $doc_id}) CREATE (d)-[:HAS_STATEMENT]->(s)",
                {
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
                    "doc_id": doc_id,
                },
            )
        return {"success": True, "uid": doc_id, "statements_count": len(statements)}

    async def list_articles(self, skip: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        results, meta = db.cypher_query(
            "MATCH (d:Document) RETURN d.uid, d.title, d.original_filename, "
            "d.processing_status, d.upload_date, d.kl_text "
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
                "has_kl_text": bool(row[5]),
            })
        return articles

    async def get_graph_data(self, doc_id: str) -> dict[str, Any]:
        results, _ = db.cypher_query(
            "MATCH (d:Document {uid: $uid})-[:HAS_STATEMENT]->(s:KnowledgeStatement) "
            "RETURN s ORDER BY s.sort_order",
            {"uid": doc_id},
        )
        statements = []
        for row in results:
            s = row[0]
            statements.append({
                "uid": s.get("uid", ""),
                "subject_text": s.get("subject_text", ""),
                "predicate": s.get("predicate", ""),
                "object_text": s.get("object_text", ""),
                "subject_type": s.get("subject_type", "concept"),
                "object_type": s.get("object_type", "concept"),
                "type": s.get("type", "FACT"),
            })
        edges = []
        stmt_by_text: dict[str, str] = {}
        for stmt in statements:
            key = (stmt["subject_text"], stmt["predicate"], stmt["object_text"])
            stmt_by_text[str(key)] = stmt["uid"]

        for stmt in statements:
            for other in statements:
                if stmt["uid"] == other["uid"]:
                    continue
                if stmt["subject_text"] == other["object_text"]:
                    edges.append({"source_id": other["uid"], "target_id": stmt["uid"]})
                if stmt["object_text"] == other["subject_text"]:
                    edges.append({"source_id": stmt["uid"], "target_id": other["uid"]})
        return {"statements": statements, "edges": edges}
