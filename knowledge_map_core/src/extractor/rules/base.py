from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.models import Statement
from src.extractor.context import ExtractionContext
from src.parser.dep_tree import DependencyTree


class BaseRule(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def matches(self, tree: DependencyTree) -> bool: ...

    @abstractmethod
    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]: ...
