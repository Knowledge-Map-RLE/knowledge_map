"""Адресное транзакционное хранение сравнения и постраничного списка пар."""
from __future__ import annotations

import gzip
import base64
import heapq
import json
import logging

from neo4j import unit_of_work

from domain.article_comparison import MODES
from domain.article_maps import require, fingerprint, ArticleMapNotFound, ArticleMapAccessDenied, ArticleMapConflict
from infrastructure.neo4j.article_maps_repository import Neo4jArticleMapsRepository

log = logging.getLogger(__name__)


def encode_pair(pair):
    # Повторяющаяся семантика пар сжимается до записи, чтобы атомарный прогон помещался в лимит Neo4j.
    return gzip.compress(json.dumps(pair, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8"), mtime=0)


def decode_pair(row):
    if row["compressed"] is not None:
        require(row["codec"] == "gzip-json-v1", "Unknown comparison-pair storage codec")
        return json.loads(gzip.decompress(row["compressed"]).decode("utf-8"))
    # Ранее опубликованные сравнения сохраняют свой исходный формат хранения.
    return json.loads(row["payload"])


def encode_groups(pairs):
    groups, identifiers = {}, set()
    for pair in pairs:
        require(pair["pair_id"] not in identifiers, "Duplicate comparison pair")
        identifiers.add(pair["pair_id"])
        groups.setdefault(pair["left_knowledge_id"], []).append(pair)
    return [{"left": left, "count": len(values), "payload": base64.b64encode(gzip.compress(
                json.dumps(sorted(values, key=lambda p: (p["right_article_id"], p["right_knowledge_id"])),
                           ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8"), mtime=0)).decode("ascii")}
            for left, values in sorted(groups.items())]


def decode_group(payload):
    return json.loads(gzip.decompress(base64.b64decode(payload, validate=True)).decode("utf-8"))


class Neo4jArticleComparisonsRepository:
    def __init__(self, maps):
        self.maps = maps
        self.driver = maps.driver

    def ensure_schema(self):
        with self.driver.session() as session:
            for cypher in (
                "CREATE CONSTRAINT article_comparison IF NOT EXISTS FOR (c:ArticleComparison) REQUIRE c.comparison_id IS UNIQUE",
                "CREATE CONSTRAINT article_comparison_pair IF NOT EXISTS FOR (p:ArticleComparisonPair) REQUIRE (p.comparison_id,p.pair_id) IS UNIQUE",
                "CREATE INDEX article_comparison_owner IF NOT EXISTS FOR (c:ArticleComparison) ON (c.user_uid)",
                "CREATE INDEX article_comparison_left IF NOT EXISTS FOR (p:ArticleComparisonPair) ON (p.comparison_id,p.left_knowledge_id)",
                "CREATE CONSTRAINT article_comparison_group IF NOT EXISTS FOR (g:ArticleComparisonGroup) REQUIRE (g.comparison_id,g.left_knowledge_id) IS UNIQUE",
            ):
                session.run(cypher).consume()

    def _access(self, result, user_uid):
        for ref in result["references"]:
            self.maps.authorize(ref["article_id"], user_uid)

    def runs(self, user_uid, offset=0, limit=100):
        require(type(offset) is int and offset >= 0 and type(limit) is int and 1 <= limit <= 200,
                "Invalid run pagination")
        # Перебирается небольшое хранилище запусков; документы находятся адресно по индексу uid.
        with self.driver.session() as session:
            rows = list(session.run("""MATCH (r:ArticleMapRun {pipeline_id:'text_reified'})
                MATCH (d:Document {uid:r.article_id}) WHERE d.created_by_uid=$owner
                RETURN r.payload AS payload,d.title AS title ORDER BY r.updated_at DESC,r.run_id
                SKIP $offset LIMIT $limit""", owner=user_uid, offset=offset, limit=limit))
        runs = []
        for row in rows:
            result = json.loads(row["payload"])
            if result["graph"]["schema_version"] == 6:
                runs.append({"article_id": result["article_id"], "pipeline_id": result["pipeline_id"],
                    "run_id": result["run_id"], "updated_at": result["updated_at"],
                    "title": row["title"] or result["article_id"], "schema_version": 6,
                    "generation": result.get("generation"), "source_sha256": result["source"]["sha256"]})
        return {"runs": runs, "next_offset": offset + limit if len(rows) == limit else None}

    def get(self, comparison_id, user_uid):
        with self.driver.session() as session:
            row = session.run("MATCH (c:ArticleComparison {comparison_id:$id}) RETURN c.payload AS payload,c.user_uid AS owner",
                              id=comparison_id).single()
        if row is None:
            return None
        if row["owner"] != user_uid:
            raise ArticleMapAccessDenied("Comparison access denied")
        result = json.loads(row["payload"])
        self._access(result, user_uid)
        return result

    def list(self, user_uid, article_id=None):
        if article_id is not None:
            self.maps.authorize(article_id, user_uid)
        with self.driver.session() as session:
            rows = list(session.run("""MATCH (c:ArticleComparison {user_uid:$owner})
                WHERE $article IS NULL OR $article IN c.article_ids RETURN c.summary AS summary
                ORDER BY c.created_at DESC""", owner=user_uid, article=article_id))
        results = []
        for row in rows:
            item = json.loads(row["summary"])
            self._access(item, user_uid)
            results.append(item)
        return results

    def save(self, result, user_uid):
        self.ensure_schema()
        base = {k: v for k, v in result.items() if k != "pairs"}
        base["pair_storage"] = "knowledge-chunks-gzip-base64-v1"
        payload = json.dumps(base, ensure_ascii=False, allow_nan=False)
        rows = encode_groups(result["pairs"])
        require(sum(row["count"] for row in rows) == result["analysis"]["pair_count"], "Incomplete comparison pair set")
        log.info("article_comparison storage start id=%s pairs=%s groups=%s encoded_bytes=%s", result["comparison_id"],
                 result["analysis"]["pair_count"], len(rows), sum(len(row["payload"]) for row in rows))
        summary = {k: base[k] for k in ("comparison_id", "created_at", "references", "analysis", "summary", "evaluation")}

        @unit_of_work(timeout=300, metadata={"operation": "save_article_comparison", "comparison_id": result["comparison_id"]})
        def write(tx):
            for ref, binding in zip(result["references"], result["binding"]["map_bindings"], strict=True):
                Neo4jArticleMapsRepository._access(tx, ref["article_id"], user_uid)
                row = tx.run("""MATCH (r:ArticleMapRun {article_id:$article,pipeline_id:$pipeline,run_id:$run})
                    RETURN r.payload AS payload""", article=ref["article_id"], pipeline=ref["pipeline_id"], run=ref["run_id"]).single()
                require(row is not None, "Comparison source run disappeared")
                saved = json.loads(row["payload"])
                require(fingerprint(saved["graph"]) == binding["graph_sha256"] and saved["source"]["sha256"] == binding["source_sha256"],
                        "Comparison input changed before storage")
            row = tx.run("MERGE (c:ArticleComparison {comparison_id:$id}) RETURN c.payload AS payload,c.user_uid AS owner",
                         id=result["comparison_id"]).single()
            if row["payload"] is not None:
                existing = json.loads(row["payload"])
                if row["owner"] != user_uid or existing["binding"] != base["binding"]:
                    raise ArticleMapConflict("Immutable comparison already differs")
                return
            tx.run("""MATCH (c:ArticleComparison {comparison_id:$id}) SET c.payload=$payload,c.user_uid=$owner,
                c.article_ids=$articles,c.created_at=$date,c.summary=$summary""", id=result["comparison_id"], payload=payload,
                owner=user_uid, articles=[r["article_id"] for r in result["references"]], date=result["created_at"],
                summary=json.dumps(summary, ensure_ascii=False)).consume()
            for i in range(0, len(rows), 50):
                tx.run("""UNWIND $rows AS row CREATE (g:ArticleComparisonGroup) SET g.comparison_id=$id,
                    g.left_knowledge_id=row.left,g.pair_count=row.count,g.payload=row.payload,
                    g.codec='knowledge-chunks-gzip-base64-v1'""", id=result["comparison_id"], rows=rows[i:i+50]).consume()
        with self.driver.session() as session:
            session.execute_write(write)
        log.info("article_comparison storage committed id=%s", result["comparison_id"])

    def pairs(self, comparison_id, user_uid, *, mode="hybrid", left_knowledge_id=None, source_article_id=None, right_knowledge_id=None,
              relation=None, offset=0, limit=10):
        require(mode in MODES and type(offset) is int and offset >= 0 and type(limit) is int and 1 <= limit <= 100, "Invalid comparison pagination")
        saved = self.get(comparison_id, user_uid)
        if saved is None:
            raise ArticleMapNotFound("Comparison not found")
        require(saved.get("pair_storage") in (None, "knowledge-chunks-gzip-base64-v1"), "Unknown comparison pair storage")
        if saved.get("pair_storage") == "knowledge-chunks-gzip-base64-v1":
            total = 0
            def filtered():
                nonlocal total
                for pair in self._group_pairs(comparison_id, left_knowledge_id):
                    if ((source_article_id is None or pair["right_article_id"] == source_article_id)
                        and (right_knowledge_id is None or pair["right_knowledge_id"] == right_knowledge_id)
                        and (relation is None or relation in pair["relations"])):
                        total += 1
                        yield pair
            ordered = heapq.nsmallest(offset + limit, filtered(), key=lambda p: (
                -p[f"{mode}_score"], p["right_article_id"], p["right_knowledge_id"], p["left_knowledge_id"]))
            return {"total": total, "offset": offset, "limit": limit, "pairs": ordered[offset:offset + limit]}
        scope = """MATCH (p:ArticleComparisonPair {comparison_id:$id})
            WHERE ($left IS NULL OR p.left_knowledge_id=$left) AND ($source IS NULL OR p.right_article_id=$source)
              AND ($right IS NULL OR p.right_knowledge_id=$right)
              AND ($relation IS NULL OR $relation IN p.relations)"""
        params = {"id": comparison_id, "left": left_knowledge_id, "source": source_article_id, "right": right_knowledge_id, "relation": relation}
        with self.driver.session() as session:
            total = session.run(scope + " RETURN count(p) AS count", **params).single()["count"]
            rows = list(session.run(scope + f" RETURN p.payload AS payload,p.payload_gzip AS compressed,p.payload_codec AS codec ORDER BY p.{mode}_score DESC,p.right_article_id,p.right_knowledge_id SKIP $offset LIMIT $limit",
                                    **params, offset=offset, limit=limit))
        return {"total": total, "offset": offset, "limit": limit, "pairs": [decode_pair(r) for r in rows]}

    def export_pairs(self, comparison_id, user_uid):
        saved = self.get(comparison_id, user_uid)
        if saved is None:
            raise ArticleMapNotFound("Comparison not found")
        require(saved.get("pair_storage") in (None, "knowledge-chunks-gzip-base64-v1"), "Unknown comparison pair storage")
        if saved.get("pair_storage") == "knowledge-chunks-gzip-base64-v1":
            return list(self._group_pairs(comparison_id))
        with self.driver.session() as session:
            return [decode_pair(row) for row in session.run("""MATCH (p:ArticleComparisonPair {comparison_id:$id})
                RETURN p.payload AS payload,p.payload_gzip AS compressed,p.payload_codec AS codec ORDER BY p.left_knowledge_id,p.right_article_id,p.right_knowledge_id""", id=comparison_id)]

    def _group_pairs(self, comparison_id, left_knowledge_id=None):
        # Группы читаются только после проверки владельцев в публичном методе, без загрузки всего набора для одной страницы.
        with self.driver.session() as session:
            scope = "{comparison_id:$id,left_knowledge_id:$left}" if left_knowledge_id is not None else "{comparison_id:$id}"
            rows = session.run("MATCH (g:ArticleComparisonGroup " + scope + ") RETURN g.payload AS payload,g.codec AS codec,g.pair_count AS count ORDER BY g.left_knowledge_id",
                               id=comparison_id, left=left_knowledge_id)
            for row in rows:
                require(row["codec"] == "knowledge-chunks-gzip-base64-v1", "Unknown comparison-group storage codec")
                values = decode_group(row["payload"])
                require(len(values) == row["count"], "Incomplete comparison group")
                yield from values
