"""
Layer: Application (Use Cases)
Package: application.patterns.unified_pattern_analyzer
Responsibility: Единый сервис анализа лингвистических паттернов.

Объединяет функциональность:
  - analyze_document_patterns (анализ одного документа через NLP)
  - analyze_linguistic_patterns (12 уровней анализа всего графа Neo4j)

Два режима:
  - document_level(doc_id) — анализ одного документа
  - global_level() — анализ всех документов

Allowed imports: typing, collections, dataclasses, logging, json, os
                 domain.*, application.ports.*, application.patterns.analyze_document_patterns
Forbidden imports: neomodel, fastapi, grpc, infrastructure, adapters, web
"""
from __future__ import annotations

import json
import logging
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Импортируем существующие dataclass и логику извлечения паттернов
from application.patterns.analyze_document_patterns import (
    AnnotationTypePatterns,
    PatternRow,
    _extract_patterns,
)

# ---------------------------------------------------------------------------
# Dataclass результата глобального анализа
# ---------------------------------------------------------------------------


@dataclass
class GlobalAnalysisResult:
    """Результат глобального (multi-level) анализа графа."""
    analysis_date: str
    graph_stats: Dict[str, Any]
    lexical_patterns: Dict[str, Any]
    bigram_patterns: Dict[str, Any]
    trigram_patterns: Dict[str, Any]
    dependency_chains: Dict[str, Any]
    action_patterns: Dict[str, Any]
    leads_to_chains: Dict[str, Any]
    cross_document_patterns: Dict[str, Any]
    mixed_patterns: Dict[str, Any]
    syntactic_dep_patterns: Dict[str, Any]
    pattern_stability: Dict[str, Any]
    summary: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "analysis_date": self.analysis_date,
            "graph_stats": self.graph_stats,
            "lexical_patterns": self.lexical_patterns,
            "bigram_patterns": self.bigram_patterns,
            "trigram_patterns": self.trigram_patterns,
            "dependency_chains": self.dependency_chains,
            "action_patterns": self.action_patterns,
            "leads_to_chains": self.leads_to_chains,
            "cross_document_patterns": self.cross_document_patterns,
            "mixed_patterns": self.mixed_patterns,
            "syntactic_dep_patterns": self.syntactic_dep_patterns,
            "pattern_stability": self.pattern_stability,
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# UnifiedPatternAnalyzer — обёртка над Neo4j драйвером
# ---------------------------------------------------------------------------

