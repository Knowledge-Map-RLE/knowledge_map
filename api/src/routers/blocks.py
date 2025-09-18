"""Роутер для работы с блоками"""
import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from neomodel import db, DoesNotExist

from src.models import Block
from services import get_layout_client
from src.schemas.api import (
    BlockInput, CreateAndLinkInput, MoveToLevelInput, PinWithScaleInput
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/blocks", tags=["blocks"])


@router.post("", response_model=Dict[str, Any])
async def create_block(block_input: BlockInput):
    """Создает новый блок в Neo4j."""
    try:
        # Используем транзакцию для атомарности
        with db.transaction:
            b = Block(content=block_input.content)
            b.save()
            b.refresh()
        
        response_block = {
            "id": b.uid,
            "content": b.content,
            "level": b.level,
            "layer": b.layer,
            "sublevel_id": b.sublevel_id,
            "is_pinned": b.is_pinned,
            "physical_scale": getattr(b, 'physical_scale', 0),
        }
        return {"success": True, "block": response_block}
    except Exception as e:
        logger.error(f"Error creating block: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{block_id}", response_model=Dict[str, Any])
async def update_block(block_id: str, block_input: BlockInput):
    """Обновляет содержимое блока в Neo4j."""
    try:
        with db.transaction:
            block = Block.nodes.get(uid=block_id)
            block.content = block_input.content
            block.save()
            
        response_block = {
            "id": block.uid,
            "content": block.content,
            "level": block.level,
            "layer": block.layer,
            "sublevel_id": block.sublevel_id,
            "is_pinned": block.is_pinned,
            "physical_scale": getattr(block, 'physical_scale', 0),
        }
        return {"success": True, "block": response_block}
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Block not found")
    except Exception as e:
        logger.error(f"Error updating block: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create_and_link", response_model=Dict[str, Any])
async def create_block_and_link(data: CreateAndLinkInput):
    """Атомарно создает новый блок и связь с существующим блоком."""
    try:
        source_block = Block.nodes.get(uid=data.source_block_id)
        
        # Создаем новый блок
        new_block = Block(content=data.new_block_content, layer=source_block.layer + 1).save()
        
        # Создаем связь
        if data.link_direction == 'from_source':
            link = source_block.target.connect(new_block)
        else: # to_source
            link = new_block.target.connect(source_block)
        
        # Получаем полный обновленный граф из Neo4j
        blocks_query = "MATCH (b:Block) RETURN b.uid as id, b.content as content, b.layer as layer, b.level as level, b.is_pinned as is_pinned, b.physical_scale as physical_scale"
        blocks_result, _ = db.cypher_query(blocks_query)
        
        links_query = "MATCH (b1:Block)-[r:LINK_TO]->(b2:Block) RETURN r.uid as id, b1.uid as source_id, b2.uid as target_id"
        links_result, _ = db.cypher_query(links_query)

        blocks_for_layout = [{"id": str(r[0]), "content": str(r[1] or ""), "layer": int(r[2] or 0), "level": int(r[3] or 0), "is_pinned": bool(r[4]) if r[4] is not None else False, "physical_scale": int(r[5] or 0) if r[5] is not None else 0, "metadata": {}} for r in blocks_result]
        links_for_layout = [{"id": str(r[0]) if r[0] else None, "source_id": str(r[1]), "target_id": str(r[2])} for r in links_result]
        
        # Вызываем сервис укладки
        client = get_layout_client()
        layout_result = await client.calculate_layout(blocks_for_layout, links_for_layout)
        
        if not layout_result.get("success"):
            raise HTTPException(status_code=500, detail="Layout service failed after creating block and link.")

        # Находим данные нового блока в результатах укладки
        final_new_block_data = next((b for b in layout_result.get("blocks", []) if b["id"] == new_block.uid), None)

        if not final_new_block_data:
            raise HTTPException(status_code=500, detail="Could not find new block in layout result.")

        return {
            "success": True,
            "new_block": final_new_block_data,
            "new_link": {
                "id": link.uid,
                "source_id": link.start_node().uid,
                "target_id": link.end_node().uid,
            }
        }
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Source block not found")
    except Exception as e:
        logger.error(f"Error creating block and link: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{block_id}", response_model=Dict[str, Any])
async def delete_block(block_id: str):
    """Удаляет блок и все связанные с ним связи."""
    try:
        with db.transaction:
            block = Block.nodes.get(uid=block_id)
            
            # Удаляем все связи, где этот блок является источником или целью
            # Сначала удаляем исходящие связи
            outgoing_query = """
            MATCH (source:Block {uid: $block_id})-[r:LINK_TO]->(target:Block)
            DELETE r
            """
            db.cypher_query(outgoing_query, {"block_id": block_id})
            
            # Затем удаляем входящие связи
            incoming_query = """
            MATCH (source:Block)-[r:LINK_TO]->(target:Block {uid: $block_id})
            DELETE r
            """
            db.cypher_query(incoming_query, {"block_id": block_id})
            
            # Удаляем сам блок
            block.delete()
            
        return {"success": True, "message": f"Block {block_id} deleted successfully"}
        
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Block not found")
    except Exception as e:
        logger.error(f"Error deleting block: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{block_id}/pin", response_model=Dict[str, Any])
async def pin_block(block_id: str):
    """Закрепляет блок за уровнем с сохранением его текущего уровня."""
    logger.info(f"🔥 PIN_BLOCK CALLED: {block_id} - НОВАЯ ВЕРСИЯ КОДА!")
    try:
        with db.transaction:
            block = Block.nodes.get(uid=block_id)
            logger.info(f"📊 Before pinning: block {block_id} is_pinned = {block.is_pinned}, level = {block.level}")
            
            # Если у блока нет уровня, устанавливаем его текущий level из позиции в графе
            if block.level == 0:
                # Получаем все блоки для определения текущего уровня
                blocks_query = "MATCH (b:Block) RETURN b.uid as id, b.content as content, b.layer as layer, b.level as level, b.is_pinned as is_pinned, b.physical_scale as physical_scale"
                blocks_result, _ = db.cypher_query(blocks_query)
                
                links_query = "MATCH (b1:Block)-[r:LINK_TO]->(b2:Block) RETURN r.uid as id, b1.uid as source_id, b2.uid as target_id"
                links_result, _ = db.cypher_query(links_query)

                blocks_for_layout = [{"id": str(r[0]), "content": str(r[1] or ""), "layer": int(r[2] or 0), "level": int(r[3] or 0), "is_pinned": bool(r[4]) if r[4] is not None else False, "physical_scale": int(r[5] or 0) if r[5] is not None else 0, "metadata": {}} for r in blocks_result]
                links_for_layout = [{"id": str(r[0]) if r[0] else None, "source_id": str(r[1]), "target_id": str(r[2])} for r in links_result]
                
                # Получаем текущую укладку для определения уровня блока
                client = get_layout_client()
                layout_result = await client.calculate_layout(blocks_for_layout, links_for_layout)
                
                if layout_result.get('success') and layout_result.get('blocks'):
                    # Находим уровень текущего блока в результатах укладки
                    current_block_level = 0
                    for block_info in layout_result['blocks']:
                        if block_info['id'] == block_id:
                            current_block_level = block_info['level']
                            break
                    
                    block.level = current_block_level
                    logger.info(f"Setting block {block_id} level to {current_block_level} based on current layout")
            
            block.is_pinned = True
            block.save()
            block.refresh()
            logger.info(f"After pinning: block {block_id} is_pinned = {block.is_pinned}, level = {block.level}")
            
        return {"success": True, "message": f"Block {block_id} pinned successfully at level {block.level}"}
        
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Block not found")
    except Exception as e:
        logger.error(f"Error pinning block: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{block_id}/unpin", response_model=Dict[str, Any])
async def unpin_block(block_id: str):
    """Открепляет блок от уровня."""
    try:
        with db.transaction:
            block = Block.nodes.get(uid=block_id)
            block.is_pinned = False
            block.save()
            
        return {"success": True, "message": f"Block {block_id} unpinned successfully"}
        
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Block not found")
    except Exception as e:
        logger.error(f"Error unpinning block: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{block_id}/pin_with_scale", response_model=Dict[str, Any])
async def pin_block_with_scale(block_id: str, data: PinWithScaleInput):
    """Закрепляет блок за уровнем с указанным физическим масштабом."""
    logger.info(f"🔥 PIN_BLOCK_WITH_SCALE CALLED: {block_id} with scale {data.physical_scale}")
    try:
        with db.transaction:
            block = Block.nodes.get(uid=block_id)
            logger.info(f"📊 Before pinning with scale: block {block_id} is_pinned = {block.is_pinned}, level = {block.level}, physical_scale = {getattr(block, 'physical_scale', 'not set')}")
            
            # Если у блока нет уровня, устанавливаем его текущий level из позиции в графе
            if block.level == 0:
                # Получаем все блоки для определения текущего уровня
                blocks_query = "MATCH (b:Block) RETURN b.uid as id, b.content as content, b.layer as layer, b.level as level, b.is_pinned as is_pinned, b.physical_scale as physical_scale"
                blocks_result, _ = db.cypher_query(blocks_query)
                
                links_query = "MATCH (b1:Block)-[r:LINK_TO]->(b2:Block) RETURN r.uid as id, b1.uid as source_id, b2.uid as target_id"
                links_result, _ = db.cypher_query(links_query)

                blocks_for_layout = [{"id": str(r[0]), "content": str(r[1] or ""), "layer": int(r[2] or 0), "level": int(r[3] or 0), "is_pinned": bool(r[4]) if r[4] is not None else False, "physical_scale": int(r[5] or 0) if r[5] is not None else 0, "metadata": {}} for r in blocks_result]
                links_for_layout = [{"id": str(r[0]) if r[0] else None, "source_id": str(r[1]), "target_id": str(r[2])} for r in links_result]
                
                # Получаем текущую укладку для определения уровня блока
                client = get_layout_client()
                layout_result = await client.calculate_layout(blocks_for_layout, links_for_layout)
                
                if layout_result.get('success') and layout_result.get('blocks'):
                    # Находим уровень текущего блока в результатах укладки
                    current_block_level = 0
                    for block_info in layout_result['blocks']:
                        if block_info['id'] == block_id:
                            current_block_level = block_info['level']
                            break
                    
                    block.level = current_block_level
                    logger.info(f"Setting block {block_id} level to {current_block_level} based on current layout")
            
            # Устанавливаем физический масштаб и закрепляем
            block.is_pinned = True
            block.physical_scale = data.physical_scale
            block.save()
            block.refresh()
            logger.info(f"After pinning with scale: block {block_id} is_pinned = {block.is_pinned}, level = {block.level}, physical_scale = {block.physical_scale}")
            
        return {"success": True, "message": f"Block {block_id} pinned successfully at level {block.level} with physical scale {data.physical_scale}"}
        
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Block not found")
    except Exception as e:
        logger.error(f"Error pinning block with scale: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{block_id}/move_to_level", response_model=Dict[str, Any])
async def move_block_to_level(block_id: str, data: MoveToLevelInput):
    """Перемещает закрепленный блок на указанный уровень."""
    logger.info(f"🔄 MOVE_BLOCK_TO_LEVEL CALLED: {block_id} -> level {data.target_level}")
    try:
        with db.transaction:
            block = Block.nodes.get(uid=block_id)
            
            # Проверяем, что блок закреплен
            if not block.is_pinned:
                raise HTTPException(status_code=400, detail="Block must be pinned to move between levels")
            
            logger.info(f"📊 Before moving: block {block_id} level = {block.level}")
            
            # Обновляем уровень блока
            block.level = data.target_level
            block.save()
            block.refresh()
            
            logger.info(f"✅ After moving: block {block_id} level = {block.level}")
            
        return {"success": True, "message": f"Block {block_id} moved to level {data.target_level} successfully"}
        
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Block not found")
    except Exception as e:
        logger.error(f"Error moving block to level: {e}")
        raise HTTPException(status_code=500, detail=str(e))
