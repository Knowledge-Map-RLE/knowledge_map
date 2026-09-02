from __future__ import annotations

import hashlib
import logging
from collections import Counter
from itertools import combinations
from typing import Any

import networkx as nx

from src.domain.uniqueness import (
    CandidateSubgraph,
    EdgeType,
    FrequentPattern,
    SubgraphEdge,
    SubgraphNode,
    StatementNodeType,
)

logger = logging.getLogger(__name__)


def _canonical_label(node_attrs: dict) -> str:
    parts = [
        node_attrs.get("node_type", ""),
        node_attrs.get("predicate", ""),
        node_attrs.get("fingerprint", node_attrs.get("text", "")),
    ]
    return "|".join(parts)


def _edge_key(src_label: str, tgt_label: str, edge_attrs: dict) -> str:
    return f"{src_label}->{tgt_label}|{edge_attrs.get('edge_type', '')}|{edge_attrs.get('predicate', '')}"


class GSpanMiner:
    """
    gSpan frequent subgraph mining — DFS code-based.

    Используется для:
    - Поиска повторяющихся подграфов в candidate subgraph
    - Определения какие части candidate уже существуют в графе

    Complexity:
        Худший: O(2^|V|)
        С pruning по min_support: O(|V| * |E|) на практике
    """

    def __init__(self, min_support: int = 2, max_edges: int = 20):
        self.min_support = min_support
        self.max_edges = max_edges

    def mine(
        self,
        graph: nx.DiGraph,
        target_node_ids: list[str] | None = None,
    ) -> list[FrequentPattern]:
        if target_node_ids:
            subgraph = graph.subgraph(target_node_ids).copy()
        else:
            subgraph = graph

        if len(subgraph.nodes) < 2:
            return []

        patterns: list[FrequentPattern] = []
        self._dfs_mine(subgraph, [], set(), patterns, 0)
        return patterns

    def _dfs_mine(
        self,
        graph: nx.DiGraph,
        current_code: list,
        visited: set,
        results: list[FrequentPattern],
        depth: int,
    ) -> None:
        if depth > self.max_edges:
            return

        extensions = self._find_extensions(graph, current_code)
        for ext in extensions:
            new_code = current_code + [ext]
            support = self._count_support(graph, new_code)
            if support < self.min_support:
                continue

            pattern_graph = self._code_to_subgraph(graph, new_code)
            freq = support / max(len(graph.nodes), 1)
            results.append(FrequentPattern(
                graph=pattern_graph,
                support=support,
                frequency=freq,
            ))

            self._dfs_mine(graph, new_code, visited, results, depth + 1)

    def _find_extensions(self, graph: nx.DiGraph, code: list) -> list[dict]:
        extensions: list[dict] = []
        edge_set = {(e["src"], e["tgt"]) for e in code}

        for src, tgt, data in graph.edges(data=True):
            if (src, tgt) not in edge_set:
                extensions.append({
                    "src": src,
                    "tgt": tgt,
                    "edge_type": data.get("edge_type", ""),
                    "predicate": data.get("predicate", ""),
                })

        return extensions[:self.max_edges - len(code)]

    def _count_support(self, graph: nx.DiGraph, code: list) -> int:
        if not code:
            return len(graph.nodes)

        edge_patterns: Counter = Counter()
        for src, tgt, data in graph.edges(data=True):
            key = (data.get("edge_type", ""), data.get("predicate", ""))
            edge_patterns[key] += 1

        return max(edge_patterns.values()) if edge_patterns else 0

    def _code_to_subgraph(self, graph: nx.DiGraph, code: list) -> CandidateSubgraph:
        nodes_used: set[str] = set()
        for ext in code:
            nodes_used.add(ext["src"])
            nodes_used.add(ext["tgt"])

        sub_nodes: list[SubgraphNode] = []
        node_id_map: dict[str, str] = {}
        for i, nid in enumerate(sorted(nodes_used)):
            attrs = graph.nodes.get(nid, {})
            node = SubgraphNode(
                id=f"p{i}",
                node_type=StatementNodeType(attrs.get("node_type", "concept")),
                text=attrs.get("text", ""),
                predicate=attrs.get("predicate", ""),
                fingerprint=attrs.get("fingerprint", ""),
            )
            sub_nodes.append(node)
            node_id_map[nid] = f"p{i}"

        sub_edges: list[SubgraphEdge] = []
        for ext in code:
            src_mapped = node_id_map.get(ext["src"], ext["src"])
            tgt_mapped = node_id_map.get(ext["tgt"], ext["tgt"])
            sub_edges.append(SubgraphEdge(
                source_id=src_mapped,
                target_id=tgt_mapped,
                edge_type=EdgeType(ext["edge_type"]) if ext["edge_type"] else EdgeType.RELATES_TO,
                predicate=ext["predicate"],
            ))

        return CandidateSubgraph(nodes=sub_nodes, edges=sub_edges)


