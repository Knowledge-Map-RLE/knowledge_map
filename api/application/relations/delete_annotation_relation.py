"""
Layer: Application (Use Cases)
Package: application.relations.delete_annotation_relation
Responsibility: Удаляет связь между двумя аннотациями.

Allowed imports: domain.*, application.ports.repositories
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

from application.ports.repositories import AnnotationRepositoryProtocol


def delete_annotation_relation(
    repo: AnnotationRepositoryProtocol,
    source_id: str,
    target_id: str,
) -> None:
    repo.delete_relation(source_uid=source_id, target_uid=target_id)
