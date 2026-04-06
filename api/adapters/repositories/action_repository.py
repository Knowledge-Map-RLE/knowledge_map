"""
Layer: Interface Adapters — Repository
Package: adapters.repositories.action_repository
Responsibility: neomodel/Cypher-реализация ActionRepositoryProtocol.

Allowed imports: neomodel, infrastructure.neo4j.orm_models, domain.exceptions
Forbidden imports: fastapi, web
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from neomodel import db

from application.action_chains.aggregate_shared_actions import compute_norm_key

logger = logging.getLogger(__name__)


class ActionRepository:
    """
    Cypher-реализация репозитория действий (Action nodes + LEADS_TO edges).
    Удовлетворяет ActionRepositoryProtocol (structural subtyping).
    """

    def save_actions(self, actions: List[Dict[str, Any]], doc_id: str) -> int:
        if not actions:
            return 0

        # Проставляем norm_key для каждого действия перед сохранением
        for action in actions:
            action["norm_key"] = compute_norm_key(
                action.get("verb") or "",
                action.get("subject"),
                action.get("object"),
            )

        query = """
        UNWIND $rows AS row
        MERGE (a:Action {doc_id: row.doc_id, full_phrase: row.full_phrase})
        ON CREATE SET
            a.uid             = row.uid,
            a.verb            = row.verb,
            a.verb_text       = row.verb_text,
            a.subject         = row.subject,
            a.object          = row.object,
            a.sentence_text   = row.sentence_text,
            a.char_start      = row.char_start,
            a.char_end        = row.char_end,
            a.annotation_uid  = row.annotation_uid,
            a.action_class    = row.action_class,
            a.norm_key        = row.norm_key
        ON MATCH SET
            a.norm_key        = row.norm_key
        RETURN row.uid AS requested_uid, a.uid AS actual_uid
        """
        results, _ = db.cypher_query(query, {"rows": actions})
        # Return mapping: requested_uid -> actual_uid (for dedup remapping in use case)
        uid_remap = {r[0]: r[1] for r in results}
        logger.debug("Saved %d actions for doc %s (%d deduplicated)", len(actions), doc_id, len(actions) - len(set(uid_remap.values())))
        return uid_remap

    def backfill_norm_keys(self) -> int:
        """Проставляет norm_key для Action-нод, у которых его ещё нет.
        Используется один раз для миграции существующих данных."""
        # Загружаем все ноды без norm_key
        results, _ = db.cypher_query(
            "MATCH (a:Action) WHERE a.norm_key IS NULL "
            "RETURN a.uid AS uid, a.verb AS verb, a.subject AS subject, a.object AS object",
        )
        if not results:
            return 0

        rows = [
            {
                "uid": r[0],
                "norm_key": compute_norm_key(r[1] or "", r[2], r[3]),
            }
            for r in results
        ]
        db.cypher_query(
            "UNWIND $rows AS row MATCH (a:Action {uid: row.uid}) SET a.norm_key = row.norm_key",
            {"rows": rows},
        )
        logger.info("Backfilled norm_key for %d Action nodes", len(rows))
        return len(rows)

    def get_aggregated_graph(self) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Возвращает агрегированный граф: одна нода на norm_key (doc_count = кол-во статей)
        и рёбра LEADS_TO между представителями разных групп."""
        # Один представитель на norm_key + doc_count
        nodes_result, _ = db.cypher_query(
            """
            MATCH (a:Action)
            WHERE a.norm_key IS NOT NULL
            WITH a.norm_key AS nk, collect(a) AS group
            WITH group[0] AS rep, size(group) AS doc_count,
                 [g IN group | g.doc_id] AS doc_ids
            RETURN rep.uid AS uid,
                   rep.verb AS verb,
                   rep.verb_text AS verb_text,
                   rep.subject AS subject,
                   rep.object AS object,
                   rep.action_class AS action_class,
                   rep.norm_key AS norm_key,
                   doc_count,
                   doc_ids
            """
        )
        if not nodes_result:
            return [], []

        nodes = [
            {
                "uid": r[0],
                "verb": r[1] or "",
                "verb_text": r[2] or "",
                "subject": r[3] or "",
                "object": r[4] or "",
                "action_class": r[5] or "action",
                "norm_key": r[6],
                "doc_count": r[7] or 1,
                "doc_ids": list(r[8]) if r[8] else [],
            }
            for r in nodes_result
        ]

        # Маппинг norm_key → uid представителя
        key_to_uid = {n["norm_key"]: n["uid"] for n in nodes}

        # Рёбра между представителями разных групп
        edges_result, _ = db.cypher_query(
            """
            MATCH (a1:Action)-[r:LEADS_TO {status: 'confirmed'}]->(a2:Action)
            WHERE a1.norm_key IS NOT NULL AND a2.norm_key IS NOT NULL
              AND a1.norm_key <> a2.norm_key
            WITH a1.norm_key AS src_key, a2.norm_key AS tgt_key,
                 count(r) AS edge_count, avg(r.confidence) AS avg_conf,
                 collect(DISTINCT r.relation_subtype)[0] AS relation_subtype
            RETURN src_key, tgt_key, edge_count, avg_conf, relation_subtype
            """
        )

        edges = []
        for r in edges_result:
            src_uid = key_to_uid.get(r[0])
            tgt_uid = key_to_uid.get(r[1])
            if src_uid and tgt_uid:
                edges.append({
                    "src_uid": src_uid,
                    "tgt_uid": tgt_uid,
                    "count": r[2] or 1,
                    "confidence": r[3] or 0.0,
                    "relation_subtype": r[4] or "",
                })

        return nodes, edges

    def save_leads_to(
        self,
        action_edges: List[Dict[str, Any]],
        goal_edges: List[Dict[str, Any]],
        doc_id: str,
    ) -> int:
        total = 0

        if action_edges:
            query = """
            UNWIND $edges AS e
            MATCH (s:Action {uid: e.src_uid}), (t:Action {uid: e.tgt_uid})
            MERGE (s)-[r:LEADS_TO {doc_id: e.doc_id, relation_subtype: e.relation_subtype}]->(t)
            ON CREATE SET
                r.confidence = e.confidence,
                r.evidence   = e.evidence,
                r.status     = e.status
            """
            db.cypher_query(query, {"edges": action_edges})
            total += len(action_edges)
            logger.debug("Saved %d Action→Action edges for doc %s", len(action_edges), doc_id)

        if goal_edges:
            query = """
            UNWIND $edges AS e
            MATCH (s:Action {uid: e.src_uid}), (t:MarkdownAnnotation {uid: e.tgt_uid})
            MERGE (s)-[r:LEADS_TO {doc_id: e.doc_id, relation_subtype: 'PART_OF_GOAL'}]->(t)
            ON CREATE SET
                r.confidence = 1.0,
                r.status     = 'confirmed'
            """
            db.cypher_query(query, {"edges": goal_edges})
            total += len(goal_edges)
            logger.debug("Saved %d Action→Goal edges for doc %s", len(goal_edges), doc_id)

        return total

    def get_for_document(self, doc_id: str) -> List[Dict[str, Any]]:
        query = """
        MATCH (a:Action {doc_id: $doc_id})
        RETURN a.uid AS uid, a.verb AS verb, a.verb_text AS verb_text,
               a.subject AS subject, a.object AS object,
               a.sentence_text AS sentence_text,
               a.char_start AS char_start, a.char_end AS char_end,
               a.annotation_uid AS annotation_uid,
               a.action_class AS action_class
        """
        results, _ = db.cypher_query(query, {"doc_id": doc_id})
        return [dict(zip(
            ["uid", "verb", "verb_text", "subject", "object",
             "sentence_text", "char_start", "char_end", "annotation_uid", "action_class"],
            row
        )) for row in results]

    def get_pending_for_document(self, doc_id: str) -> List[Dict[str, Any]]:
        query = """
        MATCH (s:Action {doc_id: $doc_id})-[r:LEADS_TO {status: 'pending'}]->(t:Action)
        RETURN
            s.uid            AS src_uid,
            s.verb_text      AS src_text,
            s.full_phrase    AS src_phrase,
            s.sentence_text  AS src_sentence,
            s.action_class   AS src_class,
            t.uid            AS tgt_uid,
            t.verb_text      AS tgt_text,
            t.full_phrase    AS tgt_phrase,
            t.sentence_text  AS tgt_sentence,
            t.action_class   AS tgt_class,
            r.relation_subtype AS relation_subtype,
            r.confidence     AS confidence,
            r.evidence       AS evidence
        ORDER BY r.confidence DESC
        """
        results, _ = db.cypher_query(query, {"doc_id": doc_id})
        cols = ["src_uid", "src_text", "src_phrase", "src_sentence", "src_class",
                "tgt_uid", "tgt_text", "tgt_phrase", "tgt_sentence", "tgt_class",
                "relation_subtype", "confidence", "evidence"]
        return [dict(zip(cols, row)) for row in results]

    def get_neighbor_ids(self, uid: str) -> List[str]:
        """Возвращает uid всех Action-узлов, достижимых напрямую из данного."""
        query = """
        MATCH (s:Action {uid: $uid})-[:LEADS_TO]->(t:Action)
        RETURN t.uid AS uid
        """
        results, _ = db.cypher_query(query, {"uid": uid})
        return [row[0] for row in results]

    def get_all_edges_for_document(self, doc_id: str) -> List[tuple[str, str]]:
        """Возвращает все LEADS_TO рёбра документа как список (src_uid, tgt_uid).
        Используется для in-memory DAG-проверки без повторных Neo4j-запросов."""
        query = """
        MATCH (s:Action {doc_id: $doc_id})-[:LEADS_TO]->(t:Action {doc_id: $doc_id})
        RETURN s.uid AS src, t.uid AS tgt
        """
        results, _ = db.cypher_query(query, {"doc_id": doc_id})
        return [(row[0], row[1]) for row in results]

    def update_edge_status(
        self, src_uid: str, tgt_uid: str, relation_subtype: str, status: str
    ) -> None:
        query = """
        MATCH (s:Action {uid: $src_uid})-[r:LEADS_TO {relation_subtype: $subtype}]->(t:Action {uid: $tgt_uid})
        SET r.status = $status
        """
        db.cypher_query(query, {
            "src_uid": src_uid,
            "tgt_uid": tgt_uid,
            "subtype": relation_subtype,
            "status": status,
        })

    def get_confirmed_graph(self, doc_id: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Возвращает все Action-узлы и подтверждённые LEADS_TO-рёбра для документа."""
        nodes_result, _ = db.cypher_query(
            "MATCH (a:Action {doc_id: $doc_id}) "
            "RETURN a.uid, a.verb, a.verb_text, a.object, a.full_phrase, a.sentence_text, a.action_class",
            {"doc_id": doc_id},
        )
        edges_result, _ = db.cypher_query(
            "MATCH (s:Action {doc_id: $doc_id})-[r:LEADS_TO {status: 'confirmed'}]->(t:Action {doc_id: $doc_id}) "
            "RETURN s.uid, t.uid, r.relation_subtype, r.confidence",
            {"doc_id": doc_id},
        )
        nodes = [
            {
                "uid": r[0], "verb": r[1] or "", "verb_text": r[2] or "",
                "object": r[3] or "", "full_phrase": r[4] or "",
                "sentence_text": r[5] or "", "action_class": r[6] or "action",
            }
            for r in nodes_result
        ]
        edges = [
            {"src_uid": r[0], "tgt_uid": r[1], "relation_subtype": r[2] or "", "confidence": r[3] or 0.0}
            for r in edges_result
        ]
        return nodes, edges

    def save_syntactic_deps(
        self,
        syntactic_edges: List[Dict[str, Any]],
        doc_id: str,
    ) -> int:
        """Сохранить синтаксические зависимости как SYNTACTIC_DEP рёбра (не LEADS_TO)."""
        if not syntactic_edges:
            return 0
        query = """
        UNWIND $edges AS e
        MATCH (s:Action {uid: e.src_uid}), (t:Action {uid: e.tgt_uid})
        MERGE (s)-[r:SYNTACTIC_DEP {doc_id: e.doc_id, dep_label: e.dep_label}]->(t)
        ON CREATE SET
            r.confidence = e.confidence
        """
        db.cypher_query(query, {"edges": syntactic_edges})
        logger.debug("Saved %d SYNTACTIC_DEP edges for doc %s", len(syntactic_edges), doc_id)
        return len(syntactic_edges)

    def delete_for_document(self, doc_id: str) -> int:
        count_query = "MATCH (a:Action {doc_id: $doc_id}) RETURN count(a) AS cnt"
        results, _ = db.cypher_query(count_query, {"doc_id": doc_id})
        count = results[0][0] if results else 0

        db.cypher_query(
            "MATCH (a:Action {doc_id: $doc_id}) DETACH DELETE a",
            {"doc_id": doc_id},
        )
        logger.debug("Deleted %d actions for doc %s", count, doc_id)
        return count
