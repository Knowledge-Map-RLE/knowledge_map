from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from strawberry.fastapi import GraphQLRouter
from schema import schema
from models import User, Block, Tag, LinkMetadata
from layout_client import get_layout_client, LayoutOptions, LayoutConfig
from config import settings
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
import logging
from neomodel import config as neomodel_config, db, UniqueIdProperty
import uuid
import json

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка подключения к Neo4j
neomodel_config.DATABASE_URL = settings.get_database_url()
logger.info(f"Neo4j connection configured: {settings.neo4j_uri}")

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

@app.get("/layout/neo4j")
async def get_layout_from_neo4j(user_id: str | None = None) -> Dict[str, Any]:
    try:
        logger.info("Starting layout calculation from Neo4j")
        
        # Запрос блоков из Neo4j
        logger.info("Querying blocks from Neo4j")
        blocks_query = """
        MATCH (b:Block)
        RETURN b.uid as id, b.content as content, b.layer as layer, b.level as level
        """
        blocks_result, _ = db.cypher_query(blocks_query)
        logger.info(f"Found {len(blocks_result)} blocks total")
        
        # Выводим первые 5 блоков для отладки
        for i, row in enumerate(blocks_result[:5]):
            logger.info(f"Sample block {i}: id={row[0]}, content={row[1]}, layer={row[2]}, level={row[3]}")
        
        if not blocks_result:
            logger.warning("No blocks found in Neo4j")
            raise HTTPException(status_code=404, detail="В базе данных нет блоков. Пожалуйста, запустите скрипт заполнения тестовыми данными.")
        
        # Запрос связей из Neo4j с проверкой на циклы
        logger.info("Querying links from Neo4j")
        links_query = """
        MATCH path = (b1:Block)-[r:LINK_TO*]->(b2:Block)
        WHERE b1 = b2  // Ищем циклы
        RETURN COUNT(path) as cycles
        """
        cycles_result, _ = db.cypher_query(links_query)
        cycles_count = cycles_result[0][0]
        logger.info(f"Found {cycles_count} cycles in the graph")

        # Запрос связей, исключая те, что создают циклы
        links_query = """
        MATCH (b1:Block)-[r:LINK_TO]->(b2:Block)
        WHERE NOT EXISTS {
            MATCH (b2)-[:LINK_TO*]->(b1)  // Проверяем, что нет обратного пути
        }
        RETURN r.uid as id, b1.uid as source_id, b2.uid as target_id
        """
        links_result, _ = db.cypher_query(links_query)
        logger.info(f"Found {len(links_result)} acyclic links")

        # Выводим первые 5 связей для отладки
        for i, row in enumerate(links_result[:5]):
            logger.info(f"Sample link {i}: id={row[0]}, source={row[1]}, target={row[2]}")
        
        # Преобразуем результаты в формат для сервиса укладки
        logger.info("Converting results to layout service format")
        
        # Используем настоящие ID из базы данных
        blocks = [
            {
                "id": str(row[0]),
                "content": str(row[1] or ""),
                "layer": int(row[2] or 0),
                "level": int(row[3] or 0),
                "metadata": {}
            }
            for row in blocks_result
        ]
        
        # Преобразуем связи
        links_for_layout = []
        for row in links_result:
            link_id = str(row[0]) if row[0] is not None else None
            source_id = str(row[1])
            target_id = str(row[2])
            logger.info(f"Processing link: id={link_id}, source={source_id}, target={target_id}")
            links_for_layout.append(
                {"id": link_id, "source_id": source_id, "target_id": target_id}
            )
        
        logger.info(f"Converted {len(blocks)} blocks and {len(links_for_layout)} links using real UIDs.")

        if not blocks:
            logger.warning("No blocks after conversion")
            raise HTTPException(status_code=404, detail="В базе данных нет блоков. Пожалуйста, запустите скрипт заполнения тестовыми данными.")
        
        # Получаем укладку
        logger.info("Getting layout client")
        client = get_layout_client()
        logger.info("Calculating layout")
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
            logger.info("Layout calculation completed")
            # Добавляем логирование результата
            logger.info("Layout result structure:")
            logger.info(f"Number of blocks: {len(result.get('blocks', []))}")
            logger.info(f"Number of links: {len(result.get('links', []))}")
            logger.info(f"Number of levels: {len(result.get('levels', []))}")
            logger.info(f"Number of sublevels: {len(result.get('sublevels', []))}")
            if result.get('levels'):
                logger.info("Sample level data:")
                logger.info(str(result['levels'][0]))
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
        }
        return {"success": True, "block": response_block}
    except Exception as e:
        logger.error(f"Error creating block: {e}")
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

    except Block.DoesNotExist:
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
        blocks_query = "MATCH (b:Block) RETURN b.uid as id, b.content as content, b.layer as layer, b.level as level"
        blocks_result, _ = db.cypher_query(blocks_query)
        
        links_query = "MATCH (b1:Block)-[r:LINK_TO]->(b2:Block) RETURN r.uid as id, b1.uid as source_id, b2.uid as target_id"
        links_result, _ = db.cypher_query(links_query)

        blocks_for_layout = [{"id": str(r[0]), "content": str(r[1] or ""), "layer": int(r[2] or 0), "level": int(r[3] or 0), "metadata": {}} for r in blocks_result]
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
    except Block.DoesNotExist:
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
        
    except Block.DoesNotExist:
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

# Подключаем GraphQL
graphql_app = GraphQLRouter(schema)
app.include_router(graphql_app, prefix="/graphql")

logger.info("Application startup complete.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)