"""Сервис для персистентного хранения статуса обработки документов"""
import json
import logging
from typing import Dict, Any, Optional
from . import get_s3_client, settings

logger = logging.getLogger(__name__)


class StatusStorage:
    """Хранилище статуса обработки документов в S3"""
    
    def __init__(self):
        self.s3_client = get_s3_client()
        self.bucket = settings.S3_BUCKET_NAME
        self.status_prefix = "status/"
    
    async def save_doc_status(self, doc_id: str, status: Dict[str, Any]) -> bool:
        """Сохраняет статус документа в S3"""
        try:
            key = f"{self.status_prefix}{doc_id}.json"
            data = json.dumps(status, ensure_ascii=False, indent=2)
            success = await self.s3_client.upload_bytes(
                data.encode('utf-8'),
                self.bucket,
                key,
                content_type="application/json"
            )
            if success:
                logger.info(f"[status] Saved status for doc {doc_id}")
            return success
        except Exception as e:
            logger.error(f"[status] Failed to save status for doc {doc_id}: {e}")
            return False
    
    async def load_doc_status(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Загружает статус документа из S3"""
        try:
            key = f"{self.status_prefix}{doc_id}.json"
            if not await self.s3_client.object_exists(self.bucket, key):
                return None
            
            data = await self.s3_client.download_text(self.bucket, key)
            if data:
                status = json.loads(data)
                logger.info(f"[status] Loaded status for doc {doc_id}")
                return status
            return None
        except Exception as e:
            logger.error(f"[status] Failed to load status for doc {doc_id}: {e}")
            return None
    
    async def delete_doc_status(self, doc_id: str) -> bool:
        """Удаляет статус документа из S3"""
        try:
            key = f"{self.status_prefix}{doc_id}.json"
            success = await self.s3_client.delete_object(self.bucket, key)
            if success:
                logger.info(f"[status] Deleted status for doc {doc_id}")
            return success
        except Exception as e:
            logger.error(f"[status] Failed to delete status for doc {doc_id}: {e}")
            return False


# Глобальный экземпляр
status_storage = StatusStorage()
