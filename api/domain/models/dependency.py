"""
Layer: Domain (Entities)
Package: domain.models.dependency
Responsibility: Dependency edge — вычисляемая связь между утверждениями (KnowledgeStatement)
для построения DAG-карты знаний.

В отличие от семантических ссылок (subject/object), dependency edge выражает:
  «Для выполнения/обоснования этого утверждения нужен следующий блок утверждения».

Allowed imports: стандартная библиотека Python + enum.
Forbidden imports: neomodel, pydantic, fastapi, grpc.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class DependencyType(str, Enum):
    """Тип зависимости между утверждениями."""

    CAUSAL = "causal"
    """A causa B: A вызывает/инициирует B (inhibits → inhibition, increases → growth)."""

    MECHANISTIC = "mechanistic"
    """A является механизмом B: A описывает как именно B происходит."""

    LOGICAL = "logical"
    """A логически следует из B: A является предпосылкой/условием B."""

    EVIDENTIAL = "evidential"
    """A подтверждает B: A является доказательством/исследованием B."""

    GOAL_DIRECTED = "goal_directed"
    """A необходим для достижения цели B: A → target → B."""

    COMPOSITIONAL = "compositional"
    """A + C → B: B является результатом композиции A и C."""


class DiscoveryMethod(str, Enum):
    """Метод обнаружения dependency-рёбер."""

    EXACT_MATCH = "exact_match"
    """A1.object == A2.subject (нормализовано)."""

    PREDICATE_DIRECTION = "predicate_direction"
    """Анализ направления предикатов (up/down/unchanged)."""

    PREDICATE_COMPOSITION = "predicate_composition"
    """Композиция предикатов (inhibits + activates → inhibits)."""

    STRUCTURAL = "structural"
    """Структурные связи (step/result/sequence) между блоками."""

    GOAL_DECOMPOSITION = "goal_decomposition"
    """META-триплеты decomposed_into."""

    LLM = "llm"
    """LLM-верификация для неоднозначных кандидатов."""


@dataclass
class DependencyEdge:
    """
    Ребро зависимости между двумя утверждениями.

    Хранит:
      - source_uid / target_uid: uid утверждений в Neo4j
      - dependency_type: семантический тип зависимости
      - confidence: уверенность (0.0 - 1.0)
      - discovery_method: как была обнаружена зависимость
      - is_verified: прошла ли LLM-верификацию
      - metadata: дополнительные данные (правило, raw LLM output и т.д.)
    """

    source_uid: str
    target_uid: str
    dependency_type: DependencyType
    confidence: float = 1.0
    discovery_method: DiscoveryMethod = DiscoveryMethod.EXACT_MATCH
    is_verified: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        """Уникальный ключ ребра для дедупликации."""
        return f"{self.source_uid}->{self.target_uid}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_uid": self.source_uid,
            "target_uid": self.target_uid,
            "dependency_type": self.dependency_type.value,
            "confidence": self.confidence,
            "discovery_method": self.discovery_method.value,
            "is_verified": self.is_verified,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DependencyEdge":
        return cls(
            source_uid=data["source_uid"],
            target_uid=data["target_uid"],
            dependency_type=DependencyType(data["dependency_type"]),
            confidence=data.get("confidence", 1.0),
            discovery_method=DiscoveryMethod(data.get("discovery_method", "exact_match")),
            is_verified=data.get("is_verified", False),
            metadata=data.get("metadata", {}),
        )
