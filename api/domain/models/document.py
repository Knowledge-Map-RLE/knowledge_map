"""
Layer: Domain (Entities)
Package: domain.models.document
Responsibility: Чистое представление PDF-документа и его аннотаций как dataclass-ов.

Принадлежит слою Domain, потому что содержит только бизнес-атрибуты и бизнес-правила
выбора активной версии Markdown. Не знает о Neo4j, S3 или HTTP.

Allowed imports: только стандартная библиотека Python
Forbidden imports: neomodel, pydantic, fastapi, aioboto3
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Any


@dataclass
class Document:
    """Унифицированная модель документа — объединяет PDFDocument и Article."""
    uid: str
    original_filename: str
    md5_hash: str
    s3_bucket: str
    s3_key: str
    file_size: Optional[int] = None
    upload_date: Optional[datetime] = None

    # Метаданные документа
    title: Optional[str] = None
    authors: Optional[List[str]] = None
    abstract: Optional[str] = None
    keywords: Optional[List[str]] = None
    publication_date: Optional[datetime] = None
    journal: Optional[str] = None
    doi: Optional[str] = None

    # S3-ключи версий Markdown
    docling_raw_md_s3_key: Optional[str] = None
    formatted_md_s3_key: Optional[str] = None
    user_md_s3_key: Optional[str] = None

    # Источник: upload / pubmed / pmc / ncbi
    source: str = "upload"
    pubmed_id: Optional[str] = None
    pmc_id: Optional[str] = None
    is_open_access: bool = False

    # Статус обработки
    is_processed: bool = False
    processing_status: str = "uploaded"
    error_message: Optional[str] = None

    def get_active_markdown_key(self) -> Optional[str]:
        """
        Возвращает S3-ключ активной версии Markdown.

        Логика приоритетов:
        1. user_md_s3_key  — если пользователь сохранял свою версию
        2. formatted_md_s3_key — AI-форматированная версия
        3. docling_raw_md_s3_key — исходная (fallback)
        """
        if self.user_md_s3_key:
            return self.user_md_s3_key
        if self.formatted_md_s3_key:
            return self.formatted_md_s3_key
        return self.docling_raw_md_s3_key

    def get_s3_url(self) -> str:
        return f"s3://{self.s3_bucket}/{self.s3_key}"

    @property
    def is_upload(self) -> bool:
        return self.source == "upload"

    @property
    def is_pubmed(self) -> bool:
        return self.source in ("pubmed", "pmc", "ncbi")

    @property
    def has_full_text(self) -> bool:
        """Есть ли полный текст статьи (не только abstract)."""
        return bool(self.docling_raw_md_s3_key or self.formatted_md_s3_key)


@dataclass
class PDFAnnotation:
    """Аннотация на уровне страниц PDF-документа."""
    uid: str
    annotation_type: str
    content: str
    confidence: Optional[float] = None
    page_number: Optional[int] = None
    bbox_x: Optional[float] = None
    bbox_y: Optional[float] = None
    bbox_width: Optional[float] = None
    bbox_height: Optional[float] = None
    metadata: Optional[Any] = None
    created_date: Optional[datetime] = None

    def get_bbox(self) -> dict:
        return {
            "x": self.bbox_x,
            "y": self.bbox_y,
            "width": self.bbox_width,
            "height": self.bbox_height,
        }
