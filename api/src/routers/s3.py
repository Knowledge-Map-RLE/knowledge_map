"""Роутер для работы с S3"""
import logging
from typing import Dict, Any, Optional
import httpx

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from src.schemas.api import S3ListResponse, S3FileResponse, S3UploadResponse
from services import get_s3_client, settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/s3", tags=["s3"])


@router.get("/buckets/{bucket_name}/objects", response_model=S3ListResponse)
async def list_s3_objects(bucket_name: str, prefix: str = ""):
    """Получает список объектов в S3 bucket."""
    try:
        s3_client = get_s3_client()
        objects = await s3_client.list_objects(bucket_name, prefix)
        return S3ListResponse(objects=objects, count=len(objects))
        
    except Exception as e:
        logger.error(f"Error listing S3 objects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/buckets/{bucket_name}/objects/{object_key:path}", response_model=S3FileResponse)
async def get_s3_object(bucket_name: str, object_key: str):
    """Получает содержимое объекта из S3."""
    try:
        s3_client = get_s3_client()
        if not await s3_client.object_exists(bucket_name, object_key):
            raise HTTPException(status_code=404, detail="Object not found")
        content = await s3_client.download_text(bucket_name, object_key)
        if content is None:
            raise HTTPException(status_code=500, detail="Failed to download object")
        return S3FileResponse(content=content, content_type="text/markdown" if object_key.endswith('.md') else "text/plain")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting S3 object: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/buckets/{bucket_name}/objects/{object_key:path}", response_model=S3UploadResponse)
async def upload_s3_object(bucket_name: str, object_key: str, content: Optional[str] = None):
    """Загружает объект в S3."""
    try:
        if not content:
            raise HTTPException(status_code=400, detail="Content is required")
        s3_client = get_s3_client()
        content_type = "text/markdown" if object_key.endswith('.md') else "text/plain"
        success = await s3_client.upload_bytes(
            data=content.encode('utf-8'),
            bucket=bucket_name,
            object_key=object_key,
            content_type=content_type,
            metadata={"uploaded_by": "knowledge_map_api", "encoding": "utf-8"}
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to upload object")
        return S3UploadResponse(success=True, object_key=object_key)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading S3 object: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/buckets/{bucket_name}/objects/{object_key:path}")
async def delete_s3_object(bucket_name: str, object_key: str):
    """Удаляет объект из S3."""
    try:
        s3_client = get_s3_client()
        if not await s3_client.object_exists(bucket_name, object_key):
            raise HTTPException(status_code=404, detail="Object not found")
        success = await s3_client.delete_object(bucket_name, object_key)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete object")
        return {"success": True, "message": f"Object {object_key} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting S3 object: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/buckets/{bucket_name}/objects/{object_key:path}/url")
async def get_s3_object_url(bucket_name: str, object_key: str, expires_in: int = 3600):
    """Генерирует временный URL для доступа к объекту."""
    try:
        s3_client = get_s3_client()
        if not await s3_client.object_exists(bucket_name, object_key):
            raise HTTPException(status_code=404, detail="Object not found")
        url = await s3_client.get_object_url(bucket_name, object_key, expires_in)
        if not url:
            raise HTTPException(status_code=500, detail="Failed to generate URL")
        return {"url": url, "expires_in": expires_in}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating S3 object URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/nlp/markdown/{filename}", response_model=S3FileResponse)
async def get_nlp_markdown(filename: str):
    """Получает markdown файл из bucket 'markdown' для NLP компонента."""
    try:
        s3_client = get_s3_client()
        if not await s3_client.object_exists("markdown", filename):
            raise HTTPException(status_code=404, detail=f"Markdown file '{filename}' not found")
        content = await s3_client.download_text("markdown", filename)
        if content is None:
            raise HTTPException(status_code=500, detail="Failed to download markdown file")
        return S3FileResponse(content=content, content_type="text/markdown")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting NLP markdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))
