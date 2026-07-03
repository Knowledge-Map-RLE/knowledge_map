import logging
from fastapi import APIRouter, HTTPException

from services.article_editor_service import ArticleEditorService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["article_editor"])
service = ArticleEditorService()


@router.get("/article_editor/articles/{doc_id}/graph")
async def get_article_graph(doc_id: str):
    data = await service.get_graph_data(doc_id)
    return data
