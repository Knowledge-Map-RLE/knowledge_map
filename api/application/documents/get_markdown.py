"""
Layer: Application (Use Cases)
Package: application.documents.get_markdown
Responsibility: Возвращает конкретную версию Markdown документа.

Allowed imports: domain.*, application.ports.*
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

import logging
from typing import Optional

from domain.exceptions import NotFoundError
from application.ports.repositories import DocumentRepositoryProtocol
from application.ports.object_storage import ObjectStorageProtocol

logger = logging.getLogger(__name__)


async def get_markdown(
    document_repo: DocumentRepositoryProtocol,
    storage: ObjectStorageProtocol,
    doc_id: str,
    version: str = "active",  # active | raw | formatted | user
) -> Optional[str]:
    """
    Возвращает Markdown выбранной версии.

    Args:
        version: 'active' — приоритетная версия; 'raw' — docling_raw;
                 'formatted' — AI-форматированная; 'user' — пользовательская

    Raises:
        NotFoundError: документ не найден
    """
    doc = document_repo.get_by_id(doc_id)
    if doc is None:
        raise NotFoundError("Document", doc_id)

    bucket = doc.s3_bucket

    if version == "raw":
        key = doc.docling_raw_md_s3_key
    elif version == "formatted":
        key = doc.formatted_md_s3_key
    elif version == "user":
        key = doc.user_md_s3_key
    else:  # active
        key = doc.get_active_markdown_key()

    if not key:
        return None

    return await storage.download_text(bucket, key)
