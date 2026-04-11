"""
Layer: Interface Adapters — Repository
Package: adapters.repositories.pattern_graph_repository
Responsibility: Оптимизированная Cypher-реализация PatternGraphRepositoryProtocol.

Оптимизации:
  - 2 запроса вместо 5 (ноды + рёбра объединены через OPTIONAL MATCH)
  - Для глобального графа — агрегация по norm_key для Action (группировка дубликатов)
  - Возвращает layout_x/layout_y если есть

Allowed imports: neomodel, typing, logging
Forbidden imports: fastapi, web
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from neomodel import db

logger = logging.getLogger(__name__)


class PatternGraphRepository:
    """Оптимизированная Cypher-реализация PatternGraphRepositoryProtocol."""

    # ------------------------------------------------------------------
    # get_document_linguistic_graph
    # ------------------------------------------------------------------

    def get_document_linguistic_graph(
        self, doc_id: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Возвращает (nodes, edges) лингвистического графа одного документа.
        Один запрос для нод, один для рёбер."""

        # --- Ноды: Actions + LexicalUnits за один запрос ---
        nodes_cypher = """
MATCH (a:Action {doc_id: $doc_id})
RETURN a.uid AS uid, 'Action' AS _type,
       a.verb AS verb, a.verb_text AS verb_text,
       a.subject AS subject, a.object_ AS object,
       a.full_phrase AS full_phrase, a.label_text AS label_text,
       a.sentence_text AS sentence_text, a.doc_id AS doc_id,
       a.action_class AS action_class, a.norm_key AS norm_key,
       a.layout_x AS layout_x, a.layout_y AS layout_y,
       NULL AS text, NULL AS lemma, NULL AS pos, NULL AS pos_fine,
       NULL AS dep, NULL AS is_stop, NULL AS is_punct
UNION ALL
MATCH (lu:LexicalUnit {doc_id: $doc_id})
RETURN lu.uid AS uid, 'LexicalUnit' AS _type,
       NULL AS verb, NULL AS verb_text,
       NULL AS subject, NULL AS object,
       NULL AS full_phrase, NULL AS label_text,
       NULL AS sentence_text, lu.doc_id AS doc_id,
       NULL AS action_class, NULL AS norm_key,
       lu.layout_x AS layout_x, lu.layout_y AS layout_y,
       lu.text AS text, lu.lemma AS lemma, lu.pos AS pos, lu.pos_fine AS pos_fine,
       lu.dep AS dep, lu.is_stop AS is_stop, lu.is_punct AS is_punct
"""
        all_nodes: List[Dict[str, Any]] = []
        result, cols = db.cypher_query(nodes_cypher, {"doc_id": doc_id})
        for row in result:
            all_nodes.append(dict(zip(cols, row)))

        # --- Рёбра: один запрос через UNION ---
        edges_cypher = """
MATCH (src:Action {doc_id: $doc_id})-[r:LEADS_TO]->(tgt:Action {doc_id: $doc_id})
RETURN src.uid AS src_uid, tgt.uid AS tgt_uid,
       r.relation_subtype AS relation_subtype, r.confidence AS confidence,
       r.status AS status, NULL AS dep_label, NULL AS token_index,
       'LEADS_TO' AS edge_type
UNION ALL
MATCH (src:LexicalUnit {doc_id: $doc_id})-[r:DEPENDS_ON]->(tgt:LexicalUnit {doc_id: $doc_id})
RETURN src.uid AS src_uid, tgt.uid AS tgt_uid,
       NULL AS relation_subtype, NULL AS confidence, NULL AS status,
       r.dep_label AS dep_label, NULL AS token_index,
       'DEPENDS_ON' AS edge_type
UNION ALL
MATCH (lu:LexicalUnit {doc_id: $doc_id})-[r:PART_OF]->(a:Action {doc_id: $doc_id})
RETURN lu.uid AS src_uid, a.uid AS tgt_uid,
       NULL AS relation_subtype, NULL AS confidence, NULL AS status,
       NULL AS dep_label, r.token_index AS token_index,
       'PART_OF' AS edge_type
"""
        all_edges: List[Dict[str, Any]] = []
        result, cols = db.cypher_query(edges_cypher, {"doc_id": doc_id})
        for row in result:
            all_edges.append(dict(zip(cols, row)))

        logger.info(
            f"[PatternGraphRepository] doc={doc_id[:8]} "
            f"nodes={len(all_nodes)} edges={len(all_edges)}"
        )
        return all_nodes, all_edges

    # ------------------------------------------------------------------
    # get_global_linguistic_graph
    # ------------------------------------------------------------------

    def get_global_linguistic_graph(
        self,
        lexical_limit: int = 1000,
        action_limit: int = 3000,
        edge_limit: int = 3000,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Возвращает (nodes, edges) глобального графа.

        Actions: ограничены action_limit, выбираются по doc_count (частота).
        LexicalUnit: ограничены lexical_limit, выбираются по частоте появления.
        Рёбра DEPENDS_ON/PART_OF: ограничены edge_limit по частоте.
        LEADS_TO: ограничены edge_limit.
        """

        # --- Actions: топ-N по doc_count (частота появления в документах) ---
        actions_cypher = """
MATCH (a:Action)
WITH a.norm_key AS nk, collect(a) AS group
WITH group, size(group) AS doc_count
ORDER BY doc_count DESC
LIMIT $action_limit
WITH group[0] AS a, doc_count
RETURN a.uid AS uid, 'Action' AS _type,
       a.verb AS verb, a.verb_text AS verb_text,
       a.subject AS subject, a.object_ AS object,
       a.full_phrase AS full_phrase, a.label_text AS label_text,
       a.sentence_text AS sentence_text, a.doc_id AS doc_id,
       a.action_class AS action_class, a.norm_key AS norm_key,
       a.layout_x AS layout_x, a.layout_y AS layout_y,
       doc_count AS doc_count,
       NULL AS text, NULL AS lemma, NULL AS pos, NULL AS pos_fine,
       NULL AS dep, NULL AS is_stop, NULL AS is_punct
"""
        all_nodes: List[Dict[str, Any]] = []
        result, cols = db.cypher_query(actions_cypher, {"action_limit": action_limit})
        for row in result:
            all_nodes.append(dict(zip(cols, row)))

        # --- LexicalUnits: топ-N по частоте появления в документах ---
        lexical_cypher = """
MATCH (lu:LexicalUnit)
WITH lu.lemma AS lemma, lu.pos AS pos, collect(lu) AS group
WITH group[0] AS lu, size(group) AS freq
ORDER BY freq DESC
LIMIT $lexical_limit
RETURN lu.uid AS uid, 'LexicalUnit' AS _type,
       NULL AS verb, NULL AS verb_text, NULL AS subject, NULL AS object,
       NULL AS full_phrase, NULL AS label_text, NULL AS sentence_text,
       lu.doc_id AS doc_id, NULL AS action_class, NULL AS norm_key,
       lu.layout_x AS layout_x, lu.layout_y AS layout_y,
       NULL AS doc_count,
       lu.text AS text, lu.lemma AS lemma, lu.pos AS pos, lu.pos_fine AS pos_fine,
       lu.dep AS dep, lu.is_stop AS is_stop, lu.is_punct AS is_punct
"""
        result, cols = db.cypher_query(lexical_cypher, {"lexical_limit": lexical_limit})
        for row in result:
            all_nodes.append(dict(zip(cols, row)))

        # --- Рёбра: LEADS_TO между Actions, топ-N по частоте ---
        leads_cypher = """
MATCH (src:Action)-[r:LEADS_TO]->(tgt:Action)
WITH src.norm_key AS src_nk, tgt.norm_key AS tgt_nk,
     collect(distinct src.uid)[0] AS src_uid,
     collect(distinct tgt.uid)[0] AS tgt_uid,
     r.relation_subtype AS subtype,
     avg(r.confidence) AS conf,
     count(*) AS edge_count
ORDER BY edge_count DESC
LIMIT $edge_limit
RETURN src_uid, tgt_uid, subtype, conf,
       NULL AS dep_label, NULL AS token_index,
       'LEADS_TO' AS edge_type, edge_count
"""
        all_edges: List[Dict[str, Any]] = []
        result, cols = db.cypher_query(leads_cypher, {"edge_limit": edge_limit})
        for row in result:
            all_edges.append(dict(zip(cols, row)))

        # --- DEPENDS_ON: топ-N по частоте ---
        deps_cypher = """
MATCH (src:LexicalUnit)-[r:DEPENDS_ON]->(tgt:LexicalUnit)
WITH src.uid AS src_uid, tgt.uid AS tgt_uid,
       r.dep_label AS dep_label,
       count(*) AS cnt
ORDER BY cnt DESC
LIMIT $edge_limit
RETURN src_uid, tgt_uid, NULL AS relation_subtype, NULL AS confidence,
       NULL AS status, dep_label, NULL AS token_index,
       'DEPENDS_ON' AS edge_type, cnt AS edge_count
"""
        result, cols = db.cypher_query(deps_cypher, {"edge_limit": edge_limit})
        for row in result:
            all_edges.append(dict(zip(cols, row)))

        # --- PART_OF: топ-N по частоте ---
        partof_cypher = """
MATCH (lu:LexicalUnit)-[r:PART_OF]->(a:Action)
WITH lu.uid AS src_uid, a.uid AS tgt_uid,
       r.token_index AS token_index,
       count(*) AS cnt
ORDER BY cnt DESC
LIMIT $edge_limit
RETURN src_uid, tgt_uid, NULL AS relation_subtype, NULL AS confidence,
       NULL AS status, NULL AS dep_label, token_index,
       'PART_OF' AS edge_type, cnt AS edge_count
"""
        result, cols = db.cypher_query(partof_cypher, {"edge_limit": edge_limit})
        for row in result:
            all_edges.append(dict(zip(cols, row)))

        logger.info(
            f"[PatternGraphRepository] global "
            f"nodes={len(all_nodes)} edges={len(all_edges)}"
        )
        return all_nodes, all_edges
