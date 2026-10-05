"""Транзакционное хранение двух независимых карт и межпроцессных блокировок."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from neo4j import GraphDatabase

from domain.article_maps import (
    PIPELINES, ArticleMapAccessDenied, ArticleMapBusy, ArticleMapConflict,
    ArticleMapNotFound, fingerprint, new_result, require,
)

log = logging.getLogger(__name__)


class Neo4jArticleMapsRepository:
    def __init__(self, uri=None, user=None, password=None, *, driver=None, lease_seconds=3900):
        self.driver = driver if driver is not None else GraphDatabase.driver(
            uri, auth=(user, password), connection_timeout=10,
        )
        self._owns_driver = driver is None
        self.lease_seconds = lease_seconds

    def close(self):
        if self._owns_driver:
            self.driver.close()

    @staticmethod
    def _access(tx, article_id, user_uid):
        row = tx.run("MATCH (d:Document {uid:$id}) RETURN d.created_by_uid AS owner", id=article_id).single()
        if row is None:
            raise ArticleMapNotFound("Article not found")
        if not user_uid or row["owner"] != user_uid:
            raise ArticleMapAccessDenied("Article access denied")

    def authorize(self, article_id, user_uid):
        with self.driver.session() as session:
            session.execute_read(self._access, article_id, user_uid)

    def ensure_schema(self):
        with self.driver.session() as session:
            session.run("""CREATE CONSTRAINT article_map_slot IF NOT EXISTS
              FOR (m:ArticleMap) REQUIRE (m.article_id,m.pipeline_id) IS UNIQUE""").consume()

    def migrate_legacy_snapshots(self, article_id=None):
        """Переносит старые snapshots один раз, не удаляя исходные данные."""
        if article_id is None:
            with self.driver.session() as session:
                session.run("""CREATE INDEX article_legacy_map_timestamp IF NOT EXISTS
                  FOR (d:Document) ON (d.deterministic_map_rebuilt_at)""").consume()
                session.run("CALL db.awaitIndex('article_legacy_map_timestamp',120)").consume()
            # Штатный snapshot всегда имеет rebuilt_at. Разреженный индекс
            # перечисляет только snapshots, не миллионы остальных документов.
            cursor, checked = "", 0
            while True:
                with self.driver.session() as session:
                    identifiers = [row["id"] for row in session.run("""MATCH (d:Document)
                      USING INDEX d:Document(deterministic_map_rebuilt_at)
                      WHERE d.deterministic_map_rebuilt_at IS NOT NULL AND d.uid > $cursor
                      RETURN d.uid AS id ORDER BY d.uid LIMIT 100""", cursor=cursor)]
                if not identifiers:
                    break
                for identifier in identifiers:
                    self.migrate_legacy_snapshots(identifier)
                checked += len(identifiers)
                cursor = identifiers[-1]
                log.info("article_map migration progress checked=%s", checked)
            log.info("article_map migration completed checked=%s", checked)
            return
        with self.driver.session() as session:
            rows = list(session.run("""MATCH (d:Document {uid:$article})
              WHERE NOT EXISTS { MATCH (d)-[:HAS_ARTICLE_MAP]->(m:ArticleMap {pipeline_id:'structural_rows'})
                                 WHERE m.run_id IS NOT NULL }
              WITH d WHERE d.deterministic_map_payload IS NOT NULL
              RETURN d.uid AS id,d.created_by_uid AS owner,d.deterministic_map_payload AS graph,
                     d.deterministic_map_blocks_fingerprint AS fingerprint,
                     d.deterministic_map_rebuilt_at AS updated_at""", article=article_id))
            for row in rows:
                if not row["owner"]:
                    continue
                graph = json.loads(row["graph"])
                result = new_result(row["id"], "structural_rows", graph,
                                    row["fingerprint"] or fingerprint(graph),
                                    validation={"migration": "legacy_snapshot"})
                if row["updated_at"]:
                    result["updated_at"] = row["updated_at"]
                session.execute_write(self._migrate, result, row["owner"])

    @staticmethod
    def _migrate(tx, result, user_uid):
        Neo4jArticleMapsRepository._access(tx, result["article_id"], user_uid)
        tx.run("""MATCH (d:Document {uid:$article})
          MERGE (m:ArticleMap {article_id:$article,pipeline_id:'structural_rows'})
          MERGE (d)-[:HAS_ARTICLE_MAP]->(m)
          WITH m WHERE m.payload IS NULL
          SET m.payload=$payload,m.updated_at=$now,m.run_id=$run""", article=result["article_id"],
          payload=json.dumps(result, ensure_ascii=False), now=result["updated_at"], run=result["run_id"]).consume()

    def get(self, article_id, pipeline_id, user_uid):
        require(pipeline_id in PIPELINES, "Unknown map pipeline")
        with self.driver.session() as session:
            def read(tx):
                self._access(tx, article_id, user_uid)
                row = tx.run("""MATCH (:Document {uid:$article})-[:HAS_ARTICLE_MAP]->
                  (m:ArticleMap {article_id:$article,pipeline_id:$pipeline}) RETURN m.payload AS payload""",
                  article=article_id, pipeline=pipeline_id).single()
                return json.loads(row["payload"]) if row and row["payload"] else None
            return session.execute_read(read)

    def list_maps(self, article_id, user_uid):
        with self.driver.session() as session:
            def read(tx):
                self._access(tx, article_id, user_uid)
                results = []
                for row in tx.run("""MATCH (:Document {uid:$article})-[:HAS_ARTICLE_MAP]->(m:ArticleMap)
                  WHERE m.payload IS NOT NULL RETURN m.payload AS payload ORDER BY m.pipeline_id""", article=article_id):
                    result = json.loads(row["payload"])
                    results.append({key: result[key] for key in (
                        "pipeline_id", "run_id", "updated_at", "input_fingerprint", "graph_schema_version", "builder_version")}
                        | {"translated_locales": list(result.get("translations", {}))})
                return results
            return session.execute_read(read)

    def acquire(self, article_id, pipeline_id, user_uid, token):
        require(pipeline_id in PIPELINES, "Unknown map pipeline")
        with self.driver.session() as session:
            session.execute_write(self._acquire, article_id, pipeline_id, user_uid, token)

    def _acquire(self, tx, article_id, pipeline_id, user_uid, token):
        self._access(tx, article_id, user_uid)
        # Запись счётчика захватывает блокировку узла до чтения lease.
        row = tx.run("""MATCH (d:Document {uid:$article})
          MERGE (m:ArticleMap {article_id:$article,pipeline_id:$pipeline})
          MERGE (d)-[:HAS_ARTICLE_MAP]->(m)
          SET m.lock_sequence=coalesce(m.lock_sequence,0)+1
          RETURN m.build_token AS token,m.lease_until AS lease""", article=article_id, pipeline=pipeline_id).single()
        now = datetime.now(timezone.utc)
        if row["token"] and row["lease"] and datetime.fromisoformat(row["lease"]) > now:
            raise ArticleMapBusy("This article map pipeline is already running")
        tx.run("""MATCH (m:ArticleMap {article_id:$article,pipeline_id:$pipeline})
          SET m.build_token=$token,m.lease_until=$lease""", article=article_id, pipeline=pipeline_id,
          token=token, lease=(now + timedelta(seconds=self.lease_seconds)).isoformat()).consume()

    def release(self, article_id, pipeline_id, user_uid, token):
        with self.driver.session() as session:
            def release(tx):
                self._access(tx, article_id, user_uid)
                tx.run("""MATCH (m:ArticleMap {article_id:$article,pipeline_id:$pipeline,build_token:$token})
                  REMOVE m.build_token,m.lease_until""", article=article_id, pipeline=pipeline_id, token=token).consume()
            session.execute_write(release)

    def renew(self, article_id, pipeline_id, user_uid, token):
        """Продлевает только собственную действующую блокировку между LLM-группами."""
        require(pipeline_id in PIPELINES, "Unknown map pipeline")
        with self.driver.session() as session:
            def renew(tx):
                self._locked(tx, article_id, pipeline_id, user_uid, token)
                lease = datetime.now(timezone.utc) + timedelta(seconds=self.lease_seconds)
                tx.run("""MATCH (m:ArticleMap {article_id:$article,pipeline_id:$pipeline,build_token:$token})
                  SET m.lease_until=$lease""", article=article_id, pipeline=pipeline_id,
                  token=token, lease=lease.isoformat()).consume()
            session.execute_write(renew)
        log.info("article_map lease_renewed article=%s pipeline=%s", article_id, pipeline_id)

    @staticmethod
    def _locked(tx, article_id, pipeline_id, user_uid, token):
        Neo4jArticleMapsRepository._access(tx, article_id, user_uid)
        row = tx.run("""MATCH (m:ArticleMap {article_id:$article,pipeline_id:$pipeline})
          SET m.lock_sequence=coalesce(m.lock_sequence,0)+1
          RETURN m.build_token AS token,m.lease_until AS lease,m.run_id AS run_id,m.payload AS payload""",
          article=article_id, pipeline=pipeline_id).single()
        if (not row or row["token"] != token or not row["lease"]
                or datetime.fromisoformat(row["lease"]) <= datetime.now(timezone.utc)):
            raise ArticleMapConflict("Map build lock expired or changed")
        return row

    def save(self, result, user_uid, token):
        require(result["pipeline_id"] in PIPELINES, "Unknown map pipeline")
        with self.driver.session() as session:
            def save(tx):
                self._locked(tx, result["article_id"], result["pipeline_id"], user_uid, token)
                tx.run("""MATCH (m:ArticleMap {article_id:$article,pipeline_id:$pipeline})
                  SET m.payload=$payload,m.updated_at=$now,m.run_id=$run""",
                  article=result["article_id"], pipeline=result["pipeline_id"],
                  payload=json.dumps(result, ensure_ascii=False, allow_nan=False),
                  now=result["updated_at"], run=result["run_id"]).consume()
            session.execute_write(save)

    def save_translation(self, article_id, pipeline_id, user_uid, run_id, translation, token):
        with self.driver.session() as session:
            def save(tx):
                row = self._locked(tx, article_id, pipeline_id, user_uid, token)
                if row["run_id"] != run_id:
                    raise ArticleMapConflict("Map changed during translation")
                result = json.loads(row["payload"])
                result.setdefault("translations", {})["ru"] = translation
                tx.run("""MATCH (m:ArticleMap {article_id:$article,pipeline_id:$pipeline}) SET m.payload=$payload""",
                       article=article_id, pipeline=pipeline_id,
                       payload=json.dumps(result, ensure_ascii=False, allow_nan=False)).consume()
            session.execute_write(save)
