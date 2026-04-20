"""
S3 клиент для data_to_db worker.

Синхронный клиент для загрузки Markdown и изображений в S3.
"""
import os
import logging
from typing import Optional, List, Dict

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

S3_BUCKET = os.getenv("S3_BUCKET", "knowledge-map-data")
S3_BUCKET_NAME = S3_BUCKET  # Alias for compatibility
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minio")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minio123456")


class S3WorkerClient:
    """Синхронный S3 клиент для воркера."""

    def __init__(self):
        self.s3 = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
        )
        self.bucket = S3_BUCKET
        self._ensure_bucket_exists()
        logger.info(f"[S3Client] Инициализирован с bucket: {self.bucket}")

    def _ensure_bucket_exists(self):
        """Создаёт bucket если не существует."""
        try:
            self.s3.head_bucket(Bucket=self.bucket)
        except ClientError:
            try:
                self.s3.create_bucket(Bucket=self.bucket)
                logger.info(f"[S3Client] Bucket создан: {self.bucket}")
            except ClientError as e:
                logger.warning(f"[S3Client] Не удалось создать bucket: {e}")

    def article_exists(self, article_id: str) -> bool:
        """Проверяет, обработана ли статья (есть Markdown в S3)."""
        key = f"documents/{article_id}/{article_id}.md"
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            logger.info(f"[S3Client] Статья уже обработана: {article_id}")
            return True
        except ClientError:
            return False

    def list_processed_articles(self, prefix: str = "documents/") -> List[str]:
        """Возвращает список уже обработанных статей."""
        try:
            response = self.s3.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
            articles = set()
            for obj in response.get("Contents", []):
                key = obj["Key"]
                if key.endswith(".md") and "/" in key:
                    article_id = key.split("/")[-2]
                    articles.add(article_id)
            return list(articles)
        except ClientError as e:
            logger.warning(f"[S3Client] Ошибка получения списка: {e}")
            return []

    def save_markdown(self, article_id: str, content: str) -> bool:
        """Сохраняет Markdown файл в S3."""
        key = f"documents/{article_id}/{article_id}.md"
        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content.encode("utf-8"),
                ContentType="text/markdown",
            )
            logger.info(f"[S3Client] Сохранён Markdown: {article_id}")
            return True
        except ClientError as e:
            logger.error(f"[S3Client] Ошибка сохранения Markdown: {e}")
            return False

    def save_image(self, article_id: str, filename: str, content: bytes, content_type: str = "image/png") -> bool:
        """Сохраняет изображение в S3."""
        key = f"documents/{article_id}/{filename}"
        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
            )
            logger.info(f"[S3Client] Сохранено изображение: {article_id}/{filename}")
            return True
        except ClientError as e:
            logger.error(f"[S3Client] Ошибка сохранения изобр��жения: {e}")
            return False

    def get_article_markdown(self, article_id: str) -> Optional[str]:
        """Получает Markdown файл из S3."""
        key = f"documents/{article_id}/{article_id}.md"
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read().decode("utf-8")
        except ClientError:
            return None

    def upload_file(self, file_path: str, bucket: str, key: str) -> bool:
        """Загружает файл в S3."""
        try:
            self.s3.upload_file(file_path, bucket, key)
            logger.info(f"[S3Client] Загружен файл: {key}")
            return True
        except ClientError as e:
            logger.error(f"[S3Client] Ошибка загрузки файла: {e}")
            return False

    def close(self):
        """Закрывает соединение."""
        self.s3.close()


# Глобальный экземпляр
_client: Optional[S3WorkerClient] = None


def get_s3_client() -> S3WorkerClient:
    global _client
    if _client is None:
        _client = S3WorkerClient()
    return _client