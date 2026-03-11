"""
Layer: Frameworks & Drivers — Infrastructure
Package: infrastructure.status.s3_status_storage
Responsibility: Хранение статуса обработки документов в S3.

Принадлежит слою Infrastructure — детали персистентности (S3).

Перемещено из services/status_storage.py.

Allowed imports: json, infrastructure.s3, infrastructure.config, стандартная библиотека
Forbidden imports: fastapi, neomodel, domain, application, adapters, web
"""
import json
import logging
from typing import Dict, Any, Optional

from infrastructure.s3.s3_storage import get_s3_client
from infrastructure.config import settings

logger = logging.getLogger(__name__)


class StatusStorage:
    """Хранилище статуса обработки документов в S3."""

    def __init__(self):
        self.s3_client = get_s3_client()
        self.bucket = settings.S3_BUCKET_NAME
        self.status_prefix = "status/"

    async def save_doc_status(self, doc_id: str, status: Dict[str, Any]) -> bool:
        try:
            key = f"{self.status_prefix}{doc_id}.json"
            data = json.dumps(status, ensure_ascii=False, indent=2)
            success = await self.s3_client.upload_bytes(
                data.encode("utf-8"), self.bucket, key, content_type="application/json"
            )
            if success:
                logger.info(f"[status] Сохранён статус для doc {doc_id}")
            return success
        except Exception as e:
            logger.error(f"[status] Не удалось сохранить статус для doc {doc_id}: {e}")
            return False

    async def load_doc_status(self, doc_id: str) -> Optional[Dict[str, Any]]:
        try:
            key = f"{self.status_prefix}{doc_id}.json"
            if not await self.s3_client.object_exists(self.bucket, key):
                return None
            data = await self.s3_client.download_text(self.bucket, key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"[status] Не удалось загрузить статус для doc {doc_id}: {e}")
            return None

    async def delete_doc_status(self, doc_id: str) -> bool:
        try:
            key = f"{self.status_prefix}{doc_id}.json"
            success = await self.s3_client.delete_object(self.bucket, key)
            if success:
                logger.info(f"[status] Удалён статус для doc {doc_id}")
            return success
        except Exception as e:
            logger.error(f"[status] Не удалось удалить статус для doc {doc_id}: {e}")
            return False


# Глобальный singleton
status_storage = StatusStorage()
