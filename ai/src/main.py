"""
Основной модуль AI сервиса для автоматической аннотации PDF документов.
"""

import logging
import time
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from .config import settings
from .models import (
    PDFAnnotationRequest, PDFAnnotationResponse, 
    PDFProcessingResult, HealthResponse, ModelInfo
)
from .pdf_processor import PDFProcessor
from .annotation_engine import AnnotationEngine, ModelConfig

# Настройка логирования
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger(__name__)

# Создаем приложение FastAPI
app = FastAPI(
    title="Knowledge Map AI Service",
    description="AI сервис для автоматической разметки PDF научных статей",
    version="1.0.0"
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальные переменные для моделей
pdf_processor: PDFProcessor = None
annotation_engine: AnnotationEngine = None
model_info: ModelInfo = None


@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске сервиса."""
    global pdf_processor, annotation_engine, model_info
    
    try:
        logger.info("Запуск AI сервиса...")
        
        # Инициализируем процессор PDF
        pdf_processor = PDFProcessor(dpi=settings.PDF_DPI)
        logger.info("PDF процессор инициализирован")
        
        # Инициализируем движок аннотации
        model_config = ModelConfig(
            name=settings.MODEL_NAME,
            max_length=settings.MODEL_MAX_LENGTH,
            device=settings.MODEL_DEVICE
        )
        
        annotation_engine = AnnotationEngine(model_config)
        logger.info("Движок аннотации инициализирован")
        
        # Создаем информацию о модели
        model_info = ModelInfo(
            name=settings.MODEL_NAME,
            parameters_count=350000000,  # Примерно 350M параметров для DialoGPT-medium
            max_context_length=settings.MODEL_MAX_LENGTH,
            device=annotation_engine.device
        )
        
        logger.info("AI сервис успешно запущен")
        
    except Exception as e:
        logger.error(f"Ошибка инициализации AI сервиса: {e}")
        raise


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Проверка здоровья сервиса."""
    return HealthResponse(
        status="healthy" if annotation_engine is not None else "unhealthy",
        model_loaded=annotation_engine is not None,
        model_info=model_info,
        timestamp=time.time()
    )


@app.get("/model/info", response_model=ModelInfo)
async def get_model_info():
    """Получить информацию о используемой модели."""
    if model_info is None:
        raise HTTPException(status_code=503, detail="Модель не загружена")
    
    return model_info


@app.post("/api/annotate/pdf", response_model=PDFAnnotationResponse)
async def annotate_pdf(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    force_reprocess: bool = Form(False)
):
    """
    Аннотирует PDF документ.
    
    Args:
        file: PDF файл для аннотации
        user_id: ID пользователя
        force_reprocess: Принудительная переобработка
        
    Returns:
        PDFAnnotationResponse: Результаты аннотации
    """
    if annotation_engine is None:
        raise HTTPException(status_code=503, detail="AI сервис не готов")
    
    start_time = time.time()
    
    try:
        # Проверяем тип файла
        if not file.content_type or not file.content_type.startswith('application/pdf'):
            raise HTTPException(status_code=400, detail="Файл должен быть PDF")
        
        # Читаем содержимое файла
        pdf_content = await file.read()
        
        logger.info(f"Начало аннотации PDF файла: {file.filename}")
        
        # Обрабатываем PDF
        pdf_structure = pdf_processor.process_pdf(pdf_content)
        
        # Аннотируем документ
        annotations = annotation_engine.annotate_pdf(pdf_structure)
        
        processing_time = time.time() - start_time
        
        # Конвертируем аннотации в словари для ответа
        annotations_data = []
        for ann in annotations:
            ann_dict = {
                'annotation_type': ann.annotation_type,
                'content': ann.content,
                'confidence': ann.confidence,
                'page_number': ann.page_number,
                'bbox': ann.bbox,
                'metadata': ann.metadata
            }
            annotations_data.append(ann_dict)
        
        logger.info(f"Аннотация завершена за {processing_time:.2f} секунд")
        
        return PDFAnnotationResponse(
            success=True,
            message="Аннотация успешно завершена",
            document_id="",  # Будет заполнено в API сервисе
            annotations_count=len(annotations),
            processing_time=processing_time,
            annotations=annotations_data
        )
        
    except Exception as e:
        logger.error(f"Ошибка аннотации PDF: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/annotate/content", response_model=Dict[str, Any])
async def annotate_content(
    content: str = Form(...),
    content_type: str = Form("text")
):
    """
    Аннотирует текстовое содержимое.
    
    Args:
        content: Текст для аннотации
        content_type: Тип содержимого (text, abstract, title, etc.)
        
    Returns:
        Dict: Результаты аннотации
    """
    if annotation_engine is None:
        raise HTTPException(status_code=503, detail="AI сервис не готов")
    
    try:
        # Создаем простую структуру для текста
        from .pdf_processor import PDFPage
        page = PDFPage(
            page_number=1,
            text=content,
            images=[],
            tables=[],
            bbox=(0, 0, 100, 100)
        )
        
        # Аннотируем текст
        annotations = annotation_engine._annotate_text(content, 1)
        
        # Конвертируем в словари
        annotations_data = []
        for ann in annotations:
            ann_dict = {
                'annotation_type': ann.annotation_type,
                'content': ann.content,
                'confidence': ann.confidence,
                'metadata': ann.metadata
            }
            annotations_data.append(ann_dict)
        
        return {
            'success': True,
            'content_type': content_type,
            'annotations_count': len(annotations),
            'annotations': annotations_data
        }
        
    except Exception as e:
        logger.error(f"Ошибка аннотации содержимого: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/annotation/types")
async def get_annotation_types():
    """Получить список поддерживаемых типов аннотаций."""
    return {
        'annotation_types': [
            {
                'type': 'title',
                'description': 'Заголовок документа или раздела',
                'confidence_threshold': 0.8
            },
            {
                'type': 'author',
                'description': 'Автор документа',
                'confidence_threshold': 0.8
            },
            {
                'type': 'abstract',
                'description': 'Аннотация документа',
                'confidence_threshold': 0.7
            },
            {
                'type': 'keyword',
                'description': 'Ключевые слова',
                'confidence_threshold': 0.6
            },
            {
                'type': 'number',
                'description': 'Числовые значения с контекстом',
                'confidence_threshold': 0.9
            },
            {
                'type': 'date',
                'description': 'Даты в различных форматах',
                'confidence_threshold': 0.8
            },
            {
                'type': 'image',
                'description': 'Изображения, графики, диаграммы',
                'confidence_threshold': 0.9
            },
            {
                'type': 'table',
                'description': 'Таблицы с данными',
                'confidence_threshold': 0.9
            },
            {
                'type': 'formula',
                'description': 'Математические формулы',
                'confidence_threshold': 0.85
            },
            {
                'type': 'entity',
                'description': 'Именованные сущности (NER)',
                'confidence_threshold': 0.7
            },
            {
                'type': 'action',
                'description': 'Действия и процессы',
                'confidence_threshold': 0.6
            }
        ]
    }


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
