"""Основной модуль FastAPI приложения"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .services.pdf_conversion_service import PDFConversionService
from .schemas.api import ConvertResponse, ModelsResponse, ProgressUpdate

logger = logging.getLogger(__name__)

# Глобальный экземпляр сервиса
conversion_service = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    global conversion_service
    
    # Инициализация
    logger.info("[app] Инициализация PDF to Markdown сервиса...")
    conversion_service = PDFConversionService()
    
    yield
    
    # Очистка
    logger.info("[app] Завершение работы сервиса...")


app = FastAPI(
    title="PDF to Markdown Service",
    description="Микросервис для преобразования PDF документов в Markdown формат",
    version="0.1.0",
    lifespan=lifespan
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {"status": "healthy", "service": "pdf_to_md"}


@app.post("/api/convert", response_model=ConvertResponse)
async def convert_pdf(
    file: UploadFile = File(...),
    model_id: str = Form(None),
    doc_id: str = Form(None)
):
    """Конвертация PDF в Markdown"""
    try:
        # Проверяем тип файла
        if not file.content_type or not file.content_type.startswith('application/pdf'):
            raise HTTPException(status_code=400, detail="Файл должен быть PDF")
        
        # Читаем содержимое файла
        pdf_content = await file.read()
        if not pdf_content:
            raise HTTPException(status_code=400, detail="Пустой файл")
        
        # Генерируем doc_id если не предоставлен
        if not doc_id:
            import hashlib
            doc_id = hashlib.md5(pdf_content).hexdigest()
        
        logger.info(f"[api] Конвертация PDF: doc_id={doc_id}, model_id={model_id}")
        
        # Выполняем конвертацию
        result = await conversion_service.convert_pdf(
            pdf_content=pdf_content,
            doc_id=doc_id,
            model_id=model_id
        )
        
        return result
        
    except Exception as e:
        logger.error(f"[api] Ошибка конвертации: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models", response_model=ModelsResponse)
async def get_models():
    """Получение списка доступных моделей"""
    try:
        models_data = await conversion_service.get_available_models()
        return ModelsResponse(**models_data)
    except Exception as e:
        logger.error(f"[api] Ошибка получения моделей: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/models/{model_id}/set-default")
async def set_default_model(model_id: str):
    """Установка модели по умолчанию"""
    try:
        success = await conversion_service.set_default_model(model_id)
        if not success:
            raise HTTPException(status_code=400, detail=f"Не удалось установить модель {model_id} по умолчанию")
        
        return {"success": True, "message": f"Модель {model_id} установлена по умолчанию"}
    except Exception as e:
        logger.error(f"[api] Ошибка установки модели по умолчанию: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/models/{model_id}/enable")
async def enable_model(model_id: str, enabled: bool = True):
    """Включение/отключение модели"""
    try:
        if enabled:
            success = await conversion_service.enable_model(model_id)
            action = "включить"
        else:
            success = await conversion_service.disable_model(model_id)
            action = "отключить"
        
        if not success:
            raise HTTPException(status_code=400, detail=f"Не удалось {action} модель {model_id}")
        
        return {"success": True, "message": f"Модель {model_id} успешно {action}ена"}
    except Exception as e:
        logger.error(f"[api] Ошибка изменения состояния модели: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status")
async def get_status():
    """Получение статуса сервиса"""
    try:
        models_data = await conversion_service.get_available_models()
        return {
            "status": "running",
            "service": "pdf_to_md",
            "models_count": len(models_data["models"]),
            "default_model": models_data["default_model"]
        }
    except Exception as e:
        logger.error(f"[api] Ошибка получения статуса: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
