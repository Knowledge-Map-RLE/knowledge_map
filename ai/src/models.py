"""
Модели для AI сервиса.
"""

from typing import List, Dict, Optional, Any, Union
from pydantic import BaseModel, Field
from datetime import datetime


class PDFAnnotationRequest(BaseModel):
    """Запрос на аннотацию PDF документа."""
    document_id: str
    user_id: str
    force_reprocess: bool = False


class PDFAnnotationResponse(BaseModel):
    """Ответ с результатами аннотации."""
    success: bool
    message: str
    document_id: str
    annotations_count: int
    processing_time: float
    annotations: List[Dict[str, Any]]


class AnnotationItem(BaseModel):
    """Отдельная аннотация."""
    annotation_type: str = Field(..., description="Тип аннотации: title, author, abstract, keyword, number, date, image, table, graph, formula, entity, action")
    content: str = Field(..., description="Содержимое аннотации")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Уверенность модели")
    page_number: Optional[int] = Field(None, description="Номер страницы")
    bbox: Optional[Dict[str, float]] = Field(None, description="Bounding box: {x, y, width, height}")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Дополнительные метаданные")


class PDFProcessingResult(BaseModel):
    """Результат обработки PDF."""
    document_id: str
    total_pages: int
    extracted_text: str
    images_count: int
    tables_count: int
    formulas_count: int
    annotations: List[AnnotationItem]
    processing_time: float
    model_used: str


class ModelInfo(BaseModel):
    """Информация о используемой модели."""
    name: str
    parameters_count: int
    max_context_length: int
    device: str
    memory_usage: Optional[str] = None


class HealthResponse(BaseModel):
    """Ответ на проверку здоровья сервиса."""
    status: str
    model_loaded: bool
    model_info: Optional[ModelInfo] = None
    timestamp: datetime
