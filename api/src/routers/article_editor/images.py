import logging
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from services.article_editor_service import ArticleEditorService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["article_editor"])
service = ArticleEditorService()


@router.post("/article_editor/images")
async def upload_image(doc_id: str = Form(...), file: UploadFile = File(...)):
    """Загружает изображение статьи в S3, возвращает object_key."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    result = await service.upload_image(
        doc_id,
        file.filename or "image",
        file.content_type or "",
        data,
    )
    if not result.get("success"):
        if result.get("error") == "not_annotated":
            raise HTTPException(status_code=403, detail=result.get("message"))
        raise HTTPException(status_code=500, detail=result.get("error", "Upload failed"))
    return result


@router.get("/article_editor/images/{object_key:path}")
async def get_image(object_key: str):
    """Отдаёт содержимое изображения из S3 с корректным content-type."""
    image = await service.get_image(object_key)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    data, content_type = image
    return Response(content=data, media_type=content_type)


@router.delete("/article_editor/images/{object_key:path}")
async def delete_image(object_key: str):
    """Удаляет изображение из S3."""
    ok = await service.delete_image(object_key)
    if not ok:
        raise HTTPException(status_code=404, detail="Image not found")
    return {"success": True}
