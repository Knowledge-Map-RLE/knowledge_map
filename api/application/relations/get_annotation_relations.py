"""
Layer: Application (Use Cases)
Package: application.relations.get_annotation_relations
Responsibility: Возвращает все связи между аннотациями документа.

Allowed imports: domain.*, application.ports.repositories
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

from typing import List

from domain.models.annotation import AnnotationRelation
from domain.exceptions import NotFoundError
from application.ports.repositories import AnnotationRepositoryProtocol, DocumentRepositoryProtocol


def get_annotation_relations(
    annotation_repo: AnnotationRepositoryProtocol,
    document_repo: DocumentRepositoryProtocol,
    doc_id: str,
) -> List[AnnotationRelation]:
    if document_repo.get_by_id(doc_id) is None:
        raise NotFoundError("Document", doc_id)
    return annotation_repo.get_relations_for_document(doc_id)
