"""API схемы для запросов и ответов"""
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


# Базовые схемы для блоков и связей
class BlockInput(BaseModel):
    content: str


class LinkInput(BaseModel):
    source: str
    target: str


class LayoutRequest(BaseModel):
    blocks: List[BlockInput]
    links: List[LinkInput]
    sublevel_spacing: Optional[int] = 200
    layer_spacing: Optional[int] = 250
    optimize_layout: bool = True


class CreateAndLinkInput(BaseModel):
    source_block_id: str
    new_block_content: str = "Новый блок"
    link_direction: str = Field(..., pattern="^(from_source|to_source)$")  # 'from_source' или 'to_source'


class MoveToLevelInput(BaseModel):
    target_level: int


class PinWithScaleInput(BaseModel):
    physical_scale: int  # степень 10 в метрах


# Схемы для S3
class S3UploadResponse(BaseModel):
    success: bool
    object_key: Optional[str] = None
    error: Optional[str] = None


class S3FileResponse(BaseModel):
    content: Optional[str] = None
    content_type: Optional[str] = None
    size: Optional[int] = None
    last_modified: Optional[str] = None
    error: Optional[str] = None


class S3ListResponse(BaseModel):
    objects: List[Dict[str, Any]]
    count: int


# Схемы для извлечения данных
class DataExtractionResponse(BaseModel):
    success: bool
    doc_id: Optional[str] = None
    message: Optional[str] = None
    files: Optional[Dict[str, str]] = None


class ImportAnnotationsRequest(BaseModel):
    doc_id: str
    annotations_json: Dict[str, Any]


class DocumentAssetsResponse(BaseModel):
    success: bool
    doc_id: str
    markdown: Optional[str] = None
    images: List[str] = []
    image_urls: Dict[str, str] = {}
    files: Optional[Dict[str, str]] = None
    pdf_url: Optional[str] = None


class DocumentItem(BaseModel):
    doc_id: str
    has_markdown: bool = False
    files: Dict[str, str] = {}


# Схемы для viewport
class ViewportBounds(BaseModel):
    left: float
    right: float
    top: float
    bottom: float


class ViewportEdgesResponse(BaseModel):
    blocks: List[Dict[str, Any]]
    links: List[Dict[str, Any]]
