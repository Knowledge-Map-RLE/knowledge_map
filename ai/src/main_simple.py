"""
Упрощенная версия AI сервиса для демонстрации.
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from typing import List, Dict, Any
import json
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Service", version="1.0.0")

@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

@app.post("/api/annotate/pdf")
async def annotate_pdf(
    file: UploadFile = File(...),
    user_id: str = Form(...)
):
    """
    Аннотация PDF файла.
    В упрощенной версии возвращает демонстрационные аннотации.
    """
    try:
        logger.info(f"Получен запрос на аннотацию PDF от пользователя {user_id}")
        
        # Читаем файл
        content = await file.read()
        logger.info(f"Размер файла: {len(content)} байт")
        
        # Генерируем демонстрационные аннотации
        demo_annotations = generate_demo_annotations(file.filename)
        
        return {
            "document_id": f"demo_{user_id}_{datetime.utcnow().timestamp()}",
            "annotations": demo_annotations,
            "processing_time": 0.5,
            "model_used": "demo-model"
        }
        
    except Exception as e:
        logger.error(f"Ошибка при аннотации PDF: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def generate_demo_annotations(filename: str) -> List[Dict[str, Any]]:
    """Генерирует демонстрационные аннотации."""
    return [
        {
            "type": "title",
            "content": "The hallmarks of Parkinson's disease",
            "confidence": 0.95,
            "page_number": 1,
            "bbox": {"x": 100, "y": 50, "width": 400, "height": 30}
        },
        {
            "type": "author",
            "content": "Antony",
            "confidence": 0.90,
            "page_number": 1,
            "bbox": {"x": 100, "y": 100, "width": 200, "height": 20}
        },
        {
            "type": "abstract",
            "content": "This paper presents a comprehensive review of Parkinson's disease...",
            "confidence": 0.85,
            "page_number": 1,
            "bbox": {"x": 100, "y": 150, "width": 400, "height": 100}
        },
        {
            "type": "keyword",
            "content": "Parkinson's disease, neurodegeneration, dopamine",
            "confidence": 0.88,
            "page_number": 1,
            "bbox": {"x": 100, "y": 300, "width": 300, "height": 20}
        },
        {
            "type": "number",
            "content": "2013",
            "confidence": 0.92,
            "page_number": 1,
            "bbox": {"x": 100, "y": 350, "width": 50, "height": 15}
        },
        {
            "type": "date",
            "content": "2013",
            "confidence": 0.90,
            "page_number": 1,
            "bbox": {"x": 200, "y": 350, "width": 50, "height": 15}
        },
        {
            "type": "entity",
            "content": "Parkinson's disease",
            "confidence": 0.95,
            "page_number": 2,
            "bbox": {"x": 100, "y": 100, "width": 150, "height": 20}
        },
        {
            "type": "action",
            "content": "increased",
            "confidence": 0.80,
            "page_number": 2,
            "bbox": {"x": 300, "y": 200, "width": 80, "height": 15}
        },
        {
            "type": "image",
            "content": "Figure 1: Brain scan showing dopamine levels",
            "confidence": 0.85,
            "page_number": 3,
            "bbox": {"x": 100, "y": 100, "width": 300, "height": 200}
        },
        {
            "type": "table",
            "content": "Table 1: Patient demographics",
            "confidence": 0.90,
            "page_number": 4,
            "bbox": {"x": 100, "y": 150, "width": 400, "height": 150}
        }
    ]

@app.get("/")
async def root():
    """Корневой endpoint."""
    return {
        "message": "AI Service для аннотации PDF",
        "version": "1.0.0",
        "endpoints": [
            "/health",
            "/api/annotate/pdf",
            "/docs"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
