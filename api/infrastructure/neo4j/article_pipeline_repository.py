"""Transactional stage snapshots and traversable provenance graph (Variant A).

Persists the article pipeline stages: source revision, linguistic profile
(tokens/sentences), structural rows (ArticleBlock with ``unit_ids`` and
``source_spans``) and the Knowledge Map payload. The direct pipeline does not
create an intermediate semantic layer or provenance edges: every block points
straight to its SourceSpan inside the SourceRevision.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from neo4j import GraphDatabase
from knowledge_contracts.validation import (require, validate_linguistic,
                                            validate_map, validate_structural)
from knowledge_pipeline.pipeline import checksum


def _span_uid(source_id: str, start: int, end: int) -> str:
    return hashlib.sha256(f"{source_id}:{start}:{end}".encode("utf-8")).hexdigest()


class Neo4jArticlePipelineRepository:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
    def close(self):
        self.driver.close()
    def ensure_indexes(self):
        with self.driver.session() as session:
            for label in ("ArticlePipelineRun", "SourceRevision", "SourceSpan", "ArticleBlock"):
                session.run(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.uid IS UNIQUE").consume()
    @staticmethod
    def _access(tx, doc_id, user_uid):
        row = tx.run("MATCH (d:Document {uid:$id}) RETURN d.created_by_uid AS owner", id=doc_id).single()
        require(row is not None, "Article not found")
        require(bool(user_uid) and row["owner"] == user_uid, "Article access denied")
    def authorize(self, doc_id, user_uid):
        with self.driver.session() as session:
            session.execute_read(self._access, doc_id, user_uid)
    def save(self, result, user_uid):
        if result.get("success"):
            self._validate_completed(result)
        with self.driver.session() as session:
            session.execute_write(self._save, result, user_uid)
    @staticmethod
    def _validate_completed(result):
        source = result["source"]
        profile = result["linguistic_profile"]
        validate_linguistic(profile, source)
        validate_structural(result["blocks"], source, profile["sentences"])
        validate_map(result["graph"], result["blocks"])
    def _save(self, tx, result, user_uid):
        doc_id = result["article_id"]
        self._access(tx, doc_id, user_uid)
        existing = tx.run("MATCH (v:ArticlePipelineRun {uid:$id}) RETURN v.payload AS payload",
                          id=result["version_id"]).single()
        if existing:
            previous = json.loads(existing["payload"])
            require(previous["article_id"] == doc_id, "Version belongs to another article")
            if previous.get("success"):
                require(previous == result, "Completed versions are immutable")
                return
        source = result["source"]
        tx.run("""MATCH (d:Document {uid:$doc})
          MERGE (r:SourceRevision {uid:$revision})
          ON CREATE SET r.text=$text,r.sha256=$sha,r.offset_encoding='unicode_codepoints'
          MERGE (d)-[:HAS_SOURCE_REVISION]->(r)
          MERGE (v:ArticlePipelineRun {uid:$version})
          ON CREATE SET v.created_at=$now,v.run_id=$run,v.created_by_uid=$user
          SET v.status=$status,v.stage=$stage,v.payload=$payload,v.updated_at=$now
          MERGE (d)-[:HAS_PIPELINE_VERSION]->(v)
          MERGE (v)-[:SOURCE]->(r)""",
          doc=doc_id, revision=source["id"], text=source["text"], sha=source["sha256"],
          version=result["version_id"], run=result["run_id"], user=user_uid, status=result["status"],
          stage=result["stage"], payload=json.dumps(result, ensure_ascii=False),
          now=datetime.now(timezone.utc).isoformat()).consume()
        if not result.get("success"):
            return
        self._validate_completed(result)
        version = result["version_id"]
        displays = {node["id"]: node["display_text"] for node in result["graph"]["nodes"]}
        block_rows = [{
            "id": block["instanceId"],
            "block_type": block["blockType"],
            "data": json.dumps(block["data"], ensure_ascii=False),
            "order": block["order"],
            "display": displays[block["instanceId"]],
            "spans": [{"uid": _span_uid(source["id"], span["start"], span["end"]),
                       "start": span["start"], "end": span["end"]}
                      for span in block["data"]["provenance"]["source_spans"]],
        } for block in result["blocks"]]
        tx.run("""MATCH (v:ArticlePipelineRun {uid:$v})
          UNWIND $rows AS row
          MERGE (b:ArticleBlock {uid:row.id})
          SET b.block_type=row.block_type,b.data=row.data,b.order=row.order,
              b.schema_version=2,b.display_text=row.display
          MERGE (v)-[:HAS_BLOCK]->(b)
          WITH b,row
          UNWIND row.spans AS span
          MERGE (s:SourceSpan {uid:span.uid})
          SET s.start=span.start,s.end=span.end
          MERGE (b)-[:SOURCE_SPAN]->(s)""", v=version, rows=block_rows).consume()
        tx.run("""WITH $rows AS rows
          UNWIND rows AS span
          MATCH (r:SourceRevision {uid:$revision})
          MERGE (s:SourceSpan {uid:span.uid})
          SET s.start=span.start,s.end=span.end
          MERGE (s)-[:IN_REVISION]->(r)""", revision=source["id"],
          rows=[span for row in block_rows for span in row["spans"]]).consume()
        tx.run("""MATCH (v:ArticlePipelineRun {uid:$v}) SET v.map_payload=$map""",
               v=version, map=json.dumps(result["graph"], ensure_ascii=False)).consume()
    def load(self, doc_id, version_id, user_uid):
        with self.driver.session() as session:
            def read(tx):
                self._access(tx, doc_id, user_uid)
                row = tx.run("""MATCH (:Document {uid:$d})-[:HAS_PIPELINE_VERSION]->
                    (v:ArticlePipelineRun {uid:$v}) RETURN v.payload AS payload""",
                             d=doc_id, v=version_id).single()
                require(row is not None, "Version not found")
                return json.loads(row["payload"])
            return session.execute_read(read)
    def versions(self, doc_id, user_uid):
        with self.driver.session() as session:
            def read(tx):
                self._access(tx, doc_id, user_uid)
                versions = []
                for row in tx.run("""MATCH (d:Document {uid:$d})-[:HAS_PIPELINE_VERSION]->(v)
                  RETURN v.uid AS version_id,v.run_id AS run_id,v.status AS status,v.stage AS stage,
                  v.created_at AS created_at,v.payload AS payload,d.active_pipeline_version = v.uid AS active
                  ORDER BY v.created_at DESC""", d=doc_id):
                    version = dict(row)
                    payload = json.loads(version.pop("payload") or "{}")
                    version["timing"] = payload.get("timing", {})
                    versions.append(version)
                return versions
            return session.execute_read(read)
    def apply(self, doc_id, version_id, user_uid, source_hash):
        with self.driver.session() as session:
            session.execute_write(self._apply, doc_id, version_id, user_uid, source_hash)
    def _apply(self, tx, doc_id, version_id, user_uid, source_hash):
        self._access(tx, doc_id, user_uid)
        # A write lock serializes concurrent activations for this article.
        tx.run("MATCH (d:Document {uid:$d}) SET d.pipeline_lock=coalesce(d.pipeline_lock,0)+1",
               d=doc_id).consume()
        row = tx.run("""MATCH (d:Document {uid:$d})-[:HAS_PIPELINE_VERSION]->(v:ArticlePipelineRun {uid:$v})
          MATCH (v)-[:SOURCE]->(r) RETURN v.status AS status,r.sha256 AS sha,d.active_pipeline_version AS active,
          coalesce(d.current_source_hash,$source_hash) AS current_hash""",
                     d=doc_id, v=version_id, source_hash=source_hash).single()
        require(row and row["status"] in ("completed", "completed_with_warnings"),
                "Version is not ready")
        require(row["sha"] == source_hash and row["current_hash"] == source_hash,
                "Source changed; extraction must be rerun")
        if row["active"] == version_id:
            return
        # Preserve current editor data, including legacy/manual edits, before switching relationships.
        tx.run("""MATCH (d:Document {uid:$d})
          CREATE (h:ArticleEditorSnapshot {created_at:datetime()}) CREATE (d)-[:HAS_EDITOR_SNAPSHOT]->(h)
          WITH d,h OPTIONAL MATCH (d)-[:HAS_BLOCK]->(b)
          FOREACH (x IN CASE WHEN b IS NULL THEN [] ELSE [b] END | CREATE (h)-[:HAS_BLOCK]->(x))""",
               d=doc_id).consume()
        tx.run("""MATCH (d:Document {uid:$d})-[r:HAS_BLOCK]->() DELETE r""", d=doc_id).consume()
        tx.run("""MATCH (d:Document {uid:$d})-[:HAS_PIPELINE_VERSION]->(v:ArticlePipelineRun {uid:$v})
          SET d.active_pipeline_version=$v
          WITH d,v MATCH (v)-[:HAS_BLOCK]->(b) MERGE (d)-[:HAS_BLOCK]->(b)""",
               d=doc_id, v=version_id).consume()
