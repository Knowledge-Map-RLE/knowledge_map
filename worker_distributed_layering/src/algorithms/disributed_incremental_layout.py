"""
Распределённый инкрементальный алгоритм укладки DAG графа.
Основан на longest path с инкрементальным добавлением вершин без полных обходов.

Ключевые особенности:
1. Один полный обход для поиска longest path
2. Инкрементальное добавление вершин в ближайшие свободные места
3. Асинхронная синхронизация между итерациями
4. Полная отказоустойчивость с Circuit Breaker
5. Интеграция с Neo4j для обработки на уровне БД
"""

import asyncio
import time
from typing import Dict, List, Tuple, Set, Any, Optional
from collections import defaultdict, deque
import logging
from dataclasses import dataclass
from enum import Enum

from ..config import settings
from ..neo4j_client import neo4j_client
from ..utils.memory_manager import memory_manager
from ..utils.metrics import metrics_collector
from ..utils.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class VertexStatus(Enum):
    """Статус вершины в алгоритме"""
    UNPROCESSED = "unprocessed"
    IN_LONGEST_PATH = "in_longest_path"
    PLACED = "placed"
    PINNED = "pinned"


@dataclass
class VertexPosition:
    """Позиция вершины в укладке"""
    vertex_id: str
    layer: int
    level: int
    sublevel_id: int
    x: float
    y: float
    status: VertexStatus
    is_pinned: bool = False


