"""
Layer: Interface Adapters — Repository
Package: adapters.repositories.action_repository
Responsibility: neomodel/Cypher-реализация ActionRepositoryProtocol.

Allowed imports: neomodel, infrastructure.neo4j.orm_models, domain.exceptions
Forbidden imports: fastapi, web
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from neomodel import db

from application.action_chains.aggregate_shared_actions import compute_norm_key

logger = logging.getLogger(__name__)


def _render_label_from_spans(spans: list[dict], subject_idx: int, verb_idx: int, object_idx: int) -> str:
    """Рендерит compact label из spans."""
    parts = []
    for i, span in enumerate(spans):
        if i == subject_idx and span.get("span_type") == "SUBJECT":
            parts.append(span["text"])
        elif i == verb_idx and span.get("span_type") == "VERB":
            parts.append(span["text"])
        elif i == object_idx and span.get("span_type") == "OBJECT":
            parts.append(span["text"])
    if not parts:
        # Fallback: собираем из span_type
        subject_text = next((s["text"] for s in spans if s["span_type"] == "SUBJECT"), "")
        verb_text = next((s["text"] for s in spans if s["span_type"] == "VERB"), "")
        object_text = next((s["text"] for s in spans if s["span_type"] == "OBJECT"), "")
        parts = [p for p in [subject_text, verb_text, object_text] if p]
    return " ".join(parts) if parts else ""


class ActionRepository:
    """
    Cypher-реализация репозитория действий (Action nodes + LEADS_TO edges).
    Удовлетворяет ActionRepositoryProtocol (structural subtyping).
    """

    def save_actions(self, actions: List[Dict[str, Any]], doc_id: str) -> int:
        if not actions:
            return 0

        # Проставляем norm_key и сериализуем лингвистические структуры
        for action in actions:
            tokens = action.get("tokens") or []
            spans = action.get("spans") or []
            verb_span_idx = action.get("verb_span_idx", -1)
            subject_span_idx = action.get("subject_span_idx", -1)
            object_span_idx = action.get("object_span_idx", -1)

            # Получаем span-словари для norm_key
            verb_span = spans[verb_span_idx] if 0 <= verb_span_idx < len(spans) else None
            subject_span = spans[subject_span_idx] if 0 <= subject_span_idx < len(spans) else None
            object_span = spans[object_span_idx] if 0 <= object_span_idx < len(spans) else None

            action["norm_key"] = compute_norm_key(
                action.get("verb") or "",
                action.get("subject"),
                action.get("object"),
                verb_span=verb_span,
                subject_span=subject_span,
                object_span=object_span,
            )

            # Сериализуем в JSON
            action["tokens_json"] = json.dumps(tokens, ensure_ascii=False)
            action["spans_json"] = json.dumps(spans, ensure_ascii=False)

            # Рендерим label_text
            action["label_text"] = _render_label_from_spans(
                spans, subject_span_idx, verb_span_idx, object_span_idx
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
            a.norm_key        = row.norm_key,
            a.tokens_json     = row.tokens_json,
            a.spans_json      = row.spans_json,
            a.label_text      = row.label_text,
            a.verb_span_idx   = row.verb_span_idx,
            a.subject_span_idx = row.subject_span_idx,
            a.object_span_idx  = row.object_span_idx
        ON MATCH SET
            a.norm_key        = row.norm_key,
            a.tokens_json     = row.tokens_json,
            a.spans_json      = row.spans_json,
            a.label_text      = row.label_text,
            a.verb_span_idx   = row.verb_span_idx,
            a.subject_span_idx = row.subject_span_idx,
            a.object_span_idx  = row.object_span_idx
        RETURN row.uid AS requested_uid, a.uid AS actual_uid
        """
        results, _ = db.cypher_query(query, {"rows": actions})
        # Return mapping: requested_uid -> actual_uid (for dedup remapping in use case)
        uid_remap = {r[0]: r[1] for r in results}
        logger.debug("Saved %d actions for doc %s (%d deduplicated)", len(actions), doc_id, len(actions) - len(set(uid_remap.values())))

        # Сохраняем LexicalUnit ноды + рёбра DEPENDS_ON
        self._save_lexical_units(actions, doc_id)

        return uid_remap

    def _save_lexical_units(self, actions: List[Dict[str, Any]], doc_id: str) -> int:
        """Сохраняет LexicalUnit ноды и рёбра DEPENDS_ON для пакета actions."""
        all_lu_rows: List[Dict[str, Any]] = []
        all_dep_rows: List[Dict[str, Any]] = []

        for action in actions:
            action_uid = action.get("uid")
            tokens = action.get("tokens") or []
            if not tokens:
                continue

            # Маппинг token.id → LexicalUnit uid
            token_id_to_lu_uid: dict[int, str] = {}

            for token in tokens:
                lu_uid = f"lu_{doc_id}_{action_uid}_{token['id']}"
                token_id_to_lu_uid[token["id"]] = lu_uid

                all_lu_rows.append({
                    "uid": lu_uid,
                    "text": token["text"],
                    "lemma": token["lemma"],
                    "pos": token["pos"],
                    "pos_fine": token.get("pos_fine", ""),
                    "dep": token.get("dep", ""),
                    "is_stop": token.get("is_stop", False),
                    "is_punct": token.get("is_punct", False),
                    "doc_id": doc_id,
                    "action_uid": action_uid,
                    "token_index": token["id"],
                })

            # Рёбра DEPENDS_ON: head_id → token.id
            for token in tokens:
                head_id = token.get("head_id", -1)
                if head_id < 0:
                    continue
                src_uid = token_id_to_lu_uid.get(head_id)
                tgt_uid = token_id_to_lu_uid.get(token["id"])
                if src_uid and tgt_uid and src_uid != tgt_uid:
                    all_dep_rows.append({
                        "src_uid": src_uid,
                        "tgt_uid": tgt_uid,
                        "dep_label": token.get("dep", ""),
                        "doc_id": doc_id,
                    })

        if not all_lu_rows:
            return 0

        # Сохраняем LexicalUnit ноды
        lu_query = """
        UNWIND $rows AS row
        MERGE (lu:LexicalUnit {uid: row.uid})
        ON CREATE SET
            lu.text     = row.text,
            lu.lemma    = row.lemma,
            lu.pos      = row.pos,
            lu.pos_fine = row.pos_fine,
            lu.dep      = row.dep,
            lu.is_stop  = row.is_stop,
            lu.is_punct = row.is_punct,
            lu.doc_id   = row.doc_id
        ON MATCH SET
            lu.text     = row.text,
            lu.lemma    = row.lemma,
            lu.pos      = row.pos,
            lu.dep      = row.dep
        WITH lu, row
        MATCH (a:Action {uid: row.action_uid})
        MERGE (lu)-[r:PART_OF {doc_id: row.doc_id}]->(a)
        ON CREATE SET r.token_index = row.token_index
        """
        db.cypher_query(lu_query, {"rows": all_lu_rows})

        # Сохраняем рёбра DEPENDS_ON
        if all_dep_rows:
            dep_query = """
            UNWIND $rows AS row
            MATCH (src:LexicalUnit {uid: row.src_uid}), (tgt:LexicalUnit {uid: row.tgt_uid})
            MERGE (src)-[r:DEPENDS_ON {doc_id: row.doc_id, dep_label: row.dep_label}]->(tgt)
            """
            db.cypher_query(dep_query, {"rows": all_dep_rows})

        logger.debug(
            "Saved %d LexicalUnit nodes and %d DEPENDS_ON edges for doc %s",
            len(all_lu_rows), len(all_dep_rows), doc_id,
        )
        return len(all_lu_rows)

    def backfill_norm_keys(self, force: bool = False) -> int:
        """Проставляет norm_key для Action-нод.

        Args:
            force: Если True — перевычисляет norm_key для ВСЕХ нод (нужно после
                   обновления словарей синонимов в compute_norm_key).
                   Если False — только для нод с norm_key IS NULL (первичная миграция).
        """
        if force:
            results, _ = db.cypher_query(
                "MATCH (a:Action) "
                "RETURN a.uid AS uid, a.verb AS verb, a.subject AS subject, a.object AS object",
            )
        else:
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
        # Батчами по 5000, чтобы не перегружать память Neo4j
        batch_size = 5000
        for i in range(0, len(rows), batch_size):
            db.cypher_query(
                "UNWIND $rows AS row MATCH (a:Action {uid: row.uid}) SET a.norm_key = row.norm_key",
                {"rows": rows[i : i + batch_size]},
            )
        mode = "force-all" if force else "null-only"
        logger.info("Backfilled norm_key (%s) for %d Action nodes", mode, len(rows))
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
                   rep.label_text AS label_text,
                   rep.tokens_json AS tokens_json,
                   rep.spans_json AS spans_json,
                   rep.verb_span_idx AS verb_span_idx,
                   rep.subject_span_idx AS subject_span_idx,
                   rep.object_span_idx AS object_span_idx,
                   doc_count,
                   doc_ids
            """
        )
        if not nodes_result:
            return [], []

        nodes = []
        for r in nodes_result:
            label_text = r[7] or ""
            tokens_json = r[8] or ""
            spans_json = r[9] or ""

            # Если label_text пустой, рендерим из spans
            if not label_text and spans_json:
                try:
                    spans = json.loads(spans_json)
                    label_text = _render_label_from_spans(
                        spans,
                        r[10] if r[10] else -1,  # subject_span_idx
                        r[11] if r[11] else -1,  # verb_span_idx (note: ordering in query)
                        r[12] if r[12] else -1,  # object_span_idx
                    )
                except (json.JSONDecodeError, IndexError):
                    pass

            if not label_text:
                # Fallback: legacy format
                label_text = f"{r[3] or ''} {r[1] or ''} {r[4] or ''}".strip()

            nodes.append({
                "uid": r[0],
                "verb": r[1] or "",
                "verb_text": r[2] or "",
                "subject": r[3] or "",
                "object": r[4] or "",
                "action_class": r[5] or "action",
                "norm_key": r[6],
                "label_text": label_text,
                "tokens_json": tokens_json,
                "spans_json": spans_json,
                "doc_count": r[13] or 1,
                "doc_ids": list(r[14]) if r[14] else [],
            })

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
               a.action_class AS action_class,
               a.label_text AS label_text,
               a.tokens_json AS tokens_json,
               a.spans_json AS spans_json,
               a.verb_span_idx AS verb_span_idx,
               a.subject_span_idx AS subject_span_idx,
               a.object_span_idx AS object_span_idx
        """
        results, _ = db.cypher_query(query, {"doc_id": doc_id})
        return [dict(zip(
            ["uid", "verb", "verb_text", "subject", "object",
             "sentence_text", "char_start", "char_end", "annotation_uid", "action_class",
             "label_text", "tokens_json", "spans_json",
             "verb_span_idx", "subject_span_idx", "object_span_idx"],
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
            "RETURN a.uid, a.verb, a.verb_text, a.object, a.full_phrase, a.sentence_text, a.action_class, "
            "a.label_text, a.tokens_json, a.spans_json, "
            "a.verb_span_idx, a.subject_span_idx, a.object_span_idx",
            {"doc_id": doc_id},
        )
        edges_result, _ = db.cypher_query(
            "MATCH (s:Action {doc_id: $doc_id})-[r:LEADS_TO {status: 'confirmed'}]->(t:Action {doc_id: $doc_id}) "
            "RETURN s.uid, t.uid, r.relation_subtype, r.confidence",
            {"doc_id": doc_id},
        )
        nodes = []
        for r in nodes_result:
            label_text = r[7] or ""
            # Fallback если label_text не заполнен
            if not label_text:
                label_text = f"{r[2] or ''} {r[3] or ''}".strip()

            nodes.append({
                "uid": r[0], "verb": r[1] or "", "verb_text": r[2] or "",
                "object": r[3] or "", "full_phrase": r[4] or "",
                "sentence_text": r[5] or "", "action_class": r[6] or "action",
                "label_text": label_text,
                "tokens_json": r[8] or "",
                "spans_json": r[9] or "",
                "verb_span_idx": r[10],
                "subject_span_idx": r[11],
                "object_span_idx": r[12],
            })
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
        # Удаляем также LexicalUnit ноды документа
        db.cypher_query(
            "MATCH (lu:LexicalUnit {doc_id: $doc_id}) DETACH DELETE lu",
            {"doc_id": doc_id},
        )
        logger.debug("Deleted %d actions and lexical units for doc %s", count, doc_id)
        return count

    # =========================================================================
    # Лингвистический поиск по графу
    # =========================================================================

    def search_lexical_units(
        self,
        lemma: str | None = None,
        pos: str | None = None,
        pos_fine: str | None = None,
        dep: str | None = None,
        doc_id: str | None = None,
        exclude_stops: bool = True,
        exclude_punct: bool = True,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Поиск LexicalUnit по лингвистическим атрибутам.

        Примеры:
            - Все глаголы с леммой "inhibit": search_lexical_units(lemma="inhibit", pos="VERB")
            - Все существительные в позиции dobj: search_lexical_units(pos="NOUN", dep="dobj")
            - Все модификаторы (amod) в документе: search_lexical_units(dep="amod", doc_id="...")
        """
        conditions = []
        params: dict[str, Any] = {"limit": limit}

        if lemma:
            conditions.append("lu.lemma = $lemma")
            params["lemma"] = lemma.lower()
        if pos:
            conditions.append("lu.pos = $pos")
            params["pos"] = pos
        if pos_fine:
            conditions.append("lu.pos_fine = $pos_fine")
            params["pos_fine"] = pos_fine
        if dep:
            conditions.append("lu.dep = $dep")
            params["dep"] = dep
        if doc_id:
            conditions.append("lu.doc_id = $doc_id")
            params["doc_id"] = doc_id
        if exclude_stops:
            conditions.append("lu.is_stop = false")
        if exclude_punct:
            conditions.append("lu.is_punct = false")

        where = " AND ".join(conditions) if conditions else "true"

        query = f"""
        MATCH (lu:LexicalUnit)
        WHERE {where}
        OPTIONAL MATCH (lu)-[:PART_OF]->(a:Action)
        RETURN lu.uid AS uid, lu.text AS text, lu.lemma AS lemma,
               lu.pos AS pos, lu.pos_fine AS pos_fine, lu.dep AS dep,
               lu.doc_id AS doc_id,
               a.uid AS action_uid, a.label_text AS action_label,
               a.sentence_text AS sentence_text
        ORDER BY lu.doc_id, lu.text
        LIMIT $limit
        """
        results, _ = db.cypher_query(query, params)
        return [dict(zip(
            ["uid", "text", "lemma", "pos", "pos_fine", "dep", "doc_id",
             "action_uid", "action_label", "sentence_text"],
            row,
        )) for row in results]

    def find_dependency_patterns(
        self,
        head_lemma: str | None = None,
        head_pos: str | None = None,
        dep_label: str | None = None,
        dep_lemma: str | None = None,
        dep_pos: str | None = None,
        doc_id: str | None = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        Поиск синтаксических паттернов: (head)-[DEPENDS_ON]->(dependent).

        Примеры:
            - Все nsubj зависимости от глагола "inhibit":
              find_dependency_patterns(head_lemma="inhibit", dep_label="nsubj")
            - Все dobj где объект — существительное "mtor":
              find_dependency_patterns(head_pos="VERB", dep_label="dobj", dep_lemma="mtor")
            - Все amod зависимости в документе:
              find_dependency_patterns(dep_label="amod", doc_id="...")
        """
        conditions = []
        params: dict[str, Any] = {"limit": limit}

        if head_lemma:
            conditions.append("head.lemma = $head_lemma")
            params["head_lemma"] = head_lemma.lower()
        if head_pos:
            conditions.append("head.pos = $head_pos")
            params["head_pos"] = head_pos
        if dep_label:
            conditions.append("r.dep_label = $dep_label")
            params["dep_label"] = dep_label
        if dep_lemma:
            conditions.append("dep.lemma = $dep_lemma")
            params["dep_lemma"] = dep_lemma.lower()
        if dep_pos:
            conditions.append("dep.pos = $dep_pos")
            params["dep_pos"] = dep_pos
        if doc_id:
            conditions.append("head.doc_id = $doc_id")
            params["doc_id"] = doc_id

        where = " AND ".join(conditions) if conditions else "true"

        query = f"""
        MATCH (head:LexicalUnit)-[r:DEPENDS_ON]->(dep:LexicalUnit)
        WHERE {where}
        OPTIONAL MATCH (head)-[:PART_OF]->(a:Action)
        RETURN head.text AS head_text, head.lemma AS head_lemma,
               head.pos AS head_pos, head.dep AS head_dep,
               r.dep_label AS dep_label,
               dep.text AS dep_text, dep.lemma AS dep_lemma,
               dep.pos AS dep_pos,
               head.doc_id AS doc_id,
               a.label_text AS action_label, a.sentence_text AS sentence_text
        ORDER BY head.doc_id, head.text
        LIMIT $limit
        """
        results, _ = db.cypher_query(query, params)
        return [dict(zip(
            ["head_text", "head_lemma", "head_pos", "head_dep",
             "dep_label", "dep_text", "dep_lemma", "dep_pos",
             "doc_id", "action_label", "sentence_text"],
            row,
        )) for row in results]

    def find_shared_patterns(
        self,
        lemma: str,
        pos: str | None = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Находит все вхождения леммы в графе и показывает контекст.

        Для каждого LexicalUnit с данной леммой возвращает:
        - Головные токены (от которых зависит)
        - Зависимые токены (которые зависят от него)
        - Action, частью которого является
        """
        conditions = ["lu.lemma = $lemma"]
        params: dict[str, Any] = {"lemma": lemma.lower(), "limit": limit}
        if pos:
            conditions.append("lu.pos = $pos")
            params["pos"] = pos

        where = " AND ".join(conditions)

        query = f"""
        MATCH (lu:LexicalUnit)
        WHERE {where}
        OPTIONAL MATCH (head:LexicalUnit)-[r_head:DEPENDS_ON]->(lu)
        OPTIONAL MATCH (lu)-[r_dep:DEPENDS_ON]->(dep:LexicalUnit)
        OPTIONAL MATCH (lu)-[:PART_OF]->(a:Action)
        RETURN
            lu.uid AS uid,
            lu.text AS text,
            lu.pos AS pos,
            lu.dep AS dep,
            lu.doc_id AS doc_id,
            head.lemma AS head_lemma,
            head.text AS head_text,
            r_head.dep_label AS head_dep_label,
            dep.lemma AS dep_lemma,
            dep.text AS dep_text,
            r_dep.dep_label AS dep_dep_label,
            a.label_text AS action_label,
            a.sentence_text AS sentence_text
        ORDER BY lu.doc_id
        LIMIT $limit
        """
        results, _ = db.cypher_query(query, params)
        return [dict(zip(
            ["uid", "text", "pos", "dep", "doc_id",
             "head_lemma", "head_text", "head_dep_label",
             "dep_lemma", "dep_text", "dep_dep_label",
             "action_label", "sentence_text"],
            row,
        )) for row in results]

    def compare_actions(
        self,
        action_uid_1: str,
        action_uid_2: str,
    ) -> Dict[str, Any]:
        """
        Сравнивает лингвистическую структуру двух Action.

        Возвращает:
        - Токены каждого Action (lemma, pos, dep)
        - Общие леммы
        - Одинаковые dependency паттерны
        """
        query = """
        MATCH (lu:LexicalUnit)-[:PART_OF]->(a:Action {uid: $uid})
        RETURN lu.uid AS uid, lu.text AS text, lu.lemma AS lemma,
               lu.pos AS pos, lu.dep AS dep
        """

        def get_tokens(uid: str) -> list[dict]:
            results, _ = db.cypher_query(query, {"uid": uid})
            return [dict(zip(["uid", "text", "lemma", "pos", "dep"], row)) for row in results]

        tokens_1 = get_tokens(action_uid_1)
        tokens_2 = get_tokens(action_uid_2)

        lemmas_1 = {t["lemma"] for t in tokens_1}
        lemmas_2 = {t["lemma"] for t in tokens_2}

        # Dependency паттерны
        dep_query = """
        MATCH (head:LexicalUnit)-[r:DEPENDS_ON]->(dep:LexicalUnit)
        WHERE head.uid IN $lu_uids OR dep.uid IN $lu_uids
        RETURN head.lemma AS head, r.dep_label AS rel, dep.lemma AS dependent
        """

        def get_dep_patterns(uid: str) -> set[tuple]:
            lu_uids = [t["uid"] for t in get_tokens(uid)]
            if not lu_uids:
                return set()
            results, _ = db.cypher_query(dep_query, {"lu_uids": lu_uids})
            return {(r[0], r[1], r[2]) for r in results}

        patterns_1 = get_dep_patterns(action_uid_1)
        patterns_2 = get_dep_patterns(action_uid_2)

        return {
            "action_1": {
                "uid": action_uid_1,
                "tokens": tokens_1,
                "dep_patterns": list(patterns_1),
            },
            "action_2": {
                "uid": action_uid_2,
                "tokens": tokens_2,
                "dep_patterns": list(patterns_2),
            },
            "common_lemmas": sorted(lemmas_1 & lemmas_2),
            "unique_to_1": sorted(lemmas_1 - lemmas_2),
            "unique_to_2": sorted(lemmas_2 - lemmas_1),
            "common_dep_patterns": sorted(patterns_1 & patterns_2),
            "jaccard_similarity": (
                len(lemmas_1 & lemmas_2) / len(lemmas_1 | lemmas_2)
                if (lemmas_1 | lemmas_2) else 0.0
            ),
        }

    def get_lexical_graph_stats(self, doc_id: str | None = None) -> Dict[str, Any]:
        """Статистика лингвистического графа."""
        where = ""
        params: dict[str, Any] = {}
        if doc_id:
            where = "WHERE lu.doc_id = $doc_id"
            params["doc_id"] = doc_id

        query = f"""
        MATCH (lu:LexicalUnit) {where}
        RETURN
            count(lu) AS total_units,
            count(DISTINCT lu.lemma) AS unique_lemmas,
            count(DISTINCT lu.pos) AS unique_pos,
            count(DISTINCT lu.dep) AS unique_deps
        """
        results, _ = db.cypher_query(query, params)
        stats = dict(zip(["total_units", "unique_lemmas", "unique_pos", "unique_deps"], results[0]))

        # Распределение по POS
        pos_query = f"""
        MATCH (lu:LexicalUnit) {where}
        RETURN lu.pos AS pos, count(lu) AS cnt
        ORDER BY cnt DESC
        """
        pos_results, _ = db.cypher_query(pos_query, params)
        stats["pos_distribution"] = {r[0]: r[1] for r in pos_results}

        # Распределение по dependency
        dep_query = f"""
        MATCH (lu:LexicalUnit) {where}
        WHERE lu.dep <> ''
        RETURN lu.dep AS dep, count(lu) AS cnt
        ORDER BY cnt DESC
        LIMIT 20
        """
        dep_results, _ = db.cypher_query(dep_query, params)
        stats["dep_distribution"] = {r[0]: r[1] for r in dep_results}

        # Рёбра DEPENDS_ON
        edge_query = f"""
        MATCH (:LexicalUnit)-[r:DEPENDS_ON]->(:LexicalUnit)
        {'WHERE r.doc_id = $doc_id' if doc_id else ''}
        RETURN r.dep_label AS rel, count(r) AS cnt
        ORDER BY cnt DESC
        """
        edge_results, _ = db.cypher_query(edge_query, params)
        stats["edge_distribution"] = {r[0]: r[1] for r in edge_results}

        return stats
