"""
Layer: Application (Use Cases)
Package: application.documents.list_documents
Responsibility: Возвращает список всех документов.

Allowed imports: domain.*, application.ports.repositories
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

from typing import List

from domain.models.document import Document
from application.ports.repositories import DocumentRepositoryProtocol


def list_documents(repo: DocumentRepositoryProtocol) -> List[Document]:
    return repo.list_all()
