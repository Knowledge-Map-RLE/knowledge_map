from __future__ import annotations

import logging
from datetime import datetime, timezone

import grpc

from src import knowledge_language_pb2
from src.services.pipeline import Pipeline

logger = logging.getLogger(__name__)


class KnowledgeLanguageServicer:
    def __init__(
        self,
        pipeline: Pipeline | None = None,
        uniqueness_pipeline=None,
    ):
        self._pipeline = pipeline or Pipeline()
        self._uniqueness = uniqueness_pipeline

    async def ProcessText(self, request, context):
        try:
            result = await self._pipeline.process(
                text=request.text,
                doc_id=request.doc_id,
            )

            response = knowledge_language_pb2.KnowledgeGraphResponse(
                success=result["success"],
                statements=result["statements"],
                concepts=result["concepts"],
                total_statements=result["total_statements"],
                total_concepts=result["total_concepts"],
                message=result["message"],
                doc_id=request.doc_id,
            )
            return response

        except Exception as e:
            logger.exception("ProcessText failed")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return knowledge_language_pb2.KnowledgeGraphResponse(
                success=False,
                message=str(e),
            )

    async def HealthCheck(self, request, context):
        return knowledge_language_pb2.HealthCheckResponse(
            status="SERVING",
            service="knowledge_language",
            details="Knowledge Language Parser running",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
        )

    async def CheckUniqueness(self, request, context):
        if not self._uniqueness:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details("Uniqueness pipeline not initialized")
            return knowledge_language_pb2.UniquenessResponse(
                status=knowledge_language_pb2.UNIQUENESS_STATUS_UNKNOWN,
                message="Uniqueness pipeline not available",
            )

        try:
            result = await self._uniqueness.check_single(
                subject_text=request.subject_text,
                predicate=request.predicate,
                object_text=request.object_text,
                sentence_text=request.sentence_text,
            )

            status_map = {
                "same": knowledge_language_pb2.UNIQUENESS_SAME,
                "uncertain": knowledge_language_pb2.UNIQUENESS_UNCERTAIN,
                "different": knowledge_language_pb2.UNIQUENESS_DIFFERENT,
                "new": knowledge_language_pb2.UNIQUENESS_NEW,
            }

            candidates = []
            for c in result.candidates:
                candidates.append(
                    knowledge_language_pb2.CandidateMatchProto(
                        statement_id=c.statement_id,
                        similarity=c.similarity,
                        subject_text=c.subject_text,
                        predicate=c.predicate,
                        object_text=c.object_text,
                    )
                )

            return knowledge_language_pb2.UniquenessResponse(
                status=status_map.get(result.status.value, knowledge_language_pb2.UNIQUENESS_STATUS_UNKNOWN),
                existing_statement_id=result.existing_statement_id or "",
                confidence=result.confidence,
                candidates=candidates,
                message=result.message,
            )

        except Exception as e:
            logger.exception("CheckUniqueness failed")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return knowledge_language_pb2.UniquenessResponse(
                status=knowledge_language_pb2.UNIQUENESS_STATUS_UNKNOWN,
                message=str(e),
            )

    async def CheckSubgraphUniqueness(self, request, context):
        if not self._uniqueness:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details("Uniqueness pipeline not initialized")
            return knowledge_language_pb2.SubgraphUniquenessResponse(
                status=knowledge_language_pb2.UNIQUENESS_STATUS_UNKNOWN,
                message="Uniqueness pipeline not available",
            )

        try:
            from src.domain.uniqueness import (
                CandidateSubgraph,
                EdgeType,
                StatementNodeType,
                SubgraphEdge,
                SubgraphNode,
            )

            nodes = []
            for n in request.nodes:
                nodes.append(SubgraphNode(
                    id=n.id,
                    node_type=StatementNodeType(n.node_type) if n.node_type else StatementNodeType.CONCEPT,
                    text=n.text,
                    predicate=n.predicate,
                    fingerprint=n.fingerprint,
                ))

            edges = []
            for e in request.edges:
                edges.append(SubgraphEdge(
                    source_id=e.source_id,
                    target_id=e.target_id,
                    edge_type=EdgeType(e.edge_type) if e.edge_type else EdgeType.RELATES_TO,
                    predicate=e.predicate,
                ))

            candidate = CandidateSubgraph(nodes=nodes, edges=edges)
            result = await self._uniqueness.check_subgraph(candidate)

            status_map = {
                "same": knowledge_language_pb2.UNIQUENESS_SAME,
                "uncertain": knowledge_language_pb2.UNIQUENESS_UNCERTAIN,
                "different": knowledge_language_pb2.UNIQUENESS_DIFFERENT,
                "new": knowledge_language_pb2.UNIQUENESS_NEW,
            }

            matches = []
            for m in result.subgraph_matches:
                matches.append(
                    knowledge_language_pb2.SubgraphMatchProto(
                        pattern_to_graph=m.pattern_node_to_graph_node,
                        matched_graph_node_ids=m.matched_graph_node_ids,
                        node_uids={
                            k: knowledge_language_pb2.NodeUidsProto(
                                as_subject=v.as_subject,
                                as_object=v.as_object,
                            )
                            for k, v in m.node_uids.items()
                        },
                        edge_uids={
                            k: knowledge_language_pb2.UidListProto(uids=v)
                            for k, v in m.edge_uids.items()
                        },
                    )
                )

            patterns = []
            for p in result.frequent_patterns:
                pat_nodes = [
                    knowledge_language_pb2.SubgraphNodeProto(
                        id=n.id,
                        node_type=n.node_type.value,
                        text=n.text,
                        predicate=n.predicate,
                    )
                    for n in p.graph.nodes
                ]
                pat_edges = [
                    knowledge_language_pb2.SubgraphEdgeProto(
                        source_id=e.source_id,
                        target_id=e.target_id,
                        edge_type=e.edge_type.value,
                        predicate=e.predicate,
                    )
                    for e in p.graph.edges
                ]
                patterns.append(
                    knowledge_language_pb2.FrequentPatternProto(
                        support=p.support,
                        frequency=p.frequency,
                        nodes=pat_nodes,
                        edges=pat_edges,
                    )
                )

            return knowledge_language_pb2.SubgraphUniquenessResponse(
                status=status_map.get(result.status.value, knowledge_language_pb2.UNIQUENESS_STATUS_UNKNOWN),
                wl_hash=result.wl_hash,
                existing_subgraph_id=result.existing_subgraph_id or "",
                subgraph_matches=matches,
                frequent_patterns=patterns,
                message=result.message,
            )

        except Exception as e:
            logger.exception("CheckSubgraphUniqueness failed")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return knowledge_language_pb2.SubgraphUniquenessResponse(
                status=knowledge_language_pb2.UNIQUENESS_STATUS_UNKNOWN,
                message=str(e),
            )

    async def CheckPatternMatch(self, request, context):
        if not self._uniqueness:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details("Uniqueness pipeline not initialized")
            return knowledge_language_pb2.PatternMatchResponse(
                status=knowledge_language_pb2.UNIQUENESS_STATUS_UNKNOWN,
                message="Uniqueness pipeline not available",
            )

        try:
            from src.domain.uniqueness import (
                EdgeType,
                PatternEdge,
                PatternGraph,
                PatternNode,
                StatementNodeType,
            )

            nodes = []
            for n in request.nodes:
                required_type = None
                if n.required_type:
                    try:
                        required_type = StatementNodeType(n.required_type)
                    except ValueError:
                        pass
                nodes.append(PatternNode(
                    id=n.id,
                    required_type=required_type,
                    text_constraint=n.text_constraint or None,
                    predicate_constraint=n.predicate_constraint or None,
                ))

            edges = []
            for e in request.edges:
                required_edge = None
                if e.required_edge_type:
                    try:
                        required_edge = EdgeType(e.required_edge_type)
                    except ValueError:
                        pass
                edges.append(PatternEdge(
                    source_id=e.source_id,
                    target_id=e.target_id,
                    required_edge_type=required_edge,
                    predicate_constraint=e.predicate_constraint or None,
                ))

            pattern = PatternGraph(nodes=nodes, edges=edges)
            result = await self._uniqueness.check_pattern(pattern)

            status_map = {
                "same": knowledge_language_pb2.UNIQUENESS_SAME,
                "uncertain": knowledge_language_pb2.UNIQUENESS_UNCERTAIN,
                "different": knowledge_language_pb2.UNIQUENESS_DIFFERENT,
                "new": knowledge_language_pb2.UNIQUENESS_NEW,
            }

            matches = []
            for m in result.matches:
                matches.append(
                    knowledge_language_pb2.SubgraphMatchProto(
                        pattern_to_graph=m.pattern_node_to_graph_node,
                        matched_graph_node_ids=m.matched_graph_node_ids,
                        node_uids={
                            k: knowledge_language_pb2.NodeUidsProto(
                                as_subject=v.as_subject,
                                as_object=v.as_object,
                            )
                            for k, v in m.node_uids.items()
                        },
                        edge_uids={
                            k: knowledge_language_pb2.UidListProto(uids=v)
                            for k, v in m.edge_uids.items()
                        },
                    )
                )

            return knowledge_language_pb2.PatternMatchResponse(
                status=status_map.get(result.status.value, knowledge_language_pb2.UNIQUENESS_STATUS_UNKNOWN),
                matches=matches,
                total_matches=result.total_matches,
                message=result.message,
            )

        except Exception as e:
            logger.exception("CheckPatternMatch failed")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return knowledge_language_pb2.PatternMatchResponse(
                status=knowledge_language_pb2.UNIQUENESS_STATUS_UNKNOWN,
                message=str(e),
            )

    async def AddStatementWithUniqueness(self, request, context):
        if not self._uniqueness:
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details("Uniqueness pipeline not initialized")
            return knowledge_language_pb2.AddStatementResponse(
                success=False,
                uniqueness_status=knowledge_language_pb2.UNIQUENESS_STATUS_UNKNOWN,
                message="Uniqueness pipeline not available",
            )

        try:
            check_result = await self._uniqueness.check_single(
                subject_text=request.subject_text,
                predicate=request.predicate,
                object_text=request.object_text,
                sentence_text=request.sentence_text,
            )

            status_map = {
                "same": knowledge_language_pb2.UNIQUENESS_SAME,
                "uncertain": knowledge_language_pb2.UNIQUENESS_UNCERTAIN,
                "different": knowledge_language_pb2.UNIQUENESS_DIFFERENT,
                "new": knowledge_language_pb2.UNIQUENESS_NEW,
            }

            if check_result.status.value == "same":
                return knowledge_language_pb2.AddStatementResponse(
                    success=True,
                    uniqueness_status=status_map["same"],
                    statement_id=check_result.existing_statement_id or "",
                    existing_statement_id=check_result.existing_statement_id or "",
                    message=f"Knowledge already exists: {check_result.message}",
                )

            process_result = await self._pipeline.process(
                text=request.sentence_text,
                doc_id=request.doc_id,
            )

            if not process_result.get("success") or not process_result.get("statements"):
                return knowledge_language_pb2.AddStatementResponse(
                    success=False,
                    uniqueness_status=status_map.get(check_result.status.value, knowledge_language_pb2.UNIQUENESS_STATUS_UNKNOWN),
                    message="Failed to process statement",
                )

            first_stmt = process_result["statements"][0]
            stmt_id = first_stmt.id

            await self._uniqueness.store_statement(
                subject_text=request.subject_text,
                predicate=request.predicate,
                object_text=request.object_text,
                sentence_text=request.sentence_text,
                statement_id=stmt_id,
            )

            return knowledge_language_pb2.AddStatementResponse(
                success=True,
                uniqueness_status=status_map.get(check_result.status.value, knowledge_language_pb2.UNIQUENESS_NEW),
                statement_id=stmt_id,
                message=f"Statement added (uniqueness: {check_result.status.value})",
            )

        except Exception as e:
            logger.exception("AddStatementWithUniqueness failed")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return knowledge_language_pb2.AddStatementResponse(
                success=False,
                message=str(e),
            )
