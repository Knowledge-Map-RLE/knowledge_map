"""
Layer: Application (Use Cases)
Package: application.annotations.get_annotations
Responsibility: Возвращает аннотации документа с пагинацией и фильтрацией.

Allowed imports: domain.*, application.ports.repositories
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

from typing import Optional, List, Tuple

from domain.models.annotation import MarkdownAnnotation
from domain.exceptions import NotFoundError
from application.ports.repositories import AnnotationRepositoryProtocol, DocumentRepositoryProtocol


def get_annotations(
    annotation_repo: AnnotationRepositoryProtocol,
    document_repo: DocumentRepositoryProtocol,
    doc_id: str,
    skip: int = 0,
    limit: Optional[int] = None,
    annotation_types: Optional[List[str]] = None,
    source: Optional[str] = None,
) -> Tuple[List[MarkdownAnnotation], int]:
    """
    Возвращает (список аннотаций, total_count).

    Raises:
        NotFoundError: документ не найден
    """
    if document_repo.get_by_id(doc_id) is None:
        raise NotFoundError("PDFDocument", doc_id)

    return annotation_repo.get_by_document(
        doc_id=doc_id,
        skip=skip,
        limit=limit,
        annotation_types=annotation_types,
        source=source,
    )
