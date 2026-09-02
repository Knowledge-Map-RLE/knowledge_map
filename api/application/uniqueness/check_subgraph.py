"""
Use case: Проверка уникальности подграфа (связанных утверждений).

Использует WL-хеш, VF2 subgraph isomorphism и
gSpan/Gaston/FSG frequent subgraph mining.
"""
from __future__ import annotations

import logging

from services.knowledge_language_grpc_client import KnowledgeLanguageGrpcClient

logger = logging.getLogger(__name__)


async def check_subgraph_uniqueness(
    grpc_client: KnowledgeLanguageGrpcClient,
    *,
    nodes: list[dict],
    edges: list[dict],
) -> dict:
    """
    Проверяет уникальность подграфа из связанных утверждений.

    Args:
        nodes: [{"id": "...", "node_type": "concept|statement|literal", "text": "...", "predicate": "..."}]
        edges: [{"source_id": "...", "target_id": "...", "edge_type": "RELATES_TO|...", "predicate": "..."}]
    """
    await grpc_client.connect()

    from utils.generated import knowledge_language_pb2

    request = knowledge_language_pb2.CheckSubgraphUniquenessRequest(
        nodes=[
            knowledge_language_pb2.SubgraphNodeProto(
                id=n["id"],
                node_type=n.get("node_type", "concept"),
                text=n.get("text", ""),
                predicate=n.get("predicate", ""),
                fingerprint=n.get("fingerprint", ""),
            )
            for n in nodes
        ],
        edges=[
            knowledge_language_pb2.SubgraphEdgeProto(
                source_id=e["source_id"],
                target_id=e["target_id"],
                edge_type=e.get("edge_type", "RELATES_TO"),
                predicate=e.get("predicate", ""),
            )
            for e in edges
        ],
    )

    try:
        response = await grpc_client.stub.CheckSubgraphUniqueness(request, timeout=60)
        status_map = {
            0: "UNKNOWN", 1: "SAME", 2: "UNCERTAIN",
            3: "DIFFERENT", 4: "NEW",
        }
        return {
            "status": status_map.get(response.status, "UNKNOWN"),
            "wl_hash": response.wl_hash,
            "existing_subgraph_id": response.existing_subgraph_id,
            "subgraph_matches": [
                {
                    "pattern_to_graph": dict(m.pattern_to_graph),
                    "matched_node_ids": list(m.matched_graph_node_ids),
                    "node_uids": {
                        k: {
                            "as_subject": list(v.as_subject),
                            "as_object": list(v.as_object),
                        }
                        for k, v in m.node_uids.items()
                    },
                    "edge_uids": {
                        k: list(v.uids)
                        for k, v in m.edge_uids.items()
                    },
                }
                for m in response.subgraph_matches
            ],
            "frequent_patterns": [
                {
                    "support": p.support,
                    "frequency": p.frequency,
                    "nodes": [
                        {"id": n.id, "node_type": n.node_type, "text": n.text}
                        for n in p.nodes
                    ],
                    "edges": [
                        {"source_id": e.source_id, "target_id": e.target_id, "edge_type": e.edge_type}
                        for e in p.edges
                    ],
                }
                for p in response.frequent_patterns
            ],
            "message": response.message,
        }
    except Exception as e:
        logger.exception("check_subgraph_uniqueness failed")
        return {"status": "UNKNOWN", "wl_hash": "", "message": str(e)}


async def check_pattern_match(
    grpc_client: KnowledgeLanguageGrpcClient,
    *,
    nodes: list[dict],
    edges: list[dict],
    max_results: int = 100,
) -> dict:
    """
    Проверяет паттерн из UI редактора на графе утверждений.

    Args:
        nodes: [{"id": "...", "required_type": "...", "text_constraint": "...", "predicate_constraint": "..."}]
        edges: [{"source_id": "...", "target_id": "...", "required_edge_type": "...", "predicate_constraint": "..."}]
        max_results: максимальное количество совпадений
    """
    await grpc_client.connect()

    from utils.generated import knowledge_language_pb2

    request = knowledge_language_pb2.CheckPatternMatchRequest(
        nodes=[
            knowledge_language_pb2.PatternNodeProto(
                id=n["id"],
                required_type=n.get("required_type", ""),
                text_constraint=n.get("text_constraint", ""),
                predicate_constraint=n.get("predicate_constraint", ""),
            )
            for n in nodes
        ],
        edges=[
            knowledge_language_pb2.PatternEdgeProto(
                source_id=e["source_id"],
                target_id=e["target_id"],
                required_edge_type=e.get("required_edge_type", ""),
                predicate_constraint=e.get("predicate_constraint", ""),
            )
            for e in edges
        ],
        max_results=max_results,
    )

    try:
        response = await grpc_client.stub.CheckPatternMatch(request, timeout=60)
        status_map = {
            0: "UNKNOWN", 1: "SAME", 2: "UNCERTAIN",
            3: "DIFFERENT", 4: "NEW",
        }
        return {
            "status": status_map.get(response.status, "UNKNOWN"),
            "matches": [
                {
                    "pattern_to_graph": dict(m.pattern_to_graph),
                    "matched_node_ids": list(m.matched_graph_node_ids),
                    "node_uids": {
                        k: {
                            "as_subject": list(v.as_subject),
                            "as_object": list(v.as_object),
                        }
                        for k, v in m.node_uids.items()
                    },
                    "edge_uids": {
                        k: list(v.uids)
                        for k, v in m.edge_uids.items()
                    },
                }
                for m in response.matches
            ],
            "total_matches": response.total_matches,
            "message": response.message,
        }
    except Exception as e:
        logger.exception("check_pattern_match failed")
        return {"status": "UNKNOWN", "total_matches": 0, "matches": [], "message": str(e)}
