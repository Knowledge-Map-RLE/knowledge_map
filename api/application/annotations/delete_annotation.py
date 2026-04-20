"""
Layer: Application (Use Cases)
Package: application.annotations.delete_annotation
Responsibility: Удаляет одну аннотацию или все аннотации документа.

Allowed imports: domain.*, application.ports.repositories
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

from domain.exceptions import NotFoundError
from application.ports.repositories import AnnotationRepositoryProtocol, DocumentRepositoryProtocol


def delete_annotation(
    repo: AnnotationRepositoryProtocol,
    annotation_id: str,
) -> None:
    """Raises: NotFoundError если аннотация не найдена."""
    ann = repo.get_by_id(annotation_id)
    if ann is None:
        raise NotFoundError("MarkdownAnnotation", annotation_id)
    repo.delete(annotation_id)


def delete_all_annotations(
    annotation_repo: AnnotationRepositoryProtocol,
    document_repo: DocumentRepositoryProtocol,
    doc_id: str,
) -> int:
    """
    Удаляет все аннотации документа.

    Returns:
        Количество удалённых аннотаций.

    Raises:
        NotFoundError: документ не найден
    """
    if document_repo.get_by_id(doc_id) is None:
        raise NotFoundError("Document", doc_id)
    return annotation_repo.delete_all_for_document(doc_id)
