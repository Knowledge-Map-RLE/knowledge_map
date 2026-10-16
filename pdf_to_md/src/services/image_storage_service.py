"""Операции чтения и удаления изображений документа в S3."""

from __future__ import annotations

import logging
from typing import Any, Dict

from .s3_service import s3_service

logger = logging.getLogger(__name__)


class ImageStorageService:
    """Отдельный адаптер для API управления уже сохранёнными рисунками."""

    def __init__(self, storage: Any = None) -> None:
        self.storage = storage or s3_service

    async def get_document_images(self, document_id: str) -> Dict[str, Any]:
        folder = f"documents/{document_id}/images"
        result = await self.storage.list_images(folder=folder)
        if not result.get("success"):
            return {
                "success": False,
                "error": result.get("error", "Не удалось получить список изображений"),
                "document_id": document_id,
            }
        return {
            "success": True,
            "document_id": document_id,
            "images": result.get("images", []),
            "count": result.get("count", 0),
        }

    async def delete_document_images(self, document_id: str) -> Dict[str, Any]:
        images_result = await self.get_document_images(document_id)
        if not images_result["success"]:
            return images_result

        errors = []
        deleted = 0
        for image in images_result["images"]:
            result = await self.storage.delete_image(image["object_key"])
            if result.get("success"):
                deleted += 1
            else:
                errors.append(
                    f"{image.get('filename', image['object_key'])}: "
                    f"{result.get('error', 'ошибка удаления')}"
                )
        return {
            "success": not errors,
            "document_id": document_id,
            "deleted_count": deleted,
            "total_count": len(images_result["images"]),
            "errors": errors,
        }


image_storage_service = ImageStorageService()
