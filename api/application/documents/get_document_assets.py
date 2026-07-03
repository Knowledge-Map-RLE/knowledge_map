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
    base_url: str = "",
) -> Dict[str, Any]:
    """
    Возвращает markdown и URL изображений документа.

    Raises:
        NotFoundError: документ не найден
    """
    doc = document_repo.get_by_id(doc_id)
    if doc is None:
        raise NotFoundError("Document", doc_id)

    import asyncio

    bucket = doc.s3_bucket
    prefix = f"documents/{doc_id}/"

    active_key = doc.get_active_markdown_key()
    if not active_key:
        active_key = f"{prefix}{doc_id}.md"

    # Параллельно: markdown + список изображений в images/
    markdown_task = storage.download_text(bucket, active_key) if active_key else asyncio.sleep(0, result=None)
    images_task = storage.list_objects(bucket, prefix=prefix)

    markdown_raw, objects = await asyncio.gather(markdown_task, images_task)

    markdown = None
    if markdown_raw:
        markdown = _convert_image_paths(markdown_raw, doc_id)

    image_names = []
    image_urls: Dict[str, str] = {}
    for obj in objects:
        key = obj.get("Key", "")
        name = key.split("/")[-1]
        if name and any(name.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp")):
            image_names.append(name)
            image_urls[name] = f"/api/data_extraction/documents/{doc_id}/images/{name}"

    return {
        "doc_id": doc_id,
        "markdown": markdown,
        "images": image_names,
        "image_urls": image_urls,
    }


def _convert_image_paths(markdown_text: str, doc_id: str) -> str:
    """Преобразует относительные пути изображений в HTML figure/img теги с относительными URL."""
    image_prefix = f"/api/data_extraction/documents/{doc_id}/images/"

    def replace_path(match):
        alt = match.group(1)
        path = match.group(2)
        if path.startswith("http://") or path.startswith("https://"):
            url = path
        elif path.startswith("/api/"):
            url = path
        else:
            url = f"{image_prefix}{path}"
        return f'<figure><img src="{url}" alt="{alt}" style="max-width:100%"/><figcaption>{alt}</figcaption></figure>'

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace_path, markdown_text)
