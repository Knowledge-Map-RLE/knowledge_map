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


class UpdateMarkdownRequest(BaseModel):
    markdown: str = Field(..., description="Markdown content to save")


class UpdateMarkdownResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    doc_id: str
    s3_key: Optional[str] = None


# Схемы для viewport
class ViewportBounds(BaseModel):
    left: float
    right: float
    top: float
    bottom: float


class ViewportEdgesResponse(BaseModel):
    blocks: List[Dict[str, Any]]
    links: List[Dict[str, Any]]


# Схемы для аннотаций Markdown
class CreateAnnotationRequest(BaseModel):
    """Запрос на создание аннотации"""
    text: str = Field(..., description="Аннотируемый текст")
    annotation_type: str = Field(..., description="Тип аннотации")
    start_offset: int = Field(..., ge=0, description="Начальная позиция в тексте")
    end_offset: int = Field(..., gt=0, description="Конечная позиция в тексте")
    color: str = Field(default="#ffeb3b", description="Цвет выделения в hex формате")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Дополнительные метаданные")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Уверенность NLP модели")
    user_id: Optional[str] = Field(default=None, description="ID пользователя")


class UpdateAnnotationRequest(BaseModel):
    """Запрос на обновление аннотации"""
    text: Optional[str] = None
    annotation_type: Optional[str] = None
    start_offset: Optional[int] = Field(default=None, ge=0)
    end_offset: Optional[int] = Field(default=None, gt=0)
    color: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AnnotationOffsetUpdate(BaseModel):
    """Обновление offset для одной аннотации"""
    annotation_id: str
    start_offset: int = Field(..., ge=0)
    end_offset: int = Field(..., gt=0)


class BatchUpdateOffsetsRequest(BaseModel):
    """Запрос на массовое обновление offset аннотаций"""
    updates: List[AnnotationOffsetUpdate] = Field(..., description="Список обновлений")


class BatchUpdateOffsetsResponse(BaseModel):
    """Ответ на массовое обновление offset"""
    success: bool
    updated_count: int
    errors: List[str] = []


class AnnotationResponse(BaseModel):
    """Ответ с данными аннотации"""
    uid: str
    text: str
    annotation_type: str
    start_offset: int
    end_offset: int
    color: str
    metadata: Dict[str, Any]
    confidence: Optional[float] = None
    created_date: Optional[str] = None


class CreateRelationRequest(BaseModel):
    """Запрос на создание связи между аннотациями"""
    target_id: str = Field(..., description="ID целевой аннотации")
    relation_type: str = Field(..., description="Тип связи")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Дополнительные метаданные")


class RelationResponse(BaseModel):
    """Ответ с данными связи"""
    relation_uid: str
    source_uid: str
    target_uid: str
    relation_type: str
    created_date: Optional[str] = None
    metadata: Dict[str, Any]


# Схемы для NLP анализа
class NLPAnalyzeRequest(BaseModel):
    """Запрос на NLP анализ текста"""
    text: str = Field(..., description="Текст для анализа")
    start: Optional[int] = Field(default=None, description="Начальная позиция выделения")
    end: Optional[int] = Field(default=None, description="Конечная позиция выделения")


# Схемы для сохранения данных в тестовый датасет
class SaveForTestsRequest(BaseModel):
    """Запрос на сохранение документа в тестовый датасет"""
    sample_name: str = Field(..., pattern="^[a-z0-9_]+$", description="Имя образца (только латиница, цифры и подчёркивание)")
    include_pdf: bool = Field(default=False, description="Включить PDF файл в экспорт")
    include_patterns: bool = Field(default=True, description="Включить паттерны в экспорт")
    include_chains: bool = Field(default=True, description="Включить цепочки действий в экспорт")
    validate: bool = Field(default=True, description="Валидировать датасет после экспорта")


class DataAvailabilityStatus(BaseModel):
    """Статус доступности данных для экспорта"""
    pdf_exists: bool = Field(..., description="Наличие PDF файла")
    markdown_exists: bool = Field(..., description="Наличие Markdown файла")
    has_annotations: bool = Field(..., description="Наличие аннотаций")
    has_relations: bool = Field(..., description="Наличие связей между аннотациями")
    has_chains: bool = Field(..., description="Наличие цепочек действий")
    has_patterns: bool = Field(..., description="Наличие паттернов")
    annotation_count: int = Field(default=0, description="Количество аннотаций")
    relation_count: int = Field(default=0, description="Количество связей")
    is_ready: bool = Field(..., description="Готовность к экспорту (PDF + MD + аннотации)")
    missing_items: List[str] = Field(default_factory=list, description="Список отсутствующих компонентов")


class SaveForTestsResponse(BaseModel):
    """Ответ на запрос сохранения в тестовый датасет"""
    success: bool = Field(..., description="Успешность операции")
    sample_id: str = Field(..., description="ID созданного образца")
    exported_files: List[str] = Field(default_factory=list, description="Список экспортированных файлов")
    validation_result: Optional[Dict[str, Any]] = Field(default=None, description="Результат валидации датасета")
    dvc_command: str = Field(..., description="Команда для фиксации датасета в DVC")
    message: Optional[str] = Field(default=None, description="Дополнительное сообщение")
