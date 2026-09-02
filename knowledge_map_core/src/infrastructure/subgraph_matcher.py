from __future__ import annotations

import logging
from typing import Any

import networkx as nx
from networkx.algorithms import isomorphism

from src.domain.uniqueness import (
    CandidateSubgraph,
    EdgeType,
    NodeUids,
    PatternEdge,
    PatternGraph,
    PatternMatchResult,
    PatternNode,
    StatementNodeType,
    SubgraphEdge,
    SubgraphMatch,
    SubgraphNode,
    UniquenessStatus,
)

logger = logging.getLogger(__name__)


def _build_networkx_from_candidate(candidate: CandidateSubgraph) -> nx.DiGraph:
    g = nx.DiGraph()
    for node in candidate.nodes:
        g.add_node(
            node.id,
            node_type=node.node_type.value,
            text=node.text,
            predicate=node.predicate,
            fingerprint=node.fingerprint,
        )
    for edge in candidate.edges:
        g.add_edge(
            edge.source_id,
            edge.target_id,
            edge_type=edge.edge_type.value,
            predicate=edge.predicate,
        )
    return g


def _build_networkx_from_pattern(pattern: PatternGraph) -> nx.DiGraph:
    g = nx.DiGraph()
    for node in pattern.nodes:
        attrs: dict[str, Any] = {}
        if node.required_type:
            attrs["node_type"] = node.required_type.value
        if node.text_constraint:
            attrs["text"] = node.text_constraint
        if node.predicate_constraint:
            attrs["predicate"] = node.predicate_constraint
        g.add_node(node.id, **attrs)
    for edge in pattern.edges:
        attrs: dict[str, Any] = {}
        if edge.required_edge_type:
            attrs["edge_type"] = edge.required_edge_type.value
        if edge.predicate_constraint:
            attrs["predicate"] = edge.predicate_constraint
        g.add_edge(edge.source_id, edge.target_id, **attrs)
    return g


def _typed_node_match(n1_data: dict, n2_data: dict) -> bool:
    required_type = n2_data.get("node_type")
    if required_type:
        actual_type = n1_data.get("node_type")
        if actual_type != required_type:
            return False

    required_text = n2_data.get("text")
    if required_text:
        actual_text = n1_data.get("text", "")
        if actual_text and actual_text.lower() != required_text.lower():
            return False

    required_pred = n2_data.get("predicate")
    if required_pred:
        actual_pred = n1_data.get("predicate", "")
        if actual_pred and actual_pred.lower() != required_pred.lower():
            return False

    return True


def _typed_edge_match(e1_data: dict, e2_data: dict) -> bool:
    required_type = e2_data.get("edge_type")
    if required_type:
        actual_type = e1_data.get("edge_type")
        if actual_type != required_type:
            return False

    required_pred = e2_data.get("predicate")
    if required_pred:
        actual = e1_data.get("predicates") or e1_data.get("predicate")
        if isinstance(actual, str):
            actual = {actual}
        else:
            actual = set(actual or [])
        needle = required_pred.lower()
        if needle not in {p.lower() for p in actual}:
            return False

    return True


class SubgraphMatcherVF2:
    """
    VF2-based subgraph isomorphism matcher для графа утверждений.

    Complexity:
        Худший случай: O(|V_G|! * |V_P|!)
        Практический случай: O(|V_G| * |V_P| * deg^2) с pruning по типам
    """

    async def find_occurrences(
        self,
        candidate: CandidateSubgraph,
        host_graph: nx.DiGraph | None = None,
    ) -> list[SubgraphMatch]:
        if not candidate.nodes:
            return []

        pattern_graph = _build_networkx_from_candidate(candidate)
        if host_graph is None:
            return []

        matcher = isomorphism.DiGraphMatcher(
            host_graph,
            pattern_graph,
            node_match=_typed_node_match,
            edge_match=_typed_edge_match,
        )

        matches: list[SubgraphMatch] = []
        for mapping in matcher.subgraph_isomorphisms_iter():
            match = SubgraphMatch(
                pattern_node_to_graph_node={v: k for k, v in mapping.items()},
                matched_graph_node_ids=list(mapping.keys()),
            )
            matches.append(match)

        logger.debug(
            "VF2 found %d subgraph matches for pattern with %d nodes",
            len(matches),
            len(candidate.nodes),
        )
        return matches

    async def find_pattern_matches(
        self,
        pattern: PatternGraph,
        host_graph: nx.DiGraph | None = None,
        max_results: int = 100,
    ) -> PatternMatchResult:
        if not pattern.nodes:
            return PatternMatchResult(
                status=UniquenessStatus.NEW,
                message="Pattern has no nodes",
            )

        pattern_graph = _build_networkx_from_pattern(pattern)
        if host_graph is None:
            return PatternMatchResult(
                status=UniquenessStatus.NEW,
                message="Host graph not loaded",
            )

        matcher = isomorphism.DiGraphMatcher(
            host_graph,
            pattern_graph,
            node_match=_typed_node_match,
            edge_match=_typed_edge_match,
        )

        matches: list[SubgraphMatch] = []
        for mapping in matcher.subgraph_isomorphisms_iter():
            if len(matches) >= max_results:
                break
            # В mapping ключи — узлы host-графа (G1), значения — узлы паттерна (G2).
            # Фронтенду нужна ориентация «узел паттерна -> узел графа».
            pattern_to_graph = {v: k for k, v in mapping.items()}
            graph_node_ids = list(mapping.keys())

            node_uids: dict[str, NodeUids] = {}
            for graph_id, pattern_id in mapping.items():
                node = host_graph.nodes.get(graph_id)
                if not node:
                    continue
                node_uids[pattern_id] = NodeUids(
                    as_subject=sorted(str(u) for u in node.get("as_subject", set()) if u),
                    as_object=sorted(str(u) for u in node.get("as_object", set()) if u),
                )

            edge_uids: dict[str, list[str]] = {}
            for pe in pattern.edges:
                src = pattern_to_graph.get(pe.source_id)
                tgt = pattern_to_graph.get(pe.target_id)
                if src and tgt and host_graph.has_edge(src, tgt):
                    edge_data = host_graph[src][tgt]
                    statement_uids = {str(u) for u in edge_data.get("statement_uids", set()) if u}
                    edge_uids[f"{src}->{tgt}"] = sorted(statement_uids)

            match = SubgraphMatch(
                pattern_node_to_graph_node=pattern_to_graph,
                matched_graph_node_ids=graph_node_ids,
                node_uids=node_uids,
                edge_uids=edge_uids,
            )
            matches.append(match)

        total = len(matches)
        if total == 0:
            status = UniquenessStatus.NEW
            msg = "No matches found for pattern"
        elif total == 1:
            status = UniquenessStatus.SAME
            msg = f"Exact match found (1 occurrence)"
        else:
            status = UniquenessStatus.SAME
            msg = f"Pattern found {total} times in the graph"

        return PatternMatchResult(
            status=status,
            matches=matches,
            total_matches=total,
            message=msg,
        )
