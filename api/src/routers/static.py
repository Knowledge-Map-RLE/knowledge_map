"""Роутер для статических файлов"""
import logging
import os
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/static", tags=["static"])


@router.get("/pdf/{filename}")
async def get_static_pdf(filename: str):
    """Получение статического PDF файла"""
    try:
        # Путь к PDF файлу
        pdf_path = f"personal_folder/{filename}"
        
        import os
        if not os.path.exists(pdf_path):
            raise HTTPException(status_code=404, detail="PDF файл не найден")
        
        # Возвращаем PDF файл
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=filename,
            headers={"Content-Disposition": "inline"}
        )
        
    except Exception as e:
        logger.error(f"Ошибка получения PDF файла: {e}")
        raise HTTPException(status_code=500, detail=str(e))
