"""
Layer: Application (Use Cases)
Package: application.documents
Responsibility: Use case — нечёткий поиск документов по названию.
"""
from __future__ import annotations

from typing import List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from application.ports.repositories import DocumentRepositoryProtocol

from domain.models.document import Document


class SearchDocumentsUseCase:
    """Нечёткий поиск документов по названию / оригинальному имени файла."""

    def __init__(self, repo: DocumentRepositoryProtocol) -> None:
        self._repo = repo

    def execute(self, q: str, skip: int = 0, limit: int = 100, full_text_only: bool = False) -> Tuple[List[Document], int]:
        if not q or not q.strip():
            docs = self._repo.list_all(skip=skip, limit=limit, full_text_only=full_text_only)
            total = self._repo.count_full_text() if full_text_only else self._repo.count_by_sources()
            return docs, total

        return self._repo.search(q=q.strip(), skip=skip, limit=limit, full_text_only=full_text_only)
