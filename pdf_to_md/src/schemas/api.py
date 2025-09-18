"""Схемы данных для API"""
from pydantic import BaseModel
from typing import Dict, Any, Optional, List


class ConvertRequest(BaseModel):
    """Запрос на конвертацию PDF"""
    pdf_content: bytes
    model_id: Optional[str] = None
    doc_id: Optional[str] = None


class ConvertResponse(BaseModel):
    """Ответ на запрос конвертации"""
    success: bool
    doc_id: str
    markdown_content: str
    images: Dict[str, bytes] = {}
    metadata: Optional[Dict[str, Any]] = None
    message: str


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
