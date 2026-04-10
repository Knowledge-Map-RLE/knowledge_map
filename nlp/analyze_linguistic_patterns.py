"""
Скрипт для комплексного анализа лингвистических паттернов в Neo4j.

Назначение:
- Найти все существующие лингвистические паттерны разного масштаба
- Рассчитать частоту каждого паттерна
- Выявить самые устойчивые (повторяющиеся в разных документах) паттерны
- Сгенерировать отчёт с ранжированием по устойчивости

Масштабы паттернов:
1. Одиночные лингвистические сущности (леммы, POS, dependency)
2. Двухзвенные синтаксические паттерны (nsubj, dobj, amod, compound)
3. Трёхзвенные паттерны (SVO, compound chains)
4. Паттерны уровня Action (LEADS_TO связи)
5. Цепочки переменной длины (1-5 шагов)
6. Кросс-документные паттерны
7. Сходящиеся/расходящиеся паттерны
8. Смешанные паттерны (LexicalUnit + Action)

Ограничения:
- НЕ использовать циклические запросы
- НЕ использовать неограниченную глубину (* без上限)
- Использовать только реально существующие в БД паттерны
"""

import os
import json
import logging
from datetime import datetime
from typing import Any

from neo4j import GraphDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Конфигурация подключения
# ---------------------------------------------------------------------------
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# Верхний предел для запросов переменной длины (безопасное значение)
MAX_PATH_LENGTH = 5

# Выходной файл
OUTPUT_FILE = "docs/pattern_analysis_report.json"
OUTPUT_TXT = "docs/pattern_analysis_report.txt"


