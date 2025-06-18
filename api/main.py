from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from strawberry.fastapi import GraphQLRouter
from schema import schema
from models import User, Block, Tag, LinkMetadata
from layout_client import get_layout_client, LayoutOptions, LayoutConfig
from config import settings
from typing import List, Dict, Optional
from pydantic import BaseModel
import logging
from neomodel import config as neomodel_config, db
import uuid

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
    id: str
    content: str = ""
    metadata: Dict[str, str] = {}


class LinkInput(BaseModel):
    id: str
    source_id: str
    target_id: str
    metadata: Dict[str, str] = {}


class LayoutRequest(BaseModel):
    blocks: List[BlockInput]
    links: List[LinkInput]
    sublevel_spacing: Optional[int] = 200
    layer_spacing: Optional[int] = 250
    optimize_layout: bool = True


# Эндпоинты для проверки здоровья
@app.get("/health")
async def health_check():
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
async def calculate_layout(request: LayoutRequest):
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
async def get_layout_from_neo4j(user_id: str | None = None):
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
            logger.info(f"Sample link {i}: id={row[0]}, source_id={row[1]}, target_id={row[2]}")
        
        # Преобразуем результаты в формат для сервиса укладки
        logger.info("Converting results to layout service format")
        logger.debug(f"Raw blocks data: {blocks_result}")
        
        blocks = []
        block_ids = {}  # Словарь для хранения соответствия старых и новых ID
        for row in blocks_result:
            # Генерируем UUID если ID отсутствует
            old_id = str(row[0]) if row[0] is not None else None
            new_id = str(uuid.uuid4())
            block_ids[old_id] = new_id if old_id else new_id
            
            block = {
                "id": new_id,
                "content": str(row[1] or ""),
                "layer": int(row[2] or 0),
                "level": int(row[3] or 0),
                "metadata": {}
            }
            blocks.append(block)
            logger.debug(f"Converted block: {block}")
        
        logger.info(f"Converted {len(blocks)} blocks")
        
        links = []
        for row in links_result:
            # Генерируем UUID если ID отсутствует
            link_id = str(row[0]) if row[0] is not None else str(uuid.uuid4())
            source_id = str(row[1]) if row[1] is not None else None
            target_id = str(row[2]) if row[2] is not None else None
            
            # Используем новые ID блоков
            if source_id in block_ids and target_id in block_ids:
                link = {
                    "id": link_id,
                    "source_id": block_ids[source_id],
                    "target_id": block_ids[target_id],
                    "metadata": {}
                }
                links.append(link)
                logger.debug(f"Converted link: {link}")
            else:
                logger.warning(f"Skipping link {link_id}: source_id={source_id} or target_id={target_id} not found in blocks")
        
        logger.info(f"Converted {len(links)} links")
        
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
                links=links,
                options=LayoutOptions(
                    sublevel_spacing=200,
                    layer_spacing=250,
                    optimize_layout=True
                )
            )
            logger.info("Layout calculation completed")
            return result
        except Exception as e:
            logger.error(f"Error in layout calculation: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Ошибка при расчете укладки: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error calculating layout from Neo4j: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при получении данных из Neo4j: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)