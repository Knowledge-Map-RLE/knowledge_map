from fastapi import APIRouter, HTTPException
from services.marker_progress import marker_progress_store
from services.pdf_to_md_grpc_client import pdf_to_md_grpc_client

router = APIRouter(prefix="/marker", tags=["marker"])


@router.get("/status/models")
async def get_models_status():
    return await marker_progress_store.get_models_progress()


@router.get("/status/doc/{doc_id}")
async def get_doc_status(doc_id: str):
    return await marker_progress_store.get_doc(doc_id)


@router.post("/reset")
async def reset_models_status():
    """Сбрасывает статус моделей"""
    await marker_progress_store.reset_models_status()
    return {"success": True, "message": "Models status reset"}


@router.get("/models")
async def get_available_models():
    """Возвращает список доступных моделей конвертации"""
    try:
        # Пытаемся получить модели из нового сервиса
        models_data = await pdf_to_md_grpc_client.get_models()
        return models_data
    except Exception as e:
        # Fallback на пустой результат
        return {
            "models": {},
            "default_model": ""
        }


@router.post("/models/{model_id}/set-default")
async def set_default_model(model_id: str):
    """Устанавливает модель по умолчанию"""
    try:
        # Пытаемся установить модель в новом сервисе
        success = await pdf_to_md_grpc_client.set_default_model(model_id)
        if success:
            return {
                "success": True, 
                "message": f"Модель {model_id} установлена по умолчанию"
            }
        else:
            raise HTTPException(status_code=400, detail=f"Не удалось установить модель {model_id} по умолчанию")
    except Exception as e:
        # Fallback на ошибку
        raise HTTPException(status_code=500, detail=f"PDF to MD сервис недоступен: {str(e)}")


@router.post("/models/{model_id}/enable")
async def enable_model(model_id: str):
    """Включает модель"""
    try:
        # Пытаемся включить модель в новом сервисе
        success = await pdf_to_md_grpc_client.enable_model(model_id, enabled=True)
        if success:
            return {
                "success": True, 
                "message": f"Модель {model_id} включена"
            }
        else:
            raise HTTPException(status_code=400, detail=f"Не удалось включить модель {model_id}")
    except Exception as e:
        # Fallback на ошибку
        raise HTTPException(status_code=500, detail=f"PDF to MD сервис недоступен: {str(e)}")


@router.post("/models/{model_id}/disable")
async def disable_model(model_id: str):
    """Отключает модель"""
    try:
        # Пытаемся отключить модель в новом сервисе
        success = await pdf_to_md_grpc_client.enable_model(model_id, enabled=False)
        if success:
            return {
                "success": True, 
                "message": f"Модель {model_id} отключена"
            }
        else:
            raise HTTPException(status_code=400, detail=f"Не удалось отключить модель {model_id}")
    except Exception as e:
        # Fallback на ошибку
        raise HTTPException(status_code=500, detail=f"PDF to MD сервис недоступен: {str(e)}")