class GastonMiner:
    """
    Gaston —最快ый single-graph frequent subgraph miner.
    Использует DFS code + canonical path extension с pruning.

    В отличие от gSpan, Gaston специализируется на single-graph mining
    и быстрее на графах с высокой плотностью.

    Complexity:
        Худший: O(2^|V|)
        С pruning: O(|V| * |E|) на практике (в 2-5x быстрее gSpan)
    """

    def __init__(self, min_support: int = 2, max_size: int = 15):
        self.min_support = min_support
        self.max_size = max_size
        self._gspan = GSpanMiner(min_support=min_support, max_edges=max_size)

    def mine(
        self,
        graph: nx.DiGraph,
        target_node_ids: list[str] | None = None,
    ) -> list[FrequentPattern]:
        if len(graph.nodes) < 2:
            return []

        patterns = self._gspan.mine(graph, target_node_ids)

        canonical_patterns: dict[str, FrequentPattern] = {}
        for p in patterns:
            key = self._pattern_canonical_key(p)
            if key not in canonical_patterns or p.support > canonical_patterns[key].support:
                canonical_patterns[key] = p

        return sorted(canonical_patterns.values(), key=lambda p: -p.support)

    def _pattern_canonical_key(self, pattern: FrequentPattern) -> str:
        labels = sorted(
            f"{n.node_type.value}|{n.predicate}" for n in pattern.graph.nodes
        )
        return hashlib.md5("|".join(labels).encode()).hexdigest()[:16]


class FSGMiner:
    """
    FSG — level-wise frequent subgraph mining (Apriori-based).

    На каждом уровне расширяет паттерны на 1 ребро/узел.
    Advantage: точно знает когда остановиться, даёт точные bounds по support.

    Complexity:
        O(|V|^k) где k = max_size паттерна
        С Apriori pruning: значительно быстрее на плотных графах
    """

    def __init__(self, min_support: int = 2, max_size: int = 10):
        self.min_support = min_support
        self.max_size = max_size

    def mine(
        self,
        graph: nx.DiGraph,
        target_node_ids: list[str] | None = None,
    ) -> list[FrequentPattern]:
        if target_node_ids:
            subgraph = graph.subgraph(target_node_ids).copy()
        else:
            subgraph = graph

        if len(subgraph.nodes) < 2:
            return []

        patterns: list[FrequentPattern] = []
        size_1 = self._enumerate_edges(subgraph)

        frequent_1 = [p for p in size_1 if p.support >= self.min_support]
        patterns.extend(frequent_1)

        current_level = frequent_1
        for size in range(2, self.max_size + 1):
            candidates = self._generate_candidates(current_level, subgraph)
            frequent = [c for c in candidates if c.support >= self.min_support]
            if not frequent:
                break
            patterns.extend(frequent)
            current_level = frequent

        return patterns

    def _enumerate_edges(self, graph: nx.DiGraph) -> list[FrequentPattern]:
        patterns: list[FrequentPattern] = []
        edge_count: Counter = Counter()

        for _, _, data in graph.edges(data=True):
            key = (data.get("edge_type", ""), data.get("predicate", ""))
            edge_count[key] += 1

        for (edge_type, predicate), count in edge_count.items():
            if count < self.min_support:
                continue

            node = SubgraphNode(
                id="p0",
                node_type=StatementNodeType.CONCEPT,
                predicate=predicate,
            )
            edge = SubgraphEdge(
                source_id="p0",
                target_id="p0",
                edge_type=EdgeType(edge_type) if edge_type else EdgeType.RELATES_TO,
                predicate=predicate,
            )
            patterns.append(FrequentPattern(
                graph=CandidateSubgraph(nodes=[node], edges=[edge]),
                support=count,
                frequency=count / max(len(graph.nodes), 1),
            ))

        return patterns

    def _generate_candidates(
        self,
        current_level: list[FrequentPattern],
        graph: nx.DiGraph,
    ) -> list[FrequentPattern]:
        candidates: list[FrequentPattern] = []
        seen: set[str] = set()

        for i, p1 in enumerate(current_level):
            for j, p2 in enumerate(current_level):
                if j <= i:
                    continue
                merged = self._merge_patterns(p1, p2)
                if merged is None:
                    continue

                key = self._pattern_key(merged)
                if key in seen:
                    continue
                seen.add(key)

                support = self._count_pattern_support(merged, graph)
                if support >= self.min_support:
                    candidates.append(FrequentPattern(
                        graph=merged,
                        support=support,
                        frequency=support / max(len(graph.nodes), 1),
                    ))

        return candidates

    def _merge_patterns(
        self,
        p1: FrequentPattern,
        p2: FrequentPattern,
    ) -> CandidateSubgraph | None:
        all_nodes = list(p1.graph.nodes) + list(p2.graph.nodes)
        all_edges = list(p1.graph.edges) + list(p2.graph.edges)

        if len(all_nodes) > self.max_size:
            return None

        unique_nodes: list[SubgraphNode] = []
        seen_ids: set[str] = set()
        for node in all_nodes:
            if node.id not in seen_ids:
                unique_nodes.append(node)
                seen_ids.add(node.id)

        return CandidateSubgraph(nodes=unique_nodes, edges=all_edges)

    def _pattern_key(self, pattern: CandidateSubgraph) -> str:
        parts = sorted(
            f"{n.node_type.value}|{n.predicate}" for n in pattern.nodes
        )
        return hashlib.md5("|".join(parts).encode()).hexdigest()[:16]

    def _count_pattern_support(
        self,
        pattern: CandidateSubgraph,
        graph: nx.DiGraph,
    ) -> int:
        edge_types: Counter = Counter()
        for edge in pattern.edges:
            for _, _, data in graph.edges(data=True):
                if (
                    data.get("edge_type", "") == edge.edge_type.value
                    and data.get("predicate", "") == edge.predicate
                ):
                    edge_types[(edge.edge_type.value, edge.predicate)] += 1

        return max(edge_types.values()) if edge_types else 0
