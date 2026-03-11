"""
Layer: Application (Use Cases)
Package: application.annotations.update_annotation
Responsibility: Обновляет поля существующей аннотации.

Allowed imports: domain.*, application.ports.repositories
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

from typing import Optional, Dict, Any

from domain.models.annotation import MarkdownAnnotation
from domain.exceptions import NotFoundError
from domain.rules.annotation_validation import validate_offsets
from application.ports.repositories import AnnotationRepositoryProtocol


def update_annotation(
    repo: AnnotationRepositoryProtocol,
    annotation_id: str,
    text: Optional[str] = None,
    annotation_type: Optional[str] = None,
    start_offset: Optional[int] = None,
    end_offset: Optional[int] = None,
    color: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> MarkdownAnnotation:
    """
    Частичное обновление аннотации (только переданные поля).

    Raises:
        NotFoundError: аннотация не найдена
        DomainValidationError: некорректные offsets
    """
    annotation = repo.get_by_id(annotation_id)
    if annotation is None:
        raise NotFoundError("MarkdownAnnotation", annotation_id)

    if text is not None:
        annotation.text = text
    if annotation_type is not None:
        annotation.annotation_type = annotation_type
    if color is not None:
        annotation.color = color
    if metadata is not None:
        annotation.metadata = metadata

    new_start = start_offset if start_offset is not None else annotation.start_offset
    new_end = end_offset if end_offset is not None else annotation.end_offset
    validate_offsets(new_start, new_end)
    annotation.start_offset = new_start
    annotation.end_offset = new_end

    return repo.save(annotation)
