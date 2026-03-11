"""
Layer: Application (Use Cases)
Package: application.relations.create_annotation_relation
Responsibility: Создаёт направленную связь между двумя аннотациями.

Allowed imports: domain.*, application.ports.repositories
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

from typing import Optional, Dict, Any

from domain.models.annotation import AnnotationRelation
from application.ports.repositories import AnnotationRepositoryProtocol


def create_annotation_relation(
    repo: AnnotationRepositoryProtocol,
    source_id: str,
    target_id: str,
    relation_type: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> AnnotationRelation:
    return repo.create_relation(
        source_uid=source_id,
        target_uid=target_id,
        relation_type=relation_type,
        metadata=metadata,
    )