class PatternAnalyzer:
    """Анализатор лингвистических паттернов в Neo4j."""

    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.results: dict[str, Any] = {
            "analysis_date": datetime.now().isoformat(),
            "database": uri,
            "patterns": {},
            "summary": {},
        }

    def close(self):
        self.driver.close()

    # -----------------------------------------------------------------------
    # Утилиты
    # -----------------------------------------------------------------------
    def _run_query(self, query: str, params: dict | None = None) -> list[dict]:
        """Выполняет Cypher-запрос и возвращает результаты."""
        with self.driver.session() as session:
            result = session.run(query, params or {})
            records = [dict(record) for record in result]
            return records

    def _count_nodes(self, label: str) -> int:
        """Считает количество узлов с данной меткой."""
        query = f"MATCH (n:{label}) RETURN count(n) AS cnt"
        result = self._run_query(query)
        return result[0]["cnt"] if result else 0

    def _count_relationships(self, rel_type: str) -> int:
        """Считает количество рёбер данного типа."""
        query = f"MATCH ()-[r:{rel_type}]->() RETURN count(r) AS cnt"
        result = self._run_query(query)
        return result[0]["cnt"] if result else 0

    # -----------------------------------------------------------------------
    # 0. Общая статистика графа
    # -----------------------------------------------------------------------
    def analyze_graph_stats(self):
        """Базовая статистика: количество узлов и рёбер каждого типа."""
        logger.info("0. Сбор общей статистики графа...")

        node_labels = ["Action", "LexicalUnit", "LinguisticPattern", "LexicalForm",
                       "PDFDocument", "MarkdownAnnotation", "Block", "User"]
        rel_types = ["LEADS_TO", "DEPENDS_ON", "PART_OF", "SYNTACTIC_DEP",
                     "FOUND_IN", "RELATES_TO", "LINK_TO"]

        stats = {
            "node_counts": {},
            "relationship_counts": {},
        }

        for label in node_labels:
            cnt = self._count_nodes(label)
            stats["node_counts"][label] = cnt
            logger.info(f"  {label}: {cnt:,} узлов")

        for rel_type in rel_types:
            cnt = self._count_relationships(rel_type)
            stats["relationship_counts"][rel_type] = cnt
            logger.info(f"  {rel_type}: {cnt:,} рёбер")

        self.results["graph_stats"] = stats
        return stats

    # -----------------------------------------------------------------------
    # 1. Одиночные лингвистические сущности (LexicalUnit)
    # -----------------------------------------------------------------------
    def analyze_single_lexical_patterns(self):
        """Паттерны уровня одной лексической единицы."""
        logger.info("1. Анализ одиночных лингвистических паттернов...")

        patterns = {}

        # 1a. Распределение по POS (части речи)
        query_pos = """
        MATCH (lu:LexicalUnit)
        RETURN lu.pos AS pos, count(*) AS cnt
        ORDER BY cnt DESC
        """
        pos_dist = self._run_query(query_pos)
        patterns["pos_distribution"] = [dict(r) for r in pos_dist]
        logger.info(f"  POS: {len(pos_dist)} уникальных категорий")

        # 1b. Распределение по dependency labels
        query_dep = """
        MATCH (lu:LexicalUnit)
        WHERE lu.dep IS NOT NULL
        RETURN lu.dep AS dep, count(*) AS cnt
        ORDER BY cnt DESC
        LIMIT 50
        """
        dep_dist = self._run_query(query_dep)
        patterns["dep_distribution"] = [dict(r) for r in dep_dist]
        logger.info(f"  Dep: {len(dep_dist)} уникальных категорий")

        # 1c. Топ-50 лемм по частоте
        query_lemma = """
        MATCH (lu:LexicalUnit)
        WHERE lu.lemma IS NOT NULL AND NOT lu.is_stop AND NOT lu.is_punct
        RETURN lu.lemma AS lemma, lu.pos AS pos, count(*) AS cnt
        ORDER BY cnt DESC
        LIMIT 50
        """
        lemma_dist = self._run_query(query_lemma)
        patterns["top_lemmas"] = [dict(r) for r in lemma_dist]
        logger.info(f"  Топ лемм: собрано")

        # 1d. POS × dep кросс-таблица (какие POS в каких dependency ролях)
        query_pos_dep = """
        MATCH (lu:LexicalUnit)
        WHERE lu.pos IS NOT NULL AND lu.dep IS NOT NULL
        RETURN lu.pos AS pos, lu.dep AS dep, count(*) AS cnt
        ORDER BY cnt DESC
        LIMIT 100
        """
        pos_dep = self._run_query(query_pos_dep)
        patterns["pos_dep_cross"] = [dict(r) for r in pos_dep]

        # 1e. Глаголы по частоте
        query_verbs = """
        MATCH (lu:LexicalUnit {pos: "VERB"})
        RETURN lu.lemma AS verb, lu.pos_fine AS tense, count(*) AS cnt
        ORDER BY cnt DESC
        LIMIT 50
        """
        verbs = self._run_query(query_verbs)
        patterns["top_verbs"] = [dict(r) for r in verbs]
        logger.info(f"  Топ глаголов: собрано")

        # 1f. Существительные по частоте
        query_nouns = """
        MATCH (lu:LexicalUnit {pos: "NOUN"})
        RETURN lu.lemma AS noun, count(*) AS cnt
        ORDER BY cnt DESC
        LIMIT 50
        """
        nouns = self._run_query(query_nouns)
        patterns["top_nouns"] = [dict(r) for r in nouns]

        # 1g. Прилагательные по частоте
        query_adjs = """
        MATCH (lu:LexicalUnit {pos: "ADJ"})
        RETURN lu.lemma AS adj, count(*) AS cnt
        ORDER BY cnt DESC
        LIMIT 30
        """
        adjs = self._run_query(query_adjs)
        patterns["top_adjectives"] = [dict(r) for r in adjs]

        # 1h. Стоп-слова vs не-стоп-слова
        query_stop = """
        MATCH (lu:LexicalUnit)
        RETURN lu.is_stop AS is_stop, count(*) AS cnt
        ORDER BY is_stop
        """
        stop = self._run_query(query_stop)
        patterns["stop_word_ratio"] = [dict(r) for r in stop]

        self.results["patterns"]["single_lexical"] = patterns
        return patterns

    # -----------------------------------------------------------------------
    # 2. Двухзвенные синтаксические паттерны (DEPENDS_ON)
    # -----------------------------------------------------------------------
    def analyze_bigram_patterns(self):
        """Паттерны из двух связанных LexicalUnit."""
        logger.info("2. Анализ двухзвенных синтаксических паттернов...")

        patterns = {}

        # 2a. nsubj: подлежащее → глагол
        query_nsubj = """
        MATCH (subj:LexicalUnit {pos:"NOUN"})-[:DEPENDS_ON {dep_label:"nsubj"}]->(verb:LexicalUnit {pos:"VERB"})
        RETURN subj.lemma AS subject, verb.lemma AS verb, count(*) AS cnt,
               count(DISTINCT subj.doc_id) AS doc_count
        ORDER BY cnt DESC
        LIMIT 50
        """
        nsubj = self._run_query(query_nsubj)
        patterns["nsubj_patterns"] = [dict(r) for r in nsubj]
        logger.info(f"  nsubj: {len(nsubj)} паттернов")

        # 2b. dobj: глагол → прямое дополнение
        query_dobj = """
        MATCH (verb:LexicalUnit {pos:"VERB"})-[:DEPENDS_ON {dep_label:"dobj"}]->(obj:LexicalUnit {pos:"NOUN"})
        RETURN verb.lemma AS verb, obj.lemma AS object, count(*) AS cnt,
               count(DISTINCT verb.doc_id) AS doc_count
        ORDER BY cnt DESC
        LIMIT 50
        """
        dobj = self._run_query(query_dobj)
        patterns["dobj_patterns"] = [dict(r) for r in dobj]
        logger.info(f"  dobj: {len(dobj)} паттернов")

        # 2c. amod: прилагательное → существительное
        query_amod = """
        MATCH (adj:LexicalUnit {pos:"ADJ"})-[:DEPENDS_ON {dep_label:"amod"}]->(noun:LexicalUnit {pos:"NOUN"})
        RETURN adj.lemma AS adjective, noun.lemma AS noun, count(*) AS cnt,
               count(DISTINCT adj.doc_id) AS doc_count
        ORDER BY cnt DESC
        LIMIT 50
        """
        amod = self._run_query(query_amod)
        patterns["amod_patterns"] = [dict(r) for r in amod]
        logger.info(f"  amod: {len(amod)} паттернов")

        # 2d. compound: составное существительное
        query_compound = """
        MATCH (n1:LexicalUnit)-[:DEPENDS_ON {dep_label:"compound"}]->(n2:LexicalUnit)
        RETURN n1.lemma AS modifier, n2.lemma AS head, count(*) AS cnt,
               count(DISTINCT n1.doc_id) AS doc_count
        ORDER BY cnt DESC
        LIMIT 50
        """
        compound = self._run_query(query_compound)
        patterns["compound_patterns"] = [dict(r) for r in compound]
        logger.info(f"  compound: {len(compound)} паттернов")

        # 2e. advmod: наречие → глагол
        query_advmod = """
        MATCH (adv:LexicalUnit)-[:DEPENDS_ON {dep_label:"advmod"}]->(verb:LexicalUnit {pos:"VERB"})
        RETURN adv.lemma AS adverb, verb.lemma AS verb, count(*) AS cnt,
               count(DISTINCT adv.doc_id) AS doc_count
        ORDER BY cnt DESC
        LIMIT 30
        """
        advmod = self._run_query(query_advmod)
        patterns["advmod_patterns"] = [dict(r) for r in advmod]
        logger.info(f"  advmod: {len(advmod)} паттернов")

        # 2f. prep: предлог → объект
        query_prep = """
        MATCH (head:LexicalUnit)-[:DEPENDS_ON {dep_label:"prep"}]->(prep_node:LexicalUnit)
        RETURN head.lemma AS head, prep_node.text AS preposition, count(*) AS cnt
        ORDER BY cnt DESC
        LIMIT 20
        """
        prep = self._run_query(query_prep)
        patterns["prep_patterns"] = [dict(r) for r in prep]

        # 2g. Все типы DEPENDS_ON — общая сводка
        query_all_deps = """
        MATCH ()-[r:DEPENDS_ON]->()
        RETURN r.dep_label AS dep_type, count(*) AS cnt,
               count(DISTINCT startNode(r).doc_id) AS doc_count
        ORDER BY cnt DESC
        """
        all_deps = self._run_query(query_all_deps)
        patterns["all_dep_types"] = [dict(r) for r in all_deps]
        logger.info(f"  Всего типов зависимостей: {len(all_deps)}")

        # 2h. Пассивные конструкции (nsubj:pass)
        query_passive = """
        MATCH (subj:LexicalUnit)-[:DEPENDS_ON {dep_label:"nsubj:pass"}]->(verb:LexicalUnit {pos:"VERB"})
        RETURN subj.lemma AS subject, verb.lemma AS verb, count(*) AS cnt,
               count(DISTINCT subj.doc_id) AS doc_count
        ORDER BY cnt DESC
        LIMIT 30
        """
        passive = self._run_query(query_passive)
        patterns["passive_patterns"] = [dict(r) for r in passive]

        self.results["patterns"]["bigram_syntactic"] = patterns
        return patterns

    # -----------------------------------------------------------------------
    # 3. Трёхзвенные паттерны
    # -----------------------------------------------------------------------
    def analyze_trigram_patterns(self):
        """Паттерны из трёх связанных LexicalUnit."""
        logger.info("3. Анализ трёхзвенных паттернов...")

        patterns = {}

        # 3a. Полная SVO: субъект → глагол → объект
        query_svo = """
        MATCH (s:LexicalUnit {pos:"NOUN"})-[:DEPENDS_ON {dep_label:"nsubj"}]->(v:LexicalUnit {pos:"VERB"})
              -[:DEPENDS_ON {dep_label:"dobj"}]->(o:LexicalUnit {pos:"NOUN"})
        RETURN s.lemma AS subject, v.lemma AS verb, o.lemma AS object,
               count(*) AS cnt,
               count(DISTINCT s.doc_id) AS doc_count
        ORDER BY cnt DESC
        LIMIT 50
        """
        svo = self._run_query(query_svo)
        patterns["svo_patterns"] = [dict(r) for r in svo]
        logger.info(f"  SVO: {len(svo)} паттернов")

        # 3b. Прил → сущ ← compound (compound modifier)
        query_adj_compound = """
        MATCH (adj:LexicalUnit {pos:"ADJ"})-[:DEPENDS_ON {dep_label:"amod"}]->(n1:LexicalUnit {pos:"NOUN"})
              <-[:DEPENDS_ON {dep_label:"compound"}]-(n2:LexicalUnit {pos:"NOUN"})
        RETURN adj.lemma AS adjective, n1.lemma AS head_noun, n2.lemma AS compound_noun,
               count(*) AS cnt,
               count(DISTINCT adj.doc_id) AS doc_count
        ORDER BY cnt DESC
        LIMIT 30
        """
        adj_compound = self._run_query(query_adj_compound)
        patterns["adj_compound_noun"] = [dict(r) for r in adj_compound]
        logger.info(f"  ADJ→NOUN←compound: {len(adj_compound)} паттернов")

        # 3c. Глагол с advmod и dobj
        query_adv_dobj = """
        MATCH (adv)-[:DEPENDS_ON {dep_label:"advmod"}]->(v:LexicalUnit {pos:"VERB"})
              -[:DEPENDS_ON {dep_label:"dobj"}]->(obj:LexicalUnit)
        RETURN adv.lemma AS adverb, v.lemma AS verb, obj.lemma AS object,
               count(*) AS cnt,
               count(DISTINCT v.doc_id) AS doc_count
        ORDER BY cnt DESC
        LIMIT 30
        """
        adv_dobj = self._run_query(query_adv_dobj)
        patterns["advmod_verb_dobj"] = [dict(r) for r in adv_dobj]

        # 3d. Субъект + глагол + объект (с пассивом)
        query_passive_svo = """
        MATCH (obj:LexicalUnit)-[:DEPENDS_ON {dep_label:"nsubj:pass"}]->(verb:LexicalUnit {pos:"VERB"})
              <-[:DEPENDS_ON {dep_label:"agent"}]-(agent)
        RETURN obj.lemma AS patient, verb.lemma AS verb, agent.lemma AS agent,
               count(*) AS cnt,
               count(DISTINCT obj.doc_id) AS doc_count
        ORDER BY cnt DESC
        LIMIT 20
        """
        passive_svo = self._run_query(query_passive_svo)
        patterns["passive_agent"] = [dict(r) for r in passive_svo]

        self.results["patterns"]["trigram_syntactic"] = patterns
        return patterns

    # -----------------------------------------------------------------------
    # 4. Цепочки переменной длины (DEPENDS_ON)
    # -----------------------------------------------------------------------
    def analyze_dependency_chains(self):
        """Синтаксические цепочки произвольной длины."""
        logger.info("4. Анализ цепочек зависимостей...")

        patterns = {}

        # 4a. Цепочки от глаголов (verb → ... → leaf)
        query_chains = """
        MATCH path = (v:LexicalUnit {pos:"VERB"})-[:DEPENDS_ON*1..4]->(leaf:LexicalUnit)
        WHERE NOT (leaf)-[:DEPENDS_ON]->()
        WITH v.lemma AS verb, length(path) AS depth,
             [n IN nodes(path) | n.text] AS phrase,
             [r IN relationships(path) | r.dep_label] AS deps
        RETURN verb, depth, count(*) AS cnt
        ORDER BY cnt DESC
        LIMIT 50
        """
        chains = self._run_query(query_chains)
        patterns["verb_dependency_chains"] = [dict(r) for r in chains]
        logger.info(f"  Цепочки от глаголов: {len(chains)} уникальных")

        # 4b. Максимальная глубина зависимостей для каждого глагола
        query_max_depth = """
        MATCH path = (v:LexicalUnit {pos:"VERB"})-[:DEPENDS_ON*1..5]->(leaf:LexicalUnit)
        WHERE NOT (leaf)-[:DEPENDS_ON]->()
        RETURN v.lemma AS verb, max(length(path)) AS max_depth,
               count(DISTINCT leaf) AS total_dependents
        ORDER BY max_depth DESC, total_dependents DESC
        LIMIT 30
        """
        max_depth = self._run_query(query_max_depth)
        patterns["verb_max_dependency_depth"] = [dict(r) for r in max_depth]

        # 4c. Цепочки от существительных (сущ ← amod ← ... или сущ ← compound ← ...)
        query_noun_chains = """
        MATCH path = (root:LexicalUnit {pos:"NOUN"})<-[:DEPENDS_ON*1..3]-(modifier:LexicalUnit)
        WHERE NOT (modifier)<-[:DEPENDS_ON]-()
        WITH root.lemma AS noun, length(path) AS depth,
             [n IN nodes(path) | n.text] AS phrase,
             [r IN relationships(path) | r.dep_label] AS deps
        RETURN noun, depth, count(*) AS cnt
        ORDER BY cnt DESC
        LIMIT 30
        """
        noun_chains = self._run_query(query_noun_chains)
        patterns["noun_modifier_chains"] = [dict(r) for r in noun_chains]

        # 4d. Распределение по длине цепочек
        query_chain_lengths = """
        MATCH path = ()-[:DEPENDS_ON*1..5]->()
        WITH length(path) AS chain_length
        RETURN chain_length, count(*) AS cnt
        ORDER BY chain_length
        """
        chain_lengths = self._run_query(query_chain_lengths)
        patterns["chain_length_distribution"] = [dict(r) for r in chain_lengths]

        self.results["patterns"]["dependency_chains"] = patterns
        return patterns

    # -----------------------------------------------------------------------
    # 5. Паттерны уровня Action (LEADS_TO)
    # -----------------------------------------------------------------------
    def analyze_action_patterns(self):
        """Паттерны на уровне Actions (причинно-следственные связи)."""
        logger.info("5. Анализ паттернов уровня Action...")

        patterns = {}

        # 5a. Все пары LEADS_TO
        query_leads_to = """
        MATCH (a1:Action)-[r:LEADS_TO]->(a2:Action)
        RETURN a1.label_text AS source, a2.label_text AS target,
               r.relation_subtype AS relation_type, r.status AS status,
               count(*) AS cnt,
               count(DISTINCT a1.doc_id) AS doc_count
        ORDER BY cnt DESC
        LIMIT 50
        """
        leads_to = self._run_query(query_leads_to)
        patterns["leads_to_pairs"] = [dict(r) for r in leads_to]
        logger.info(f"  LEADS_TO пар: {len(leads_to)}")

        # 5b. Распределение по relation_subtype
        query_rel_subtype = """
        MATCH ()-[r:LEADS_TO]->()
        RETURN r.relation_subtype AS subtype, r.status AS status, count(*) AS cnt
        ORDER BY cnt DESC
        """
        rel_subtype = self._run_query(query_rel_subtype)
        patterns["relation_subtype_distribution"] = [dict(r) for r in rel_subtype]

        # 5c. Распределение по action_class
        query_action_class = """
        MATCH (a:Action)
        RETURN a.action_class AS class, a.verb AS verb, count(*) AS cnt
        ORDER BY cnt DESC
        LIMIT 30
        """
        action_class = self._run_query(query_action_class)
        patterns["action_class_distribution"] = [dict(r) for r in action_class]

        # 5d. Самые «связанные» Actions (out-degree)
        query_out_degree = """
        MATCH (a:Action)-[:LEADS_TO]->(other:Action)
        RETURN a.label_text AS action, a.verb AS verb,
               count(DISTINCT other) AS out_degree
        ORDER BY out_degree DESC
        LIMIT 20
        """
        out_degree = self._run_query(query_out_degree)
        patterns["high_out_degree_actions"] = [dict(r) for r in out_degree]

        # 5e. Самые «популярные» целевые Actions (in-degree)
        query_in_degree = """
        MATCH (a:Action)<-[:LEADS_TO]-(other:Action)
        RETURN a.label_text AS action, a.verb AS verb,
               count(DISTINCT other) AS in_degree
        ORDER BY in_degree DESC
        LIMIT 20
        """
        in_degree = self._run_query(query_in_degree)
        patterns["high_in_degree_actions"] = [dict(r) for r in in_degree]

        # 5f. Actions со статусом pending/confirmed/rejected
        query_status = """
        MATCH ()-[r:LEADS_TO]->()
        RETURN r.status AS status, count(*) AS cnt
        ORDER BY cnt DESC
        """
        status = self._run_query(query_status)
        patterns["edge_status_distribution"] = [dict(r) for r in status]

        # 5g. Топ глаголов в Actions
        query_action_verbs = """
        MATCH (a:Action)
        RETURN a.verb AS verb, count(*) AS cnt,
               count(DISTINCT a.doc_id) AS doc_count
        ORDER BY cnt DESC
        LIMIT 30
        """
        action_verbs = self._run_query(query_action_verbs)
        patterns["top_action_verbs"] = [dict(r) for r in action_verbs]

        self.results["patterns"]["action_level"] = patterns
        return patterns

    # -----------------------------------------------------------------------
    # 6. Цепочки LEADS_TO переменной длины
    # -----------------------------------------------------------------------
    def analyze_leads_to_chains(self):
        """Цепочки причинно-следственных связей."""
        logger.info("6. Анализ цепочек LEADS_TO...")

        patterns = {}

        # 6a. Цепочки длиной 2-5 шагов
        query_chains = """
        MATCH path = (start:Action)-[:LEADS_TO*2..5]->(end:Action)
        WHERE all(r IN relationships(path) WHERE r.status = "confirmed" OR r.status IS NULL)
        WITH length(path) AS steps,
             [n IN nodes(path) | n.label_text] AS chain,
             [n IN nodes(path) | n.verb] AS verbs
        RETURN steps, count(*) AS cnt
        ORDER BY steps
        """
        chains = self._run_query(query_chains)
        patterns["chain_length_distribution"] = [dict(r) for r in chains]
        logger.info(f"  Распределение по длине цепочек: {len(chains)} уровней")

        # 6b. Самые длинные цепочки
        query_longest = """
        MATCH path = (start:Action)-[:LEADS_TO*2..5]->(end:Action)
        WHERE NOT (end)-[:LEADS_TO]->()
        RETURN start.label_text AS start,
               end.label_text AS end,
               length(path) AS steps,
               [n IN nodes(path) | n.label_text] AS chain
        ORDER BY steps DESC
        LIMIT 20
        """
        longest = self._run_query(query_longest)
        patterns["longest_chains"] = [dict(r) for r in longest]

        # 6c. Расходящиеся паттерны: один Action → много последствий
        query_diverging = """
        MATCH (start:Action)-[:LEADS_TO*1..3]->(end:Action)
        RETURN start.label_text AS start_action, start.verb AS verb,
               count(DISTINCT end) AS reach
        ORDER BY reach DESC
        LIMIT 15
        """
        diverging = self._run_query(query_diverging)
        patterns["diverging_patterns"] = [dict(r) for r in diverging]
        logger.info(f"  Расходящиеся паттерны: собрано")

        # 6d. Сходящиеся паттерны: много Actions → один результат
        query_converging = """
        MATCH (a1:Action)-[:LEADS_TO]->(common:Action)<-[:LEADS_TO]-(a2:Action)
        WHERE a1.uid < a2.uid
        RETURN common.label_text AS target,
               a1.label_text AS source1,
               a2.label_text AS source2,
               count(*) AS cnt
        ORDER BY cnt DESC
        LIMIT 20
        """
        converging = self._run_query(query_converging)
        patterns["converging_2to1"] = [dict(r) for r in converging]
        logger.info(f"  Сходящиеся паттерны (2→1): собрано")

        # 6e. Сходящиеся паттерны 3→1
        query_converging3 = """
        MATCH (a1:Action)-[:LEADS_TO]->(d:Action)
              <-[:LEADS_TO]-(a2:Action)
              <-[:LEADS_TO]-(a3:Action)
        WHERE a1.uid < a2.uid AND a2.uid < a3.uid
        RETURN d.label_text AS target,
               count(DISTINCT a1) + count(DISTINCT a2) + count(DISTINCT a3) AS sources_count
        ORDER BY sources_count DESC
        LIMIT 15
        """
        converging3 = self._run_query(query_converging3)
        patterns["converging_3to1"] = [dict(r) for r in converging3]

        # 6f. Цепочки с фильтрацией по verb
        query_verb_chains = """
        MATCH path = (start:Action)-[:LEADS_TO*1..4]->(end:Action)
        WHERE start.verb IN ["inhibit", "activate", "reduce", "increase", "induce", "promote"]
        RETURN start.verb AS start_verb, length(path) AS steps,
               end.label_text AS end_action,
               [n IN nodes(path) | n.label_text] AS chain
        ORDER BY steps DESC
        LIMIT 30
        """
        verb_chains = self._run_query(query_verb_chains)
        patterns["key_verb_chains"] = [dict(r) for r in verb_chains]

        self.results["patterns"]["leads_to_chains"] = patterns
        return patterns

    # -----------------------------------------------------------------------
    # 7. Кросс-документные паттерны
    # -----------------------------------------------------------------------
    def analyze_cross_document_patterns(self):
        """Паттерны, повторяющиеся в разных документах."""
        logger.info("7. Анализ кросс-документных паттернов...")

        patterns = {}

        # 7a. Одинаковые syntactic паттерны в разных статьях
        query_cross_syn = """
        MATCH (v1:LexicalUnit {pos:"VERB"})-[:DEPENDS_ON {dep_label:"dobj"}]->(o1:LexicalUnit {pos:"NOUN"})
        WITH v1.lemma AS verb, o1.lemma AS obj,
             count(DISTINCT v1.doc_id) AS docs,
             count(*) AS total
        WHERE docs > 1
        RETURN verb, obj, docs, total
        ORDER BY docs DESC, total DESC
        LIMIT 50
        """
        cross_syn = self._run_query(query_cross_syn)
        patterns["cross_doc_verb_obj"] = [dict(r) for r in cross_syn]
        logger.info(f"  Verb+Obj в разных документах: {len(cross_syn)} паттернов")

        # 7b. Одинаковые SVO в разных статьях
        query_cross_svo = """
        MATCH (s:LexicalUnit {pos:"NOUN"})-[:DEPENDS_ON {dep_label:"nsubj"}]->(v:LexicalUnit {pos:"VERB"})
              -[:DEPENDS_ON {dep_label:"dobj"}]->(o:LexicalUnit {pos:"NOUN"})
        WITH s.lemma AS subj, v.lemma AS verb, o.lemma AS obj,
             count(DISTINCT s.doc_id) AS docs,
             count(*) AS total
        WHERE docs > 1
        RETURN subj, verb, obj, docs, total
        ORDER BY docs DESC, total DESC
        LIMIT 30
        """
        cross_svo = self._run_query(query_cross_svo)
        patterns["cross_doc_svo"] = [dict(r) for r in cross_svo]
        logger.info(f"  SVO в разных документах: {len(cross_svo)} паттернов")

        # 7c. Одинаковые amod в разных статьях
        query_cross_amod = """
        MATCH (adj:LexicalUnit {pos:"ADJ"})-[:DEPENDS_ON {dep_label:"amod"}]->(noun:LexicalUnit {pos:"NOUN"})
        WITH adj.lemma AS adj, noun.lemma AS noun,
             count(DISTINCT adj.doc_id) AS docs,
             count(*) AS total
        WHERE docs > 1
        RETURN adj, noun, docs, total
        ORDER BY docs DESC, total DESC
        LIMIT 30
        """
        cross_amod = self._run_query(query_cross_amod)
        patterns["cross_doc_amod"] = [dict(r) for r in cross_amod]

        # 7d. LEADS_TO между Actions из разных документов (агрегированные)
        query_cross_leads = """
        MATCH (a1:Action)-[r:LEADS_TO]->(a2:Action)
        WHERE a1.doc_id <> a2.doc_id
        RETURN a1.label_text AS source, a2.label_text AS target,
               r.relation_subtype AS relation_type,
               count(DISTINCT a1.doc_id + a2.doc_id) AS doc_pairs
        ORDER BY doc_pairs DESC
        LIMIT 20
        """
        cross_leads = self._run_query(query_cross_leads)
        patterns["cross_doc_leads_to"] = [dict(r) for r in cross_leads]

        # 7e. Самые кросс-документные глаголы
        query_cross_verbs = """
        MATCH (v:LexicalUnit {pos:"VERB"})
        RETURN v.lemma AS verb,
               count(DISTINCT v.doc_id) AS doc_count,
               count(*) AS total_occurrences
        ORDER BY doc_count DESC
        LIMIT 30
        """
        cross_verbs = self._run_query(query_cross_verbs)
        patterns["cross_doc_verbs"] = [dict(r) for r in cross_verbs]

        # 7f. Кросс-документные compound
        query_cross_compound = """
        MATCH (n1)-[:DEPENDS_ON {dep_label:"compound"}]->(n2:LexicalUnit {pos:"NOUN"})
        WITH n1.lemma AS modifier, n2.lemma AS head,
             count(DISTINCT n1.doc_id) AS docs,
             count(*) AS total
        WHERE docs > 1
        RETURN modifier, head, docs, total
        ORDER BY docs DESC, total DESC
        LIMIT 30
        """
        cross_compound = self._run_query(query_cross_compound)
        patterns["cross_doc_compound"] = [dict(r) for r in cross_compound]

        self.results["patterns"]["cross_document"] = patterns
        return patterns

    # -----------------------------------------------------------------------
    # 8. Смешанные паттерны (LexicalUnit + Action)
    # -----------------------------------------------------------------------
    def analyze_mixed_patterns(self):
        """Паттерны, связывающие LexicalUnit и Action."""
        logger.info("8. Анализ смешанных паттернов...")

        patterns = {}

        # 8a. Action с определёнными глаголами (через LexicalUnit)
        query_action_lex = """
        MATCH (lu:LexicalUnit {pos:"VERB"})-[:PART_OF]->(a:Action)
        RETURN lu.lemma AS verb, a.action_class AS class,
               count(*) AS cnt,
               count(DISTINCT a.doc_id) AS doc_count
        ORDER BY cnt DESC
        LIMIT 30
        """
        action_lex = self._run_query(query_action_lex)
        patterns["action_lexical_overlap"] = [dict(r) for r in action_lex]
        logger.info(f"  Action+LexicalUnit: собрано")

        # 8b. LEADS_TO где оба Action содержат определённые глаголы
        query_leads_lex = """
        MATCH (a1:Action)-[:LEADS_TO]->(a2:Action)
              <-[:PART_OF]-(v2:LexicalUnit {pos:"VERB"}),
              (a1)<-[:PART_OF]-(v1:LexicalUnit {pos:"VERB"})
        RETURN v1.lemma AS source_verb, v2.lemma AS target_verb,
               count(*) AS cnt,
               count(DISTINCT a1.doc_id) AS doc_count
        ORDER BY cnt DESC
        LIMIT 30
        """
        leads_lex = self._run_query(query_leads_lex)
        patterns["leads_to_verb_pairs"] = [dict(r) for r in leads_lex]
        logger.info(f"  LEADS_TO verb pairs: собрано")

        # 8c. Действия, связанные с конкретными существительными
        query_action_noun = """
        MATCH (noun:LexicalUnit {pos:"NOUN"})-[:PART_OF]->(a:Action)
              -[:LEADS_TO]->(result:Action)
        RETURN noun.lemma AS noun_in_source, result.label_text AS result_action,
               count(*) AS cnt
        ORDER BY cnt DESC
        LIMIT 20
        """
        action_noun = self._run_query(query_action_noun)
        patterns["noun_in_source_leads_to_result"] = [dict(r) for r in action_noun]

        self.results["patterns"]["mixed_level"] = patterns
        return patterns

    # -----------------------------------------------------------------------
    # 9. SYNTACTIC_DEP паттерны
    # -----------------------------------------------------------------------
    def analyze_syntactic_dep_patterns(self):
        """Паттерны синтаксических зависимостей между Actions."""
        logger.info("9. Анализ SYNTACTIC_DEP паттернов...")

        patterns = {}

        # 9a. Распределение по dep_label
        query_syn_dep = """
        MATCH (a1:Action)-[r:SYNTACTIC_DEP]->(a2:Action)
        RETURN r.dep_label AS dep_type, count(*) AS cnt,
               count(DISTINCT a1.doc_id) AS doc_count
        ORDER BY cnt DESC
        """
        syn_dep = self._run_query(query_syn_dep)
        patterns["syntactic_dep_distribution"] = [dict(r) for r in syn_dep]
        logger.info(f"  SYNTACTIC_DEP типов: {len(syn_dep)}")

        # 9b. Конкретные пары с SYNTACTIC_DEP
        query_syn_dep_pairs = """
        MATCH (a1:Action)-[r:SYNTACTIC_DEP]->(a2:Action)
        RETURN a1.label_text AS source, a2.label_text AS target,
               r.dep_label AS dep_type, count(*) AS cnt
        ORDER BY cnt DESC
        LIMIT 20
        """
        syn_dep_pairs = self._run_query(query_syn_dep_pairs)
        patterns["syntactic_dep_pairs"] = [dict(r) for r in syn_dep_pairs]

        self.results["patterns"]["syntactic_dep"] = patterns
        return patterns

    # -----------------------------------------------------------------------
    # 10. LinguisticPattern (извлечённые паттерны)
    # -----------------------------------------------------------------------
    def analyze_linguistic_patterns_entity(self):
        """Анализ сущностей LinguisticPattern (если они есть в БД)."""
        logger.info("10. Анализ LinguisticPattern сущностей...")

        patterns = {}

        # 10a. Существование LinguisticPattern
        count_lp = self._count_nodes("LinguisticPattern")
        patterns["total_linguistic_patterns"] = count_lp
        logger.info(f"  LinguisticPattern узлов: {count_lp:,}")

        if count_lp > 0:
            # 10b. Распределение по pattern_type
            query_pattern_type = """
            MATCH (lp:LinguisticPattern)
            RETURN lp.pattern_type AS type, lp.annotation_type AS annotation,
                   count(*) AS cnt
            ORDER BY cnt DESC
            """
            pattern_type = self._run_query(query_pattern_type)
            patterns["pattern_type_distribution"] = [dict(r) for r in pattern_type]

            # 10c. Топ паттернов по frequency
            query_top_freq = """
            MATCH (lp:LinguisticPattern)
            RETURN lp.pattern_str AS pattern, lp.frequency AS freq,
                   lp.pattern_type AS type, count(*) AS cnt
            ORDER BY freq DESC
            LIMIT 30
            """
            top_freq = self._run_query(query_top_freq)
            patterns["top_frequency_patterns"] = [dict(r) for r in top_freq]

        self.results["patterns"]["linguistic_pattern_entity"] = patterns
        return patterns

    # -----------------------------------------------------------------------
    # 11. Расчёт устойчивости паттернов
    # -----------------------------------------------------------------------
    def calculate_pattern_stability(self):
        """Расчёт метрик устойчивости для найденных паттернов."""
        logger.info("11. Расчёт устойчивости паттернов...")

        stability = {}

        # 11a. Устойчивость verb+obj: отношение doc_count к total
        if "bigram_syntactic" in self.results["patterns"]:
            dobj_patterns = self.results["patterns"]["bigram_syntactic"].get("dobj_patterns", [])
            if dobj_patterns:
                stability_scores = []
                for p in dobj_patterns:
                    total = p.get("cnt", 0)
                    docs = p.get("doc_count", 1)
                    # Устойчивость = насколько паттерн повторяется в разных документах
                    score = docs / total if total > 0 else 0
                    stability_scores.append({
                        "pattern": f"{p.get('verb')} → {p.get('object')}",
                        "total": total,
                        "docs": docs,
                        "stability_score": round(score, 4),
                        "avg_per_doc": round(total / docs, 2) if docs > 0 else 0,
                    })
                stability_scores.sort(key=lambda x: x["stability_score"], reverse=True)
                stability["verb_obj_stability"] = stability_scores[:30]
                logger.info(f"  Устойчивость verb+obj: рассчитана для {len(stability_scores)} паттернов")

        # 11b. Устойчивость SVO
        if "trigram_syntactic" in self.results["patterns"]:
            svo_patterns = self.results["patterns"]["trigram_syntactic"].get("svo_patterns", [])
            if svo_patterns:
                svo_stability = []
                for p in svo_patterns:
                    total = p.get("cnt", 0)
                    docs = p.get("doc_count", 1)
                    score = docs / total if total > 0 else 0
                    svo_stability.append({
                        "pattern": f"{p.get('subject')} → {p.get('verb')} → {p.get('object')}",
                        "total": total,
                        "docs": docs,
                        "stability_score": round(score, 4),
                        "avg_per_doc": round(total / docs, 2) if docs > 0 else 0,
                    })
                svo_stability.sort(key=lambda x: x["stability_score"], reverse=True)
                stability["svo_stability"] = svo_stability[:30]
                logger.info(f"  Устойчивость SVO: рассчитана для {len(svo_stability)} паттернов")

        # 11c. Устойчивость amod
        if "bigram_syntactic" in self.results["patterns"]:
            amod_patterns = self.results["patterns"]["bigram_syntactic"].get("amod_patterns", [])
            if amod_patterns:
                amod_stability = []
                for p in amod_patterns:
                    total = p.get("cnt", 0)
                    docs = p.get("doc_count", 1)
                    score = docs / total if total > 0 else 0
                    amod_stability.append({
                        "pattern": f"{p.get('adjective')} + {p.get('noun')}",
                        "total": total,
                        "docs": docs,
                        "stability_score": round(score, 4),
                        "avg_per_doc": round(total / docs, 2) if docs > 0 else 0,
                    })
                amod_stability.sort(key=lambda x: x["stability_score"], reverse=True)
                stability["amod_stability"] = amod_stability[:30]

        # 11d. Кросс-документная устойчивость (из cross_document)
        if "cross_document" in self.results["patterns"]:
            cross_svo = self.results["patterns"]["cross_document"].get("cross_doc_svo", [])
            if cross_svo:
                cross_stability = []
                for p in cross_svo:
                    docs = p.get("docs", 0)
                    total = p.get("total", 1)
                    cross_stability.append({
                        "pattern": f"{p.get('subj')} → {p.get('verb')} → {p.get('obj')}",
                        "doc_count": docs,
                        "total": total,
                        "stability_score": round(docs / total, 4) if total > 0 else 0,
                    })
                cross_stability.sort(key=lambda x: x["doc_count"], reverse=True)
                stability["cross_doc_svo_stability"] = cross_stability[:30]
                logger.info(f"  Кросс-документная устойчивость: рассчитана")

        self.results["pattern_stability"] = stability
        return stability

    # -----------------------------------------------------------------------
    # 12. Итоговая сводка
    # -----------------------------------------------------------------------
    def generate_summary(self):
        """Генерация итоговой сводки."""
        logger.info("12. Генерация итоговой сводки...")

        summary = {
            "total_patterns_found": 0,
            "most_stable_patterns": [],
            "pattern_categories": {},
        }

        # Считаем общее количество паттернов
        patterns = self.results["patterns"]
        for category, data in patterns.items():
            if isinstance(data, dict):
                summary["pattern_categories"][category] = len(data)
                for key, val in data.items():
                    if isinstance(val, list):
                        summary["total_patterns_found"] += len(val)

        # Находим самые устойчивые паттерны
        stability = self.results.get("pattern_stability", {})

        # Собираем топ-10 самых устойчивых из всех категорий
        all_stable = []
        for category, items in stability.items():
            if isinstance(items, list):
                for item in items:
                    if "stability_score" in item and item.get("docs", 0) > 1:
                        all_stable.append(item)

        all_stable.sort(key=lambda x: (x.get("stability_score", 0), x.get("docs", 0)), reverse=True)
        summary["most_stable_patterns"] = all_stable[:20]

        # Статистика по графу
        stats = self.results.get("graph_stats", {})
        summary["graph_summary"] = {
            "total_actions": stats.get("node_counts", {}).get("Action", 0),
            "total_lexical_units": stats.get("node_counts", {}).get("LexicalUnit", 0),
            "total_leads_to": stats.get("relationship_counts", {}).get("LEADS_TO", 0),
            "total_depends_on": stats.get("relationship_counts", {}).get("DEPENDS_ON", 0),
        }

        self.results["summary"] = summary
        return summary

    # -----------------------------------------------------------------------
    # Вывод результатов
    # -----------------------------------------------------------------------
    def save_results(self):
        """Сохраняет результаты в JSON и TXT."""
        # JSON
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        logger.info(f"Результаты сохранены в {OUTPUT_FILE}")

        # TXT отчёт
        self._save_text_report()
        logger.info(f"Текстовый отчёт сохранён в {OUTPUT_TXT}")

    def _save_text_report(self):
        """Генерирует человекочитаемый текстовый отчёт."""
        lines = []
        lines.append("=" * 100)
        lines.append("ОТЧЁТ: АНАЛИЗ ЛИНГВИСТИЧЕСКИХ ПАТТЕРНОВ В NEO4J")
        lines.append("=" * 100)
        lines.append(f"Дата анализа: {self.results['analysis_date']}")
        lines.append(f"База данных: {self.results['database']}")
        lines.append("")

        # Граф
        stats = self.results.get("graph_stats", {})
        lines.append("─" * 100)
        lines.append("ОБЩАЯ СТАТИСТИКА ГРАФА")
        lines.append("─" * 100)
        for label, cnt in stats.get("node_counts", {}).items():
            lines.append(f"  {label}: {cnt:,} узлов")
        for rel, cnt in stats.get("relationship_counts", {}).items():
            lines.append(f"  {rel}: {cnt:,} рёбер")
        lines.append("")

        # Паттерны по категориям
        for category, patterns in self.results["patterns"].items():
            lines.append("─" * 100)
            lines.append(f"КАТЕГОРИЯ: {category}")
            lines.append("─" * 100)

            if isinstance(patterns, dict):
                for pattern_name, items in patterns.items():
                    if isinstance(items, list) and items:
                        lines.append("")
                        lines.append(f"  [{pattern_name}] ({len(items)} элементов)")
                        lines.append(f"  {'Топ-10 по частоте:':40s}")

                        for i, item in enumerate(items[:10], 1):
                            # Формируем читаемое представление
                            parts = []
                            for k, v in item.items():
                                if k not in ("cnt", "count"):
                                    parts.append(f"{k}={v}")
                            cnt_val = item.get("cnt", item.get("count", ""))
                            desc = ", ".join(parts)
                            lines.append(f"    {i:3d}. [{cnt_val:>6}] {desc}")

            lines.append("")

        # Устойчивость
        stability = self.results.get("pattern_stability", {})
        if stability:
            lines.append("─" * 100)
            lines.append("УСТОЙЧИВОСТЬ ПАТТЕРНОВ")
            lines.append("─" * 100)

            for category, items in stability.items():
                if isinstance(items, list) and items:
                    lines.append("")
                    lines.append(f"  [{category}]")
                    lines.append(f"  {'Паттерн':50s} {'Score':>8} {'Docs':>6} {'Total':>6}")

                    for item in items[:15]:
                        pattern = item.get("pattern", "")[:50]
                        score = item.get("stability_score", 0)
                        docs = item.get("docs", item.get("doc_count", 0))
                        total = item.get("total", 0)
                        lines.append(f"  {pattern:50s} {score:>8.4f} {docs:>6} {total:>6}")

            lines.append("")

        # Топ-20 самых устойчивых
        summary = self.results.get("summary", {})
        most_stable = summary.get("most_stable_patterns", [])
        if most_stable:
            lines.append("─" * 100)
            lines.append("ТОП-20 САМЫХ УСТОЙЧИВЫХ ПАТТЕРНОВ (общий рейтинг)")
            lines.append("─" * 100)
            for i, item in enumerate(most_stable, 1):
                pattern = item.get("pattern", "")
                score = item.get("stability_score", 0)
                docs = item.get("docs", item.get("doc_count", 0))
                total = item.get("total", 0)
                lines.append(f"  {i:3d}. {score:.4f} | {docs:3d} docs | {total:5d} total | {pattern}")
            lines.append("")

        # Итог
        lines.append("=" * 100)
        lines.append("ИТОГО")
        lines.append("=" * 100)
        lines.append(f"Всего паттернов найдено: {summary.get('total_patterns_found', 0)}")
        graph = summary.get("graph_summary", {})
        lines.append(f"  Actions: {graph.get('total_actions', 0):,}")
        lines.append(f"  LexicalUnit: {graph.get('total_lexical_units', 0):,}")
        lines.append(f"  LEADS_TO: {graph.get('total_leads_to', 0):,}")
        lines.append(f"  DEPENDS_ON: {graph.get('total_depends_on', 0):,}")
        lines.append(f"Категорий паттернов: {len(summary.get('pattern_categories', {}))}")
        lines.append("")

        with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    logger.info("=" * 60)
    logger.info("АНАЛИЗ ЛИНГВИСТИЧЕСКИХ ПАТТЕРНОВ")
    logger.info("=" * 60)

    analyzer = PatternAnalyzer(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        # 0. Общая статистика
        analyzer.analyze_graph_stats()

        # 1-4. Синтаксические паттерны (LexicalUnit уровень)
        analyzer.analyze_single_lexical_patterns()
        analyzer.analyze_bigram_patterns()
        analyzer.analyze_trigram_patterns()
        analyzer.analyze_dependency_chains()

        # 5-6. Паттерны Actions (LEADS_TO уровень)
        analyzer.analyze_action_patterns()
        analyzer.analyze_leads_to_chains()

        # 7. Кросс-документные паттерны
        analyzer.analyze_cross_document_patterns()

        # 8. Смешанные паттерны
        analyzer.analyze_mixed_patterns()

        # 9. SYNTACTIC_DEP паттерны
        analyzer.analyze_syntactic_dep_patterns()

        # 10. LinguisticPattern сущности
        analyzer.analyze_linguistic_patterns_entity()

        # 11. Расчёт устойчивости
        analyzer.calculate_pattern_stability()

        # 12. Итоговая сводка
        analyzer.generate_summary()

        # Сохранение
        analyzer.save_results()

        logger.info("=" * 60)
        logger.info("АНАЛИЗ ЗАВЕРШЁН УСПЕШНО")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Ошибка при анализе: {e}", exc_info=True)
        raise
    finally:
        analyzer.close()


if __name__ == "__main__":
    main()
