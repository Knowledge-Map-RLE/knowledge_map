from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

from .models import Statement, Concept


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
