"""Pydantic-схемы для структурированного вывода LLM-экстракции триплетов.

Unified (one-stage): модель выдаёт ВСЕ блоки (контейнеры + T4 + T58/T59) за один вызов.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class StructureBlock(BaseModel):
    """Один контейнерный блок из ответа Stage 1 (two-stage) или unified."""
    blockType: int = Field(alias="blockType")
    data: Dict[str, Any] = Field(default_factory=dict)
    tag: str = ""

    @field_validator("data", mode="before")
    @classmethod
    def coerce_data(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, dict):
            return v
        return {}


class StructureResponse(BaseModel):
    """Ответ Stage 1 (Structure): список контейнерных блоков."""
    blocks: List[StructureBlock] = Field(default_factory=list)


class AtomizeBlock(BaseModel):
    """Один атомарный T4-триплет из ответа Stage 2."""
    blockType: int = 4
    data: Dict[str, Any] = Field(default_factory=dict)
    container: str = ""

    @field_validator("data", mode="before")
    @classmethod
    def coerce_data(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, dict):
            return v
        return {}


class AtomizeResponse(BaseModel):
    """Ответ Stage 2 (Atomize): T4-триплеты + маппинг последовательностей."""
    blocks: List[AtomizeBlock] = Field(default_factory=list)
    sequences: Dict[str, Any] = Field(default_factory=dict)


class UnifiedBlock(BaseModel):
    """Блок из unified-ответа (one-stage): все типы включая T4, T58, T59."""
    blockType: int = Field(alias="blockType")
    data: Dict[str, Any] = Field(default_factory=dict)
    tag: str = ""

    @field_validator("data", mode="before")
    @classmethod
    def coerce_data(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, dict):
            return v
        return {}


class UnifiedResponse(BaseModel):
    """Ответ unified (one-stage): все блоки за один вызов."""
    blocks: List[UnifiedBlock] = Field(default_factory=list)


# Константы для типов блоков
class BlockType:
    METADATA = 1
    RESEARCH_GOAL = 2
    FREE_TEXT = 3
    DIRECT_TRIPLET = 4
    PRIMARY_ENDPOINT = 5
    SECONDARY_ENDPOINTS = 6
    HYPOTHESIS = 7
    PREREQUISITES = 8
    EXPECTATIONS = 9
    KNOWLEDGE_DEPS = 10
    STUDY_DESIGN = 11
    MATERIALS = 12
    METHODS = 13
    EXPERIMENT = 14
    INCLUSION_CRITERIA = 15
    BIOLOGICAL_MECHANISM = 16
    TARGET_OF_ACTION = 17
    INTERVENTION = 18
    ANIMAL_MODEL = 19
    CONCLUSIONS = 20
    RESEARCH_LOGIC = 21
    ENTITIES = 22
    CONCEPT_DEFINITION = 23
    ASSUMPTIONS = 24
    SAMPLE_SIZE = 25
    DATA_SOURCES = 26
    P_VALUE = 27
    DISPERSION = 28
    EFFECT_SIZE = 29
    POWER = 30
    CONFIDENCE_INTERVAL = 31
    NAMED_NUMBERS = 32
    FORMULAS = 33
    CAUSAL_GRAPHS = 34
    PERL_CRITERIA = 35
    RESULTS_TABLE = 36
    STAT_PROCESSING = 37
    CLAIM = 38
    LIMITATIONS = 39
    SIDE_FINDINGS = 40
    SIDE_EFFECTS = 41
    POST_CLAIMS = 42
    OPEN_QUESTIONS = 43
    NOVELTY = 44
    VERSIONS = 45
    FUTURE_RESEARCH = 46
    REFERENCES = 47
    AGING_CONNECTION = 48
    IMAGES = 49
    CODE = 50
    FUNDING = 51
    CONFLICT_OF_INTEREST = 52
    INFORMATIONAL_VALUE = 53
    ACTION = 54
    ANIMAL_GROUP = 55
    EXPERIMENT_STEP = 56
    RESULT = 57
    ACTION_DEPENDENCY = 58   # NEW: каузальная связь между действиями
    TEMPORAL_RELATION = 59   # NEW: временная последовательность

    # Типы, у которых есть sequence (контейнеры для T4-триплетов).
    CONTAINER_TYPES = frozenset({7, 16, 22, 23, 37, 38, 39, 40, 44, 46, 47, 56, 57})

    # Все типы (для гистограмм и т.д.)
    ALL_TYPES = frozenset(range(1, 60))
