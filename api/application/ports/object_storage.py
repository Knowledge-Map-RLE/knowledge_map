"""
Layer: Application (Use Cases) — Ports
Package: application.ports.object_storage
Responsibility: Абстракция файлового хранилища (S3/MinIO/локальное).

Реализации находятся в infrastructure/s3/.

Allowed imports: typing, стандартная библиотека
Forbidden imports: aioboto3, fastapi, neomodel, adapters, infrastructure, web
"""
from __future__ import annotations

from typing import Protocol, Optional, List, Dict


class ObjectStorageProtocol(Protocol):
    """Асинхронные операции с объектным хранилищем."""

    async def upload_bytes(
        self,
        data: bytes,
        bucket_name: str,
        object_key: str,
        content_type: str = "application/octet-stream",
        metadata: Optional[Dict[str, str]] = None,
    ) -> bool: ...

    async def download_bytes(self, bucket_name: str, object_key: str) -> Optional[bytes]: ...

    async def download_text(
        self, bucket_name: str, object_key: str, encoding: str = "utf-8"
    ) -> Optional[str]: ...

    async def object_exists(self, bucket_name: str, object_key: str) -> bool: ...

    async def delete_object(self, bucket_name: str, object_key: str) -> bool: ...

    async def list_objects(self, bucket_name: str, prefix: str = "") -> List[Dict]: ...

    async def get_object_url(
        self, bucket_name: str, object_key: str, expires_in: int = 3600
    ) -> Optional[str]: ...
