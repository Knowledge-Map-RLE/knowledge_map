"""API маршруты для работы с S3 изображениями"""

import logging
from fastapi import APIRouter, HTTPException, UploadFile, File, Path as PathParam, Query
from typing import List

from ..schemas.api import (
    DocumentImagesResponse, 
    ImageUploadResponse, 
    S3HealthResponse,
    S3ImageInfo
)
from ..services.s3_service import s3_service
from ..services.coordinate_extraction_service import coordinate_extraction_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/s3", tags=["S3 Images"])


@router.get("/health", response_model=S3HealthResponse)
async def check_s3_health():
    """Проверка состояния S3 сервиса"""
    try:
        health_result = await s3_service.health_check()
        
        return S3HealthResponse(
            success=health_result['success'],
            endpoint=health_result.get('endpoint', ''),
            bucket=health_result.get('bucket', ''),
            bucket_exists=health_result.get('bucket_exists', False),
            message=health_result.get('error') if not health_result['success'] else "S3 сервис работает"
        )
        
    except Exception as e:
        logger.error(f"Ошибка проверки S3: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка проверки S3: {str(e)}")


@router.get("/documents/{document_id}/images", response_model=DocumentImagesResponse)
async def get_document_images(document_id: str = PathParam(..., description="ID документа")):
    """Получить все изображения документа из S3"""
    try:
        result = await coordinate_extraction_service.get_document_images(document_id)
        
        if result['success']:
            # Конвертируем в схему API
            s3_images = []
            for img in result['images']:
                s3_images.append(S3ImageInfo(
                    filename=img['filename'],
                    s3_url=img['url'],
                    s3_object_key=img['object_key'],
                    page_no=1,  # Значение по умолчанию, так как в списке S3 нет информации о странице
                    size_bytes=img['size_bytes']
                ))
            
            return DocumentImagesResponse(
                success=True,
                document_id=document_id,
                images=s3_images,
                count=result['count'],
                message=f"Найдено {result['count']} изображений"
            )
        else:
            return DocumentImagesResponse(
                success=False,
                document_id=document_id,
                images=[],
                count=0,
                message=result.get('error', 'Не удалось получить изображения')
            )
            
    except Exception as e:
        logger.error(f"Ошибка получения изображений документа {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения изображений: {str(e)}")


@router.delete("/documents/{document_id}/images")
async def delete_document_images(document_id: str = PathParam(..., description="ID документа")):
    """Удалить все изображения документа из S3"""
    try:
        result = await coordinate_extraction_service.delete_document_images(document_id)
        
        if result['success']:
            return {
                "success": True,
                "document_id": document_id,
                "deleted_count": result['deleted_count'],
                "total_count": result['total_count'],
                "message": f"Удалено {result['deleted_count']} из {result['total_count']} изображений"
            }
        else:
            return {
                "success": False,
                "document_id": document_id,
                "deleted_count": result.get('deleted_count', 0),
                "total_count": result.get('total_count', 0),
                "errors": result.get('errors', []),
                "message": result.get('error', 'Ошибка удаления изображений')
            }
            
    except Exception as e:
        logger.error(f"Ошибка удаления изображений документа {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка удаления изображений: {str(e)}")


@router.post("/upload", response_model=ImageUploadResponse)
async def upload_image(
    file: UploadFile = File(..., description="Изображение для загрузки"),
    folder: str = "uploads"
):
    """Загрузить изображение в S3"""
    try:
        # Проверяем тип файла
        if not file.content_type or not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Файл должен быть изображением")
        
        # Читаем данные файла
        image_data = await file.read()
        
        if len(image_data) == 0:
            raise HTTPException(status_code=400, detail="Файл пустой")
        
        # Загружаем в S3
        upload_result = await s3_service.upload_image(
            image_data=image_data,
            filename=file.filename,
            folder=folder
        )
        
        if upload_result['success']:
            return ImageUploadResponse(
                success=True,
                filename=upload_result['filename'],
                s3_url=upload_result['url'],
                s3_object_key=upload_result['object_key'],
                size_bytes=upload_result.get('size_bytes'),
                message="Изображение успешно загружено"
            )
        else:
            raise HTTPException(
                status_code=500, 
                detail=f"Ошибка загрузки: {upload_result.get('error')}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка загрузки изображения: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки изображения: {str(e)}")


@router.delete("/images/{object_key:path}")
async def delete_image(object_key: str = PathParam(..., description="Ключ объекта в S3")):
    """Удалить изображение из S3"""
    try:
        result = await s3_service.delete_image(object_key)
        
        if result['success']:
            return {
                "success": True,
                "object_key": object_key,
                "message": "Изображение успешно удалено"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Ошибка удаления: {result.get('error')}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка удаления изображения {object_key}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка удаления изображения: {str(e)}")


@router.get("/images")
async def list_images(folder: str = "images", limit: int = 100):
    """Получить список изображений в папке"""
    try:
        result = await s3_service.list_images(folder=folder, limit=limit)
        
        if result['success']:
            return {
                "success": True,
                "folder": folder,
                "images": result['images'],
                "count": result['count'],
                "message": f"Найдено {result['count']} изображений"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Ошибка получения списка: {result.get('error')}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения списка изображений: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения списка: {str(e)}")


@router.get("/image/{object_key:path}")
async def get_image_proxy(
    object_key: str = PathParam(..., description="Ключ объекта в S3")
):
    """Проксировать изображение из S3 через API (постоянная ссылка)"""
    try:
        # Получаем изображение из S3
        image_data = await s3_service.download_bytes(object_key)
        
        if image_data:
            # Возвращаем изображение напрямую с правильными заголовками
            from fastapi.responses import Response
            
            return Response(
                content=image_data,
                media_type="image/png",
                headers={
                    "Cache-Control": "public, max-age=604800",  # Кэш на 7 дней
                    "Access-Control-Allow-Origin": "*",  # CORS
                    "Content-Disposition": f"inline; filename={object_key.split('/')[-1]}"
                }
            )
        else:
            raise HTTPException(status_code=404, detail="Изображение не найдено")
            
    except Exception as e:
        logger.error(f"Ошибка получения изображения {object_key}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения изображения: {str(e)}")


@router.get("/url/{object_key:path}")
async def get_image_url(
    object_key: str = PathParam(..., description="Ключ объекта в S3"),
    expiration: int = Query(3600, description="Время жизни URL в секундах")
):
    """Получить presigned URL изображения для безопасного доступа из браузера"""
    try:
        # Генерируем presigned URL
        presigned_url = await s3_service.generate_presigned_url(object_key, expiration)
        
        if presigned_url:
            return {
                "success": True,
                "object_key": object_key,
                "url": presigned_url,
                "expiration": expiration,
                "message": "Presigned URL получен успешно"
            }
        else:
            # Fallback к прямому URL
            direct_url = s3_service.get_image_url(object_key)
            return {
                "success": True,
                "object_key": object_key,
                "url": direct_url,
                "expiration": None,
                "message": "Прямой URL получен (presigned URL недоступен)"
            }
        
    except Exception as e:
        logger.error(f"Ошибка получения URL для {object_key}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения URL: {str(e)}")
