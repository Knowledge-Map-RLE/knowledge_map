"""
Высокопроизводительный клиент для работы с Neo4j в распределённом воркере.
Поддерживает потоковую обработку больших графов и connection pooling.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, List, Optional, Tuple, Any
import time

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from neo4j.exceptions import Neo4jError, TransientError
import structlog

from .config import get_neo4j_config, settings
from .utils.circuit_breaker import CircuitBreaker
from .utils.metrics import metrics_collector

logger = structlog.get_logger(__name__)


class Neo4jClient:
    """
    Асинхронный клиент для Neo4j с поддержкой:
    - Connection pooling
    - Circuit breaker
    - Retry механизмы
    - Потоковая обработка
    - Метрики производительности
    """

    def __init__(self):
        self.driver: Optional[AsyncDriver] = None
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=settings.circuit_breaker_failure_threshold,
            recovery_timeout=settings.circuit_breaker_recovery_timeout,
        )
        self._connection_pool_size = settings.neo4j_pool_size
        self.last_progress_log = 0
        self.progress_log_interval = 60  # Логировать не чаще раза в минуту

    async def connect(self) -> None:
        """Устанавливает соединение с Neo4j"""
        if self.driver:
            return

        config = get_neo4j_config()
        try:
            self.driver = AsyncGraphDatabase.driver(**config)
            await self.driver.verify_connectivity()
            logger.info("Connected to Neo4j", uri=config["uri"])
        except Exception as e:
            logger.error("Failed to connect to Neo4j", error=str(e))
            raise

    async def close(self) -> None:
        """Закрывает соединение с Neo4j"""
        if self.driver:
            await self.driver.close()
            self.driver = None
            logger.info("Disconnected from Neo4j")
    
    async def reconnect(self) -> None:
        """Переподключается к Neo4j"""
        logger.info("Reconnecting to Neo4j...")
        await self.close()
        await asyncio.sleep(1)  # Небольшая пауза перед переподключением
        await self.connect()
        logger.info("Reconnected to Neo4j")

    @asynccontextmanager
    async def session(self, **kwargs) -> AsyncGenerator[AsyncSession, None]:
        """Контекстный менеджер для сессий Neo4j"""
        if not self.driver:
            await self.connect()

        session = self.driver.session(**kwargs)
        try:
            yield session
        finally:
            await session.close()

    async def execute_query_with_retry(
        self, query: str, parameters: Optional[Dict] = None, max_retries: int = 3
    ) -> List[Dict]:
        """
        Выполняет запрос с retry механизмом и circuit breaker
        """
        parameters = parameters or {}
        
        for attempt in range(max_retries + 1):
            try:
                async with self.circuit_breaker:
                    start_time = time.time()
                    
                    # Проверяем соединение перед выполнением запроса
                    if not self.driver:
                        await self.connect()
                    
                    async with self.session() as session:
                        result = await session.run(query, parameters)
                        records = await result.data()
                        
                    execution_time = time.time() - start_time
                    metrics_collector.record_neo4j_query("query", execution_time)
                    
                    logger.debug(
                        "Query executed successfully",
                        query=query[:100] + "..." if len(query) > 100 else query,
                        execution_time=execution_time,
                        records_count=len(records),
                    )
                    
                    return records

            except TransientError as e:
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(
                        "Transient error, retrying",
                        error=str(e),
                        attempt=attempt + 1,
                        wait_time=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    # Переподключаемся при transient ошибках
                    await self.reconnect()
                    continue
                raise
            except Exception as e:
                # Проверяем, является ли ошибка связанной с соединением
                if "connection" in str(e).lower() or "defunct" in str(e).lower():
                    if attempt < max_retries:
                        logger.warning(
                            "Connection error, reconnecting and retrying",
                            error=str(e),
                            attempt=attempt + 1,
                        )
                        await asyncio.sleep(2 ** attempt)
                        await self.reconnect()
                        continue
                # Ошибка записывается в логи
                logger.error("Query execution failed", error=str(e), query=query[:100])
                raise

        raise Exception(f"Query failed after {max_retries} retries")

    async def stream_nodes_chunked(
        self, 
        node_labels: List[str], 
        chunk_size: int = None,
        filters: Optional[Dict] = None
    ) -> AsyncGenerator[List[Dict], None]:
        """
        Потоковая загрузка узлов по чанкам для экономии памяти
        """
        chunk_size = chunk_size or settings.chunk_size
        filters = filters or {}
        
        # Строим WHERE условие из фильтров
        where_conditions = []
        for key, value in filters.items():
            if isinstance(value, str):
                where_conditions.append(f"n.{key} = '{value}'")
            else:
                where_conditions.append(f"n.{key} = {value}")
        
        where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""
        
        # Если метки не заданы, по умолчанию работаем со статьями
        labels_str = ":".join(node_labels) if node_labels else "Article"
        
        # Сначала получаем общее количество узлов
        count_query = f"""
        MATCH (n{':' + labels_str if labels_str else ''})
        {where_clause}
        RETURN count(n) as total_count
        """
        
        count_result = await self.execute_query_with_retry(count_query)
        total_count = count_result[0]["total_count"]
        
        logger.info(
            "Starting chunked node streaming",
            total_nodes=total_count,
            chunk_size=chunk_size,
            estimated_chunks=total_count // chunk_size + 1,
        )

        # Загружаем узлы по чанкам с оптимизацией
        offset = 0
        chunk_number = 0
        
        while offset < total_count:
            # Используем более эффективный запрос с параметрами
            chunk_query = f"""
            MATCH (n{':' + labels_str if labels_str else ''})
            {where_clause}
            RETURN n.uid as id, n.content as content, 
                   COALESCE(n.layer, 0) as layer,
                   COALESCE(n.level, 0) as level, 
                   COALESCE(n.is_pinned, false) as is_pinned, 
                   COALESCE(n.physical_scale, 0) as physical_scale
            ORDER BY n.uid
            SKIP $offset
            LIMIT $limit
            """
            
            chunk_params = {"offset": offset, "limit": chunk_size}
            
            start_time = time.time()
            chunk_data = await self.execute_query_with_retry(chunk_query, chunk_params)
            load_time = time.time() - start_time
            
            if not chunk_data:
                break
                
            logger.debug(
                "Loaded node chunk",
                chunk_number=chunk_number,
                nodes_in_chunk=len(chunk_data),
                load_time=load_time,
                offset=offset,
            )
            
            yield chunk_data
            
            offset += chunk_size
            chunk_number += 1

    async def stream_edges_chunked(
        self, 
        chunk_size: int = None,
        node_ids: Optional[List[str]] = None
    ) -> AsyncGenerator[List[Dict], None]:
        """
        Потоковая загрузка рёбер по чанкам
        """
        chunk_size = chunk_size or settings.chunk_size
        
        # Если указаны конкретные узлы, фильтруем рёбра
        if node_ids:
            node_ids_str = "', '".join(node_ids)
            where_clause = f"WHERE source.uid IN ['{node_ids_str}'] AND target.uid IN ['{node_ids_str}']"
        else:
            where_clause = ""
        
        # Получаем общее количество рёбер
        count_query = f"""
        MATCH (source:Article)-[r:CITES]->(target:Article)
        {where_clause}
        RETURN count(r) as total_count
        """
        
        count_result = await self.execute_query_with_retry(count_query)
        total_count = count_result[0]["total_count"]
        
        logger.info(
            "Starting chunked edge streaming",
            total_edges=total_count,
            chunk_size=chunk_size,
            estimated_chunks=total_count // chunk_size + 1,
        )

        # Загружаем рёбра по чанкам
        offset = 0
        chunk_number = 0
        
        while offset < total_count:
            chunk_query = f"""
            MATCH (source:Article)-[r:CITES]->(target:Article)
            {where_clause}
            RETURN r.uid as id, source.uid as source_id, target.uid as target_id
            ORDER BY r.uid
            SKIP $offset
            LIMIT $limit
            """
            
            chunk_params = {"offset": offset, "limit": chunk_size}
            
            start_time = time.time()
            chunk_data = await self.execute_query_with_retry(chunk_query, chunk_params)
            load_time = time.time() - start_time
            
            if not chunk_data:
                break
                
            logger.debug(
                "Loaded edge chunk",
                chunk_number=chunk_number,
                edges_in_chunk=len(chunk_data),
                load_time=load_time,
                offset=offset,
            )
            
            yield chunk_data
            
            offset += chunk_size
            chunk_number += 1

    async def get_graph_statistics(self) -> Dict[str, Any]:
        """
        Получает статистику графа для планирования обработки
        """
        logger.info("Starting graph statistics collection...")
        
        # Упрощённый запрос для быстрого получения статистики
        stats_query = """
        MATCH (n:Article) 
        RETURN count(n) as node_count
        LIMIT 1
        """
        
        try:
            logger.info("Executing node count query...")
            result = await self.execute_query_with_retry(stats_query)
            node_count = result[0]["node_count"] if result else 0
            logger.info(f"Found {node_count} nodes in graph")
            
            # Быстрый запрос для рёбер - используем прямой COUNT
            logger.info("Executing edge count query...")
            
            try:
                # Прямой COUNT работает быстро (проверено)
                edge_query = """
                MATCH ()-[r:CITES]->() 
                RETURN count(r) as edge_count
                """
                edge_result = await self.execute_query_with_retry(edge_query)
                edge_count = edge_result[0]["edge_count"] if edge_result else 0
                logger.info(f"Found {edge_count} edges in graph")
                        
            except Exception as e:
                logger.warning(f"Edge count query failed, using estimate: {str(e)}")
                # Используем приблизительную оценку
                edge_count = node_count * 2  # Примерная оценка
                logger.info(f"Using fallback edge count estimate: {edge_count}")
            
            # Быстрый запрос для закреплённых узлов (с таймаутом)
            logger.info("Executing pinned nodes count query...")
            pinned_count = 0
            
            try:
                # Сначала проверяем, есть ли вообще поле is_pinned
                check_query = """
                MATCH (n:Article) 
                WHERE n.is_pinned IS NOT NULL 
                RETURN count(n) as count 
                LIMIT 1
                """
                
                check_result = await self.execute_query_with_retry(check_query)
                if check_result and check_result[0]["count"] > 0:
                    # Если поле существует, считаем закреплённые узлы
                    pinned_query = """
                    MATCH (n:Article {is_pinned: true}) 
                    RETURN count(n) as pinned_count 
                    LIMIT 1
                    """
                    pinned_result = await self.execute_query_with_retry(pinned_query)
                    pinned_count = pinned_result[0]["pinned_count"] if pinned_result else 0
                else:
                    # Если поля нет, считаем что закреплённых узлов нет
                    pinned_count = 0
                    
                logger.info(f"Found {pinned_count} pinned nodes")
                
            except Exception as e:
                logger.warning(f"Pinned nodes count failed, using default: {str(e)}")
                pinned_count = 0
            
            return {
                "node_count": node_count,
                "edge_count": edge_count,
                "pinned_count": pinned_count,
                "all_labels": ["Article"],  # Упрощённо
                "component_count": 1,  # Упрощённо
                "density": edge_count / (node_count * (node_count - 1)) if node_count > 1 else 0,
                "avg_degree": 2 * edge_count / node_count if node_count > 0 else 0,
            }
            
        except Exception as e:
            logger.error(f"Failed to get graph statistics: {str(e)}")
            # Возвращаем дефолтные значения для продолжения работы
            return {
                "node_count": 1000,  # Дефолтное значение для тестирования
                "edge_count": 2000,
                "pinned_count": 0,
                "all_labels": ["Article"],
                "component_count": 1,
                "density": 0.002,
                "avg_degree": 4.0,
            }

    async def batch_update_positions(
        self, 
        node_positions: List[Dict[str, Any]], 
        batch_size: int = None
    ) -> None:
        """
        Батчевое обновление позиций узлов в Neo4j
        """
        batch_size = batch_size or settings.batch_size
        
        logger.info(
            "Starting batch position update",
            total_nodes=len(node_positions),
            batch_size=batch_size,
        )
        
        for i in range(0, len(node_positions), batch_size):
            batch = node_positions[i:i + batch_size]
            
            # Подготавливаем параметры для батча
            batch_params = []
            for pos in batch:
                batch_params.append({
                    "id": pos["id"],
                    "level": pos.get("level", 0),
                    "sublevel_id": pos.get("sublevel_id", 0),
                    "layer": pos.get("layer", 0),
                })
            
            update_query = """
            UNWIND $batch as row
            MATCH (n:Article {uid: row.id})
            SET n.level = row.level,
                n.sublevel_id = row.sublevel_id,
                n.layer = row.layer
            """
            
            start_time = time.time()
            await self.execute_query_with_retry(
                update_query, 
                {"batch": batch_params}
            )
            update_time = time.time() - start_time
            
            logger.debug(
                "Updated batch",
                batch_number=i // batch_size + 1,
                nodes_updated=len(batch),
                update_time=update_time,
            )

    async def get_subgraph_by_component(
        self, 
        component_id: int,
        chunk_size: int = None
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Получает подграф для конкретной компоненты связности
        """
        # Это упрощённая версия - в реальности нужно использовать GDS
        # для выделения компонент связности
        
        # Пока возвращаем весь граф как одну компоненту
        nodes = []
        edges = []
        
        async for node_chunk in self.stream_nodes_chunked(["Article"], chunk_size):
            nodes.extend(node_chunk)
            
        node_ids = [node["id"] for node in nodes]
        
        async for edge_chunk in self.stream_edges_chunked(chunk_size, node_ids):
            edges.extend(edge_chunk)
            
        return nodes, edges


# Глобальный экземпляр клиента
neo4j_client = Neo4jClient()
