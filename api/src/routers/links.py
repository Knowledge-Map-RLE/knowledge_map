"""Роутер для работы со связями между блоками"""
import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from neomodel import db, DoesNotExist

from src.models import Block
from src.schemas.api import LinkInput

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/links", tags=["links"])


@router.post("", response_model=Dict[str, Any])
async def create_link(link_input: LinkInput):
    """Создает новую связь между блоками."""
    try:
        # Используем транзакцию для надежности
        with db.transaction:
            source_block = Block.nodes.get(uid=link_input.source)
            target_block = Block.nodes.get(uid=link_input.target)

            # connect теперь возвращает экземпляр LinkRel, который мы можем сохранить
            rel = source_block.target.connect(target_block)
            rel.save() # <-- Явно сохраняем саму связь
        
        response_link = {
            "id": rel.uid,
            "source_id": source_block.uid,
            "target_id": target_block.uid
        }
        return {"success": True, "link": response_link}

    except DoesNotExist:
        logger.error(f"Attempted to create link with non-existent block. Source: {link_input.source}, Target: {link_input.target}")
        raise HTTPException(status_code=404, detail="Один из блоков для создания связи не найден.")
    except Exception as e:
        logger.error(f"Error creating link: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка при создании связи: {e}")


@router.delete("/{link_id}", response_model=Dict[str, Any])
async def delete_link(link_id: str):
    """Удаляет связь по её ID."""
    try:
        with db.transaction:
            # Находим и удаляем связь по её UID
            delete_query = """
            MATCH ()-[r:LINK_TO {uid: $link_id}]->()
            DELETE r
            RETURN count(r) as deleted_count
            """
            result, _ = db.cypher_query(delete_query, {"link_id": link_id})
            deleted_count = result[0][0] if result else 0
            
            if deleted_count == 0:
                raise HTTPException(status_code=404, detail="Link not found")
                
        return {"success": True, "message": f"Link {link_id} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting link: {e}")
        raise HTTPException(status_code=500, detail=str(e))
