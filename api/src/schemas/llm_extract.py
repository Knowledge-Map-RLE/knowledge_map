"""Pydantic-схемы для структурированного вывода LLM-экстракции триплетов.

Unified (one-stage): модель выдаёт ВСЕ блоки (контейнеры + statement + relation)
за один вызов.

Типы блоков — строковые обозначения из Спецификации.md (см. block_types.py).
Старые числовые коды (1..59) принимаются на чтение через коэрцию.
"""
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator

from .block_types import BlockType, coerce_block_type

# Ключи из JSON-ответа LLM (two-stage / unified) → обозначение типа.
_UNIFIED_BLOCK_TYPE_MAP: Dict[str, str] = {
    "article": BlockType.METADATA,
    "objective": BlockType.GOAL,
    "research_goal": BlockType.GOAL,
    "hypothesis": BlockType.HYPOTHESIS,
    "statement": BlockType.STATEMENT,
    "study": BlockType.STATEMENT,
    "atomic_statement": BlockType.STATEMENT,
    "direct_triplet": BlockType.STATEMENT,
    "experiment": BlockType.EXPERIMENT,
    "entity": BlockType.ENTITY,
    "definition": BlockType.DEFINITION,
    "concept_definition": BlockType.DEFINITION,
    "intervention": BlockType.INTERVENTION,
    "model": BlockType.ANIMAL_MODEL,
    "animal_model": BlockType.ANIMAL_MODEL,
    "group": BlockType.ANIMAL_GROUP,
    "animal_group": BlockType.ANIMAL_GROUP,
    "procedure_step": BlockType.EXPERIMENT_STEP,
    "experiment_step": BlockType.EXPERIMENT_STEP,
    "result": BlockType.RESULT,
    "result_finding": BlockType.FINDING,
    "finding": BlockType.FINDING,
    "statistic": BlockType.STATISTICAL_PROCESSING,
    "statistical_processing": BlockType.STATISTICAL_PROCESSING,
    "claim": BlockType.CLAIM,
    "mechanism": BlockType.BIOLOGICAL_MECHANISM,
    "biological_mechanism": BlockType.BIOLOGICAL_MECHANISM,
    "action": BlockType.ACTION,
    "relation": BlockType.RELATION,
    "action_relation": BlockType.RELATION,
    "temporal_relation": BlockType.TEMPORAL_RELATION,
    "limitation": BlockType.LIMITATIONS,
    "study_limitations": BlockType.LIMITATIONS,
    "novelty": BlockType.NOVELTY,
    "future_proposal": BlockType.FUTURE_RESEARCH_SUGGESTIONS,
    "reference": BlockType.REFERENCE,
    "links_to_previous_research": BlockType.REFERENCE,
    "funding": BlockType.FUNDING,
    "funding_sources": BlockType.FUNDING,
    "side_finding": BlockType.SIDE_FINDINGS,
    "p_value": BlockType.PROBABILITY_VALUE,
    "conclusions": BlockType.POST_CLAIMS,
    "post_claims": BlockType.POST_CLAIMS,
    "goal": BlockType.GOAL,
    "text": BlockType.TEXT,
    "prerequisite": BlockType.PREREQUISITE,
    "expectations": BlockType.EXPECTATIONS,
    "research_design": BlockType.RESEARCH_DESIGN,
    "material": BlockType.MATERIAL,
    "method": BlockType.METHOD,
    "inclusion_exclusion_criteria": BlockType.INCLUSION_EXCLUSION_CRITERIA,
    "impact_goal": BlockType.IMPACT_GOAL,
    "assumptions": BlockType.ASSUMPTIONS,
    "sample_size": BlockType.SAMPLE_SIZE,
    "data_source": BlockType.DATA_SOURCE,
    "probability_value": BlockType.PROBABILITY_VALUE,
    "variance": BlockType.VARIANCE,
    "effect_size": BlockType.EFFECT_SIZE,
    "statistical_power": BlockType.STATISTICAL_POWER,
    "confidence_interval": BlockType.CONFIDENCE_INTERVAL,
    "magnitude_value": BlockType.MAGNITUDE_VALUE,
    "formula": BlockType.FORMULA,
    "causal_graph": BlockType.CAUSAL_GRAPH,
    "identifiability_criteria": BlockType.IDENTIFIABILITY_CRITERIA,
    "side_effects": BlockType.SIDE_EFFECTS,
    "open_questions": BlockType.OPEN_QUESTIONS,
    "versions": BlockType.VERSIONS,
    "link_with_aging": BlockType.LINK_WITH_AGING,
    "image": BlockType.IMAGE,
    "code": BlockType.CODE,
    "interest_conflict": BlockType.INTEREST_CONFLICT,
    "scientific_knowledge_value": BlockType.SCIENTIFIC_KNOWLEDGE_VALUE,
}


def _coerce(v: Any) -> str:
    """Строковое обозначение типа из значения ответа LLM."""
    if isinstance(v, str):
        key = v.strip()
        mapped = _UNIFIED_BLOCK_TYPE_MAP.get(key)
        if mapped:
            return mapped
        return coerce_block_type(key)
    return coerce_block_type(v)


class StructureBlock(BaseModel):
    """Один контейнерный блок из ответа Stage 1 (two-stage) или unified."""
    blockType: str = Field(alias="blockType")
    data: Dict[str, Any] = Field(default_factory=dict)
    tag: str = ""

    @field_validator("blockType", mode="before")
    @classmethod
    def coerce_block_type(cls, v: Any) -> str:
        return _coerce(v)

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
    """Один атомарный statement-триплет из ответа Stage 2."""
    blockType: str = BlockType.STATEMENT
    data: Dict[str, Any] = Field(default_factory=dict)
    container: str = ""

    @field_validator("blockType", mode="before")
    @classmethod
    def coerce_block_type(cls, v: Any) -> str:
        return _coerce(v)

    @field_validator("data", mode="before")
    @classmethod
    def coerce_data(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, dict):
            return v
        return {}


class AtomizeResponse(BaseModel):
    """Ответ Stage 2 (Atomize): statement-триплеты + маппинг последовательностей."""
    blocks: List[AtomizeBlock] = Field(default_factory=list)
    sequences: Dict[str, Any] = Field(default_factory=dict)


class UnifiedBlock(BaseModel):
    """Блок из unified-ответа (one-stage): все типы включая statement, relation."""
    blockType: str = Field(alias="blockType")
    data: Dict[str, Any] = Field(default_factory=dict)
    tag: str = ""

    @field_validator("blockType", mode="before")
    @classmethod
    def coerce_block_type(cls, v: Any) -> str:
        return _coerce(v)

    @field_validator("data", mode="before")
    @classmethod
    def coerce_data(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, dict):
            return v
        return {}


class UnifiedResponse(BaseModel):
    """Ответ unified (one-stage): все блоки за один вызов."""
    blocks: List[UnifiedBlock] = Field(default_factory=list)