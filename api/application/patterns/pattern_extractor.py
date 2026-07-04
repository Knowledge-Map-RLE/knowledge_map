"""
Layer: Application (Use Cases)
Package: application.patterns.pattern_extractor
Responsibility: Извлечение паттернов как графов Action + LexicalUnit.

Паттерн — это подграф произвольной топологии (от 1 до ~100 вершин),
состоящий из:
  - Action-узлов (глаголы + зависимые слова)
  - LexicalUnit-узлов (существительные, прилагательные, наречия)
  - Рёбер LEADS_TO, DEPENDS_ON, PART_OF

Включает функциональность, аналогичную analyze_dependency_ngrams:
  - Dependency n-gram цепочки (как часть паттерна)
  - Action-цепочки (LEADS_TO)
  - Смешанные паттерны (Action + LexicalUnit)

Allowed imports: typing, collections, dataclasses, json, logging, hashlib, uuid, uuid
                 domain.*, application.patterns.unified_pattern_analyzer
Forbidden imports: neomodel, fastapi, grpc, infrastructure, adapters, web
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter, defaultdict

from src.uuid8 import uuid8_str
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from domain.models.pattern import (
    NodeRole,
    Pattern,
    PatternEdge,
    PatternEdgeType,
    PatternInstance,
    PatternNode,
    PatternNodeType,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Result
# =============================================================================

@dataclass
class PatternExtractionResult:
    """Результат извлечения паттернов."""
    patterns: List[Pattern]
    total_patterns: int
    max_nodes_seen: int
    extraction_mode: str  # "document" | "global"
    doc_ids: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patterns": [p.to_dict() for p in self.patterns],
            "total_patterns": self.total_patterns,
            "max_nodes_seen": self.max_nodes_seen,
            "extraction_mode": self.extraction_mode,
            "doc_ids": self.doc_ids,
        }


# =============================================================================
# Helpers
# =============================================================================

def _canonical_node_key(
    node_type: PatternNodeType,
    lemma: str,
    pos: str = "",
    action_class: str = "",
) -> str:
    """Канонический ключ узла для дедупликации."""
    if node_type == PatternNodeType.ACTION:
        return f"ACT:{action_class}:{lemma}"
    return f"LU:{pos}:{lemma}"


def _role_from_dep_label(dep_label: str) -> NodeRole:
    """Определяет роль узла по типу зависимости."""
    role_map = {
        "nsubj": NodeRole.SUBJECT,
        "nsubjpass": NodeRole.SUBJECT,
        "dobj": NodeRole.OBJECT,
        "pobj": NodeRole.OBJECT,
        "amod": NodeRole.MODIFIER,
        "advmod": NodeRole.MODIFIER,
        "compound": NodeRole.COMPOUND,
        "prep": NodeRole.MODIFIER,
        "aux": NodeRole.MODIFIER,
        "det": NodeRole.MODIFIER,
    }
    return role_map.get(dep_label, NodeRole.MODIFIER)


def _size_category(n: int) -> str:
    if n == 1:
        return "unigram"
    elif n <= 3:
        return "small"
    elif n <= 10:
        return "medium"
    elif n <= 30:
        return "large"
    else:
        return "xlarge"


# =============================================================================
# PatternExtractor
# =============================================================================

class PatternExtractor:
    """
    Извлекает паттерны из графа Neo4j.

    Работает напрямую с Neo4j driver (не через neomodel) для производительности.
    Включает функциональность analyze_dependency_ngrams как один из режимов.

    Режимы:
      - extract_from_document(doc_id) — паттерны одного документа
      - extract_global(max_patterns, max_nodes) — глобальные паттерны
      - extract_dependency_ngrams(max_depth, limit_per_n) — аналог analyze_dependency_ngrams
    """

    def __init__(self, driver):
        """
        :param driver: neo4j.GraphDatabase.driver instance
        """
        self.driver = driver

    def _run_query(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        with self.driver.session() as session:
            result = session.run(query, params or {})
            return [dict(record) for record in result]

    # ------------------------------------------------------------------
    # Public API: extract_dependency_ngrams (аналог analyze_dependency_ngrams)
    # ------------------------------------------------------------------

    def extract_dependency_ngrams(
        self,
        max_depth: int = 5,
        limit_per_n: int = 50,
        max_exemplars: int = 100,
        doc_id: Optional[str] = None,
    ) -> PatternExtractionResult:
        """
        Извлекает dependency n-gram паттерны как Pattern-объекты.

        Аналог analyze_dependency_ngrams из UnifiedPatternAnalyzer,
        но возвращает полноценные Pattern с канонической структурой.

        Алгоритм (DP с memoization, как в оригинале):
          1. Загружаем граф DEPENDS_ON в память (adjacency list)
          2. DP: memo[node, depth] → Counter сигнатур + exemplars
          3. Преобразуем топ-n-граммы в Pattern-объекты

        :param max_depth: максимальная глубина (1..10)
        :param limit_per_n: лимит паттернов для каждой длины
        :param max_exemplars: макс. цепочек на сигнатуру
        :param doc_id: фильтр по документу (None = все документы)
        """
        clamped_depth = max(1, min(max_depth, 10))
        results: List[Pattern] = []
        max_nodes_seen = 0

        # --- 1. Загружаем граф DEPENDS_ON ---
        doc_filter = "WHERE lu.doc_id = $doc_id AND lu2.doc_id = $doc_id" if doc_id else ""
        edges_data = self._run_query(
            f"""
            MATCH (lu:LexicalUnit)-[r:DEPENDS_ON]->(lu2:LexicalUnit)
            {doc_filter}
            RETURN
                id(lu) AS sid,
                id(lu2) AS tid,
                coalesce(lu.text, lu.lemma, '') AS s_text,
                coalesce(lu2.text, lu2.lemma, '') AS t_text,
                coalesce(lu.lemma, '') AS s_lemma,
                coalesce(lu2.lemma, '') AS t_lemma,
                coalesce(lu.pos, '') AS s_pos,
                coalesce(lu2.pos, '') AS t_pos,
                coalesce(lu.doc_id, '') AS doc_id,
                coalesce(r.dep_label, '') AS dep_label
            """,
            {"doc_id": doc_id} if doc_id else None,
        )

        out_edges: Dict[int, List[Tuple[str, int]]] = defaultdict(list)
        in_degree: Dict[int, int] = defaultdict(int)
        all_node_ids: Set[int] = set()
        node_info: Dict[int, Dict] = {}

        for row in edges_data:
            sid, tid = row["sid"], row["tid"]
            all_node_ids.add(sid)
            all_node_ids.add(tid)
            dep_label = row["dep_label"] or ""
            rel_key = f"DEPENDS_ON:{dep_label}"
            out_edges[sid].append((rel_key, tid))
            in_degree[tid] += 1
            in_degree.setdefault(sid, in_degree.get(sid, 0))

            node_info[sid] = {
                "text": row["s_text"],
                "lemma": row["s_lemma"],
                "pos": row["s_pos"],
                "doc_id": row["doc_id"],
            }
            node_info[tid] = {
                "text": row["t_text"],
                "lemma": row["t_lemma"],
                "pos": row["t_pos"],
                "doc_id": row["doc_id"],
            }

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

            node_text = node_info.get(node_id, {}).get("text", str(node_id))
            node_pos = node_info.get(node_id, {}).get("pos", "")

            if depth == 1:
                sig = (node_text, node_pos)
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
                    new_sig = (node_text, node_pos, rel) + child_sig
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

        # --- 4. Собираем результаты по каждой глубине ---
        doc_ids_set: Set[str] = set()

        for depth in range(1, clamped_depth + 1):
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

            top = depth_counter.most_common(limit_per_n)
            for h, cnt in top:
                sig = sig_text[h]
                # Преобразуем сигнатуру в Pattern
                pattern = self._sig_to_pattern(sig, h, cnt, depth, depth_exemplars.get(h, []), doc_id)
                if pattern:
                    pattern.frequency = cnt
                    doc_ids = set()
                    for chain in depth_exemplars.get(h, [])[:10]:
                        for nid in chain:
                            d = node_info.get(nid, {}).get("doc_id", "")
                            if d:
                                doc_ids.add(d)
                    pattern.doc_count = len(doc_ids)
                    pattern.stability = round(pattern.doc_count / cnt, 4) if cnt > 0 else 0.0
                    doc_ids_set.update(doc_ids)

                    # Собираем instances
                    for chain in depth_exemplars.get(h, [])[:min(5, len(depth_exemplars.get(h, [])))]:
                        mapping = {}
                        for i, nid in enumerate(chain):
                            info = node_info.get(nid, {})
                            node_key = f"node_{i}"
                            mapping[node_key] = str(nid)
                            if info.get("doc_id"):
                                pattern.instances.append(PatternInstance(
                                    node_mapping=mapping.copy(),
                                    doc_id=info["doc_id"],
                                ))

                    max_nodes_seen = max(max_nodes_seen, pattern.node_count)
                    results.append(pattern)

        return PatternExtractionResult(
            patterns=results,
            total_patterns=len(results),
            max_nodes_seen=max_nodes_seen,
            extraction_mode="document" if doc_id else "global",
            doc_ids=list(doc_ids_set),
        )

    def _sig_to_pattern(
        self,
        sig: tuple,
        sig_hash_int: int,
        cnt: int,
        depth: int,
        exemplar_chains: List[List[int]],
        doc_id: Optional[str],
    ) -> Optional[Pattern]:
        """Преобразует сигнатуру DP в Pattern-объект."""
        if not sig:
            return None

        pattern_hash = f"{abs(sig_hash_int):016x}"[:16]
        pattern_uid = uuid8_str()

        # Строим узлы и рёбра из сигнатуры
        # Сигнатура: (text, pos, rel, text, pos, rel, ..., text, pos)
        nodes: List[PatternNode] = []
        edges: List[PatternEdge] = []

        n_tokens = len(sig) // 2  # каждое слово = (text, pos)
        for i in range(n_tokens):
            text_idx = i * 2
            pos_idx = i * 2 + 1
            text = sig[text_idx] if text_idx < len(sig) else ""
            pos = sig[pos_idx] if pos_idx < len(sig) else ""
            rel = sig[pos_idx + 1] if pos_idx + 1 < len(sig) and (pos_idx + 1) % 2 == 1 else ""

            node_id = f"node_{i}"
            role = NodeRole.VERB if pos == "VERB" else _role_from_dep_label(rel.split(":")[-1] if ":" in rel else rel)

            nodes.append(PatternNode(
                node_id=node_id,
                node_type=PatternNodeType.LEXICAL_UNIT,
                role=role,
                text=text,
                lemma=text,
                pos=pos,
                doc_id=doc_id or "",
            ))

            # Ребро к следующему узлу
            if i < n_tokens - 1:
                rel_str = sig[pos_idx + 1] if pos_idx + 1 < len(sig) else ""
                if ":" in rel_str:
                    _, dep_label = rel_str.split(":", 1)
                else:
                    dep_label = rel_str

                edges.append(PatternEdge(
                    source_id=f"node_{i}",
                    target_id=f"node_{i+1}",
                    edge_type=PatternEdgeType.DEPENDS_ON,
                    relation_subtype=dep_label,
                ))

        if not nodes:
            return None

        size = len(nodes)
        return Pattern(
            uid=pattern_uid,
            name=f"DEP-{depth}-gram ({cnt})",
            description=f"Dependency {depth}-gram, {cnt} occurrences",
            pattern_hash=pattern_hash,
            canon_nodes=nodes,
            canon_edges=edges,
            frequency=cnt,
        )

    # ------------------------------------------------------------------
    # Public API: extract_action_patterns
    # ------------------------------------------------------------------

    def extract_action_patterns(
        self,
        max_nodes: int = 100,
        min_frequency: int = 1,
        doc_id: Optional[str] = None,
    ) -> PatternExtractionResult:
        """
        Извлекает паттерны из Action-узлов и рёбер LEADS_TO.

        Включает:
          - Одиночные Actions (unigram)
          - Цепочки LEADS_TO длины 2..N
          - Diverging/converging паттерны (1→много, много→1)

        :param max_nodes: макс. узлов в паттерне
        :param min_frequency: мин. частота для включения
        :param doc_id: фильтр по документу
        """
        results: List[Pattern] = []
        max_nodes_seen = 0
        doc_ids_set: Set[str] = set()

        doc_filter = "WHERE a.doc_id = $doc_id" if doc_id else ""
        doc_filter2 = "WHERE a1.doc_id = $doc_id AND a2.doc_id = $doc_id" if doc_id else ""
        params = {"doc_id": doc_id} if doc_id else None

        # --- 1. Одиночные Actions ---
        actions = self._run_query(
            f"""
            MATCH (a:Action)
            {doc_filter}
            RETURN a.uid AS uid, a.verb AS verb, a.action_class AS action_class,
                   a.label_text AS label_text, a.doc_id AS doc_id,
                   count {{(a)-[:LEADS_TO]->()}} AS out_degree,
                   count {{(a)<-[:LEADS_TO]-()}} AS in_degree
            ORDER BY out_degree + in_degree DESC
            LIMIT 200
            """,
            params,
        )

        for row in actions:
            if row["out_degree"] + row["in_degree"] < min_frequency:
                continue

            node_id = f"act_{row['uid']}"
            pattern = Pattern(
                uid=uuid8_str(),
                name=f"Action: {row['verb']} ({row['action_class']})",
                description=f"Action '{row['verb']}' class='{row['action_class']}', "
                            f"in={row['in_degree']}, out={row['out_degree']}",
                canon_nodes=[
                    PatternNode(
                        node_id=node_id,
                        node_type=PatternNodeType.ACTION,
                        role=NodeRole.VERB,
                        text=row["verb"],
                        lemma=row["verb"],
                        action_class=row["action_class"],
                        doc_id=row["doc_id"],
                    )
                ],
                canon_edges=[],
                frequency=row["in_degree"] + row["out_degree"],
                doc_count=1,
                stability=1.0,
            )
            max_nodes_seen = max(max_nodes_seen, pattern.node_count)
            results.append(pattern)
            if row["doc_id"]:
                doc_ids_set.add(row["doc_id"])

        # --- 2. Цепочки LEADS_TO длины 2..5 ---
        for length in range(2, 6):
            chains = self._run_query(
                f"""
                MATCH path = ()-[:LEADS_TO*{length}]->()
                {doc_filter}
                WITH path, length(path) AS len,
                     [n IN nodes(path) | {{uid: n.uid, verb: n.verb, cls: n.action_class, doc_id: n.doc_id}}] AS actions
                ORDER BY len DESC
                LIMIT {min(500, 500 // length)}
                RETURN actions, len
                """,
                params,
            )

            seen_hashes: Set[str] = set()
            for row in chains:
                chain_actions = row["actions"]
                if len(chain_actions) > max_nodes:
                    continue

                nodes: List[PatternNode] = []
                edges: List[PatternEdge] = []

                for i, act in enumerate(chain_actions):
                    node_id = f"act_{act['uid']}"
                    nodes.append(PatternNode(
                        node_id=node_id,
                        node_type=PatternNodeType.ACTION,
                        role=NodeRole.CONNECTOR,
                        text=act.get("verb", ""),
                        lemma=act.get("verb", ""),
                        action_class=act.get("cls", ""),
                        doc_id=act.get("doc_id", ""),
                    ))
                    if i < len(chain_actions) - 1:
                        edges.append(PatternEdge(
                            source_id=f"act_{chain_actions[i]['uid']}",
                            target_id=f"act_{chain_actions[i+1]['uid']}",
                            edge_type=PatternEdgeType.LEADS_TO,
                            relation_subtype="sequential",
                        ))

                # Дедупликация по hash
                chain_hash = hashlib.sha256(
                    json.dumps([a.get("verb", "") for a in chain_actions], ensure_ascii=False).encode()
                ).hexdigest()[:16]
                if chain_hash in seen_hashes:
                    continue
                seen_hashes.add(chain_hash)

                pattern = Pattern(
                    uid=uuid8_str(),
                    name=f"LEADS_TO chain (len={len(chain_actions)})",
                    description=" → ".join(a.get("verb", "?") for a in chain_actions),
                    pattern_hash=chain_hash,
                    canon_nodes=nodes,
                    canon_edges=edges,
                    frequency=1,
                    doc_count=1,
                    stability=1.0,
                )
                max_nodes_seen = max(max_nodes_seen, pattern.node_count)
                results.append(pattern)

        return PatternExtractionResult(
            patterns=results,
            total_patterns=len(results),
            max_nodes_seen=max_nodes_seen,
            extraction_mode="document" if doc_id else "global",
            doc_ids=list(doc_ids_set),
        )

    # ------------------------------------------------------------------
    # Public API: extract_mixed_patterns (Action + LexicalUnit)
    # ------------------------------------------------------------------

    def extract_mixed_patterns(
        self,
        max_nodes: int = 100,
        min_frequency: int = 1,
        doc_id: Optional[str] = None,
    ) -> PatternExtractionResult:
        """
        Извлекает смешанные паттерны: Action + LexicalUnit вместе.

        Для каждого Action находит связанные LexicalUnit через PART_OF
        и строит полный подграф.

        :param max_nodes: макс. узлов в паттерне
        :param min_frequency: мин. частота
        :param doc_id: фильтр по документу
        """
        results: List[Pattern] = []
        max_nodes_seen = 0
        doc_ids_set: Set[str] = set()

        params = {"doc_id": doc_id} if doc_id else None
        doc_filter = "WHERE a.doc_id = $doc_id" if doc_id else ""

        # --- Actions с LexicalUnit ---
        mixed = self._run_query(
            f"""
            MATCH (a:Action)
            {doc_filter}
            OPTIONAL MATCH (lu:LexicalUnit)-[r:PART_OF]->(a)
            WITH a,
                 collect(lu {{.uid, .text, .lemma, .pos, .dep, .doc_id, role: r.token_index}}) AS lexical_units
            WHERE size(lexical_units) > 0
            RETURN a.uid AS uid, a.verb AS verb, a.action_class AS action_class,
                   a.label_text AS label_text, a.doc_id AS doc_id,
                   lexical_units,
                   size(lexical_units) AS lu_count
            ORDER BY lu_count DESC
            LIMIT 100
            """,
            params,
        )

        seen_hashes: Set[str] = set()
        for row in mixed:
            if row["lu_count"] + 1 > max_nodes:
                continue

            action_uid = row["uid"]
            action_node_id = f"act_{action_uid}"

            nodes: List[PatternNode] = [
                PatternNode(
                    node_id=action_node_id,
                    node_type=PatternNodeType.ACTION,
                    role=NodeRole.VERB,
                    text=row["verb"],
                    lemma=row["verb"],
                    action_class=row["action_class"],
                    doc_id=row["doc_id"],
                )
            ]
            edges: List[PatternEdge] = []

            for lu in row["lexical_units"]:
                lu_node = PatternNode(
                    node_id=f"lu_{lu['uid']}",
                    node_type=PatternNodeType.LEXICAL_UNIT,
                    role=_role_from_dep_label(lu.get("dep", "")),
                    text=lu.get("text", ""),
                    lemma=lu.get("lemma", ""),
                    pos=lu.get("pos", ""),
                    doc_id=lu.get("doc_id", ""),
                )
                nodes.append(lu_node)
                edges.append(PatternEdge(
                    source_id=lu_node.node_id,
                    target_id=action_node_id,
                    edge_type=PatternEdgeType.PART_OF,
                ))

            # DEPENDS_ON между LexicalUnit внутри Action
            lu_uids = [lu["uid"] for lu in row["lexical_units"]]
            if lu_uids:
                deps = self._run_query(
                    """
                    UNWIND $uids AS uid
                    MATCH (src:LexicalUnit {uid: uid})-[r:DEPENDS_ON]->(tgt:LexicalUnit)
                    WHERE tgt.uid IN $uids
                    RETURN src.uid AS src, tgt.uid AS tgt, r.dep_label AS dep
                    """,
                    {"uids": lu_uids},
                )
                for dep in deps:
                    edges.append(PatternEdge(
                        source_id=f"lu_{dep['src']}",
                        target_id=f"lu_{dep['tgt']}",
                        edge_type=PatternEdgeType.DEPENDS_ON,
                        relation_subtype=dep["dep"] or "",
                    ))

            # Дедупликация
            pattern_hash = hashlib.sha256(
                json.dumps({
                    "verb": row["verb"],
                    "lu_count": row["lu_count"],
                    "lu_poses": sorted(lu.get("pos", "") for lu in row["lexical_units"]),
                }, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()[:16]

            if pattern_hash in seen_hashes:
                continue
            seen_hashes.add(pattern_hash)

            pattern = Pattern(
                uid=uuid8_str(),
                name=f"Mixed: {row['verb']} + {row['lu_count']} LU",
                description=f"Action '{row['verb']}' с {row['lu_count']} LexicalUnit",
                pattern_hash=pattern_hash,
                canon_nodes=nodes,
                canon_edges=edges,
                frequency=1,
                doc_count=1,
                stability=1.0,
            )
            max_nodes_seen = max(max_nodes_seen, pattern.node_count)
            results.append(pattern)
            if row["doc_id"]:
                doc_ids_set.add(row["doc_id"])

        return PatternExtractionResult(
            patterns=results,
            total_patterns=len(results),
            max_nodes_seen=max_nodes_seen,
            extraction_mode="document" if doc_id else "global",
            doc_ids=list(doc_ids_set),
        )

    # ------------------------------------------------------------------
    # Public API: extract_all (объединённый)
    # ------------------------------------------------------------------

    def extract_all(
        self,
        max_nodes: int = 100,
        max_depth: int = 5,
        limit_per_n: int = 50,
        min_frequency: int = 1,
        doc_id: Optional[str] = None,
    ) -> PatternExtractionResult:
        """
        Извлекает все типы паттернов и объединяет результаты.

        Включает:
          - Dependency n-grams (как Pattern)
          - Action patterns (LEADS_TO цепочки)
          - Mixed patterns (Action + LexicalUnit)

        :param max_nodes: макс. узлов в паттерне
        :param max_depth: глубина dependency n-grams
        :param limit_per_n: лимит на длину для n-grams
        :param min_frequency: мин. частота
        :param doc_id: фильтр по документу
        """
        dep_result = self.extract_dependency_ngrams(
            max_depth=max_depth,
            limit_per_n=limit_per_n,
            doc_id=doc_id,
        )
        action_result = self.extract_action_patterns(
            max_nodes=max_nodes,
            min_frequency=min_frequency,
            doc_id=doc_id,
        )
        mixed_result = self.extract_mixed_patterns(
            max_nodes=max_nodes,
            min_frequency=min_frequency,
            doc_id=doc_id,
        )

        all_patterns = dep_result.patterns + action_result.patterns + mixed_result.patterns
        all_doc_ids = set(dep_result.doc_ids) | set(action_result.doc_ids) | set(mixed_result.doc_ids)
        max_nodes = max(dep_result.max_nodes_seen, action_result.max_nodes_seen, mixed_result.max_nodes_seen)

        # Дедупликация по pattern_hash
        seen: Set[str] = set()
        unique: List[Pattern] = []
        for p in all_patterns:
            if p.pattern_hash not in seen:
                seen.add(p.pattern_hash)
                unique.append(p)

        return PatternExtractionResult(
            patterns=unique,
            total_patterns=len(unique),
            max_nodes_seen=max_nodes,
            extraction_mode="document" if doc_id else "global",
            doc_ids=list(all_doc_ids),
        )
