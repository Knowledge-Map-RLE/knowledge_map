"""Схемы данных для API"""
from pydantic import BaseModel
from typing import Dict, Any, Optional, List


class ConvertRequest(BaseModel):
    """Запрос на конвертацию PDF"""
    pdf_content: bytes
    model_id: Optional[str] = None
    doc_id: Optional[str] = None
    use_coordinate_extraction: bool = True


class S3ImageInfo(BaseModel):
    """Информация об изображении в S3"""
    filename: str
    s3_url: str
    s3_object_key: str
    page_no: int
    size_bytes: Optional[int] = None
    image_size: Optional[List[int]] = None  # [width, height]


class ConvertResponse(BaseModel):
    """Ответ на запрос конвертации"""
    success: bool
    doc_id: str
    markdown_content: str
    images: Dict[str, bytes] = {}
    metadata: Optional[Dict[str, Any]] = None
    message: str
    s3_images: Optional[List[S3ImageInfo]] = None
    extraction_method: Optional[str] = None


class ProgressUpdate(BaseModel):
    """Обновление прогресса"""
    doc_id: str
    percent: int
    phase: str
    message: str


class ModelInfo(BaseModel):
    """Информация о модели"""
    name: str
    description: str
    enabled: bool
    default: bool


class ModelsResponse(BaseModel):
    """Ответ со списком моделей"""
    models: Dict[str, ModelInfo]
    default_model: str


class SetDefaultModelRequest(BaseModel):
    """Запрос на установку модели по умолчанию"""
    model_id: str


class EnableModelRequest(BaseModel):
    """Запрос на включение/отключение модели"""
    model_id: str
    enabled: bool


class DocumentImagesRequest(BaseModel):
    """Запрос на получение изображений документа"""
    document_id: str


class DocumentImagesResponse(BaseModel):
    """Ответ со списком изображений документа"""
    success: bool
    document_id: str
    images: List[S3ImageInfo] = []
    count: int = 0
    message: Optional[str] = None


class ImageUploadResponse(BaseModel):
    """Ответ на загрузку изображения"""
    success: bool
    filename: str
    s3_url: Optional[str] = None
    s3_object_key: Optional[str] = None
    size_bytes: Optional[int] = None
    message: Optional[str] = None


class S3HealthResponse(BaseModel):
    """Ответ проверки состояния S3"""
    success: bool
    endpoint: str
    bucket: str
    bucket_exists: bool
    message: Optional[str] = None
