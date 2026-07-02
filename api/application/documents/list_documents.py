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
) -> Tuple[List[Document], int]:
    docs = repo.list_all(skip=skip, limit=limit)
    total = repo.count_all()
    return docs, total
