from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Union


class StatementType(Enum):
    FACT = "F"
    META = "M"


class SubjectType(Enum):
    CONCEPT = "concept"
    STATEMENT = "statement"


class ObjectType(Enum):
    CONCEPT = "concept"
    STATEMENT = "statement"
    LITERAL = "literal"


@dataclass(frozen=True)
class StatementID:
    uuid: uuid.UUID

    @classmethod
    def new(cls) -> StatementID:
        from .uuidv8 import uuid8
        return cls(uuid=uuid8())

    def __str__(self) -> str:
        return str(self.uuid)

    def __repr__(self) -> str:
        return str(self.uuid)


@dataclass
class Concept:
    id: str
    text: str
    normalized_text: str | None = None

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Concept):
            return NotImplemented
        return self.id == other.id


@dataclass
class Literal:
    value: str
    type: str = "string"


@dataclass
class Statement:
    id: StatementID
    type: StatementType
    subject: Union[Concept, Statement]
    predicate: str
    object: Union[Concept, Statement, Literal]
    confidence: float = 1.0
    sentence_text: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    @property
    def subject_id(self) -> str:
        if isinstance(self.subject, Concept):
            return self.subject.id
        return str(self.subject.id)

    @property
    def object_id(self) -> str:
        if isinstance(self.object, Concept):
            return self.object.id
        if isinstance(self.object, Statement):
            return str(self.object.id)
        return self.object.value

    @property
    def subject_type(self) -> SubjectType:
        if isinstance(self.subject, Concept):
            return SubjectType.CONCEPT
        return SubjectType.STATEMENT

    @property
    def object_type(self) -> ObjectType:
        if isinstance(self.object, Concept):
            return ObjectType.CONCEPT
        if isinstance(self.object, Statement):
            return ObjectType.STATEMENT
        return ObjectType.LITERAL
