from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum


class UniquenessStatus(Enum):
    SAME = "same"
    UNCERTAIN = "uncertain"
    DIFFERENT = "different"
    NEW = "new"


class Polarity(Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"


class StatementNodeType(Enum):
    STATEMENT = "statement"
    CONCEPT = "concept"
    LITERAL = "literal"


class EdgeType(Enum):
    RELATES_TO = "RELATES_TO"
    CONTAINS = "CONTAINS"
    SUPPORTS = "SUPPORTS"
    OPPOSES = "OPPOSES"


@dataclass(frozen=True)
class CanonicalStatement:
    subject_id: str
    subject_text: str
    predicate: str
    object_id: str
    object_text: str
    polarity: Polarity = Polarity.POSITIVE

    def fingerprint(self) -> str:
        raw = f"{self.subject_id}|{self.predicate}|{self.object_id}|{self.polarity.value}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CandidateMatch:
    statement_id: str
    similarity: float
    subject_text: str
    predicate: str
    object_text: str
    wl_hash: str = ""


@dataclass(frozen=True)
class SubgraphNode:
    id: str
    node_type: StatementNodeType
    text: str = ""
    predicate: str = ""
    fingerprint: str = ""


@dataclass(frozen=True)
class SubgraphEdge:
    source_id: str
    target_id: str
    edge_type: EdgeType
    predicate: str = ""


@dataclass
class CandidateSubgraph:
    nodes: list[SubgraphNode] = field(default_factory=list)
    edges: list[SubgraphEdge] = field(default_factory=list)

    @property
    def node_ids(self) -> list[str]:
        return [n.id for n in self.nodes]

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    @property
    def node_count(self) -> int:
        return len(self.nodes)


@dataclass
class NodeUids:
    """UUID утверждений, где узел выступает субъектом/объектом."""
    as_subject: list[str] = field(default_factory=list)
    as_object: list[str] = field(default_factory=list)


@dataclass
class SubgraphMatch:
    pattern_node_to_graph_node: dict[str, str]
    matched_graph_node_ids: list[str]
    matched_edge_ids: list[str] = field(default_factory=list)
    node_uids: dict[str, NodeUids] = field(default_factory=dict)
    edge_uids: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class FrequentPattern:
    graph: CandidateSubgraph
    support: int
    frequency: float = 0.0


@dataclass
class UniquenessResult:
    status: UniquenessStatus
    existing_statement_id: str | None = None
    confidence: float = 0.0
    candidates: list[CandidateMatch] = field(default_factory=list)
    subgraph_matches: list[SubgraphMatch] = field(default_factory=list)
    message: str = ""


@dataclass
class SubgraphUniquenessResult:
    status: UniquenessStatus
    wl_hash: str = ""
    existing_subgraph_id: str | None = None
    subgraph_matches: list[SubgraphMatch] = field(default_factory=list)
    frequent_patterns: list[FrequentPattern] = field(default_factory=list)
    message: str = ""


@dataclass
class PatternNode:
    id: str
    required_type: StatementNodeType | None = None
    text_constraint: str | None = None
    predicate_constraint: str | None = None


@dataclass
class PatternEdge:
    source_id: str
    target_id: str
    required_edge_type: EdgeType | None = None
    predicate_constraint: str | None = None


@dataclass
class PatternGraph:
    nodes: list[PatternNode] = field(default_factory=list)
    edges: list[PatternEdge] = field(default_factory=list)

    def node_ids(self) -> list[str]:
        return [n.id for n in self.nodes]


@dataclass
class PatternMatchResult:
    status: UniquenessStatus
    matches: list[SubgraphMatch] = field(default_factory=list)
    total_matches: int = 0
    message: str = ""
