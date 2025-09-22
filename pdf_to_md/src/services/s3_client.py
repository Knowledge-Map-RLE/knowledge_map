"""
Асинхронный S3 клиент для PDF-to-MD микросервиса.

Поддерживает:
- Работу с MinIO/AWS S3
- Автоматическое создание bucket'ов
- Загрузку/скачивание файлов
- Работу с изображениями и Markdown файлами
"""

import os
import logging
from typing import Optional, Dict, List, Union, BinaryIO
from contextlib import asynccontextmanager
import mimetypes

import aioboto3
from botocore.exceptions import ClientError, NoCredentialsError

try:
    from ..core.config import settings
except ImportError:
    from core.config import settings

logger = logging.getLogger(__name__)


class S3Config:
    """Конфигурация для подключения к S3/MinIO."""
    
    def __init__(self):
        self.endpoint_url = getattr(settings, 's3_endpoint_url', os.getenv('S3_ENDPOINT_URL', 'http://localhost:9000'))
        self.access_key = getattr(settings, 's3_access_key', os.getenv('S3_ACCESS_KEY', 'minio'))
        self.secret_key = getattr(settings, 's3_secret_key', os.getenv('S3_SECRET_KEY', 'minio123456'))
        self.region = getattr(settings, 's3_region', os.getenv('S3_REGION', 'us-east-1'))
        self.bucket_name = getattr(settings, 's3_bucket_name', os.getenv('S3_BUCKET_NAME', 'knowledge-map'))
        
    def get_boto3_config(self) -> Dict:
        """Возвращает конфигурацию для aioboto3."""
        return {
            'endpoint_url': self.endpoint_url,
            'aws_access_key_id': self.access_key,
            'aws_secret_access_key': self.secret_key,
            'region_name': self.region
        }


class AsyncS3Client:
    """Асинхронный клиент для работы с S3/MinIO."""
    
    def __init__(self, config: Optional[S3Config] = None):
        self.config = config or S3Config()
        self.session = aioboto3.Session()
        self._client = None
        logger.info(f"S3 клиент инициализирован для {self.config.endpoint_url}")
    
    @asynccontextmanager
    async def client_context(self):
        """Контекстный менеджер для S3 клиента."""
        async with self.session.client('s3', **self.config.get_boto3_config()) as client:
            yield client
    
    async def ensure_bucket_exists(self, bucket_name: str) -> bool:
        """Проверяет существование bucket и создает его при необходимости."""
        try:
            async with self.client_context() as s3:
                try:
                    await s3.head_bucket(Bucket=bucket_name)
                    logger.debug(f"Bucket '{bucket_name}' уже существует")
                    return True
                except ClientError as e:
                    error_code = e.response['Error']['Code']
                    if error_code == '404':
                        # Bucket не существует, создаем его
                        await s3.create_bucket(Bucket=bucket_name)
                        logger.info(f"Bucket '{bucket_name}' создан")
                        return True
                    else:
                        logger.error(f"Ошибка при проверке bucket '{bucket_name}': {e}")
                        return False
        except Exception as e:
            logger.error(f"Неожиданная ошибка при работе с bucket '{bucket_name}': {e}")
            return False
    
    async def upload_bytes(self,
                          data: bytes,
                          bucket_name: str,
                          object_key: str,
                          content_type: str = 'application/octet-stream',
                          metadata: Optional[Dict[str, str]] = None) -> bool:
        """Загружает байты в S3."""
        try:
            # Обеспечиваем существование bucket
            await self.ensure_bucket_exists(bucket_name)
            
            async with self.client_context() as s3:
                await s3.put_object(
                    Bucket=bucket_name,
                    Key=object_key,
                    Body=data,
                    ContentType=content_type,
                    Metadata=metadata or {}
                )
                
                logger.info(f"Данные загружены: s3://{bucket_name}/{object_key}")
                return True
                
        except ClientError as e:
            logger.error(f"Ошибка загрузки данных: {e}")
            return False
    
    async def upload_file(self,
                         file_path: str,
                         bucket_name: str,
                         object_key: str,
                         content_type: Optional[str] = None,
                         metadata: Optional[Dict[str, str]] = None) -> bool:
        """Загружает файл в S3."""
        try:
            if not content_type:
                content_type, _ = mimetypes.guess_type(file_path)
                if not content_type:
                    content_type = 'application/octet-stream'
            
            with open(file_path, 'rb') as f:
                data = f.read()
            
            return await self.upload_bytes(data, bucket_name, object_key, content_type, metadata)
                
        except Exception as e:
            logger.error(f"Ошибка загрузки файла {file_path}: {e}")
            return False
    
    async def download_bytes(self,
                           bucket_name: str,
                           object_key: str) -> Optional[bytes]:
        """Скачивает объект как bytes."""
        try:
            async with self.client_context() as s3:
                response = await s3.get_object(Bucket=bucket_name, Key=object_key)
                async with response['Body'] as stream:
                    return await stream.read()
                    
        except ClientError as e:
            logger.error(f"Ошибка скачивания объекта: {e}")
            return None
    
    async def download_text(self,
                          bucket_name: str,
                          object_key: str,
                          encoding: str = 'utf-8') -> Optional[str]:
        """Скачивает текстовый объект."""
        data = await self.download_bytes(bucket_name, object_key)
        if data:
            return data.decode(encoding)
        return None
    
    async def object_exists(self, bucket_name: str, object_key: str) -> bool:
        """Проверяет существование объекта в S3."""
        try:
            async with self.client_context() as s3:
                await s3.head_object(Bucket=bucket_name, Key=object_key)
                return True
        except ClientError:
            return False
    
    async def list_objects(self, bucket_name: str, prefix: str = '') -> List[Dict]:
        """Возвращает список объектов в bucket с указанным префиксом."""
        try:
            async with self.client_context() as s3:
                response = await s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
                return response.get('Contents', [])
        except ClientError as e:
            logger.error(f"Ошибка получения списка объектов: {e}")
            return []
    
    async def delete_object(self, bucket_name: str, object_key: str) -> bool:
        """Удаляет объект из S3."""
        try:
            async with self.client_context() as s3:
                await s3.delete_object(Bucket=bucket_name, Key=object_key)
                logger.info(f"Объект удален: s3://{bucket_name}/{object_key}")
                return True
        except ClientError as e:
            logger.error(f"Ошибка удаления объекта: {e}")
            return False
    
    async def get_object_url(self, bucket_name: str, object_key: str, expiration: int = 3600) -> Optional[str]:
        """Генерирует presigned URL для объекта."""
        try:
            async with self.client_context() as s3:
                url = await s3.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': bucket_name, 'Key': object_key},
                    ExpiresIn=expiration
                )
                return url
        except ClientError as e:
            logger.error(f"Ошибка генерации URL: {e}")
            return None


# Глобальный экземпляр клиента
_s3_client = None


def get_s3_client() -> AsyncS3Client:
    """Возвращает глобальный экземпляр S3 клиента."""
    global _s3_client
    if _s3_client is None:
        _s3_client = AsyncS3Client()
    return _s3_client