class UnifiedPatternAnalyzer:
    """
    Анализатор, работающий напрямую с Neo4j (как старый скрипт),
    но оформленный как переиспользуемый сервис.
    """

    def __init__(self, driver):
        """
        :param driver: neo4j.GraphDatabase.driver instance
        """
        self.driver = driver

    # ------------------------------------------------------------------
    # Утилиты
    # ------------------------------------------------------------------
    def _run_query(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        with self.driver.session() as session:
            result = session.run(query, params or {})
            return [dict(record) for record in result]

    def _count_nodes(self, label: str) -> int:
        r = self._run_query(f"MATCH (n:{label}) RETURN count(n) AS cnt")
        return r[0]["cnt"] if r else 0

    def _count_relationships(self, rel_type: str) -> int:
        r = self._run_query(f"MATCH ()-[r:{rel_type}]->() RETURN count(r) AS cnt")
        return r[0]["cnt"] if r else 0

    # ------------------------------------------------------------------
    # 0. Общая статистика графа
    # ------------------------------------------------------------------
    def analyze_graph_stats(self) -> Dict[str, Any]:
        node_labels = ["Action", "LexicalUnit", "LinguisticPattern", "LexicalForm",
                       "MarkdownAnnotation"]
        node_counts = {lbl: self._count_nodes(lbl) for lbl in node_labels}

        rel_types = ["LEADS_TO", "DEPENDS_ON", "PART_OF", "FOUND_IN",
                     "DEP_RELATION", "SYNTACTIC_DEP"]
        rel_counts = {rt: self._count_relationships(rt) for rt in rel_types}

        return {"nodes": node_counts, "relationships": rel_counts}

    # ------------------------------------------------------------------
    # 1. Одиночные лингвистические паттерны
    # ------------------------------------------------------------------
    def analyze_single_lexical_patterns(self) -> Dict[str, Any]:
        results: Dict[str, Any] = {}

        # POS distribution
        pos_data = self._run_query(
            "MATCH (lu:LexicalUnit) WHERE lu.pos IS NOT NULL "
            "RETURN lu.pos AS pos, count(*) AS cnt ORDER BY cnt DESC LIMIT 50"
        )
        results["pos_distribution"] = pos_data

        # Dependency label distribution
        dep_data = self._run_query(
            "MATCH (lu:LexicalUnit) WHERE lu.dep IS NOT NULL "
            "RETURN lu.dep AS dep, count(*) AS cnt ORDER BY cnt DESC LIMIT 50"
        )
        results["dep_label_distribution"] = dep_data

        # Top lemmas
        lemma_data = self._run_query(
            "MATCH (lu:LexicalUnit) WHERE lu.lemma IS NOT NULL "
            "RETURN lu.lemma AS lemma, count(*) AS cnt ORDER BY cnt DESC LIMIT 50"
        )
        results["top_lemmas"] = lemma_data

        # Verbs
        verb_data = self._run_query(
            "MATCH (lu:LexicalUnit) WHERE lu.pos = 'VERB' AND lu.lemma IS NOT NULL "
            "RETURN lu.lemma AS verb, count(*) AS cnt ORDER BY cnt DESC LIMIT 50"
        )
        results["top_verbs"] = verb_data

        # Nouns
        noun_data = self._run_query(
            "MATCH (lu:LexicalUnit) WHERE lu.pos = 'NOUN' AND lu.lemma IS NOT NULL "
            "RETURN lu.lemma AS noun, count(*) AS cnt ORDER BY cnt DESC LIMIT 50"
        )
        results["top_nouns"] = noun_data

        # Adjectives
        adj_data = self._run_query(
            "MATCH (lu:LexicalUnit) WHERE lu.pos = 'ADJ' AND lu.lemma IS NOT NULL "
            "RETURN lu.lemma AS adj, count(*) AS cnt ORDER BY cnt DESC LIMIT 50"
        )
        results["top_adjectives"] = adj_data

        # Stop-word ratio
        total = self._run_query("MATCH (lu:LexicalUnit) RETURN count(lu) AS cnt")
        stops = self._run_query(
            "MATCH (lu:LexicalUnit) WHERE lu.is_stop = true RETURN count(lu) AS cnt"
        )
        total_cnt = total[0]["cnt"] if total else 0
        stop_cnt = stops[0]["cnt"] if stops else 0
        results["stop_word_ratio"] = {
            "total": total_cnt,
            "stop_words": stop_cnt,
            "ratio": round(stop_cnt / total_cnt, 4) if total_cnt > 0 else 0,
        }

        return results

    # ------------------------------------------------------------------
    # 2. Биграммы (DEPENDS_ON двухзвенные)
    # ------------------------------------------------------------------
    def analyze_bigram_patterns(self) -> Dict[str, Any]:
        bigrams = self._run_query(
            "MATCH (src:LexicalUnit)-[r:DEPENDS_ON]->(tgt:LexicalUnit) "
            "WHERE r.dep_label IS NOT NULL "
            "RETURN r.dep_label AS dep, count(*) AS cnt ORDER BY cnt DESC LIMIT 50"
        )

        # Конкретные паттерны
        patterns = {
            "nsubj": self._run_query(
                "MATCH (n:NOUN)-[r:DEPENDS_ON {dep_label: 'nsubj'}]->(v:LexicalUnit {pos: 'VERB'}) "
                "RETURN n.text AS noun, v.text AS verb, count(*) AS cnt ORDER BY cnt DESC LIMIT 20"
            ),
            "dobj": self._run_query(
                "MATCH (v:LexicalUnit {pos: 'VERB'})-[r:DEPENDS_ON {dep_label: 'dobj'}]->(n:NOUN) "
                "RETURN v.text AS verb, n.text AS noun, count(*) AS cnt ORDER BY cnt DESC LIMIT 20"
            ),
            "amod": self._run_query(
                "MATCH (n:NOUN)-[r:DEPENDS_ON {dep_label: 'amod'}]->(adj:LexicalUnit {pos: 'ADJ'}) "
                "RETURN adj.text AS adj, n.text AS noun, count(*) AS cnt ORDER BY cnt DESC LIMIT 20"
            ),
            "compound": self._run_query(
                "MATCH (n1:NOUN)-[r:DEPENDS_ON {dep_label: 'compound'}]->(n2:NOUN) "
                "RETURN n1.text AS n1, n2.text AS n2, count(*) AS cnt ORDER BY cnt DESC LIMIT 20"
            ),
        }

        return {"bigram_distribution": bigrams, "specific_patterns": patterns}

    # ------------------------------------------------------------------
    # 3. Триграммы
    # ------------------------------------------------------------------
    def analyze_trigram_patterns(self) -> Dict[str, Any]:
        # SVO: subject -> verb -> object
        svo = self._run_query(
            "MATCH (subj:LexicalUnit)-[:DEPENDS_ON {dep_label: 'nsubj'}]->"
            "(verb:LexicalUnit {pos: 'VERB'})-[:DEPENDS_ON {dep_label: 'dobj'}]->"
            "(obj:LexicalUnit) "
            "RETURN subj.text AS subject, verb.text AS verb, obj.text AS object, "
            "count(*) AS cnt ORDER BY cnt DESC LIMIT 50"
        )

        # ADJ -> NOUN <- compound
        adj_compound = self._run_query(
            "MATCH (adj:LexicalUnit {pos: 'ADJ'})-[:DEPENDS_ON {dep_label: 'amod'}]->"
            "(noun:NOUN)<-[:DEPENDS_ON {dep_label: 'compound'}]-(compound:NOUN) "
            "RETURN adj.text AS adj, noun.text AS noun, compound.text AS compound, "
            "count(*) AS cnt ORDER BY cnt DESC LIMIT 50"
        )

        return {"svo_patterns": svo, "adj_compound_noun": adj_compound}

    # ------------------------------------------------------------------
    # 4. Цепочки зависимостей переменной длины
    # ------------------------------------------------------------------
    def analyze_dependency_chains(self) -> Dict[str, Any]:
        results: Dict[str, Any] = {"by_length": {}}

        for length in range(1, 6):
            rels = "()-[:DEPENDS_ON]->" * length
            query = f"""
            MATCH path = {rels}
            WITH length(path) AS len, 
                 [n IN nodes(path) | coalesce(n.lemma, n.text)] AS lemmas
            WHERE len = {length}
            RETURN lemmas, count(*) AS cnt
            ORDER BY cnt DESC
            LIMIT 30
            """
            results["by_length"][str(length)] = self._run_query(query)

        # Максимальная глубина от глаголов
        max_depth = self._run_query(
            "MATCH (v:LexicalUnit {pos: 'VERB'}) "
            "OPTIONAL MATCH path = (v)-[:DEPENDS_ON*1..5]->() "
            "WITH v, max(length(path)) AS max_depth "
            "ORDER BY max_depth DESC LIMIT 20 "
            "RETURN v.text AS verb, max_depth"
        )
        results["max_depth_from_verbs"] = max_depth

        return results

    # ------------------------------------------------------------------
    # 5. Паттерны действий (LEADS_TO)
    # ------------------------------------------------------------------
    def analyze_action_patterns(self) -> Dict[str, Any]:
        # Пары LEADS_TO
        pairs = self._run_query(
            "MATCH (src:Action)-[r:LEADS_TO]->(tgt:Action) "
            "RETURN src.verb AS src_verb, tgt.verb AS tgt_verb, "
            "r.relation_subtype AS subtype, count(*) AS cnt "
            "ORDER BY cnt DESC LIMIT 50"
        )

        # Распределение по relation_subtype
        subtypes = self._run_query(
            "MATCH ()-[r:LEADS_TO]->() WHERE r.relation_subtype IS NOT NULL "
            "RETURN r.relation_subtype AS subtype, count(*) AS cnt ORDER BY cnt DESC"
        )

        # Распределение по action_class
        classes = self._run_query(
            "MATCH (a:Action) WHERE a.action_class IS NOT NULL "
            "RETURN a.action_class AS cls, count(*) AS cnt ORDER BY cnt DESC"
        )

        # In-degree
        in_degree = self._run_query(
            "MATCH (tgt:Action)<-[:LEADS_TO]-() "
            "RETURN tgt.verb AS verb, count(*) AS in_degree ORDER BY in_degree DESC LIMIT 20"
        )

        # Out-degree
        out_degree = self._run_query(
            "MATCH (src:Action)-[:LEADS_TO]->() "
            "RETURN src.verb AS verb, count(*) AS out_degree ORDER BY out_degree DESC LIMIT 20"
        )

        # Статусы рёбер
        statuses = self._run_query(
            "MATCH ()-[r:LEADS_TO]->() WHERE r.status IS NOT NULL "
            "RETURN r.status AS status, count(*) AS cnt ORDER BY cnt DESC"
        )

        return {
            "lead_pairs": pairs,
            "relation_subtypes": subtypes,
            "action_classes": classes,
            "in_degree_top": in_degree,
            "out_degree_top": out_degree,
            "edge_statuses": statuses,
        }

    # ------------------------------------------------------------------
    # 6. Цепочки LEADS_TO
    # ------------------------------------------------------------------
    def analyze_leads_to_chains(self) -> Dict[str, Any]:
        results: Dict[str, Any] = {"by_length": {}}

        for length in range(2, 6):
            rels = "()-[:LEADS_TO]->" * length
            query = f"""
            MATCH path = {rels}
            WITH length(path) AS len,
                 [n IN nodes(path) | coalesce(n.verb_text, n.verb)] AS verbs
            WHERE len = {length}
            RETURN verbs, count(*) AS cnt
            ORDER BY cnt DESC
            LIMIT 30
            """
            results["by_length"][str(length)] = self._run_query(query)

        # Самые длинные цепочки
        longest = self._run_query(
            "MATCH path = ()-[:LEADS_TO*2..5]->() "
            "WITH length(path) AS len, "
            "[n IN nodes(path) | coalesce(n.verb_text, n.verb)] AS verbs "
            "ORDER BY len DESC LIMIT 20 "
            "RETURN verbs, len"
        )
        results["longest_chains"] = longest

        # Diverging (1 -> много)
        diverging = self._run_query(
            "MATCH (src:Action)-[:LEADS_TO]->(t1:Action), "
            "      (src:Action)-[:LEADS_TO]->(t2:Action) "
            "WHERE t1 <> t2 "
            "RETURN src.verb AS src_verb, count(DISTINCT t1) + count(DISTINCT t2) AS targets "
            "ORDER BY targets DESC LIMIT 20"
        )
        results["diverging_patterns"] = diverging

        # Converging (много -> 1)
        converging = self._run_query(
            "MATCH (s1:Action)-[:LEADS_TO]->(tgt:Action), "
            "      (s2:Action)-[:LEADS_TO]->(tgt:Action) "
            "WHERE s1 <> s2 "
            "RETURN tgt.verb AS tgt_verb, count(DISTINCT s1) + count(DISTINCT s2) AS sources "
            "ORDER BY sources DESC LIMIT 20"
        )
        results["converging_patterns"] = converging

        return results

    # ------------------------------------------------------------------
    # 7. Кросс-документные паттерны
    # ------------------------------------------------------------------
    def analyze_cross_document_patterns(self) -> Dict[str, Any]:
        # Одинаковые verb+obj в разных документах
        verb_obj = self._run_query(
            "MATCH (a:Action) WHERE a.verb IS NOT NULL "
            "WITH a.verb AS verb, a.doc_id AS doc, count(*) AS cnt "
            "WITH verb, count(DISTINCT doc) AS doc_count, sum(cnt) AS total "
            "WHERE doc_count > 1 "
            "RETURN verb, doc_count, total ORDER BY doc_count DESC, total DESC LIMIT 50"
        )

        # Одинаковые SVO
        svo_cross = self._run_query(
            "MATCH (subj:LexicalUnit)-[:DEPENDS_ON {dep_label: 'nsubj'}]->"
            "(verb:LexicalUnit {pos: 'VERB'})-[:DEPENDS_ON {dep_label: 'dobj'}]->"
            "(obj:LexicalUnit) "
            "WITH subj.text AS s, verb.text AS v, obj.text AS o, "
            "     count(DISTINCT subj.doc_id) AS docs "
            "WHERE docs > 1 "
            "RETURN s, v, o, docs ORDER BY docs DESC LIMIT 50"
        )

        # Одинаковые LEADS_TO
        leads_cross = self._run_query(
            "MATCH (src:Action)-[:LEADS_TO]->(tgt:Action) "
            "WHERE src.verb IS NOT NULL AND tgt.verb IS NOT NULL "
            "WITH src.verb AS src_v, tgt.verb AS tgt_v, "
            "     count(DISTINCT src.doc_id) AS docs "
            "WHERE docs > 1 "
            "RETURN src_v, tgt_v, docs ORDER BY docs DESC LIMIT 50"
        )

        return {
            "verb_obj_cross_doc": verb_obj,
            "svo_cross_doc": svo_cross,
            "leads_to_cross_doc": leads_cross,
        }

    # ------------------------------------------------------------------
    # 8. Смешанные паттерны (LexicalUnit + Action)
    # ------------------------------------------------------------------
    def analyze_mixed_patterns(self) -> Dict[str, Any]:
        # verb overlap в LEADS_TO
        verb_overlap = self._run_query(
            "MATCH (a:Action)-[:LEADS_TO]->() "
            "WHERE a.verb IS NOT NULL "
            "WITH a.verb AS v, count(*) AS cnt ORDER BY cnt DESC LIMIT 30 "
            "RETURN v, cnt"
        )

        # noun в source leads to result
        noun_result = self._run_query(
            "MATCH (lu:LexicalUnit {pos: 'NOUN'})-[:PART_OF]->"
            "(src:Action)-[:LEADS_TO]->(tgt:Action {action_class: 'result'}) "
            "RETURN lu.text AS noun, src.verb AS src_verb, tgt.verb AS tgt_verb, "
            "count(*) AS cnt ORDER BY cnt DESC LIMIT 30"
        )

        return {"verb_overlap_in_leads": verb_overlap, "noun_source_to_result": noun_result}

    # ------------------------------------------------------------------
    # 9. SYNTACTIC_DEP между Actions
    # ------------------------------------------------------------------
    def analyze_syntactic_dep_patterns(self) -> Dict[str, Any]:
        dist = self._run_query(
            "MATCH ()-[r:SYNTACTIC_DEP]->() WHERE r.dep_label IS NOT NULL "
            "RETURN r.dep_label AS dep, count(*) AS cnt ORDER BY cnt DESC"
        )

        pairs = self._run_query(
            "MATCH (src:Action)-[r:SYNTACTIC_DEP]->(tgt:Action) "
            "RETURN src.verb AS src_verb, tgt.verb AS tgt_verb, "
            "r.dep_label AS dep, count(*) AS cnt ORDER BY cnt DESC LIMIT 50"
        )

        return {"dep_label_distribution": dist, "specific_pairs": pairs}

    # ------------------------------------------------------------------
    # 10. LinguisticPattern сущности
    # ------------------------------------------------------------------
    def analyze_linguistic_patterns_entity(self) -> Dict[str, Any]:
        type_dist = self._run_query(
            "MATCH (lp:LinguisticPattern) "
            "RETURN lp.pattern_type AS type, count(*) AS cnt ORDER BY cnt DESC"
        )

        freq_dist = self._run_query(
            "MATCH (lp:LinguisticPattern) "
            "RETURN lp.frequency AS freq, count(*) AS cnt ORDER BY freq DESC LIMIT 30"
        )

        return {"type_distribution": type_dist, "frequency_distribution": freq_dist}

    # ------------------------------------------------------------------
    # 11. Устойчивость паттернов
    # ------------------------------------------------------------------
    def calculate_pattern_stability(self) -> Dict[str, Any]:
        # verb+obj по документам
        verb_obj = self._run_query(
            "MATCH (v:LexicalUnit {pos: 'VERB'})-[:DEPENDS_ON {dep_label: 'dobj'}]->"
            "(o:LexicalUnit) "
            "WITH v.lemma AS verb, o.lemma AS obj, "
            "     count(DISTINCT v.doc_id) AS docs, count(*) AS total "
            "RETURN verb, obj, docs, total, "
            "       toFloat(docs) / total AS stability "
            "WHERE docs > 1 ORDER BY stability DESC LIMIT 50"
        )

        # SVO
        svo = self._run_query(
            "MATCH (s:LexicalUnit)-[:DEPENDS_ON {dep_label: 'nsubj'}]->"
            "(v:LexicalUnit {pos: 'VERB'})-[:DEPENDS_ON {dep_label: 'dobj'}]->"
            "(o:LexicalUnit) "
            "WITH v.lemma AS verb, s.lemma AS subj, o.lemma AS obj, "
            "     count(DISTINCT v.doc_id) AS docs, count(*) AS total "
            "WHERE docs > 1 "
            "RETURN subj, verb, obj, docs, total, "
            "       toFloat(docs) / total AS stability "
            "ORDER BY stability DESC LIMIT 50"
        )

        return {"verb_obj_stability": verb_obj, "svo_stability": svo}

    # ------------------------------------------------------------------
    # 13. Dependency N-grams (DP с memoization + exemplars)
    # ------------------------------------------------------------------
    def analyze_dependency_ngrams(self, max_depth: int = 5, limit_per_n: int = 50, max_exemplars: int = 100) -> Dict[str, Any]:
        """
        Точный подсчёт dependency n-gram паттернов через dynamic programming.

        Вместо MATCH path = ()-[:...*N]->() (комбинаторный взрыв) используем:
        1. Загружаем граф в память (adjacency list)
        2. DP: memo[node, depth] → Counter сигнатур + exemplars (цепочки node_id)
        3. Агрегируем снизу вверх от leaf-узлов

        Поддерживает: DEPENDS_ON, PART_OF, LEADS_TO + LexicalUnit, Action.

        :param max_exemplars: макс. число уникальных цепочек node_id на сигнатуру (по умолчанию 100)
        """
        from collections import Counter, defaultdict

        results: Dict[str, Any] = {}
        clamped_depth = max(1, min(max_depth, 10))

        # --- 1. Загружаем граф в память ---
        edges_data = self._run_query("""
            MATCH (s)-[r:DEPENDS_ON|PART_OF|LEADS_TO]->(t)
            WHERE (s:LexicalUnit OR s:Action) AND (t:LexicalUnit OR t:Action)
            RETURN
                id(s) AS sid,
                id(t) AS tid,
                CASE WHEN s:LexicalUnit THEN coalesce(s.text, s.lemma, '')
                     WHEN s:Action THEN coalesce(s.verb, s.verb_lemma, '')
                     ELSE '' END AS s_text,
                CASE WHEN t:LexicalUnit THEN coalesce(t.text, t.lemma, '')
                     WHEN t:Action THEN coalesce(t.verb, t.verb_lemma, '')
                     ELSE '' END AS t_text,
                type(r) AS rel_type,
                coalesce(r.dep_label, '') AS dep_label
        """)

        labels: Dict[int, str] = {}
        out_edges: Dict[int, List[Tuple[str, int]]] = defaultdict(list)
        in_degree: Dict[int, int] = defaultdict(int)
        all_node_ids: set = set()
        node_types: Dict[int, str] = {}

        for row in edges_data:
            sid, tid = row["sid"], row["tid"]
            all_node_ids.add(sid)
            all_node_ids.add(tid)
            labels[sid] = row["s_text"] or str(sid)
            labels[tid] = row["t_text"] or str(tid)
            rel = row["rel_type"] + ":" + (row["dep_label"] or "")
            out_edges[sid].append((rel, tid))
            in_degree[tid] += 1
            in_degree.setdefault(sid, in_degree.get(sid, 0))
            if sid not in node_types:
                node_types[sid] = "Action" if sid < 1000000 else "LexicalUnit"
            if tid not in node_types:
                node_types[tid] = "Action" if tid < 1000000 else "LexicalUnit"

        # --- 2. Находим leaf-узлы ---
        leaves = [nid for nid in all_node_ids if in_degree.get(nid, 0) == 0]
        if not leaves:
            leaves = list(all_node_ids)
        max_leaves = 3000
        if len(leaves) > max_leaves:
            leaves = sorted(leaves, key=lambda nid: len(out_edges.get(nid, [])))[:max_leaves]

        # --- 3. DP с memoization + exemplars ---
        memo: Dict[Tuple[int, int], Counter] = {}
        exemplars: Dict[int, List[List[int]]] = defaultdict(list)
        exemplars_set: Dict[int, set] = defaultdict(set)
        sig_text: Dict[int, tuple] = {}

        def get_signature_hash(sig: tuple) -> int:
            h = hash(sig)
            if h not in sig_text:
                sig_text[h] = sig
            return h

        def solve(node_id: int, depth: int) -> Counter:
            key = (node_id, depth)
            if key in memo:
                return memo[key]

            node_text = labels.get(node_id, str(node_id))

            if depth == 1:
                sig = (node_text,)
                h = get_signature_hash(sig)
                result = Counter({h: 1})
                if len(exemplars_set[h]) < max_exemplars:
                    chain_key = (node_id,)
                    if chain_key not in exemplars_set[h]:
                        exemplars_set[h].add(chain_key)
                        exemplars[h].append([node_id])
                memo[key] = result
                return result

            acc = Counter()
            for rel, nxt in out_edges.get(node_id, []):
                child = solve(nxt, depth - 1)
                for child_hash, cnt in child.items():
                    child_sig = sig_text[child_hash]
                    new_sig = (node_text, rel) + child_sig
                    h = get_signature_hash(new_sig)
                    acc[h] += cnt
                    if len(exemplars_set[h]) < max_exemplars:
                        for child_chain in exemplars.get(child_hash, []):
                            new_chain = [node_id] + child_chain
                            chain_key = tuple(new_chain)
                            if chain_key not in exemplars_set[h]:
                                exemplars_set[h].add(chain_key)
                                exemplars[h].append(new_chain)
                                if len(exemplars_set[h]) >= max_exemplars:
                                    break
                    if len(exemplars_set[h]) >= max_exemplars:
                        break

            memo[key] = acc
            return acc

        # --- 4. Собираем результаты ---
        # 1-граммы
        unigram_counter = Counter()
        unigram_exemplars: Dict[int, List[List[int]]] = defaultdict(list)
        unigram_exemplars_set: Dict[int, set] = defaultdict(set)

        for nid in all_node_ids:
            text = labels.get(nid, str(nid))
            ntype = node_types.get(nid, "?")
            sig = (text, ntype)
            h = get_signature_hash(sig)
            unigram_counter[h] += 1
            if len(unigram_exemplars_set[h]) < max_exemplars:
                if nid not in unigram_exemplars_set[h]:
                    unigram_exemplars_set[h].add(nid)
                    unigram_exemplars[h].append([nid])

        unigrams = []
        for h, cnt in unigram_counter.most_common(limit_per_n):
            sig = sig_text[h]
            ntype = sig[1] if len(sig) > 1 else "?"
            unigrams.append({
                "pos": sig[0], "dep": "", "lemma": sig[0],
                "node_type": ntype, "cnt": cnt,
                "sig_hash": str(h),
                "exemplars": unigram_exemplars.get(h, [])[:max_exemplars],
            })
        results["unigrams"] = unigrams

        # 2..N-граммы
        n_grams: Dict[str, Any] = {}
        for depth in range(2, clamped_depth + 1):
            depth_counter = Counter()
            depth_exemplars: Dict[int, List[List[int]]] = defaultdict(list)
            depth_exemplars_set: Dict[int, set] = defaultdict(set)

            for leaf in leaves:
                leaf_counter = solve(leaf, depth)
                depth_counter.update(leaf_counter)
                for h in leaf_counter:
                    if len(depth_exemplars_set[h]) < max_exemplars:
                        for chain in exemplars.get(h, []):
                            chain_key = tuple(chain)
                            if chain_key not in depth_exemplars_set[h]:
                                depth_exemplars_set[h].add(chain_key)
                                depth_exemplars[h].append(chain)
                                if len(depth_exemplars_set[h]) >= max_exemplars:
                                    break

            top = depth_counter.most_common(limit_per_n)
            if top:
                formatted = []
                for h, cnt in top:
                    sig = sig_text[h]
                    chain = []
                    for i in range(0, len(sig) - 2, 2):
                        chain.append([sig[i], sig[i + 1], sig[i + 2]])
                    if chain:
                        formatted.append({
                            "chain": chain, "cnt": cnt,
                            "sig_hash": str(h),
                            "exemplars": depth_exemplars.get(h, [])[:max_exemplars],
                        })
                if formatted:
                    n_grams[f"{depth}-grams"] = formatted

        results["n_grams"] = n_grams

        # --- Длинные цепочки (>5) ---
        long_chains = []
        if clamped_depth > 5:
            for depth in range(6, clamped_depth + 1):
                depth_counter = Counter()
                depth_exemplars: Dict[int, List[List[int]]] = defaultdict(list)
                depth_exemplars_set: Dict[int, set] = defaultdict(set)
                for leaf in leaves:
                    leaf_counter = solve(leaf, depth)
                    depth_counter.update(leaf_counter)
                    for h in leaf_counter:
                        if len(depth_exemplars_set[h]) < max_exemplars:
                            for chain in exemplars.get(h, []):
                                chain_key = tuple(chain)
                                if chain_key not in depth_exemplars_set[h]:
                                    depth_exemplars_set[h].add(chain_key)
                                    depth_exemplars[h].append(chain)

                for h, cnt in depth_counter.most_common(limit_per_n):
                    sig = sig_text[h]
                    texts = [sig[i] for i in range(0, len(sig), 2)]
                    rels = [sig[i] for i in range(1, len(sig), 2)]
                    long_chains.append({
                        "texts": texts, "deps": rels, "depth": depth, "cnt": cnt,
                        "sig_hash": str(h),
                        "exemplars": depth_exemplars.get(h, [])[:max_exemplars],
                    })

        results["long_chains"] = long_chains

        # --- Кросс-документная устойчивость ---
        cross_doc = []
        for depth in range(1, min(clamped_depth + 1, 6)):
            depth_counter = Counter()
            for leaf in leaves:
                depth_counter.update(solve(leaf, depth))
            for h, cnt in depth_counter.most_common(limit_per_n):
                sig = sig_text[h]
                lemmas = [sig[i] for i in range(0, len(sig), 2)]
                deps = [sig[i] for i in range(1, len(sig), 2)]
                cross_doc.append({"lemmas": lemmas, "deps": deps, "depth": depth, "cnt": cnt})

        results["cross_doc"] = cross_doc

        # Очищаем кэш
        memo.clear()
        sig_text.clear()
        exemplars.clear()
        exemplars_set.clear()

        return results

    # ------------------------------------------------------------------
    # 12. Сводка
    # ------------------------------------------------------------------
    def generate_summary(self, all_results: Dict[str, Any]) -> Dict[str, Any]:
        summary: Dict[str, Any] = {}

        # Топ устойчивых паттернов
        stability = all_results.get("pattern_stability", {})
        verb_obj_stability = stability.get("verb_obj_stability", [])
        summary["top_stable_verb_obj"] = verb_obj_stability[:10]

        svo_stability = stability.get("svo_stability", [])
        summary["top_stable_svo"] = svo_stability[:10]

        # Сводка по графу
        graph_stats = all_results.get("graph_stats", {})
        summary["graph_summary"] = {
            "total_nodes": sum(graph_stats.get("nodes", {}).values()),
            "total_relationships": sum(graph_stats.get("relationships", {}).values()),
        }

        return summary

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_global(self, output_dir: str = "docs") -> GlobalAnalysisResult:
        """Выполняет полный 12-уровневый анализ и сохраняет результат."""
        logger.info("Начало глобального анализа...")

        graph_stats = self.analyze_graph_stats()
        logger.info(f"Граф: {graph_stats}")

        lexical = self.analyze_single_lexical_patterns()
        bigram = self.analyze_bigram_patterns()
        trigram = self.analyze_trigram_patterns()
        dep_chains = self.analyze_dependency_chains()
        action = self.analyze_action_patterns()
        leads_chains = self.analyze_leads_to_chains()
        cross_doc = self.analyze_cross_document_patterns()
        mixed = self.analyze_mixed_patterns()
        syntactic = self.analyze_syntactic_dep_patterns()
        lp_entity = self.analyze_linguistic_patterns_entity()
        stability = self.calculate_pattern_stability()

        all_results = {
            "graph_stats": graph_stats,
            "lexical_patterns": lexical,
            "bigram_patterns": bigram,
            "trigram_patterns": trigram,
            "dependency_chains": dep_chains,
            "action_patterns": action,
            "leads_to_chains": leads_chains,
            "cross_document_patterns": cross_doc,
            "mixed_patterns": mixed,
            "syntactic_dep_patterns": syntactic,
            "linguistic_pattern_entity": lp_entity,
            "pattern_stability": stability,
        }

        summary = self.generate_summary(all_results)
        all_results["summary"] = summary

        # Сохранение
        os.makedirs(output_dir, exist_ok=True)
        json_path = os.path.join(output_dir, "pattern_analysis_report.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        logger.info(f"JSON-отчёт сохранён: {json_path}")

        # Текстовый отчёт
        txt_path = os.path.join(output_dir, "pattern_analysis_report.txt")
        self._save_text_report(all_results, txt_path)
        logger.info(f"Текстовый отчёт сохранён: {txt_path}")

        return GlobalAnalysisResult(
            analysis_date=datetime.now().isoformat(),
            graph_stats=graph_stats,
            lexical_patterns=lexical,
            bigram_patterns=bigram,
            trigram_patterns=trigram,
            dependency_chains=dep_chains,
            action_patterns=action,
            leads_to_chains=leads_chains,
            cross_document_patterns=cross_doc,
            mixed_patterns=mixed,
            syntactic_dep_patterns=syntactic,
            pattern_stability=stability,
            summary=summary,
        )

    def _save_text_report(self, data: Dict[str, Any], path: str) -> None:
        """Генерирует человекочитаемый текстовый отчёт."""
        lines: List[str] = []
        lines.append("=" * 60)
        lines.append("АНАЛИЗ ЛИНГВИСТИЧЕСКИХ ПАТТЕРНОВ")
        lines.append(f"Дата: {data.get('analysis_date', 'N/A')}")
        lines.append("=" * 60)
        lines.append("")

        # Graph stats
        gs = data.get("graph_stats", {})
        lines.append("0. СТАТИСТИКА ГРАФА")
        lines.append(f"  Узлы: {gs.get('nodes', {})}")
        lines.append(f"  Рёбра: {gs.get('relationships', {})}")
        lines.append("")

        # Lexical
        lp = data.get("lexical_patterns", {})
        lines.append("1. ОДИНОЧНЫЕ ЛИНГВИСТИЧЕСКИЕ ПАТТЕРНЫ")
        pos_dist = lp.get("pos_distribution", [])
        lines.append(f"  POS-распределение (топ-5):")
        for item in pos_dist[:5]:
            lines.append(f"    {item['pos']}: {item['cnt']}")
        lines.append("")

        # Bigrams
        bg = data.get("bigram_patterns", {})
        lines.append("2. БИГРАММЫ")
        for item in bg.get("bigram_distribution", [])[:10]:
            lines.append(f"  {item['dep']}: {item['cnt']}")
        lines.append("")

        # Actions
        ap = data.get("action_patterns", {})
        lines.append("5. ПАТТЕРНЫ ДЕЙСТВИЙ (LEADS_TO)")
        for item in ap.get("relation_subtypes", [])[:10]:
            lines.append(f"  {item['subtype']}: {item['cnt']}")
        lines.append("")

        # Stability
        st = data.get("pattern_stability", {})
        lines.append("11. УСТОЙЧИВОСТЬ ПАТТЕРНОВ")
        for item in st.get("verb_obj_stability", [])[:10]:
            lines.append(
                f"  {item['verb']} -> {item.get('obj', '?')} "
                f"(docs={item['docs']}, total={item['total']}, "
                f"stability={item['stability']:.3f})"
            )
        lines.append("")

        summary = data.get("summary", {})
        lines.append("ИТОГО")
        gsummary = summary.get("graph_summary", {})
        lines.append(f"Всего узлов: {gsummary.get('total_nodes', 0)}")
        lines.append(f"Всего рёбер: {gsummary.get('total_relationships', 0)}")
        lines.append(f"Категорий паттернов: {len(data)}")
        lines.append("")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
