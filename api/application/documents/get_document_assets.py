"""
Layer: Application (Use Cases)
Package: application.documents.get_document_assets
Responsibility: Получает markdown и список изображений для документа.

Allowed imports: domain.*, application.ports.repositories, application.ports.object_storage
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

import logging
import re
from typing import Dict, Any, Optional

from domain.exceptions import NotFoundError
from application.ports.repositories import DocumentRepositoryProtocol
from application.ports.object_storage import ObjectStorageProtocol

logger = logging.getLogger(__name__)


async def get_document_assets(
    document_repo: DocumentRepositoryProtocol,
    storage: ObjectStorageProtocol,
    doc_id: str,
    base_url: str = "http://localhost:8000",
) -> Dict[str, Any]:
    """
    Возвращает markdown и URL изображений документа.

    Raises:
        NotFoundError: документ не найден
    """
    doc = document_repo.get_by_id(doc_id)
    if doc is None:
        raise NotFoundError("PDFDocument", doc_id)

    bucket = doc.s3_bucket
    prefix = f"documents/{doc_id}/"

    # Получаем активный markdown
    active_key = doc.get_active_markdown_key()
    markdown = None
    if active_key:
        markdown = await storage.download_text(bucket, active_key)
        if markdown:
            markdown = _convert_image_paths(markdown, doc_id, base_url)

    # Список изображений
    objects = await storage.list_objects(bucket, prefix=f"{prefix}images/")
    if not objects:
        # fallback — изображения прямо в prefix без подпапки images/
        objects = await storage.list_objects(bucket, prefix=prefix)

    image_names = []
    image_urls: Dict[str, str] = {}
    for obj in objects:
        key = obj.get("Key", "")
        name = key.split("/")[-1]
        if name and any(name.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp")):
            image_names.append(name)
            image_urls[name] = f"{base_url}/api/v1/s3/image/{key}"

    return {
        "doc_id": doc_id,
        "markdown": markdown,
        "images": image_names,
        "image_urls": image_urls,
    }


def _convert_image_paths(markdown_text: str, doc_id: str, base_url: str) -> str:
    """Преобразует относительные пути изображений в абсолютные URL."""
    image_prefix = f"{base_url}/api/v1/s3/image/documents/{doc_id}/images/"

    def replace_path(match):
        alt = match.group(1)
        path = match.group(2)
        if path.startswith("http://") or path.startswith("https://"):
            return match.group(0)
        return f"![{alt}](<{image_prefix}{path}>)"

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace_path, markdown_text)
