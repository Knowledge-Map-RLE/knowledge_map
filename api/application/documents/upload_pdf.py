"""
Layer: Application (Use Cases)
Package: application.documents.upload_pdf
Responsibility: Загружает PDF, проверяет дедупликацию по MD5 и ставит задачу на обработку.

Принадлежит слою Application — оркестрирует: хеш → дедупликация → S3 → Neo4j.
Не знает о HTTP, FastAPI.BackgroundTasks, или деталях gRPC.

Allowed imports: domain.*, application.ports.*, стандартная библиотека
Forbidden imports: fastapi, neomodel, grpc (напрямую), infrastructure, web
"""
from __future__ import annotations

import logging
from typing import Callable, Awaitable, Dict, Any

from domain.models.document import Document
from domain.exceptions import DocumentAlreadyExistsError, StorageError
from application.ports.repositories import DocumentRepositoryProtocol
from application.ports.object_storage import ObjectStorageProtocol

logger = logging.getLogger(__name__)


async def upload_pdf(
    document_repo: DocumentRepositoryProtocol,
    storage: ObjectStorageProtocol,
    pdf_bytes: bytes,
    filename: str,
    bucket: str,
    md5_hash: str,
    enqueue_processing: Callable[[str, bytes, str], Awaitable[None]],
) -> Dict[str, Any]:
    """
    Загружает PDF-файл в хранилище. Если документ с таким MD5 уже существует —
    возвращает информацию о нём. Иначе создаёт запись в Neo4j и ставит в очередь
    фоновую обработку.

    Args:
        document_repo: репозиторий документов
        storage: файловое хранилище
        pdf_bytes: байты PDF
        filename: оригинальное имя файла
        bucket: S3-bucket
        md5_hash: MD5-хеш содержимого
        enqueue_processing: callable для постановки задачи конвертации PDF→MD

    Returns:
        dict с ключами: doc_id, is_duplicate, message
    """
    prefix = f"documents/{md5_hash}/"
    pdf_key = f"{prefix}{md5_hash}.pdf"

    # Проверяем дедупликацию
    existing = document_repo.get_by_md5(md5_hash)
    pdf_exists = await storage.object_exists(bucket, pdf_key)

    if existing and pdf_exists:
        logger.info(f"[upload_pdf] Документ {md5_hash} уже существует")
        return {"doc_id": existing.uid, "is_duplicate": True, "message": "Документ уже загружен"}

    # Загружаем PDF в S3
    uploaded = await storage.upload_bytes(
        data=pdf_bytes,
        bucket_name=bucket,
        object_key=pdf_key,
        content_type="application/pdf",
        metadata={"original_filename": filename},
    )
    if not uploaded:
        raise StorageError("upload_pdf", f"Не удалось загрузить {filename} в S3")

    # Создаём/обновляем запись в Neo4j
    if not existing:
        doc = Document(
            uid=md5_hash,
            original_filename=filename,
            md5_hash=md5_hash,
            s3_bucket=bucket,
            s3_key=pdf_key,
            file_size=len(pdf_bytes),
            processing_status="uploaded",
            is_processed=False,
        )
        document_repo.save(doc)
        logger.info(f"[upload_pdf] Создан документ {md5_hash}")

    # Ставим в очередь фоновую конвертацию PDF → Markdown
    await enqueue_processing(md5_hash, pdf_bytes, filename)

    return {"doc_id": md5_hash, "is_duplicate": False, "message": "PDF загружен, обработка начата"}
