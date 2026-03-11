"""
Layer: Domain (Entities)
Package: domain.models.block
Responsibility: Чистое представление блока и записи связи как dataclass-ов.

Принадлежит слою Domain, потому что содержит только бизнес-атрибуты без
зависимостей от фреймворков. Не знает о Neo4j, FastAPI или gRPC.

Allowed imports: только стандартная библиотека Python
Forbidden imports: neomodel, pydantic, fastapi, grpc, aioboto3
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class Block:
    """Блок в графе знаний."""
    uid: str
    content: str
    layer: int = 0
    level: int = 0
    sublevel_id: int = -1
    physical_scale: int = 0
    is_pinned: bool = False
    data: Optional[Any] = None


@dataclass
class LinkRecord:
    """Запись о связи между двумя блоками."""
    uid: str
    source_id: str
    target_id: str


@dataclass
class Tag:
    """Метка блока."""
    text: str


@dataclass
class LinkMetadata:
    """Метаданные связи."""
    uid: str
    source_id: str
    target_id: str
