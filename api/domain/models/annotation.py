"""
Layer: Domain (Entities)
Package: domain.models.annotation
Responsibility: Чистое представление Markdown-аннотации и связи между аннотациями.

Принадлежит слою Domain — только бизнес-атрибуты, никаких зависимостей от Neo4j или HTTP.

Allowed imports: только стандартная библиотека Python
Forbidden imports: neomodel, pydantic, fastapi
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any


@dataclass
class MarkdownAnnotation:
    """Аннотация фрагмента текста в Markdown-документе."""
    uid: str
    text: str
    annotation_type: str
    start_offset: int
    end_offset: int
    color: str = "#ffeb3b"
    metadata: Optional[Any] = None
    confidence: Optional[float] = None
    created_date: Optional[datetime] = None
    source: str = "user"
    processor_version: Optional[str] = None


@dataclass
class AnnotationRelation:
    """Направленная связь между двумя Markdown-аннотациями."""
    uid: str
    source_uid: str
    target_uid: str
    relation_type: str
    created_date: Optional[datetime] = None
    metadata: Optional[Any] = None
