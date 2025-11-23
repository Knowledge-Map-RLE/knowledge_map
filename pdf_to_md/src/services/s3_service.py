#!/usr/bin/env python3
"""S3 сервис для сохранения и загрузки изображений"""

import logging
import asyncio
import os
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config
from PIL import Image
import io

logger = logging.getLogger(__name__)

class S3Service:
    """
    Сервис для работы с S3-совместимым хранилищем (MinIO)
    """
    
    def __init__(self):
        self.endpoint_url = os.getenv('S3_ENDPOINT_URL', 'http://localhost:9000')
        self.access_key = os.getenv('S3_ACCESS_KEY', 'minio')
        self.secret_key = os.getenv('S3_SECRET_KEY', 'minio123456')
        self.region = os.getenv('S3_REGION', 'us-east-1')
        self.bucket_name = os.getenv('S3_BUCKET_NAME', 'knowledge-map-data')
        
        # Конфигурация для MinIO
        self.config = Config(
            region_name=self.region,
            retries={'max_attempts': 3},
            signature_version='s3v4'
        )
        
        self.s3_client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Инициализация S3 клиента"""
        try:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=self.config
            )
            logger.info(f"S3 client initialized with endpoint: {self.endpoint_url}")
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            raise
    
    async def ensure_bucket_exists(self) -> bool:
        """Убедиться, что bucket существует, создать если нет"""
        try:
            # Проверяем существование bucket
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"Bucket '{self.bucket_name}' exists")
            return True
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                # Bucket не существует, создаем
                try:
                    self.s3_client.create_bucket(Bucket=self.bucket_name)
                    logger.info(f"Created bucket '{self.bucket_name}'")
                    return True
                except ClientError as create_error:
                    logger.error(f"Failed to create bucket: {create_error}")
                    return False
            else:
                logger.error(f"Error checking bucket: {e}")
                return False
    
    async def upload_image(
        self,
        image_data: Union[bytes, Image.Image, Path],
        filename: Optional[str] = None,
        folder: str = "images"
    ) -> Dict[str, Any]:
        """
        Загрузить изображение в S3
        
        Args:
            image_data: Данные изображения (bytes, PIL Image или Path)
            filename: Имя файла (генерируется автоматически если не указано)
            folder: Папка в bucket
            
        Returns:
            Информация о загруженном файле
        """
        try:
            # Убеждаемся что bucket существует
            await self.ensure_bucket_exists()
            
            # Генерируем имя файла если не указано
            if not filename:
                file_id = uuid.uuid4().hex[:8]
                filename = f"image_{file_id}.png"
            
            # Формируем ключ объекта
            object_key = f"{folder}/{filename}"
            
            # Подготавливаем данные для загрузки
            upload_data = await self._prepare_image_data(image_data)
            
            # Загружаем в S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=object_key,
                Body=upload_data,
                ContentType='image/png'
                # Убираем ACL - будем использовать presigned URLs с максимальным временем жизни
            )
            
            # Формируем постоянную API ссылку для проксирования через FastAPI
            # Эта ссылка не истекает и проксирует изображения из S3
            # Используем основной API (порт 8000), который проксирует запросы к pdf_to_md сервису
            api_base_url = os.getenv('API_BASE_URL', 'http://localhost:8000')
            image_url = f"{api_base_url}/api/v1/s3/image/{object_key}"
            logger.info(f"Generated permanent API proxy URL")
            
            logger.info(f"Uploaded image: {object_key}")
            
            return {
                "success": True,
                "filename": filename,
                "object_key": object_key,
                "url": image_url,
                "bucket": self.bucket_name,
                "size_bytes": len(upload_data) if isinstance(upload_data, bytes) else None
            }
            
        except Exception as e:
            logger.error(f"Failed to upload image: {e}")
            return {
                "success": False,
                "error": str(e),
                "filename": filename
            }
    
    async def _prepare_image_data(self, image_data: Union[bytes, Image.Image, Path]) -> bytes:
        """Подготовить данные изображения для загрузки"""
        
        if isinstance(image_data, bytes):
            return image_data
        
        elif isinstance(image_data, Image.Image):
            # Конвертируем PIL Image в bytes
            buffer = io.BytesIO()
            image_data.save(buffer, format='PNG')
            return buffer.getvalue()
        
        elif isinstance(image_data, (str, Path)):
            # Читаем файл
            path = Path(image_data)
            if not path.exists():
                raise FileNotFoundError(f"Image file not found: {path}")
            
            return path.read_bytes()
        
        else:
            raise ValueError(f"Unsupported image data type: {type(image_data)}")
    
    async def upload_markdown(
        self,
        markdown_content: str,
        filename: str,
        folder: str = "markdown"
    ) -> Dict[str, Any]:
        """
        Загрузить Markdown файл в S3

        Args:
            markdown_content: Текст Markdown
            filename: Имя файла
            folder: Папка в bucket

        Returns:
            Информация о загруженном файле
        """
        try:
            # Убеждаемся что bucket существует
            await self.ensure_bucket_exists()

            # Формируем ключ объекта
            object_key = f"{folder}/{filename}"

            # Конвертируем строку в bytes
            markdown_bytes = markdown_content.encode('utf-8')

            # Загружаем в S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=object_key,
                Body=markdown_bytes,
                ContentType='text/markdown; charset=utf-8'
            )

            logger.info(f"Uploaded markdown: {object_key} ({len(markdown_bytes)} bytes)")

            return {
                "success": True,
                "filename": filename,
                "object_key": object_key,
                "bucket": self.bucket_name,
                "size_bytes": len(markdown_bytes)
            }

        except Exception as e:
            logger.error(f"Failed to upload markdown: {e}")
            return {
                "success": False,
                "error": str(e),
                "filename": filename
            }

    async def download_image(self, object_key: str) -> Dict[str, Any]:
        """
        Скачать изображение из S3

        Args:
            object_key: Ключ объекта в S3

        Returns:
            Данные изображения
        """
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=object_key
            )

            image_data = response['Body'].read()

            return {
                "success": True,
                "data": image_data,
                "content_type": response.get('ContentType'),
                "size_bytes": len(image_data)
            }

        except ClientError as e:
            logger.error(f"Failed to download image {object_key}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def delete_image(self, object_key: str) -> Dict[str, Any]:
        """
        Удалить изображение из S3
        
        Args:
            object_key: Ключ объекта в S3
            
        Returns:
            Результат операции
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=object_key
            )
            
            logger.info(f"Deleted image: {object_key}")
            
            return {
                "success": True,
                "object_key": object_key
            }
            
        except ClientError as e:
            logger.error(f"Failed to delete image {object_key}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def list_images(self, folder: str = "images", limit: int = 100) -> Dict[str, Any]:
        """
        Получить список изображений в папке
        
        Args:
            folder: Папка для поиска
            limit: Максимальное количество файлов
            
        Returns:
            Список изображений
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=f"{folder}/",
                MaxKeys=limit
            )
            
            images = []
            for obj in response.get('Contents', []):
                images.append({
                    "object_key": obj['Key'],
                    "filename": obj['Key'].split('/')[-1],
                    "size_bytes": obj['Size'],
                    "last_modified": obj['LastModified'].isoformat(),
                    "url": f"{self.endpoint_url}/{self.bucket_name}/{obj['Key']}"
                })
            
            return {
                "success": True,
                "images": images,
                "count": len(images)
            }
            
        except ClientError as e:
            logger.error(f"Failed to list images: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_image_url(self, object_key: str) -> str:
        """Получить URL изображения"""
        return f"{self.endpoint_url}/{self.bucket_name}/{object_key}"
    
    async def download_bytes(self, object_key: str) -> Optional[bytes]:
        """
        Скачать изображение из S3 как bytes
        
        Args:
            object_key: Ключ объекта в S3
            
        Returns:
            Данные изображения в bytes или None
        """
        
        def _download_sync():
            try:
                response = self.s3_client.get_object(
                    Bucket=self.bucket_name,
                    Key=object_key
                )
                return response['Body'].read()
            except Exception as e:
                logger.error(f"Failed to download {object_key}: {e}")
                return None
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _download_sync)

    async def generate_presigned_url(self, object_key: str, expiration: int = 3600) -> Optional[str]:
        """
        Генерировать presigned URL для безопасного доступа к объекту
        
        Args:
            object_key: Ключ объекта в S3
            expiration: Время жизни URL в секундах (по умолчанию 1 час)
            
        Returns:
            Presigned URL или None в случае ошибки
        """
        
        def _generate_sync():
            try:
                return self.s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': self.bucket_name, 'Key': object_key},
                    ExpiresIn=expiration
                )
            except Exception as e:
                logger.error(f"Failed to generate presigned URL for {object_key}: {e}")
                return None
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _generate_sync)

    async def health_check(self) -> Dict[str, Any]:
        """Проверка состояния S3 сервиса"""
        try:
            # Проверяем подключение
            self.s3_client.list_buckets()
            
            # Проверяем bucket
            bucket_exists = await self.ensure_bucket_exists()
            
            return {
                "success": True,
                "endpoint": self.endpoint_url,
                "bucket": self.bucket_name,
                "bucket_exists": bucket_exists
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "endpoint": self.endpoint_url
            }


# Глобальный экземпляр сервиса
s3_service = S3Service()


async def test_s3_service():
    """Тест S3 сервиса"""
    
    logger.info("=== Testing S3 Service ===")
    
    # Проверка состояния
    health = await s3_service.health_check()
    logger.info(f"Health check: {health}")
    
    if not health['success']:
        logger.error("S3 service is not healthy")
        return
    
    # Тест загрузки изображения
    test_image = Image.new('RGB', (100, 100), color='red')
    
    upload_result = await s3_service.upload_image(
        image_data=test_image,
        filename="test_image.png",
        folder="test"
    )
    
    logger.info(f"Upload result: {upload_result}")
    
    if upload_result['success']:
        # Тест скачивания
        download_result = await s3_service.download_image(upload_result['object_key'])
        logger.info(f"Download result: {download_result['success']}, size: {download_result.get('size_bytes')}")
        
        # Тест списка файлов
        list_result = await s3_service.list_images("test")
        logger.info(f"List result: {list_result}")
        
        # Тест удаления
        delete_result = await s3_service.delete_image(upload_result['object_key'])
        logger.info(f"Delete result: {delete_result}")


if __name__ == "__main__":
    asyncio.run(test_s3_service())
