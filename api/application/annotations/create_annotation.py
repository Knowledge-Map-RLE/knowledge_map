"""
Layer: Application (Use Cases)
Package: application.annotations.create_annotation
Responsibility: Создаёт новую Markdown-аннотацию для документа.

Allowed imports: domain.*, application.ports.repositories
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

from domain.models.annotation import MarkdownAnnotation
from domain.exceptions import NotFoundError
from domain.rules.annotation_validation import validate_offsets
from application.ports.repositories import AnnotationRepositoryProtocol, DocumentRepositoryProtocol


def create_annotation(
    annotation_repo: AnnotationRepositoryProtocol,
    document_repo: DocumentRepositoryProtocol,
    doc_id: str,
    text: str,
    annotation_type: str,
    start_offset: int,
    end_offset: int,
    color: str = "#ffeb3b",
    metadata: dict = None,
    confidence: float = None,
    source: str = "user",
    processor_version: str = None,
) -> MarkdownAnnotation:
    """
    Создаёт аннотацию. Валидирует offsets и проверяет существование документа.

    Raises:
        NotFoundError: документ не найден
        DomainValidationError: некорректные offsets
    """
    if document_repo.get_by_id(doc_id) is None:
        raise NotFoundError("Document", doc_id)

    validate_offsets(start_offset, end_offset)

    annotation = MarkdownAnnotation(
        uid="",
        text=text,
        annotation_type=annotation_type,
        start_offset=start_offset,
        end_offset=end_offset,
        color=color,
        metadata=metadata or {},
        confidence=confidence,
        source=source,
        processor_version=processor_version,
    )
    annotation = annotation_repo.create(annotation, doc_id)

    # Статус 'annotated' НЕ присваивается здесь: он назначается только при
    # сохранении валидного markdown через PUT /documents/{id}/markdown.
    return annotation
