"""
Layer: Application (Use Cases)
Package: application.documents.update_markdown
Responsibility: Сохраняет пользовательскую версию Markdown в S3 и обновляет запись в Neo4j.

Allowed imports: domain.*, application.ports.*
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

import logging
import re
from typing import Optional, Dict, Any

from domain.exceptions import NotFoundError, StorageError
from application.ports.repositories import DocumentRepositoryProtocol
from application.ports.object_storage import ObjectStorageProtocol

logger = logging.getLogger(__name__)


def _extract_title(markdown: str) -> Optional[str]:
    """Извлекает заголовок первого уровня из Markdown."""
    for line in markdown.split("\n"):
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            title = line[2:].strip()
            if title:
                return title
    return None


async def update_markdown(
    document_repo: DocumentRepositoryProtocol,
    storage: ObjectStorageProtocol,
    doc_id: str,
    markdown: str,
    bucket: str,
    annotate: bool = False,
) -> Dict[str, Any]:
    """
    Сохраняет markdown как user_md_s3_key.

    Args:
        annotate: если True, переводит документ в статус 'annotated'

    Raises:
        NotFoundError: документ не найден
        StorageError: не удалось загрузить в S3
    """
    doc = document_repo.get_by_id(doc_id)
    if doc is None:
        raise NotFoundError("Document", doc_id)

    user_key = f"documents/{doc_id}/{doc_id}_user.md"
    uploaded = await storage.upload_bytes(
        data=markdown.encode("utf-8"),
        bucket_name=bucket,
        object_key=user_key,
        content_type="text/markdown; charset=utf-8",
    )
    if not uploaded:
        raise StorageError("update_markdown", f"Не удалось сохранить markdown для {doc_id}")

    # Обновляем запись
    if annotate:
        doc.processing_status = "annotated"
        doc.is_processed = True
    doc.user_md_s3_key = user_key
    new_title = _extract_title(markdown)
    if new_title:
        doc.title = new_title

    document_repo.save(doc)
    logger.info(f"[update_markdown] Сохранён markdown для {doc_id}, ключ: {user_key}, annotate={annotate}")

    return {
        "doc_id": doc_id,
        "s3_key": user_key,
        "title": doc.title,
    }
