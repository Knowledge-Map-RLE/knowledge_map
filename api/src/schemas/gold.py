"""Pydantic-схемы и константы золотых эталонов (eval/gold).

Единый источник для API-сервиса эталонов и CLI-валидатора eval/validate_gold.py.
"""
from typing import Any, Dict

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tools.llm_extract.metrics import is_uuid

GOLD_SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = {GOLD_SCHEMA_VERSION}
MANIFEST_NAME = "manifest.json"
CHECKSUMS_NAME = "checksums.sha256"
STRUCTURAL_LINES_NAME = "structural_lines.json"
ARTICLE_NAME = "article.md"
META_NAME = "meta.json"
CASE_FILES = (ARTICLE_NAME, META_NAME, STRUCTURAL_LINES_NAME)
REQUIRED_META_FIELDS = ("slug", "schema_version", "article_title", "source_article")
OPTIONAL_META_FIELDS = ("doi", "lang")
CHECKSUM_EXCLUDES = {CHECKSUMS_NAME}


class GoldBlock(BaseModel):
    """Схема одной структурной строки эталона."""

    model_config = ConfigDict(extra="allow")

    instanceId: str
    blockType: int = Field(ge=1, le=59)
    order: int = Field(ge=0)
    data: Dict[str, Any]

    @field_validator("instanceId")
    @classmethod
    def _instance_id_is_uuid(cls, value: str) -> str:
        if not is_uuid(value):
            raise ValueError("instanceId не является корректным UUID")
        return value

    @field_validator("data")
    @classmethod
    def _data_not_empty(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        if not value:
            raise ValueError("data не может быть пустым объектом")
        return value
