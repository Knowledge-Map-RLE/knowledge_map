"""
Layer: Application (Use Cases)
Package: application.documents.delete_document
Responsibility: Удаляет документ из Neo4j и все связанные файлы из S3.

Allowed imports: domain.*, application.ports.repositories, application.ports.object_storage
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

import logging

from domain.exceptions import NotFoundError
from application.ports.repositories import DocumentRepositoryProtocol
from application.ports.object_storage import ObjectStorageProtocol

logger = logging.getLogger(__name__)


async def delete_document(
    document_repo: DocumentRepositoryProtocol,
    storage: ObjectStorageProtocol,
    doc_id: str,
) -> None:
    """
    Удаляет документ и все его S3-файлы.

    Raises:
        NotFoundError: документ не найден
    """
    doc = document_repo.get_by_id(doc_id)
    if doc is None:
        raise NotFoundError("PDFDocument", doc_id)

    bucket = doc.s3_bucket
    prefix = f"documents/{doc_id}/"

    # Удаляем все файлы из S3
    objects = await storage.list_objects(bucket, prefix=prefix)
    for obj in objects:
        key = obj.get("Key", "")
        if key:
            await storage.delete_object(bucket, key)
            logger.info(f"[delete_document] Удалён S3-объект: {key}")

    # Удаляем запись из Neo4j
    document_repo.delete(doc_id)
    logger.info(f"[delete_document] Удалён документ {doc_id}")
