from __future__ import annotations

import hashlib
from collections import defaultdict

import networkx as nx

from src.domain.uniqueness import (
    CandidateSubgraph,
    EdgeType,
    SubgraphEdge,
    SubgraphNode,
    StatementNodeType,
)


def _initial_node_label(node: SubgraphNode) -> str:
    return f"{node.node_type.value}|{node.predicate}|{hashlib.md5(node.text.encode()).hexdigest()[:8]}"


def _edge_label(edge: SubgraphEdge) -> str:
    return f"{edge.edge_type.value}|{edge.predicate}"


def compute_wl_hash(candidate: CandidateSubgraph, iterations: int = 3) -> str:
    """
    Weisfeiler-Lehman graph hash для подграфа.

    Complexity: O(|V| * |E| * iterations)
    Для типизированных графов знаний — чувствителен к:
    - типам узлов (Statement/Concept/Literal)
    - предикатам связей
    - структуре графа

    Не чувствителен к:
    - нумерации узлов
    - порядку обхода
    """
    if not candidate.nodes:
        return ""

    graph = _build_networkx_graph(candidate)
    labels: dict[str, str] = {}

    for node in graph.nodes:
        node_data = candidate.nodes[graph.nodes[node].get("idx", 0)]
        labels[node] = _initial_node_label(node_data)

    for _ in range(iterations):
        new_labels: dict[str, str] = {}
        for node in graph.nodes:
            neighbor_labels = sorted(
                (labels[neighbor], _get_edge_label_between(graph, node, neighbor))
                for neighbor in graph.neighbors(node)
            )
            combined = (labels[node], tuple(neighbor_labels))
            new_labels[node] = hashlib.sha256(
                str(combined).encode("utf-8")
            ).hexdigest()[:16]
        labels = new_labels

    sorted_hashes = sorted(labels.values())
    return hashlib.sha256("|".join(sorted_hashes).encode("utf-8")).hexdigest()


def compute_wl_subgraph_hash_for_neo4j(
    node_fingerprints: list[str],
    edge_predicates: list[str],
    iterations: int = 3,
) -> str:
    """
    Быстрый WL-хеш без построения CandidateSubgraph.
    Используется для запросов к Neo4j где узлы уже загружены.
    """
    if not node_fingerprints:
        return ""

    labels = {f"n{i}": fp for i, fp in enumerate(node_fingerprints)}
    adjacency = _build_adjacency_from_flat(node_fingerprints, edge_predicates)

    for _ in range(iterations):
        new_labels: dict[str, str] = {}
        for node, label in labels.items():
            neighbors = adjacency.get(node, [])
            neighbor_labels = sorted(neighbors)
            combined = (label, tuple(neighbor_labels))
            new_labels[node] = hashlib.sha256(
                str(combined).encode("utf-8")
            ).hexdigest()[:16]
        labels = new_labels

    sorted_hashes = sorted(labels.values())
    return hashlib.sha256("|".join(sorted_hashes).encode("utf-8")).hexdigest()


def _build_adjacency_from_flat(
    node_fingerprints: list[str],
    edge_predicates: list[str],
) -> dict[str, list[str]]:
    adj: dict[str, list[str]] = defaultdict(list)
    for i, fp in enumerate(node_fingerprints):
        node = f"n{i}"
        if i < len(edge_predicates):
            adj[node].append(f"{edge_predicates[i]}|n{(i + 1) % len(node_fingerprints)}")
    return dict(adj)


def _build_networkx_graph(candidate: CandidateSubgraph) -> nx.DiGraph:
    g = nx.DiGraph()
    for i, node in enumerate(candidate.nodes):
        g.add_node(node.id, idx=i)
    for edge in candidate.edges:
        g.add_edge(edge.source_id, edge.target_id)
    return g


def _get_edge_label_between(graph: nx.DiGraph, source: str, target: str) -> str:
    edge_data = graph.edges.get((source, target), {})
    return edge_data.get("label", "")
