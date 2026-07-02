"""
Layer: Frameworks & Drivers — Infrastructure
Package: infrastructure.s3.s3_storage
Responsibility: Асинхронный клиент S3/MinIO — детали хранилища файлов.

Принадлежит слою Infrastructure, потому что содержит aioboto3-специфичный код.
Удовлетворяет ObjectStorageProtocol из application/ports/object_storage.py
без явного наследования (structural subtyping).

Перемещено из services/s3_client.py.

Allowed imports: aioboto3, botocore, os, mimetypes, infrastructure.config, стандартная библиотека
Forbidden imports: fastapi, neomodel, domain, application, adapters, web
"""
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional, Dict, List

import aioboto3
from botocore.exceptions import ClientError

from infrastructure.config import settings

logger = logging.getLogger(__name__)


class S3Config:
    """Конфигурация для подключения к S3/MinIO."""

    def __init__(self):
        self.endpoint_url = settings.S3_ENDPOINT_URL
        self.access_key = settings.S3_ACCESS_KEY
        self.secret_key = settings.S3_SECRET_KEY
        self.region = settings.S3_REGION

    def get_boto3_config(self) -> Dict:
        return {
            "endpoint_url": self.endpoint_url,
            "aws_access_key_id": self.access_key,
            "aws_secret_access_key": self.secret_key,
            "region_name": self.region,
        }


class AsyncS3Client:
    """
    Асинхронный клиент S3/MinIO.

    Удовлетворяет ObjectStorageProtocol (application/ports/object_storage.py)
    без явного наследования.
    """

    def __init__(self, config: Optional[S3Config] = None):
        self.config = config or S3Config()
        self.session = aioboto3.Session()
        logger.info(f"S3 клиент инициализирован для {self.config.endpoint_url}")

    @asynccontextmanager
    async def client_context(self):
        client = self.session.client("s3", **self.config.get_boto3_config())
        async with client as s3:
            yield s3

    async def ensure_bucket_exists(self, bucket_name: str) -> bool:
        try:
            async with self.client_context() as s3:
                await s3.head_bucket(Bucket=bucket_name)
                return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                try:
                    async with self.client_context() as s3:
                        await s3.create_bucket(Bucket=bucket_name)
                        logger.info(f"Bucket '{bucket_name}' создан")
                        return True
                except ClientError as create_error:
                    logger.error(f"Не удалось создать bucket '{bucket_name}': {create_error}")
                    return False
            logger.error(f"Ошибка при проверке bucket '{bucket_name}': {e}")
            return False

    async def upload_bytes(
        self,
        data: bytes,
        bucket_name: str,
        object_key: str,
        content_type: str = "application/octet-stream",
        metadata: Optional[Dict[str, str]] = None,
    ) -> bool:
        try:
            await self.ensure_bucket_exists(bucket_name)
            async with self.client_context() as s3:
                await s3.put_object(
                    Bucket=bucket_name,
                    Key=object_key,
                    Body=data,
                    ContentType=content_type,
                    Metadata=metadata or {},
                )
            logger.info(f"Загружено: s3://{bucket_name}/{object_key}")
            return True
        except ClientError as e:
            logger.error(f"Ошибка загрузки: {e}")
            return False

    async def download_bytes(self, bucket_name: str, object_key: str) -> Optional[bytes]:
        try:
            async with self.client_context() as s3:
                response = await s3.get_object(Bucket=bucket_name, Key=object_key)
                async with response["Body"] as stream:
                    return await stream.read()
        except ClientError as e:
            logger.error(f"Ошибка скачивания: {e}")
            return None

    async def download_text(
        self, bucket_name: str, object_key: str, encoding: str = "utf-8"
    ) -> Optional[str]:
        data = await self.download_bytes(bucket_name, object_key)
        if data:
            try:
                return data.decode(encoding)
            except UnicodeDecodeError as e:
                logger.error(f"Ошибка декодирования: {e}")
        return None

    async def list_objects(self, bucket_name: str, prefix: str = "") -> List[Dict]:
        try:
            async with self.client_context() as s3:
                response = await s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
                return response.get("Contents", [])
        except ClientError as e:
            logger.error(f"Ошибка получения списка объектов: {e}")
            return []

    async def delete_object(self, bucket_name: str, object_key: str) -> bool:
        try:
            async with self.client_context() as s3:
                await s3.delete_object(Bucket=bucket_name, Key=object_key)
            logger.info(f"Удалено: s3://{bucket_name}/{object_key}")
            return True
        except ClientError as e:
            logger.error(f"Ошибка удаления: {e}")
            return False

    async def get_object_url(
        self, bucket_name: str, object_key: str, expires_in: int = 3600
    ) -> Optional[str]:
        try:
            async with self.client_context() as s3:
                return await s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": bucket_name, "Key": object_key},
                    ExpiresIn=expires_in,
                )
        except ClientError as e:
            logger.error(f"Ошибка генерации URL: {e}")
            return None

    async def object_exists(self, bucket_name: str, object_key: str) -> bool:
        try:
            async with self.client_context() as s3:
                await s3.head_object(Bucket=bucket_name, Key=object_key)
            return True
        except ClientError:
            return False


# Глобальный singleton
_s3_client: Optional[AsyncS3Client] = None


def get_s3_client() -> AsyncS3Client:
    """Возвращает глобальный экземпляр S3-клиента."""
    global _s3_client
    if _s3_client is None:
        _s3_client = AsyncS3Client()
    return _s3_client
