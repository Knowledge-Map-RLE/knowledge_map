"""
Layer: Application (Use Cases)
Package: application.documents.get_document_assets
Responsibility: Получает Markdown, исходный PDF и изображения документа.

Allowed imports: domain.*, application.ports.repositories, application.ports.object_storage
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

import logging
import re
from typing import Dict, Any, Optional
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from domain.exceptions import NotFoundError
from domain.models.document import Document
from application.ports.repositories import DocumentRepositoryProtocol
from application.ports.object_storage import ObjectStorageProtocol

logger = logging.getLogger(__name__)


def _build_abstract_markdown(doc: Document) -> str:
    """
    Генерирует markdown из метаданных документа для случаев,
    когда полный текст статьи отсутствует в S3 (PubMed-only и т.д.).
    """
    parts: list[str] = []

    if doc.title:
        parts.append(f"# {doc.title}\n")

    if doc.authors:
        if isinstance(doc.authors, list):
            authors_str = ", ".join(doc.authors)
        else:
            authors_str = str(doc.authors)
        parts.append(f"**Authors:** {authors_str}\n")

    meta_parts: list[str] = []
    if doc.journal:
        meta_parts.append(f"**Journal:** {doc.journal}")
    if doc.publication_date:
        meta_parts.append(f"**Published:** {doc.publication_date.strftime('%Y-%m-%d') if hasattr(doc.publication_date, 'strftime') else doc.publication_date}")
    if doc.doi:
        meta_parts.append(f"**DOI:** {doc.doi}")
    if doc.pubmed_id:
        meta_parts.append(f"**PMID:** {doc.pubmed_id}")
    if doc.pmc_id:
        meta_parts.append(f"**PMCID:** {doc.pmc_id}")
    if meta_parts:
        parts.append(" | ".join(meta_parts) + "\n")

    if doc.abstract:
        parts.append(f"## Abstract\n\n{doc.abstract}\n")

    if doc.keywords:
        if isinstance(doc.keywords, list):
            kw_str = ", ".join(doc.keywords)
        else:
            kw_str = str(doc.keywords)
        parts.append(f"**Keywords:** {kw_str}\n")

    return "\n".join(parts) if parts else ""


async def get_document_assets(
    document_repo: DocumentRepositoryProtocol,
    storage: ObjectStorageProtocol,
    doc_id: str,
    base_url: str = "",
) -> Dict[str, Any]:
    """
    Возвращает Markdown, URL исходного PDF и URL изображений документа.

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

    # Проверяем существование markdown перед скачиванием (избегаем NoSuchKey)
    md_exists = await storage.object_exists(bucket, active_key) if active_key else False
    markdown_task = storage.download_text(bucket, active_key) if md_exists else asyncio.sleep(0, result=None)
    images_task = storage.list_objects(bucket, prefix=prefix)

    markdown_raw, objects = await asyncio.gather(markdown_task, images_task)

    image_object_keys: Dict[str, str] = {}
    image_names = []
    image_urls: Dict[str, str] = {}
    image_extensions = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff")
    for obj in objects:
        key = obj.get("Key", "")
        name = key.split("/")[-1]
        if not name or not name.lower().endswith(image_extensions):
            continue

        relative_key = key[len(prefix):] if key.startswith(prefix) else name
        image_object_keys[relative_key] = key
        image_object_keys.setdefault(name, key)
        image_names.append(name)
        image_urls[name] = f"/api/v1/s3/image/{quote(key, safe='/')}"

    markdown = None
    if markdown_raw:
        markdown = _convert_image_paths(markdown_raw, doc_id, image_object_keys)

    # Fallback: если markdown отсутствует в S3, генерируем из метаданных документа.
    # Это обеспечивает отображение текста для PubMed-only статей, у которых
    # есть abstract/title/authors в Neo4j, но нет markdown-файла в S3.
    if not markdown:
        fallback_md = _build_abstract_markdown(doc)
        if fallback_md:
            markdown = fallback_md
            logger.info(
                f"[get_document_assets] Markdown отсутствует в S3 для doc_id={doc_id} "
                f"(source={doc.source}), используется fallback из abstract ({len(fallback_md)} chars)"
            )

    result: Dict[str, Any] = {
        "doc_id": doc_id,
        "markdown": markdown,
        "images": image_names,
        "image_urls": image_urls,
    }

    # Возвращаем браузерный URL через API-прокси, а не внутренний S3 URL.
    if doc.source == "upload" and doc.s3_key and doc.s3_key.lower().endswith(".pdf"):
        if await storage.object_exists(bucket, doc.s3_key):
            pdf_url = f"/api/v1/s3/image/{quote(doc.s3_key, safe='/')}"
            result["pdf_url"] = pdf_url
            result["files"] = {"pdf": pdf_url}
        else:
            logger.warning(
                "[get_document_assets] Исходный PDF отсутствует в S3: doc_id=%s, key=%s",
                doc_id,
                doc.s3_key,
            )

    return result


def _convert_image_paths(
    markdown_text: str,
    doc_id: str,
    image_object_keys: Optional[Dict[str, str]] = None,
) -> str:
    """Преобразует относительные пути изображений в HTML figure/img теги с относительными URL."""
    image_prefix = f"/api/data_extraction/documents/{doc_id}/images/"
    image_object_keys = image_object_keys or {}

    def replace_path(match):
        alt = match.group(1)
        path = match.group(2)
        parsed = urlsplit(path)
        if parsed.scheme in ("http", "https") and parsed.path.startswith("/api/"):
            url = urlunsplit(("", "", parsed.path, parsed.query, parsed.fragment))
        elif path.startswith("/api/"):
            url = path
        elif parsed.scheme in ("http", "https"):
            url = path
        else:
            relative_path = unquote(parsed.path).replace("\\", "/").lstrip("./")
            object_key = image_object_keys.get(relative_path)
            if object_key is None:
                object_key = image_object_keys.get(relative_path.rsplit("/", 1)[-1])
            if object_key:
                url = f"/api/v1/s3/image/{quote(object_key, safe='/')}"
            else:
                url = f"{image_prefix}{quote(relative_path, safe='/')}"
        return f'<figure><img src="{url}" alt="{alt}" style="max-width:100%"/><figcaption>{alt}</figcaption></figure>'

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace_path, markdown_text)
