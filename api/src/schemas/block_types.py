"""Тонкий реэкспорт канонического реестра структурных строк.

Единый источник истины — `knowledge_contracts.block_types`. Этот модуль
сохраняется для совместимости существующих импортов.
"""
from __future__ import annotations

from knowledge_contracts.block_types import (  # noqa: F401
    ALL_TYPES,
    ALL_TYPES_SET,
    BLOCK_TYPE_NAMES,
    KEY_TO_LEGACY_INT,
    LEGACY_INT_TO_KEY,
    BlockType,
    coerce_block_type,
)