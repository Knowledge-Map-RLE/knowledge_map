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
from domain.models.document import Document
from application.ports.repositories import DocumentRepositoryProtocol
from application.ports.object_storage import ObjectStorageProtocol

logger = logging.getLogger(__name__)


def _build_abstract_markdown(doc: Document) -> str:
    """Генерирует markdown из метаданных документа как fallback."""
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
        if version == "active":
            fallback = _build_abstract_markdown(doc)
            if fallback:
                logger.info(
                    f"[get_markdown] Active markdown key отсутствует для doc_id={doc_id} "
                    f"(source={doc.source}), используется fallback из abstract"
                )
                return fallback
        return None

    content = await storage.download_text(bucket, key)
    if not content and version == "active":
        fallback = _build_abstract_markdown(doc)
        if fallback:
            logger.info(
                f"[get_markdown] Markdown не найден в S3 по ключу {key} для doc_id={doc_id} "
                f"(source={doc.source}), используется fallback из abstract"
            )
            return fallback
    return content
