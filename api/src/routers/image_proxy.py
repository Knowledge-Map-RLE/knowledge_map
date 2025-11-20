"""Роутер для получения изображений напрямую из S3"""
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from services import get_s3_client, settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["image-proxy"])


@router.get("/s3/image/{object_key:path}")
async def get_s3_image(object_key: str):
    """
    Получает изображения напрямую из S3.

    Упрощённое решение без проксирования через pdf_to_md сервис.
    """
    try:
        s3_client = get_s3_client()
        # Изображения хранятся в отдельном бакете knowledge-map-images
        bucket = "knowledge-map-images"

        logger.info(f"Загрузка изображения из S3: bucket={bucket}, key={object_key}")

        # Проверяем существование изображения
        if not await s3_client.object_exists(bucket, object_key):
            raise HTTPException(status_code=404, detail="Изображение не найдено")

        # Загружаем изображение
        image_data = await s3_client.download_bytes(bucket, object_key)
        if not image_data:
            raise HTTPException(status_code=500, detail="Не удалось загрузить изображение")

        # Определяем content-type по расширению
        content_type = "image/jpeg"
        object_key_lower = object_key.lower()
        if object_key_lower.endswith('.png'):
            content_type = "image/png"
        elif object_key_lower.endswith('.gif'):
            content_type = "image/gif"
        elif object_key_lower.endswith('.bmp'):
            content_type = "image/bmp"

        return Response(content=image_data, media_type=content_type)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения изображения из S3: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
