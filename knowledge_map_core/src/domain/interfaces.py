from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

from .models import Statement, Concept
from .uniqueness import (
    CandidateSubgraph,
    CandidateMatch,
    SubgraphMatch,
    SubgraphUniquenessResult,
    UniquenessResult,
    PatternGraph,
    PatternMatchResult,
    CanonicalStatement,
    FrequentPattern,
)


class Rule(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def matches(self, sentence_text: str, dep_tree: dict) -> bool: ...

    @abstractmethod
    def extract(self, sentence_text: str, dep_tree: dict, existing_concepts: dict[str, Concept]) -> list[Statement]: ...


class PipelineStep(ABC):
    @abstractmethod
    def process(self, statements: list[Statement], concepts: dict[str, Concept], context: dict) -> tuple[list[Statement], dict[str, Concept]]: ...


class ConceptNormalizer(Protocol):
    def normalize(self, text: str) -> str: ...


class GraphValidator(Protocol):
    def validate(self, statements: list[Statement]) -> tuple[bool, list[str]]: ...


class GraphSerializer(Protocol):
    def serialize_statements(self, statements: list[Statement], concepts: dict[str, Concept]) -> list[dict]: ...

    def to_proto(self, statements: list[Statement], concepts: dict[str, Concept]) -> tuple[list, list]: ...


class StatementEmbedder(Protocol):
    async def embed(self, text: str) -> list[float]: ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class VectorStore(Protocol):
    async def search(self, vector: list[float], top_k: int) -> list[CandidateMatch]: ...

    async def upsert(self, id: str, vector: list[float], metadata: dict) -> None: ...

    async def delete(self, id: str) -> None: ...


class SubgraphMatcher(Protocol):
    async def find_occurrences(
        self,
        candidate: CandidateSubgraph,
    ) -> list[SubgraphMatch]: ...

    async def find_pattern_matches(
        self,
        pattern: PatternGraph,
        max_results: int = 100,
    ) -> PatternMatchResult: ...


class FrequentMiner(Protocol):
    async def mine(
        self,
        subgraph_ids: list[str],
        min_support: int = 1,
        max_size: int = 10,
    ) -> list[FrequentPattern]: ...


class WLHasher(Protocol):
    def compute_hash(self, candidate: CandidateSubgraph) -> str: ...


class UniquenessChecker(Protocol):
    async def check_single(
        self,
        subject_text: str,
        predicate: str,
        object_text: str,
        sentence_text: str,
    ) -> UniquenessResult: ...

    async def check_subgraph(
        self,
        candidate: CandidateSubgraph,
    ) -> SubgraphUniquenessResult: ...

    async def check_pattern(
        self,
        pattern: PatternGraph,
    ) -> PatternMatchResult: ...
