from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from strawberry.fastapi import GraphQLRouter
from schema import schema
from models import User, Block, Tag, LinkMetadata
from layout_client import get_layout_client, LayoutOptions, LayoutConfig
from config import settings
from s3_client import get_s3_client
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
import logging
from neomodel import config as neomodel_config, db, UniqueIdProperty, DoesNotExist
import uuid
import json

from auth_client import auth_client
from schemas import (
    UserRegisterRequest, UserLoginRequest, UserRecoveryRequest, 
    UserPasswordResetRequest, User2FASetupRequest, User2FAVerifyRequest,
    AuthResponse, TokenVerifyResponse
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка подключения к Neo4j
neomodel_config.DATABASE_URL = settings.get_database_url()
logger.info(f"Neo4j connection configured: {settings.NEO4J_URI}")

# Настройка CORS
origins = [
    "http://localhost:5173",  # Vite dev server
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

logger.info(f"Configuring CORS with origins: {origins}")

# Создаем приложение FastAPI
app = FastAPI(
    title="Knowledge Map API",
    description="GraphQL API для карты знаний с микросервисом укладки",
    version="1.0.0"
)

# Настраиваем CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,  # Кэшируем CORS ответы на 1 час
)

# Middleware для логирования запросов
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Request: {request.method} {request.url}")
    logger.info(f"Headers: {dict(request.headers)}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response

# Middleware для добавления CORS заголовков
@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    response = await call_next(request)
    if request.headers.get("origin") in origins:
        response.headers["Access-Control-Allow-Origin"] = request.headers["origin"]
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "*"
    return response

# Pydantic модели для API запросов
class BlockInput(BaseModel):
    content: str

class LinkInput(BaseModel):
    source: str
    target: str

class LayoutRequest(BaseModel):
    blocks: List[BlockInput]
    links: List[LinkInput]
    sublevel_spacing: Optional[int] = 200
    layer_spacing: Optional[int] = 250
    optimize_layout: bool = True

class CreateAndLinkInput(BaseModel):
    source_block_id: str
    new_block_content: str = "Новый блок"
    link_direction: str = Field(..., pattern="^(from_source|to_source)$") # 'from_source' или 'to_source'

class MoveToLevelInput(BaseModel):
    target_level: int

class PinWithScaleInput(BaseModel):
    physical_scale: int  # степень 10 в метрах

# Pydantic модели для S3 запросов
class S3UploadResponse(BaseModel):
    success: bool
    object_key: Optional[str] = None
    error: Optional[str] = None

class S3FileResponse(BaseModel):
    content: Optional[str] = None
    content_type: Optional[str] = None
    size: Optional[int] = None
    last_modified: Optional[str] = None
    error: Optional[str] = None

class S3ListResponse(BaseModel):
    objects: List[Dict[str, Any]]
    count: int

# Эндпоинты для проверки здоровья
@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Проверяет здоровье API"""
    return {"status": "ok", "message": "API is healthy"}


@app.get("/layout/health")
async def check_layout_health():
    """Проверяет здоровье сервиса укладки"""
    try:
        client = get_layout_client()
        is_healthy = await client.health_check()
        if is_healthy:
            return {"status": "ok", "message": "Layout service is healthy"}
        else:
            return {"status": "error", "message": "Layout service is not healthy"}, 503
    except Exception as e:
        logger.error(f"Layout health check error: {e}")
        return {"status": "error", "message": str(e)}, 503


# Эндпоинт для получения укладки
@app.post("/layout")
async def calculate_layout(request: LayoutRequest) -> Dict[str, Any]:
    """Рассчитывает укладку для заданного графа"""
    try:
        client = get_layout_client()
        
        # Преобразуем запрос в формат для сервиса укладки
        blocks = [
            {
                "id": block.id,
                "content": block.content,
                "metadata": block.metadata
            }
            for block in request.blocks
        ]
        
        links = [
            {
                "id": link.id,
                "source_id": link.source_id,
                "target_id": link.target_id,
                "metadata": link.metadata
            }
            for link in request.links
        ]
        
        # Настройки алгоритма
        options = LayoutOptions(
            sublevel_spacing=request.sublevel_spacing,
            layer_spacing=request.layer_spacing,
            optimize_layout=request.optimize_layout
        )
        
        # Получаем укладку
        result = await client.calculate_layout(blocks, links, options)
        
        # Проверяем результат
        if not result.get("success", False):
            error_msg = result.get("error", "Неизвестная ошибка при расчете укладки")
            logger.error(f"Layout calculation error: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
        
        return result
        
    except Exception as e:
        logger.error(f"Layout calculation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    return {
        "message": "Knowledge Map API", 
        "graphql": "/graphql",
        "docs": "/docs",
        "layout": "/layout/calculate",
        "layout_health": "/layout/health",
        "neo4j_browser": "http://localhost:7474"
    }

@app.get("/layout/articles")
async def get_articles_layout() -> Dict[str, Any]:
    """Получает укладку только для статей (блоков с типом "Article")"""
    try:
        logger.info("Starting articles layout calculation from Neo4j")
        
        # Читаем граф из Neo4j: узлы помечены как Node, связи - CITES
        logger.info("Querying articles from Neo4j")
        blocks_query = """
        MATCH (n:Node)
        RETURN n.uid as id,
               n.content as content,
               n.layer as layer,
               n.level as level,
               n.sublevel_id as sublevel_id,
               n.is_pinned as is_pinned,
               n.physical_scale as physical_scale,
               n.x as x,
               n.y as y
        """
        blocks_result, _ = db.cypher_query(blocks_query)
        logger.info(f"Found {len(blocks_result)} nodes total")
        
        if not blocks_result:
            logger.warning("No nodes found in Neo4j")
            raise HTTPException(status_code=404, detail="В базе данных нет узлов Node. Загрузите данные.")
        
        links_query = """
        MATCH (s:Node)-[r:CITES]->(t:Node)
        RETURN r.uid as id, s.uid as source_id, t.uid as target_id
        """
        links_result, _ = db.cypher_query(links_query)
        
        # Используем настоящие ID из базы данных
        blocks = []
        for row in blocks_result:
            block_data = {
                "id": str(row[0]),
                "content": str(row[1] or ""),
                "layer": int(row[2] or 0),
                "level": int(row[3] or 0),
                "sublevel_id": int(row[4] or 0),
                "is_pinned": bool(row[5]) if row[5] is not None else False,
                "physical_scale": int(row[6] or 0) if row[6] is not None else 0,
                "x": float(row[7]) if row[7] is not None else None,
                "y": float(row[8]) if row[8] is not None else None,
                "metadata": {}
            }
            if block_data.get("is_pinned"):
                logger.info(f"Found pinned node in DB: {block_data['id']} - is_pinned: {block_data['is_pinned']}")
            blocks.append(block_data)
        
        # Преобразуем связи
        links_for_layout = []
        for row in links_result:
            link_id = str(row[0]) if row[0] is not None else None
            source_id = str(row[1])
            target_id = str(row[2])
            links_for_layout.append(
                {"id": link_id, "source_id": source_id, "target_id": target_id}
            )

        if not blocks:
            raise HTTPException(status_code=404, detail="В базе данных нет статей.")
        
        # Удаляем потенциальные циклы: оставляем рёбра только вперёд по слоям/уровням
        # TODO это должно делаться на стороне бэкенда
        level_index = {b["id"]: (b.get("layer", 0), b.get("level", 0)) for b in blocks}
        filtered_links = []
        for l in links_for_layout:
            s = l["source_id"]; t = l["target_id"]
            if s in level_index and t in level_index:
                sl, sv = level_index[s]
                tl, tv = level_index[t]
                if (tl > sl) or (tl == sl and tv > sv):
                    filtered_links.append(l)
        if len(filtered_links) < len(links_for_layout):
            logger.info(f"Filtered potential cycles: kept {len(filtered_links)} of {len(links_for_layout)} links")
        
        # Получаем укладку
        client = get_layout_client()
        try:
            result = await client.calculate_layout(
                blocks=blocks,
                links=filtered_links,
                options=LayoutOptions(
                    sublevel_spacing=200,
                    layer_spacing=250,
                    optimize_layout=False
                )
            )
            return result
        except Exception as e:
            logger.error(f"Error in articles layout calculation: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Ошибка при расчете укладки статей: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error calculating articles layout from Neo4j: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при получении данных статей из Neo4j: {str(e)}")


@app.get("/layout/articles_all")
async def get_all_articles_layout() -> Dict[str, Any]:
    """Возвращает все блоки и связи из графа статей."""
    try:
        logger.info("Loading all articles and links")

        # Запрос всех узлов
        nodes_query = """
        MATCH (n:Node)
        RETURN n.uid as id,
               coalesce(n.title, n.name, n.content, toString(n.uid)) as title,
               n.layer as layer,
               n.level as level,
               n.sublevel_id as sublevel_id,
               n.is_pinned as is_pinned,
               n.physical_scale as physical_scale,
               n.x as x,
               n.y as y,
               n.layout_status as layout_status
        """
        blocks_result, _ = db.cypher_query(nodes_query)

        if not blocks_result:
            return {
                "success": True,
                "blocks": [],
                "links": [],
                "levels": [],
                "sublevels": [],
                "total": 0
            }

        blocks: list[dict] = []
        for row in blocks_result:
            block = {
                "id": str(row[0]),
                "content": str(row[1] or ""),
                "layer": int(row[2] or 0),
                "level": int(row[3] or 0),
                "sublevel_id": int(row[4] or 0),
                "is_pinned": bool(row[5]) if row[5] is not None else False,
                "physical_scale": int(row[6] or 0) if row[6] is not None else 0,
                "x": float(row[7]) if row[7] is not None else None,
                "y": float(row[8]) if row[8] is not None else None,
                "layout_status": str(row[9] or ""),
                "metadata": {},
            }
            blocks.append(block)

        # Запрос всех связей
        links_query = """
        MATCH (s:Node)-[r:CITES]->(t:Node)
        RETURN r.uid as id, s.uid as source_id, t.uid as target_id
        """
        links_result, _ = db.cypher_query(links_query)
        
        links: list[dict] = []
        for row in links_result:
            link_id = row[0]
            links.append({
                "id": str(link_id) if link_id is not None else f"{row[1]}-{row[2]}",
                "source_id": str(row[1]),
                "target_id": str(row[2]),
            })

        logger.info(f"Loaded {len(blocks)} blocks and {len(links)} links")

        return {
            "success": True,
            "blocks": blocks,
            "links": links,
            "levels": [],
            "sublevels": [],
            "total": len(blocks)
        }
    except Exception as e:
        logger.error(f"Error loading all articles: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/layout/articles_page")
async def get_articles_layout_page(
    offset: int = 0,
    limit: int = 2000,
    center_layer: int = 0,
    center_level: int = 0,
) -> Dict[str, Any]:
    """Возвращает часть графа статей, упорядоченную по близости к (center_layer, center_level).

    - Узлы и связи берутся из Neo4j (`Node`, `CITES`).
    - Связи фильтруются, чтобы не допустить циклов (вперёд по (layer, level)).
    - Укладка считается только для выбранной партии.
    """
    try:
        logger.info(
            f"Articles page requested: offset={offset}, limit={limit}, center=({center_layer},{center_level})"
        )

        # Всего узлов (для прогресса)
        total_query = """
        MATCH (n:Node)
        RETURN count(n) as total
        """
        total_res, _ = db.cypher_query(total_query)
        total_nodes = int(total_res[0][0]) if total_res else 0

        # Выбираем ближние к центру (layer, level)
        nodes_query = """
        MATCH (n:Node)
        WITH n,
             abs(n.layer - $center_layer) AS dl,
             abs(n.level - $center_level) AS dv
        RETURN n.uid as id,
               coalesce(n.title, n.name, n.content, toString(n.uid)) as title,
               n.layer as layer,
               n.level as level,
               n.sublevel_id as sublevel_id,
               n.is_pinned as is_pinned,
               n.physical_scale as physical_scale,
               n.x as x,
               n.y as y,
               dl, dv
        ORDER BY (n.layout_status = 'in_longest_path') DESC, dl ASC, dv ASC
        SKIP $offset LIMIT $limit
        """
        blocks_result, _ = db.cypher_query(
            nodes_query,
            {
                "center_layer": center_layer,
                "center_level": center_level,
                "offset": offset,
                "limit": limit,
            },
        )

        if not blocks_result:
            return {
                "success": True,
                "blocks": [],
                "links": [],
                "levels": [],
                "sublevels": [],
                "page": {"offset": offset, "limit": limit, "returned": 0, "total": total_nodes},
            }

        blocks: list[dict] = []
        selected_ids: set[str] = set()
        for row in blocks_result:
            block = {
                "id": str(row[0]),
                "content": str(row[1] or ""),
                "layer": int(row[2] or 0),
                "level": int(row[3] or 0),
                "sublevel_id": int(row[4] or 0),
                "is_pinned": bool(row[5]) if row[5] is not None else False,
                "physical_scale": int(row[6] or 0) if row[6] is not None else 0,
                "x": float(row[7]) if row[7] is not None else None,
                "y": float(row[8]) if row[8] is not None else None,
                "metadata": {},
            }
            blocks.append(block)
            selected_ids.add(block["id"])

        # Связи только внутри выбранного подмножества
        links_query = """
        MATCH (s:Node)-[r:CITES]->(t:Node)
        WHERE s.uid IN $ids AND t.uid IN $ids
        RETURN r.uid as id, s.uid as source_id, t.uid as target_id
        """
        links_result, _ = db.cypher_query(links_query, {"ids": list(selected_ids)})
        links_for_layout: list[dict] = []
        for row in links_result:
            link_id = row[0]
            links_for_layout.append(
                {
                    "id": str(link_id) if link_id is not None else f"{row[1]}-{row[2]}",
                    "source_id": str(row[1]),
                    "target_id": str(row[2]),
                }
            )

        # Дополнительно: связи внутри longest path, но только если оба узла есть в текущей странице
        # Это гарантирует, что LP связи будут видны, когда загружены соответствующие узлы
        lp_links_query = """
        MATCH (s:Node {layout_status: 'in_longest_path'})-[r:CITES]->(t:Node {layout_status: 'in_longest_path'})
        WHERE s.uid IN $ids OR t.uid IN $ids
        RETURN r.uid as id, s.uid as source_id, t.uid as target_id
        """
        lp_links_result, _ = db.cypher_query(lp_links_query, {"ids": list(selected_ids)})
        # Добавляем, избегая дубликатов
        existing = set(f"{l['source_id']}->{l['target_id']}" for l in links_for_layout)
        
        for row in lp_links_result:
            sid = str(row[1]); tid = str(row[2])
            key = f"{sid}->{tid}"
            if key in existing:
                continue
            links_for_layout.append({
                "id": str(row[0]) if row[0] is not None else key,
                "source_id": sid,
                "target_id": tid,
            })
            existing.add(key)

        # Фильтрация циклов (вперёд по (layer, level))
        level_index = {b["id"]: (b.get("layer", 0), b.get("level", 0)) for b in blocks}
        filtered_links = []
        for l in links_for_layout:
            s = l["source_id"]; t = l["target_id"]
            if s in level_index and t in level_index:
                sl, sv = level_index[s]
                tl, tv = level_index[t]
                if (tl > sl) or (tl == sl and tv > sv):
                    filtered_links.append(l)

        # Возвращаем напрямую без вызова gRPC укладки (уровни/подуровни уже в БД)
        return {
            "success": True,
            "blocks": blocks,
            "links": filtered_links,
            "levels": [],
            "sublevels": [],
            "page": {
                "offset": offset,
                "limit": limit,
                "returned": len(blocks),
                "total": total_nodes,
            },
        }
    except Exception as e:
        logger.error(f"Error in paged articles layout: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/layout/neo4j")
async def get_layout_from_neo4j(user_id: str | None = None) -> Dict[str, Any]:
    try:
        logger.info("Starting layout calculation from Neo4j")
        
        # Запрос блоков из Neo4j
        logger.info("Querying blocks from Neo4j")
        blocks_query = """
        MATCH (b:Block)
        RETURN b.uid as id, b.content as content, b.layer as layer, b.level as level, b.is_pinned as is_pinned, b.physical_scale as physical_scale
        """
        blocks_result, _ = db.cypher_query(blocks_query)
        logger.info(f"Found {len(blocks_result)} blocks total")
        
        if not blocks_result:
            logger.warning("No blocks found in Neo4j")
            raise HTTPException(status_code=404, detail="В базе данных нет блоков. Пожалуйста, запустите скрипт заполнения тестовыми данными.")
        
        # Запрос связей из Neo4j (упрощённый без проверки циклов)
        links_query = """
        MATCH (b1:Block)-[r:LINK_TO]->(b2:Block)
        RETURN r.uid as id, b1.uid as source_id, b2.uid as target_id
        """
        links_result, _ = db.cypher_query(links_query)
        
        # Используем настоящие ID из базы данных
        blocks = []
        for row in blocks_result:
            block_data = {
                "id": str(row[0]),
                "content": str(row[1] or ""),
                "layer": int(row[2] or 0),
                "level": int(row[3] or 0),
                "is_pinned": bool(row[4]) if row[4] is not None else False,
                "physical_scale": int(row[5] or 0) if row[5] is not None else 0,
                "metadata": {}
            }
            if block_data["is_pinned"]:
                logger.info(f"Found pinned block in DB: {block_data['id']} - is_pinned: {block_data['is_pinned']}")
            blocks.append(block_data)
        
        # Преобразуем связи
        links_for_layout = []
        for row in links_result:
            link_id = str(row[0]) if row[0] is not None else None
            source_id = str(row[1])
            target_id = str(row[2])
            links_for_layout.append(
                {"id": link_id, "source_id": source_id, "target_id": target_id}
            )

        if not blocks:
            raise HTTPException(status_code=404, detail="В базе данных нет блоков.")
        
        # Получаем укладку
        client = get_layout_client()
        try:
            result = await client.calculate_layout(
                blocks=blocks,
                links=links_for_layout,
                options=LayoutOptions(
                    sublevel_spacing=200,
                    layer_spacing=250,
                    optimize_layout=True
                )
            )

            
            # Сохраняем обновлённые уровни и подуровни обратно в базу данных
            if result.get('success') and result.get('blocks'):
                logger.info("🔥 СОХРАНЯЕМ ОБНОВЛЁННЫЕ УРОВНИ БЛОКОВ В БАЗУ ДАННЫХ...")
                
                # Сначала покажем что пришло из алгоритма
                pinned_in_result = [b for b in result['blocks'] if b.get('is_pinned', False)]
                logger.info(f"🔥 ЗАКРЕПЛЁННЫХ БЛОКОВ В РЕЗУЛЬТАТЕ: {len(pinned_in_result)}")
                for block_info in pinned_in_result:
                    logger.info(f"   🔥 PINNED RESULT: {block_info['id'][:8]}... level={block_info['level']}, sublevel={block_info['sublevel_id']}")
                
                with db.transaction:
                    updates_count = 0
                    for block_info in result['blocks']:
                        try:
                            block = Block.nodes.get(uid=block_info['id'])
                            # Обновляем уровень и подуровень только если они изменились
                            old_level = block.level
                            old_sublevel = block.sublevel_id
                            new_level = block_info['level']
                            new_sublevel = block_info['sublevel_id']
                            
                            if old_level != new_level or old_sublevel != new_sublevel:
                                block.level = new_level
                                block.sublevel_id = new_sublevel
                                block.save()
                                updates_count += 1
                                
                                if block.is_pinned:
                                    logger.info(f"🔥 PINNED UPDATED: {block_info['id'][:8]}... level {old_level}->{new_level}, sublevel {old_sublevel}->{new_sublevel}")
                                else:
                                    logger.info(f"Updated block {block_info['id'][:8]}...: level {old_level}->{new_level}, sublevel {old_sublevel}->{new_sublevel}")
                                
                        except DoesNotExist:
                            logger.warning(f"Block {block_info['id']} not found in database")
                        except Exception as e:
                            logger.error(f"Error updating block {block_info['id']}: {e}")
                            
                logger.info(f"🔥 ✓ ОБНОВЛЕНО {updates_count} БЛОКОВ В БАЗЕ ДАННЫХ")
            
            return result
        except Exception as e:
            logger.error(f"Error in layout calculation: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Ошибка при расчете укладки: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error calculating layout from Neo4j: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при получении данных из Neo4j: {str(e)}")


# === CRUD Эндпоинты для блоков и связей ===

@app.post("/api/blocks", response_model=Dict[str, Any])
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

@app.put("/api/blocks/{block_id}", response_model=Dict[str, Any])
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

@app.post("/api/links", response_model=Dict[str, Any])
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

@app.post("/api/blocks/create_and_link", response_model=Dict[str, Any])
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
        # (Эта логика дублирует /layout/neo4j, но необходима для получения координат)
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

@app.delete("/api/blocks/{block_id}", response_model=Dict[str, Any])
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

@app.delete("/api/links/{link_id}", response_model=Dict[str, Any])
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

@app.post("/api/blocks/{block_id}/pin", response_model=Dict[str, Any])
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

@app.post("/api/blocks/{block_id}/unpin", response_model=Dict[str, Any])
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

@app.post("/api/blocks/{block_id}/pin_with_scale", response_model=Dict[str, Any])
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

@app.post("/api/blocks/{block_id}/move_to_level", response_model=Dict[str, Any])
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

# S3 эндпоинты
@app.get("/api/s3/buckets/{bucket_name}/objects", response_model=S3ListResponse)
async def list_s3_objects(bucket_name: str, prefix: str = ""):
    """Получает список объектов в S3 bucket."""
    try:
        s3_client = get_s3_client()
        objects = await s3_client.list_objects(bucket_name, prefix)
        
        return S3ListResponse(
            objects=objects,
            count=len(objects)
        )
        
    except Exception as e:
        logger.error(f"Error listing S3 objects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/s3/buckets/{bucket_name}/objects/{object_key:path}", response_model=S3FileResponse)
async def get_s3_object(bucket_name: str, object_key: str):
    """Получает содержимое объекта из S3."""
    try:
        s3_client = get_s3_client()
        
        # Проверяем существование объекта
        if not await s3_client.object_exists(bucket_name, object_key):
            raise HTTPException(status_code=404, detail="Object not found")
        
        # Скачиваем содержимое
        content = await s3_client.download_text(bucket_name, object_key)
        
        if content is None:
            raise HTTPException(status_code=500, detail="Failed to download object")
        
        return S3FileResponse(
            content=content,
            content_type="text/markdown" if object_key.endswith('.md') else "text/plain"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting S3 object: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/s3/buckets/{bucket_name}/objects/{object_key:path}", response_model=S3UploadResponse)
async def upload_s3_object(bucket_name: str, object_key: str, content: Optional[str] = None):
    """Загружает объект в S3."""
    try:
        if not content:
            raise HTTPException(status_code=400, detail="Content is required")
        
        s3_client = get_s3_client()
        
        # Определяем MIME тип
        content_type = "text/markdown" if object_key.endswith('.md') else "text/plain"
        
        # Загружаем объект
        success = await s3_client.upload_bytes(
            data=content.encode('utf-8'),
            bucket_name=bucket_name,
            object_key=object_key,
            content_type=content_type,
            metadata={
                "uploaded_by": "knowledge_map_api",
                "encoding": "utf-8"
            }
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to upload object")
        
        return S3UploadResponse(
            success=True,
            object_key=object_key
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading S3 object: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/s3/buckets/{bucket_name}/objects/{object_key:path}")
async def delete_s3_object(bucket_name: str, object_key: str):
    """Удаляет объект из S3."""
    try:
        s3_client = get_s3_client()
        
        # Проверяем существование объекта
        if not await s3_client.object_exists(bucket_name, object_key):
            raise HTTPException(status_code=404, detail="Object not found")
        
        # Удаляем объект
        success = await s3_client.delete_object(bucket_name, object_key)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete object")
        
        return {"success": True, "message": f"Object {object_key} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting S3 object: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/s3/buckets/{bucket_name}/objects/{object_key:path}/url")
async def get_s3_object_url(bucket_name: str, object_key: str, expires_in: int = 3600):
    """Генерирует временный URL для доступа к объекту."""
    try:
        s3_client = get_s3_client()
        
        # Проверяем существование объекта
        if not await s3_client.object_exists(bucket_name, object_key):
            raise HTTPException(status_code=404, detail="Object not found")
        
        # Генерируем URL
        url = await s3_client.get_object_url(bucket_name, object_key, expires_in)
        
        if not url:
            raise HTTPException(status_code=500, detail="Failed to generate URL")
        
        return {"url": url, "expires_in": expires_in}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating S3 object URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Специальный эндпоинт для загрузки markdown файлов для NLP компонента
@app.get("/api/nlp/markdown/{filename}", response_model=S3FileResponse)
async def get_nlp_markdown(filename: str):
    """Получает markdown файл из bucket 'markdown' для NLP компонента."""
    try:
        s3_client = get_s3_client()
        
        # Проверяем существование файла
        if not await s3_client.object_exists("markdown", filename):
            raise HTTPException(status_code=404, detail=f"Markdown file '{filename}' not found")
        
        # Скачиваем содержимое
        content = await s3_client.download_text("markdown", filename)
        
        if content is None:
            raise HTTPException(status_code=500, detail="Failed to download markdown file")
        
        return S3FileResponse(
            content=content,
            content_type="text/markdown"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting NLP markdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Подключаем GraphQL
graphql_app = GraphQLRouter(schema)
app.include_router(graphql_app, prefix="/graphql")



# ===== Auth endpoints =====
@app.post("/api/auth/register", response_model=AuthResponse)
async def register_user(request: UserRegisterRequest):
    """Регистрирует нового пользователя"""
    try:
        result = auth_client.register(
            login=request.login,
            password=request.password,
            nickname=request.nickname,
            captcha=request.captcha
        )
        
        if result["success"]:
            return AuthResponse(
                success=True,
                message=result["message"],
                user=result["user"],
                recovery_keys=result["recovery_keys"]
            )
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/login", response_model=AuthResponse)
async def login_user(request: UserLoginRequest):
    """Аутентифицирует пользователя"""
    try:
        result = auth_client.login(
            login=request.login,
            password=request.password,
            captcha=request.captcha,
            device_info=request.device_info or "",
            ip_address=request.ip_address or ""
        )
        
        if result["success"]:
            return AuthResponse(
                success=True,
                message=result["message"],
                token=result["token"],
                user=result["user"],
                requires_2fa=result["requires_2fa"]
            )
        else:
            raise HTTPException(status_code=401, detail=result["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/logout")
async def logout_user(token: str, logout_all: bool = False):
    """Выходит из системы"""
    try:
        result = auth_client.logout(token, logout_all)
        
        if result["success"]:
            return {"success": True, "message": result["message"]}
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/verify", response_model=TokenVerifyResponse)
async def verify_user_token(token: str):
    """Проверяет токен пользователя"""
    try:
        result = auth_client.verify_token(token)
        
        if result["valid"]:
            return TokenVerifyResponse(
                valid=True,
                user=result["user"],
                message=result["message"]
            )
        else:
            raise HTTPException(status_code=401, detail=result["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/recovery", response_model=AuthResponse)
async def recovery_request(request: UserRecoveryRequest):
    """Проверяет ключ восстановления"""
    try:
        result = auth_client.recovery_request(
            recovery_key=request.recovery_key,
            captcha=request.captcha
        )
        
        if result["success"]:
            return AuthResponse(
                success=True,
                message=result["message"],
                user={"uid": result["user_id"]}
            )
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/reset-password")
async def reset_password(request: UserPasswordResetRequest):
    """Сбрасывает пароль пользователя"""
    try:
        result = auth_client.reset_password(
            user_id=request.user_id,
            new_password=request.new_password
        )
        
        if result["success"]:
            return {"success": True, "message": result["message"]}
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/2fa/setup", response_model=AuthResponse)
async def setup_2fa(request: User2FASetupRequest):
    """Настраивает 2FA для пользователя"""
    try:
        result = auth_client.setup_2fa(request.user_id)
        
        if result["success"]:
            return AuthResponse(
                success=True,
                message=result["message"],
                user={"uid": request.user_id},
                recovery_keys=result["backup_codes"]
            )
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/2fa/verify")
async def verify_2fa(request: User2FAVerifyRequest):
    """Проверяет код 2FA"""
    try:
        result = auth_client.verify_2fa(
            user_id=request.user_id,
            code=request.code
        )
        
        if result["success"]:
            return {"success": True, "message": result["message"]}
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/auth/captcha")
async def get_captcha():
    """Генерирует капчу (заглушка)"""
    # В реальной реализации здесь будет генерация капчи
    return {
        "captcha_id": "test_captcha_123",
        "captcha_image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    }
# ===== Auth endpoints END =====


logger.info("Application startup complete.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)