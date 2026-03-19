"""Синхронный S3/MinIO клиент для воркера worker_data_to_db.

Использует boto3 (не aioboto3) для синхронного кода.
"""
import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minio")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minio123456")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "knowledge-map-data")

_s3_client = None


class SyncS3Client:
    """Синхронный S3 клиент через boto3."""

    def __init__(self):
        self._client = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT_URL,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            region_name=S3_REGION,
        )
        logger.info(f"[s3_client] Создан клиент: {S3_ENDPOINT_URL}")

    def upload_text(self, text: str, bucket: str, key: str) -> bool:
        """Загружает текст в S3 как UTF-8 файл.

        Args:
            text: текстовое содержимое
            bucket: имя бакета
            key: S3 ключ (путь)

        Returns:
            True если успешно, False при ошибке
        """
        try:
            self._client.put_object(
                Bucket=bucket,
                Key=key,
                Body=text.encode("utf-8"),
                ContentType="text/markdown; charset=utf-8",
            )
            logger.debug(f"[s3_client] Загружено: s3://{bucket}/{key}")
            return True
        except ClientError as e:
            logger.error(f"[s3_client] Ошибка загрузки s3://{bucket}/{key}: {e}")
            return False
        except Exception as e:
            logger.error(f"[s3_client] Неожиданная ошибка при загрузке {key}: {e}")
            return False


def get_s3_client() -> SyncS3Client:
    """Lazy singleton для синхронного S3 клиента."""
    global _s3_client
    if _s3_client is None:
        _s3_client = SyncS3Client()
    return _s3_client
