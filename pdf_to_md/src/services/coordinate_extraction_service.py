"""Устаревший импорт для S3-операций с изображениями."""

from .image_storage_service import ImageStorageService, image_storage_service

CoordinateExtractionService = ImageStorageService
coordinate_extraction_service = image_storage_service

__all__ = [
    "CoordinateExtractionService",
    "coordinate_extraction_service",
]