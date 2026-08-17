"""Pydantic-схемы для структурированного вывода LLM-экстракции триплетов.

Стадия 1 (Structure): модель выдаёт контейнерные блоки (T7, T14, T22 и т.д.)
Стадия 2 (Atomize): модель выдаёт атомарные T4-триплеты с привязкой к контейнерам.

Схемы заменяют ручные ``_parse_structure_json``/``_parse_atomize_json`` и
обеспечивают валидацию на этапе парсинга (fail-fast при некорректном выводе).
JSON-ремонт (``_repair_common_json``, ``_extract_json_fragments``) остаётся
как нормализация перед парсингом.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class StructureBlock(BaseModel):
    """Один контейнерный блок из ответа Stage 1."""
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