class DistributedIncrementalLayout:
    """
    Распределённый инкрементальный алгоритм укладки на основе longest path
    """
    
    def __init__(self):
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=settings.circuit_breaker_failure_threshold,
            recovery_timeout=settings.circuit_breaker_recovery_timeout,
        )
        self.memory_manager = memory_manager
        self.progress_log_interval = 60
        self.last_progress_log = 0
        
        # Кэш для оптимизации
        self.longest_path_cache = {}
        self.vertex_positions_cache = {}
        self.free_positions_cache = {}
        
        # Метрики
        self.iteration_count = 0
        self.vertices_processed = 0
        self.db_operations = 0

    async def calculate_incremental_layout(
        self,
        node_labels: Optional[List[str]] = None,
        filters: Optional[Dict] = None,
        options: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Основной метод инкрементальной укладки
        """
        start_time = time.time()
        options = options or {}
        
        logger.info("Starting distributed incremental layout calculation")
        
        try:
            # 1. Инициализация и получение статистики
            stats = await self._initialize_layout(node_labels or [], filters)
            
            # 2. Поиск longest path (единственный полный обход)
            longest_path = await self._find_longest_path_neo4j()
            
            # 3. Размещение longest path
            await self._place_longest_path(longest_path)
            
            # 4. Инкрементальное размещение остальных вершин
            result = await self._incremental_placement_iterations()
            
            # 5. Финальная обработка закреплённых блоков
            await self._process_pinned_blocks()
            
            processing_time = time.time() - start_time
            result["statistics"]["processing_time_seconds"] = processing_time
            
            # Записываем метрики
            metrics_collector.record_task_execution(
                task_type="incremental_layout",
                duration=processing_time,
                success=result.get("success", False)
            )
            
            logger.info(
                f"Incremental layout completed in {processing_time:.2f}s, "
                f"iterations: {self.iteration_count}, "
                f"vertices: {self.vertices_processed}, "
                f"db_ops: {self.db_operations}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Incremental layout failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "statistics": {"processing_time_seconds": time.time() - start_time},
            }

    async def _initialize_layout(
        self, 
        node_labels: List[str], 
        filters: Optional[Dict]
    ) -> Dict[str, Any]:
        """
        Инициализация укладки и получение статистики
        """
        logger.info("Initializing incremental layout")
        
        async with self.circuit_breaker:
            # Получаем статистику графа
            stats = await neo4j_client.get_graph_statistics()
            
            # Инициализируем таблицы в Neo4j для укладки
            await self._init_layout_tables()
            
            # Очищаем кэши
            self.longest_path_cache.clear()
            self.vertex_positions_cache.clear()
            self.free_positions_cache.clear()
            
            # Сбрасываем метрики
            self.iteration_count = 0
            self.vertices_processed = 0
            self.db_operations = 0
            
        return stats

    async def _init_layout_tables(self):
        """
        Инициализация таблиц в Neo4j для хранения состояния укладки
        """
        init_queries = [
            # Создаём индексы для оптимизации
            """
            CREATE INDEX IF NOT EXISTS FOR (n:Node) ON (n.layout_status, n.layer, n.level)
            """,
            
            # Создаём таблицу для отслеживания свободных позиций
            """
            CREATE CONSTRAINT IF NOT EXISTS ON (p:Position) ASSERT p.id IS UNIQUE
            """,
            
            # Инициализируем статусы всех узлов
            """
            MATCH (n:Node)
            SET n.layout_status = 'unprocessed',
                n.layer = -1,
                n.level = -1,
                n.sublevel_id = -1,
                n.x = 0.0,
                n.y = 0.0
            """,
            
            # Создаём таблицу для longest path
            """
            CREATE CONSTRAINT IF NOT EXISTS ON (lp:LongestPath) ASSERT lp.id IS UNIQUE
            """
        ]
        
        for query in init_queries:
            async with self.circuit_breaker:
                await neo4j_client.execute_query_with_retry(query)
                self.db_operations += 1

    async def _find_longest_path_neo4j(self) -> List[str]:
        """
        Поиск longest path в Neo4j (единственный полный обход графа)
        Использует алгоритм динамического программирования в Cypher
        """
        logger.info("Finding longest path in Neo4j")
        
        # Проверяем кэш
        if self.longest_path_cache:
            logger.info("Using cached longest path")
            return self.longest_path_cache
        
        longest_path_query = """
        // Алгоритм поиска longest path в DAG
        MATCH (n:Node)
        WHERE NOT EXISTS((:Node)-[:CITES]->(n))  // Находим источники (узлы без входящих рёбер)
        
        CALL {
            WITH n
            MATCH path = (n)-[:CITES*]->(target)
            WHERE NOT EXISTS((target)-[:CITES]->())  // До стоков (узлов без исходящих рёбер)
            RETURN n, path, length(path) as path_length
            ORDER BY path_length DESC
            LIMIT 1
        }
        
        WITH n, path, path_length
        UNWIND nodes(path) as node_in_path
        RETURN DISTINCT node_in_path.uid as vertex_id
        ORDER BY path_length DESC
        """
        
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(longest_path_query)
            self.db_operations += 1
            
            if isinstance(result, list):
                longest_path = [row["vertex_id"] for row in result]
            else:
                longest_path = []
            
            # Сохраняем в кэш
            self.longest_path_cache = longest_path
            
            # Сохраняем в Neo4j для последующего использования
            await self._save_longest_path_to_neo4j(longest_path)
            
        logger.info(f"Longest path found: {len(longest_path)} vertices")
        return longest_path

    async def _save_longest_path_to_neo4j(self, longest_path: List[str]):
        """
        Сохраняет longest path в Neo4j для последующего использования
        """
        # Очищаем предыдущий longest path
        clear_query = "MATCH (lp:LongestPath) DELETE lp"
        
        # Сохраняем новый longest path
        save_query = """
        UNWIND $path AS path_item
        MATCH (n:Node {uid: path_item.vertex_id})
        CREATE (lp:LongestPath {
            id: path_item.vertex_id,
            position: path_item.position,
            layer: path_item.layer
        })
        """
        
        path_data = [
            {
                "vertex_id": vertex_id,
                "position": i,
                "layer": i
            }
            for i, vertex_id in enumerate(longest_path)
        ]
        
        async with self.circuit_breaker:
            await neo4j_client.execute_query_with_retry(clear_query)
            await neo4j_client.execute_query_with_retry(save_query, {"path": path_data})
            self.db_operations += 2

    async def _place_longest_path(self, longest_path: List[str]):
        """
        Размещает longest path в укладке
        """
        logger.info("Placing longest path")
        
        placement_query = """
        MATCH (lp:LongestPath)
        MATCH (n:Node {uid: lp.id})
        SET n.layout_status = 'in_longest_path',
            n.layer = lp.layer,
            n.level = 0,
            n.sublevel_id = 0,
            n.x = lp.layer * 250.0,
            n.y = 0.0
        """
        
        async with self.circuit_breaker:
            await neo4j_client.execute_query_with_retry(placement_query)
            self.db_operations += 1
            
        # Обновляем кэш позиций
        for i, vertex_id in enumerate(longest_path):
            self.vertex_positions_cache[vertex_id] = VertexPosition(
                vertex_id=vertex_id,
                layer=i,
                level=0,
                sublevel_id=0,
                x=i * 250.0,
                y=0.0,
                status=VertexStatus.IN_LONGEST_PATH
            )

    async def _incremental_placement_iterations(self) -> Dict[str, Any]:
        """
        Инкрементальное размещение остальных вершин без полных обходов
        """
        logger.info("Starting incremental placement iterations")
        
        max_iterations = settings.max_iterations
        convergence_threshold = settings.convergence_threshold
        
        for iteration in range(max_iterations):
            self.iteration_count += 1
            
            # Логируем прогресс
            current_time = time.time()
            if current_time - self.last_progress_log >= self.progress_log_interval:
                logger.info(f"Iteration {iteration + 1}/{max_iterations}")
                self.last_progress_log = current_time
            
            # 1. Находим неразмещённые вершины
            unplaced_vertices = await self._get_unplaced_vertices()
            
            if not unplaced_vertices:
                logger.info("All vertices placed, stopping iterations")
                break
            
            # 2. Находим ближайшие свободные позиции для каждой вершины
            placements = await self._find_nearest_free_positions(unplaced_vertices)
            
            # 3. Размещаем вершины асинхронно
            placed_count = await self._place_vertices_incremental(placements)
            
            self.vertices_processed += placed_count
            
            # 4. Проверяем сходимость
            if placed_count < convergence_threshold:
                logger.info(f"Convergence reached at iteration {iteration + 1}")
                break
            
            # 5. Обновляем кэш свободных позиций
            await self._update_free_positions_cache()
        
        return await self._build_final_result()

    async def _get_unplaced_vertices(self) -> List[str]:
        """
        Получает список неразмещённых вершин
        """
        query = """
        MATCH (n:Node)
        WHERE n.layout_status = 'unprocessed'
        RETURN n.uid as vertex_id
        LIMIT 1000  // Обрабатываем батчами для производительности
        """
        
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(query)
            self.db_operations += 1
            
        return [row["vertex_id"] for row in result]

    async def _find_nearest_free_positions(
        self, 
        unplaced_vertices: List[str]
    ) -> List[Tuple[str, int, int, int]]:
        """
        Находит ближайшие свободные позиции для вершин
        Возвращает список (vertex_id, layer, level, sublevel_id)
        """
        placements = []
        
        for vertex_id in unplaced_vertices:
            # Получаем соседей вершины
            neighbors = await self._get_vertex_neighbors(vertex_id)
            
            # Находим ближайшую свободную позицию
            position = await self._find_nearest_position_for_vertex(vertex_id, neighbors)
            
            if position:
                placements.append((vertex_id, *position))
        
        return placements

    async def _get_vertex_neighbors(self, vertex_id: str) -> Dict[str, List[str]]:
        """
        Получает соседей вершины (предшественники и потомки)
        """
        query = """
        MATCH (n:Node {uid: $vertex_id})
        OPTIONAL MATCH (pred:Node)-[:CITES]->(n)
        OPTIONAL MATCH (n)-[:CITES]->(succ:Node)
        RETURN 
            collect(DISTINCT pred.uid) as predecessors,
            collect(DISTINCT succ.uid) as successors
        """
        
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(query, {"vertex_id": vertex_id})
            self.db_operations += 1
            
        if result:
            row = result[0]
            return {
                "predecessors": row["predecessors"] or [],
                "successors": row["successors"] or []
            }
        
        return {"predecessors": [], "successors": []}

    async def _find_nearest_position_for_vertex(
        self, 
        vertex_id: str, 
        neighbors: Dict[str, List[str]]
    ) -> Optional[Tuple[int, int, int]]:
        """
        Находит ближайшую свободную позицию для вершины
        """
        # Получаем позиции соседей
        neighbor_positions = await self._get_neighbor_positions(neighbors)
        
        # Вычисляем оптимальную позицию на основе соседей
        optimal_layer = self._calculate_optimal_layer(neighbor_positions)
        
        # Находим ближайшую свободную позицию
        free_position = await self._find_free_position_near_layer(optimal_layer)
        
        return free_position

    async def _get_neighbor_positions(
        self, 
        neighbors: Dict[str, List[str]]
    ) -> Dict[str, List[VertexPosition]]:
        """
        Получает позиции соседей вершины
        """
        if not neighbors["predecessors"] and not neighbors["successors"]:
            return {"predecessors": [], "successors": []}
        
        query = """
        MATCH (n:Node)
        WHERE n.uid IN $vertex_ids AND n.layout_status IN ['placed', 'in_longest_path']
        RETURN n.uid as vertex_id, n.layer as layer, n.level as level, n.sublevel_id as sublevel_id
        """
        
        vertex_ids = neighbors["predecessors"] + neighbors["successors"]
        
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(query, {"vertex_ids": vertex_ids})
            self.db_operations += 1
        
        positions = {}
        for row in result:
            pos = VertexPosition(
                vertex_id=row["vertex_id"],
                layer=row["layer"],
                level=row["level"],
                sublevel_id=row["sublevel_id"],
                x=0.0,
                y=0.0,
                status=VertexStatus.PLACED
            )
            
            if row["vertex_id"] in neighbors["predecessors"]:
                if "predecessors" not in positions:
                    positions["predecessors"] = []
                positions["predecessors"].append(pos)
            else:
                if "successors" not in positions:
                    positions["successors"] = []
                positions["successors"].append(pos)
        
        return positions

    def _calculate_optimal_layer(
        self, 
        neighbor_positions: Dict[str, List[VertexPosition]]
    ) -> int:
        """
        Вычисляет оптимальный слой на основе позиций соседей
        """
        pred_layers = [pos.layer for pos in neighbor_positions.get("predecessors", [])]
        succ_layers = [pos.layer for pos in neighbor_positions.get("successors", [])]
        
        if pred_layers and succ_layers:
            # Среднее между максимальным слоем предшественников и минимальным слоем потомков
            max_pred_layer = max(pred_layers)
            min_succ_layer = min(succ_layers)
            return (max_pred_layer + min_succ_layer) // 2
        elif pred_layers:
            # Только предшественники - размещаем после них
            return max(pred_layers) + 1
        elif succ_layers:
            # Только потомки - размещаем перед ними
            return min(succ_layers) - 1
        else:
            # Изолированная вершина - размещаем в середине
            return 0

    async def _find_free_position_near_layer(self, target_layer: int) -> Optional[Tuple[int, int, int]]:
        """
        Находит свободную позицию рядом с целевым слоем
        """
        # Ищем свободные позиции в кэше
        if target_layer in self.free_positions_cache:
            if self.free_positions_cache[target_layer]:
                return self.free_positions_cache[target_layer].pop(0)
        
        # Ищем свободные позиции в соседних слоях
        for offset in range(10):  # Ищем в пределах ±10 слоёв
            for layer_offset in [-offset, offset]:
                layer = target_layer + layer_offset
                if layer < 0:
                    continue
                
                free_pos = await self._find_free_position_in_layer(layer)
                if free_pos:
                    return free_pos
        
        # Если не нашли, создаём новую позицию
        return (target_layer, 0, 0)

    async def _find_free_position_in_layer(self, layer: int) -> Optional[Tuple[int, int, int]]:
        """
        Находит свободную позицию в конкретном слое
        """
        query = """
        MATCH (n:Node {layer: $layer})
        RETURN n.level as level, n.sublevel_id as sublevel_id
        ORDER BY n.level DESC, n.sublevel_id DESC
        LIMIT 1
        """
        
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(query, {"layer": layer})
            self.db_operations += 1
        
        if result:
            row = result[0]
            return (layer, row["level"] + 1, 0)
        else:
            return (layer, 0, 0)

    async def _place_vertices_incremental(
        self, 
        placements: List[Tuple[str, int, int, int]]
    ) -> int:
        """
        Размещает вершины инкрементально
        """
        if not placements:
            return 0
        
        # Группируем размещения по батчам для эффективности
        batch_size = 100
        placed_count = 0
        
        for i in range(0, len(placements), batch_size):
            batch = placements[i:i + batch_size]
            
            # Создаём параметры для батча
            batch_data = [
                {
                    "vertex_id": vertex_id,
                    "layer": layer,
                    "level": level,
                    "sublevel_id": sublevel_id
                }
                for vertex_id, layer, level, sublevel_id in batch
            ]
            
            # Выполняем батч-обновление
            query = """
            UNWIND $batch AS item
            MATCH (n:Node {uid: item.vertex_id})
            SET n.layout_status = 'placed',
                n.layer = item.layer,
                n.level = item.level,
                n.sublevel_id = item.sublevel_id,
                n.x = item.layer * 250.0,
                n.y = item.level * 100.0
            """
            
            async with self.circuit_breaker:
                await neo4j_client.execute_query_with_retry(query, {"batch": batch_data})
                self.db_operations += 1
                placed_count += len(batch)
            
            # Обновляем кэш
            for vertex_id, layer, level, sublevel_id in batch:
                self.vertex_positions_cache[vertex_id] = VertexPosition(
                    vertex_id=vertex_id,
                    layer=layer,
                    level=level,
                    sublevel_id=sublevel_id,
                    x=layer * 250.0,
                    y=level * 100.0,
                    status=VertexStatus.PLACED
                )
        
        return placed_count

    async def _update_free_positions_cache(self):
        """
        Обновляет кэш свободных позиций
        """
        # Очищаем старый кэш
        self.free_positions_cache.clear()
        
        # Находим свободные позиции
        query = """
        MATCH (n:Node)
        WHERE n.layout_status = 'placed' OR n.layout_status = 'in_longest_path'
        WITH n.layer as layer, n.level as level, n.sublevel_id as sublevel_id
        ORDER BY layer, level, sublevel_id
        
        // Находим пропуски в позициях
        WITH layer, level, sublevel_id,
             row_number() OVER (PARTITION BY layer ORDER BY level, sublevel_id) as rn
        WHERE rn > 1  // Есть пропуски
        RETURN layer, level, sublevel_id
        LIMIT 1000
        """
        
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(query)
            self.db_operations += 1
        
        # Группируем по слоям
        for row in result:
            layer = row["layer"]
            if layer not in self.free_positions_cache:
                self.free_positions_cache[layer] = []
            
            self.free_positions_cache[layer].append(
                (layer, row["level"], row["sublevel_id"])
            )

    async def _process_pinned_blocks(self):
        """
        Обрабатывает закреплённые блоки с строгим соблюдением их позиций
        """
        logger.info("Processing pinned blocks")
        
        # Получаем закреплённые блоки
        query = """
        MATCH (n:Node)
        WHERE n.is_pinned = true
        RETURN n.uid as vertex_id, n.level as target_level
        """
        
        async with self.circuit_breaker:
            pinned_blocks = await neo4j_client.execute_query_with_retry(query)
            self.db_operations += 1
        
        for block in pinned_blocks:
            vertex_id = block["vertex_id"]
            target_level = block["target_level"]
            
            # Принудительно устанавливаем позицию закреплённого блока
            await self._force_pinned_position(vertex_id, target_level)

    async def _force_pinned_position(self, vertex_id: str, target_level: int):
        """
        Принудительно устанавливает позицию закреплённого блока
        """
        # Находим свободную позицию на целевом уровне
        query = """
        MATCH (n:Node {level: $target_level})
        RETURN max(n.sublevel_id) as max_sublevel
        """
        
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(query, {"target_level": target_level})
            self.db_operations += 1
        
        next_sublevel = 0
        if result and result[0]["max_sublevel"] is not None:
            next_sublevel = result[0]["max_sublevel"] + 1
        
        # Устанавливаем позицию
        update_query = """
        MATCH (n:Node {uid: $vertex_id})
        SET n.layout_status = 'pinned',
            n.level = $target_level,
            n.sublevel_id = $sublevel_id,
            n.y = $target_level * 100.0
        """
        
        async with self.circuit_breaker:
            await neo4j_client.execute_query_with_retry(
                update_query, 
                {
                    "vertex_id": vertex_id,
                    "target_level": target_level,
                    "sublevel_id": next_sublevel
                }
            )
            self.db_operations += 1

    async def _build_final_result(self) -> Dict[str, Any]:
        """
        Строит финальный результат укладки
        """
        logger.info("Building final layout result")
        
        # Получаем все размещённые вершины
        query = """
        MATCH (n:Node)
        WHERE n.layout_status IN ['placed', 'in_longest_path', 'pinned']
        RETURN n.uid as vertex_id, n.layer as layer, n.level as level, 
               n.sublevel_id as sublevel_id, n.x as x, n.y as y,
               n.layout_status as status, n.is_pinned as is_pinned
        ORDER BY n.layer, n.level, n.sublevel_id
        """
        
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(query)
            self.db_operations += 1
        
        # Строим структуры данных
        blocks = []
        layers = {}
        sublevels = defaultdict(list)
        levels = defaultdict(list)
        
        for row in result:
            vertex_id = row["vertex_id"]
            layer = row["layer"]
            level = row["level"]
            sublevel_id = row["sublevel_id"]
            
            # Добавляем блок
            blocks.append({
                "id": vertex_id,
                "layer": layer,
                "level": level,
                "sublevel_id": sublevel_id,
                "x": row["x"],
                "y": row["y"],
                "is_pinned": row["is_pinned"]
            })
            
            # Обновляем слои
            layers[vertex_id] = layer
            
            # Обновляем подуровни
            sublevels[sublevel_id].append(vertex_id)
            
            # Обновляем уровни
            if sublevel_id not in levels[level]:
                levels[level].append(sublevel_id)
        
        # Статистика
        statistics = {
            "total_blocks": len(blocks),
            "total_layers": len(set(layers.values())),
            "total_levels": len(levels),
            "total_sublevels": len(sublevels),
            "iterations": self.iteration_count,
            "vertices_processed": self.vertices_processed,
            "db_operations": self.db_operations,
            "longest_path_length": len(self.longest_path_cache)
        }
        
        return {
            "success": True,
            "blocks": blocks,
            "layers": layers,
            "sublevels": dict(sublevels),
            "levels": dict(levels),
            "statistics": statistics
        }


# Глобальный экземпляр алгоритма
distributed_incremental_layout = DistributedIncrementalLayout()
