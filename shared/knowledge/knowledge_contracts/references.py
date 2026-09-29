"""Typed semantic references and source positions."""
from dataclasses import dataclass, field

@dataclass(frozen=True)
class ConceptReference:
    id: str
    kind: str = field(default="concept", init=False)

@dataclass(frozen=True)
class AssertionReference:
    id: str
    kind: str = field(default="assertion", init=False)

@dataclass(frozen=True)
class Predicate:
    id: str
    label: str
    arity: int

@dataclass(frozen=True)
class SourceSpan:
    revision_id: str
    start: int
    end: int
