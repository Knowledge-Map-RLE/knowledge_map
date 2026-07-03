import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.article_editor_service import ArticleEditorService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["article_editor"])
service = ArticleEditorService()


class CreateArticleRequest(BaseModel):
    title: str = "New Article"


class SaveTextRequest(BaseModel):
    text: str


class SaveStatementsRequest(BaseModel):
    statements: list[dict]


@router.post("/article_editor/articles")
async def create_article(req: CreateArticleRequest):
    return await service.create_article(title=req.title)


@router.get("/article_editor/articles")
async def list_articles(skip: int = 0, limit: int = 200):
    return {"articles": await service.list_articles(skip=skip, limit=limit), "success": True}


@router.get("/article_editor/articles/{doc_id}")
async def get_article(doc_id: str):
    article = await service.get_article(doc_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return {"article": article, "success": True}


@router.put("/article_editor/articles/{doc_id}/text")
async def save_article_text(doc_id: str, req: SaveTextRequest):
    result = await service.save_article_text(doc_id, req.text)
    return result


@router.get("/article_editor/articles/{doc_id}/text")
async def get_article_text(doc_id: str):
    text = await service.get_article_text(doc_id)
    return {"text": text, "success": True}


@router.put("/article_editor/articles/{doc_id}/statements")
async def save_statements(doc_id: str, req: SaveStatementsRequest):
    return await service.save_statements(doc_id, req.statements)
