from __future__ import annotations

import logging
from typing import Any

import networkx as nx
from neo4j import AsyncGraphDatabase

from src.config import settings
from src.domain.uniqueness import (
    CandidateMatch,
    CandidateSubgraph,
    CanonicalStatement,
    EdgeType,
    Polarity,
    StatementNodeType,
    SubgraphEdge,
    SubgraphMatch,
    SubgraphNode,
    SubgraphUniquenessResult,
    UniquenessResult,
    UniquenessStatus,
    PatternGraph,
    PatternMatchResult,
    FrequentPattern,
)
from src.domain.interfaces import (
    StatementEmbedder,
    VectorStore,
    SubgraphMatcher,
    FrequentMiner,
    WLHasher,
    UniquenessChecker,
)

logger = logging.getLogger(__name__)


class UniquenessPipeline(UniquenessChecker):
    """
    3-level uniqueness pipeline:

    Level 1: Single statement — fingerprint + vector search
    Level 2: Connected subgraph — WL-hash + gSpan/Gaston/FSG + VF2
    Level 3: Pattern from UI — typed VF2 subgraph isomorphism

    Complexity: O(log N) single, O(|V|*|E|) subgraph, O(|V|*|P|*deg²) pattern
    """

    def __init__(
        self,
        embedder: StatementEmbedder,
        vector_store: VectorStore,
        subgraph_matcher: SubgraphMatcher,
        frequent_miner: FrequentMiner,
        wl_hasher: WLHasher,
        neo4j_uri: str | None = None,
        neo4j_user: str | None = None,
        neo4j_password: str | None = None,
    ):
        self._embedder = embedder
        self._vector_store = vector_store
        self._subgraph_matcher = subgraph_matcher
        self._miner = frequent_miner
        self._wl_hasher = wl_hasher
        self._neo4j_uri = neo4j_uri or settings.neo4j_uri
        self._neo4j_user = neo4j_user or settings.neo4j_user
        self._neo4j_password = neo4j_password or settings.neo4j_password
        self._driver = None

    async def _get_driver(self):
        if self._driver is None:
            self._driver = AsyncGraphDatabase.driver(
                self._neo4j_uri,
                auth=(self._neo4j_user, self._neo4j_password),
            )
        return self._driver

    async def close(self):
        if self._driver:
            await self._driver.close()
            self._driver = None

    async def check_single(
        self,
        subject_text: str,
        predicate: str,
        object_text: str,
        sentence_text: str,
    ) -> UniquenessResult:
        canonical = CanonicalStatement(
            subject_id=subject_text.lower().strip(),
            subject_text=subject_text,
            predicate=predicate.lower().strip(),
            object_id=object_text.lower().strip(),
            object_text=object_text,
        )

        fp = canonical.fingerprint()
        existing = await self._find_by_fingerprint(fp)
        if existing:
            return UniquenessResult(
                status=UniquenessStatus.SAME,
                existing_statement_id=existing,
                confidence=1.0,
                message=f"Exact fingerprint match: {existing}",
            )

        embedding = await self._embedder.embed(sentence_text)
        candidates = await self._vector_store.search(
            embedding,
            top_k=settings.uniqueness_top_k,
        )

        if not candidates:
            return UniquenessResult(
                status=UniquenessStatus.NEW,
                confidence=0.0,
                message="No similar statements found",
            )

        best = candidates[0]
        if best.similarity >= settings.uniqueness_cosine_threshold:
            return UniquenessResult(
                status=UniquenessStatus.SAME,
                existing_statement_id=best.statement_id,
                confidence=best.similarity,
                candidates=candidates,
                message=f"Semantic match (similarity={best.similarity:.4f})",
            )
        elif best.similarity >= settings.uniqueness_cosine_uncertain:
            return UniquenessResult(
                status=UniquenessStatus.UNCERTAIN,
                confidence=best.similarity,
                candidates=candidates,
                message=f"Possibly duplicate (similarity={best.similarity:.4f}), review needed",
            )

        return UniquenessResult(
            status=UniquenessStatus.DIFFERENT,
            confidence=best.similarity,
            candidates=candidates,
            message=f"No match (best similarity={best.similarity:.4f})",
        )

    async def check_subgraph(
        self,
        candidate: CandidateSubgraph,
    ) -> SubgraphUniquenessResult:
        wl_hash = self._wl_hasher.compute_hash(candidate)

        existing = await self._find_subgraph_by_wl_hash(wl_hash)
        if existing:
            return SubgraphUniquenessResult(
                status=UniquenessStatus.SAME,
                wl_hash=wl_hash,
                existing_subgraph_id=existing,
                message=f"Exact subgraph WL-hash match: {existing}",
            )

        host_graph = await self._load_host_subgraph(candidate.node_ids)
        if not host_graph or len(host_graph.nodes) == 0:
            return SubgraphUniquenessResult(
                status=UniquenessStatus.NEW,
                wl_hash=wl_hash,
                message="Host graph empty, subgraph is new",
            )

        matches = await self._subgraph_matcher.find_occurrences(
            candidate, host_graph,
        )

        if matches:
            return SubgraphUniquenessResult(
                status=UniquenessStatus.SAME,
                wl_hash=wl_hash,
                subgraph_matches=matches,
                message=f"Subgraph found {len(matches)} times via VF2",
            )

        # Frequent subgraph mining on host graph — check if sub-structures of the
        # candidate already appear frequently (indicating parts are known).
        patterns = self._miner.mine(host_graph)
        frequent = [
            p for p in patterns
            if p.support >= settings.uniqueness_fsg_min_support
        ]

        if frequent:
            return SubgraphUniquenessResult(
                status=UniquenessStatus.UNCERTAIN,
                wl_hash=wl_hash,
                frequent_patterns=frequent,
                message=f"Found {len(frequent)} frequent sub-patterns, review needed",
            )

        return SubgraphUniquenessResult(
            status=UniquenessStatus.NEW,
            wl_hash=wl_hash,
            message="Subgraph is unique (no VF2 match, no frequent patterns)",
        )

    async def check_pattern(
        self,
        pattern: PatternGraph,
    ) -> PatternMatchResult:
        host_graph = await self._load_full_knowledge_graph()
        return await self._subgraph_matcher.find_pattern_matches(
            pattern, host_graph,
        )

    async def _find_by_fingerprint(self, fingerprint: str) -> str | None:
        driver = await self._get_driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (s:Statement {fingerprint: $fp})
                RETURN s.id AS id LIMIT 1
                """,
                fp=fingerprint,
            )
            record = await result.single()
            return record["id"] if record else None

    async def _find_subgraph_by_wl_hash(self, wl_hash: str) -> str | None:
        driver = await self._get_driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (sf:SubgraphFingerprint {wl_hash: $wl_hash})
                RETURN sf.id AS id LIMIT 1
                """,
                wl_hash=wl_hash,
            )
            record = await result.single()
            return record["id"] if record else None

    async def _load_host_subgraph(
        self,
        anchor_node_ids: list[str],
        depth: int = 2,
    ) -> nx.DiGraph | None:
        driver = await self._get_driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (anchor:Statement)
                WHERE anchor.id IN $ids
                MATCH path = (anchor)-[*0..$depth]-(neighbor:Statement)
                WITH DISTINCT neighbor
                OPTIONAL MATCH (neighbor)-[r:RELATES_TO]-(other)
                RETURN neighbor.id AS node_id,
                       neighbor.type AS node_type,
                       neighbor.predicate AS predicate,
                       neighbor.sentence AS sentence,
                       other.id AS other_id,
                       other.type AS other_type,
                       type(r) AS rel_type,
                       r.predicate AS rel_predicate
                """,
                ids=anchor_node_ids,
                depth=depth,
            )
            records = [dict(r) async for r in result]

        if not records:
            return None

        g = nx.DiGraph()
        for r in records:
            nid = r["node_id"]
            if nid not in g:
                g.add_node(
                    nid,
                    node_type=r.get("node_type", "Fact"),
                    predicate=r.get("predicate", ""),
                    text=r.get("sentence", ""),
                )
            other_id = r.get("other_id")
            if other_id:
                if other_id not in g:
                    g.add_node(
                        other_id,
                        node_type=r.get("other_type", "Fact"),
                        predicate="",
                        text="",
                    )
                g.add_edge(
                    nid,
                    other_id,
                    edge_type=r.get("rel_type", "RELATES_TO"),
                    predicate=r.get("rel_predicate", ""),
                )

        return g

    async def _load_full_knowledge_graph(self) -> nx.DiGraph:
        """
        Materializes the real knowledge graph from :KnowledgeStatement triples into a
        typed directed graph suitable for VF2 subgraph isomorphism.

        Each triple (subject_text --predicate--> object_text) becomes:
          - a Concept (or Literal) node for the subject,
          - a Concept (or Literal) node for the object,
          - a directed RELATES_TO edge carrying the predicate.

        This mirrors the domain intent (Concepts/Literals + Statements) and lets
        pattern blocks of type `concept`/`literal` match on exact text while edges
        match on RELATES_TO + predicate.
        """
        driver = await self._get_driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (s:KnowledgeStatement)
                WHERE s.predicate IS NOT NULL AND s.predicate <> ''
                  AND s.predicate <> 'title'
                  AND s.subject_text IS NOT NULL AND s.object_text IS NOT NULL
                RETURN s.subject_text AS subject_text,
                       s.predicate AS predicate,
                       s.object_text AS object_text,
                       s.subject_type AS subject_type,
                       s.object_type AS object_type,
                       s.uid AS uid
                """
            )
            records = [dict(r) async for r in result]

        g = nx.DiGraph()
        for r in records:
            subj = str(r.get("subject_text") or "").strip()
            pred = str(r.get("predicate") or "").strip()
            obj = str(r.get("object_text") or "").strip()
            uid = str(r.get("uid") or "").strip()
            if not subj or not obj:
                continue

            s_type = str(r.get("subject_type") or "concept").lower()
            o_type = str(r.get("object_type") or "concept").lower()
            s_nodetype = s_type if s_type in ("concept", "literal") else "concept"
            o_nodetype = o_type if o_type in ("concept", "literal") else "concept"

            subj_id = f"n:{subj.lower()}"
            obj_id = f"n:{obj.lower()}"

            if subj_id not in g:
                g.add_node(
                    subj_id,
                    node_type=s_nodetype,
                    text=subj,
                    predicate="",
                    as_subject=set(),
                    as_object=set(),
                )
            if obj_id not in g:
                g.add_node(
                    obj_id,
                    node_type=o_nodetype,
                    text=obj,
                    predicate="",
                    as_subject=set(),
                    as_object=set(),
                )

            # Накапливаем uids утверждений, где узел выступает субъектом/объектом,
            # чтобы интерфейс мог показывать источники каждого найденного концепта.
            if uid:
                g.nodes[subj_id]["as_subject"].add(uid)
                g.nodes[obj_id]["as_object"].add(uid)

            # Пара (subject, object) может соответствовать нескольким утверждениям
            # с разными предикатами (например vitamin D -> oxidative stress через
            # 'limit' и 'neutralize'). Накопляем все предикаты и uids утверждений,
            # чтобы ни один не терялся при повторной вставке ребра (раньше add_edge
            # затирал предикат).
            if g.has_edge(subj_id, obj_id):
                g[subj_id][obj_id]["predicates"].add(pred)
                if uid:
                    g[subj_id][obj_id]["statement_uids"].add(uid)
            else:
                g.add_edge(
                    subj_id,
                    obj_id,
                    edge_type="RELATES_TO",
                    predicates={pred},
                    statement_uids={uid} if uid else set(),
                )

        return g

    async def store_statement(
        self,
        subject_text: str,
        predicate: str,
        object_text: str,
        sentence_text: str,
        statement_id: str,
    ) -> None:
        embedding = await self._embedder.embed(sentence_text)
        await self._vector_store.upsert(
            id=statement_id,
            vector=embedding,
            metadata={
                "subject_text": subject_text,
                "predicate": predicate,
                "object_text": object_text,
            },
        )

        canonical = CanonicalStatement(
            subject_id=subject_text.lower().strip(),
            subject_text=subject_text,
            predicate=predicate.lower().strip(),
            object_id=object_text.lower().strip(),
            object_text=object_text,
        )

        driver = await self._get_driver()
        async with driver.session() as session:
            await session.run(
                """
                MATCH (s:Statement {id: $id})
                SET s.fingerprint = $fp
                """,
                id=statement_id,
                fp=canonical.fingerprint(),
            )

    async def store_subgraph_fingerprint(
        self,
        candidate: CandidateSubgraph,
        subgraph_id: str,
    ) -> None:
        wl_hash = self._wl_hasher.compute_hash(candidate)
        driver = await self._get_driver()
        async with driver.session() as session:
            await session.run(
                """
                MERGE (sf:SubgraphFingerprint {wl_hash: $wl_hash})
                SET sf.id = $subgraph_id,
                    sf.node_count = $node_count,
                    sf.edge_count = $edge_count
                WITH sf
                MATCH (s:Statement)
                WHERE s.id IN $node_ids
                MERGE (s)-[:PART_OF_SUBGRAPH]->(sf)
                """,
                wl_hash=wl_hash,
                subgraph_id=subgraph_id,
                node_count=len(candidate.nodes),
                edge_count=len(candidate.edges),
                node_ids=candidate.node_ids,
            )
