"""
Layer: Application (Use Cases)
Package: application.documents.list_documents
Responsibility: Возвращает список документов с пагинацией.

Allowed imports: domain.*, application.ports.repositories
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from domain.models.document import Document
from application.ports.repositories import DocumentRepositoryProtocol


def list_documents(
    repo: DocumentRepositoryProtocol,
    skip: int = 0,
    limit: Optional[int] = None,
    full_text_only: bool = False,
) -> Tuple[List[Document], int]:
    docs = repo.list_all(skip=skip, limit=limit, full_text_only=full_text_only)
    if full_text_only:
        total = repo.count_full_text()
    else:
        total = repo.count_by_sources()
    return docs, total
