"""
Распределённый инкрементальный алгоритм укладки DAG графа.
Основан на longest path с инкрементальным добавлением вершин без полных обходов.

Ключевые особенности:
1. Один полный обход для поиска longest path
2. Инкрементальное добавление вершин в ближайшие свободные места
3. Асинхронная синхронизация между итерациями
4. Полная отказоустойчивость с Circuit Breaker
5. Интеграция с Neo4j для обработки на уровне БД

Команда запуска
poetry run python -c "import asyncio; from src.algorithms.disributed_incremental_layout import distributed_incremental_layout; asyncio.run(distributed_incremental_layout.calculate_incremental_layout())"
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
        # Логируем реже, чтобы не засорять вывод
        self.progress_log_interval = 300
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
            
            # 4. Поиск и размещение компонентов связности
            components = await self._find_connected_components()
            for i, component in enumerate(components):
                start_layer = i % 10  # Распределяем по слоям
                start_level = (i // 10) % 5  # Распределяем по уровням
                await self._place_connected_component(component, start_layer, start_level)
            
            # 5. Инкрементальное размещение остальных вершин
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
            CREATE CONSTRAINT IF NOT EXISTS FOR (p:Position) REQUIRE p.id IS UNIQUE
            """,
            # Гарантируем уникальность места (layer, level, sublevel_id)
            """
            CREATE CONSTRAINT IF NOT EXISTS FOR (n:Node) REQUIRE (n.layer, n.level, n.sublevel_id) IS UNIQUE
            """,
            
            # Инициализируем только статус (не трогаем layer/level/sublevel/x/y из-за уникального ограничения)
            """
            MATCH (n:Node)
            SET n.layout_status = 'unprocessed'
            """,
            
            # Создаём таблицу для longest path
            """
            CREATE CONSTRAINT IF NOT EXISTS FOR (lp:LongestPath) REQUIRE lp.id IS UNIQUE
            """
        ]
        
        for query in init_queries:
            async with self.circuit_breaker:
                await neo4j_client.execute_query_with_retry(query)
                if self.db_operations is None:
                    self.db_operations = 0
                self.db_operations += 1

    async def _find_longest_path_neo4j(self) -> List[str]:
        """
        Поиск longest path в Neo4j (единственный полный обход графа)
        Использует алгоритм динамического программирования в Cypher
        """
        logger.info("Finding longest path in Neo4j")
        
        # Проверяем кэш
        if isinstance(self.longest_path_cache, list) and self.longest_path_cache:
            logger.info("Using cached longest path")
            return self.longest_path_cache
        
        longest_path_query = """
        // Алгоритм поиска longest path в DAG
        MATCH (source:Node)
        WHERE NOT EXISTS((:Node)-[:CITES]->(source))  // Находим источники (узлы без входящих рёбер)
        
        CALL {
            WITH source
            MATCH path = (source)-[:CITES*]->(target)
            WHERE NOT EXISTS((target)-[:CITES]->())  // До стоков (узлов без исходящих рёбер)
            RETURN path, length(path) as path_length
            ORDER BY path_length DESC
            LIMIT 1
        }
        
        WITH path
        UNWIND nodes(path) as node_in_path
        RETURN DISTINCT node_in_path.uid as vertex_id
        """
        
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(longest_path_query)
            if self.db_operations is None:
                self.db_operations = 0
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
            if self.db_operations is None:
                self.db_operations = 0
            self.db_operations += 2

    async def _place_longest_path(self, longest_path: List[str]):
        """
        Размещает longest path в укладке
        """
        logger.info("Placing longest path")
        # Для каждого узла LP выбираем следующий свободный sublevel_id на (layer=lp.layer, level=0)
        placement_query = """
        MATCH (lp:LongestPath)
        WITH lp
        ORDER BY lp.layer
        CALL {
          WITH lp
          MATCH (n:Node {uid: lp.id})
          OPTIONAL MATCH (m:Node {layer: lp.layer, level: 0})
          WITH n, lp, coalesce(max(m.sublevel_id), -1) AS maxSub
          SET n.layout_status = 'in_longest_path',
              n.layer = lp.layer,
              n.level = 0,
              n.sublevel_id = maxSub + 1,
              n.x = lp.layer * 20.0 + (maxSub + 1) * 15.0,
              n.y = 0.0
          RETURN 1 AS ok
        }
        RETURN count(ok)
        """

        async with self.circuit_breaker:
            await neo4j_client.execute_query_with_retry(placement_query)
            self.db_operations += 1
            
        # Обновляем кэш позиций
        # Считываем фактически выставленные позиции LP из БД, чтобы кэш совпадал
        read_lp_query = """
        MATCH (lp:LongestPath)
        MATCH (n:Node {uid: lp.id})
        RETURN n.uid as uid, n.layer as layer, n.level as level, n.sublevel_id as sub, n.x as x, n.y as y
        ORDER BY layer, sub
        """
        async with self.circuit_breaker:
            rows = await neo4j_client.execute_query_with_retry(read_lp_query)
            self.db_operations += 1
        for row in rows:
            self.vertex_positions_cache[row["uid"]] = VertexPosition(
                vertex_id=row["uid"],
                layer=row["layer"],
                level=row["level"],
                sublevel_id=row["sub"],
                x=row["x"],
                y=row["y"],
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
            
            # Умеренный прогресс (редко)
            current_time = time.time()
            if current_time - self.last_progress_log >= self.progress_log_interval:
                logger.info(f"Incremental iterations progress: iter={iteration + 1}")
                self.last_progress_log = current_time
            
            # 1. Находим неразмещённые вершины
            unplaced_vertices = await self._get_unplaced_vertices()
            
            if not unplaced_vertices:
                logger.info("All vertices placed, stopping iterations")
                break
            
            # 2. Находим ближайшие свободные позиции для каждой вершины
            placements = await self._find_nearest_free_positions(unplaced_vertices)
            
            # 3. Размещаем вершины асинхронно
            placed_count = await self._place_vertices_incremental([p[0] for p in placements])
            
            if placed_count is not None:
                self.vertices_processed += placed_count
            
            # 4. Проверяем сходимость
            if placed_count is not None and placed_count < convergence_threshold:
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
            if self.db_operations is None:
                self.db_operations = 0
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
            if self.db_operations is None:
                self.db_operations = 0
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
        Находит ближайшую свободную позицию для вершины.
        Сначала выбираем целевые layer и level на основе соседей,
        затем ищем свободный sublevel_id для этой пары (layer, level).
        """
        # Получаем позиции соседей
        neighbor_positions = await self._get_neighbor_positions(neighbors)

        # Вычисляем оптимальные layer и level
        target_layer = self._calculate_optimal_layer(neighbor_positions)
        target_level = self._calculate_optimal_level(neighbors)

        # Находим ближайшую свободную позицию около (layer, level)
        # Приоритет: сначала пробуем оптимальный уровень, потом ищем свободные
        free_position = await self._find_free_position_near(target_layer, target_level)
        
        # Если не нашли свободную позицию, создаём новую на оптимальном уровне
        if not free_position:
            # Создаём новый уровень выше существующих в этом слое
            max_level_query = """
            MATCH (n:Node {layer: $layer})
            WHERE n.layout_status IN ['placed', 'in_longest_path']
            RETURN coalesce(max(n.level), -1) as max_level
            """
            async with self.circuit_breaker:
                result = await neo4j_client.execute_query_with_retry(max_level_query, {"layer": target_layer})
                if self.db_operations is None:
                    self.db_operations = 0
                self.db_operations += 1
            
            new_level = 0
            try:
                if result and result[0] and result[0].get("max_level") is not None:
                    max_level_val = result[0]["max_level"]
                    if max_level_val is not None:
                        new_level = int(max_level_val) + 1
            except (ValueError, TypeError):
                new_level = 0
            
            free_position = (target_layer, new_level, 0)

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
            if self.db_operations is None:
                self.db_operations = 0
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
        """Оптимальный layer: между предшественниками и потомками, иначе рядом с существующими."""
        pred_layers = [pos.layer for pos in neighbor_positions.get("predecessors", [])]
        succ_layers = [pos.layer for pos in neighbor_positions.get("successors", [])]

        if pred_layers and succ_layers:
            max_pred_layer = max(pred_layers)
            min_succ_layer = min(succ_layers)
            return (max_pred_layer + min_succ_layer) // 2
        if pred_layers:
            return max(pred_layers) + 1
        if succ_layers:
            return min(succ_layers) - 1
        return 0

    def _calculate_optimal_level(
        self,
        neighbor_positions: Dict[str, List[str]]
    ) -> int:
        """Оптимальный level: разнообразие по уровням для избежания наложений."""
        # Для простоты возвращаем случайный уровень, так как у нас нет позиций
        import random
        return random.randint(0, 5)  # 0-5 уровней для разнообразия

    async def _find_free_position_near(self, target_layer: int, target_level: int) -> Optional[Tuple[int, int, int]]:
        """
        Находит ближайшую свободную позицию около (target_layer, target_level).
        Сначала проверяем точное совпадение, затем расширяем поиск по уровням и слоям.
        Возвращает (layer, level, sublevel_id).
        """
        # 1) Пробуем точное место
        sublevel = await self._next_sublevel_at(target_layer, target_level)
        if sublevel is not None:
            return (target_layer, target_level, sublevel)

        # 2) Ищем ближние уровни в этом же слое (приоритет разнообразия)
        for d_level in range(1, 15):  # Увеличиваем диапазон поиска для большего разнообразия
            for sign in (-1, 1):
                lvl = target_level + sign * d_level
                if lvl < 0:
                    continue
                sub = await self._next_sublevel_at(target_layer, lvl)
                if sub is not None:
                    return (target_layer, lvl, sub)

        # 3) Ищем соседние слои на том же уровне
        for d_layer in range(1, 6):
            for sign in (-1, 1):
                lyr = target_layer + sign * d_layer
                if lyr < 0:
                    continue
                sub = await self._next_sublevel_at(lyr, target_level)
                if sub is not None:
                    return (lyr, target_level, sub)

        # 4) В крайнем случае — создаём новый уровень выше существующих
        # Находим максимальный уровень в этом слое
        max_level_query = """
        MATCH (n:Node {layer: $layer})
        WHERE n.layout_status IN ['placed', 'in_longest_path']
        RETURN max(n.level) as max_level
        """
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(max_level_query, {"layer": target_layer})
            if self.db_operations is None:
                self.db_operations = 0
            self.db_operations += 1
        
        new_level = 0
        if result and result[0]["max_level"] is not None:
            new_level = int(result[0]["max_level"]) + 1
        
        return (target_layer, new_level, 0)

    async def _next_sublevel_at(self, layer: int, level: int) -> Optional[int]:
        """Возвращает следующий свободный sublevel_id для (layer, level)."""
        query = """
        MATCH (n:Node {layer: $layer, level: $level})
        RETURN max(n.sublevel_id) as max_sublevel
        """
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(query, {"layer": layer, "level": level})
            if self.db_operations is None:
                self.db_operations = 0
            self.db_operations += 1
        if not result or not result[0]:
            return 0
        max_sub = result[0].get("max_sublevel")
        if max_sub is None:
            return 0
        try:
            return int(max_sub) + 1
        except (ValueError, TypeError):
            return 0

    async def _place_connected_component(self, component: List[str], start_layer: int, start_level: int):
        """
        Размещает компонент связности рядом с основным (LP)
        """
        logger.info(f"Placing component with {len(component)} nodes at layer {start_layer}, level {start_level}")
        
        # Находим соседей компонента для определения оптимального размещения
        neighbors_query = """
        MATCH (n:Node)-[:CITES]-(m:Node)
        WHERE n.uid IN $component_ids AND m.layout_status IN ['placed', 'in_longest_path']
        RETURN m.layer as layer, m.level as level, m.x as x, m.y as y
        """
        
        async with self.circuit_breaker:
            neighbors = await neo4j_client.execute_query_with_retry(neighbors_query, {"component_ids": component})
            if self.db_operations is None:
                self.db_operations = 0
            self.db_operations += 1
        
        if neighbors:
            # Находим ближайшую позицию к соседям
            avg_layer = sum(n["layer"] for n in neighbors) / len(neighbors)
            avg_level = sum(n["level"] for n in neighbors) / len(neighbors)
            target_layer = int(avg_layer)
            target_level = int(avg_level)
        else:
            # Если соседей нет, размещаем рядом с LP
            target_layer = start_layer + 1
            target_level = start_level
        
        # Размещаем узлы компонента с уникальными sublevel_id
        placements = []
        for i, vertex_id in enumerate(component):
            # Находим свободную позицию около target_layer, target_level
            free_pos = await self._find_free_position_near(target_layer, target_level)
            if free_pos:
                layer, level, sublevel = free_pos
                x = layer * 20.0 + sublevel * 15.0
                y = level * 40.0  # Уменьшаем разницу по y
                placements.append({
                    "vertex_id": vertex_id,
                    "layer": layer,
                    "level": level,
                    "sublevel_id": sublevel,
                    "x": x,
                    "y": y
                })
        
        if placements:
            # Группируем по (layer, level) для уникальности sublevel_id
            grouped = {}
            for p in placements:
                key = (p["layer"], p["level"])
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(p)
            
            # Находим максимальные sublevel_id для каждой группы
            max_map = {}
            for key in grouped:
                layer, level = key
                max_query = """
                MATCH (n:Node {layer: $layer, level: $level})
                WHERE n.layout_status IN ['placed', 'in_longest_path']
                RETURN coalesce(max(n.sublevel_id), -1) as max_sub
                """
                async with self.circuit_breaker:
                    result = await neo4j_client.execute_query_with_retry(max_query, {"layer": layer, "level": level})
                    if self.db_operations is None:
                        self.db_operations = 0
                    self.db_operations += 1
                
                max_map[key] = 0
                if result and result[0] and result[0].get("max_sub") is not None:
                    max_map[key] = int(result[0]["max_sub"])
            
            # Присваиваем уникальные sublevel_id внутри партии
            assigned_items = []
            for key, items in grouped.items():
                base = max_map[key] + 1
                # Сортируем элементы по приоритету для детерминированности
                sorted_items = sorted(items, key=lambda x: x["vertex_id"])
                for idx, item in enumerate(sorted_items):
                    sub = base + idx
                    assigned_items.append({
                        "vertex_id": item["vertex_id"],
                        "layer": item["layer"],
                        "level": item["level"],
                        "sublevel_id": sub,
                        "x": item["layer"] * 20.0 + sub * 15.0,
                        "y": item["level"] * 40.0,
                    })
            
            # Обновляем узлы в базе
            update_query = """
            UNWIND $batch AS item
            MATCH (n:Node {uid: item.vertex_id})
            SET n.layout_status = 'placed',
                n.layer = item.layer,
                n.level = item.level,
                n.sublevel_id = item.sublevel_id,
                n.x = item.x,
                n.y = item.y
            """
            
        async with self.circuit_breaker:
            await neo4j_client.execute_query_with_retry(update_query, {"batch": assigned_items})
            if self.db_operations is None:
                self.db_operations = 0
            self.db_operations += 1
            
            # Обновляем кэш
            for item in assigned_items:
                self.vertex_positions_cache[item["vertex_id"]] = VertexPosition(
                    vertex_id=item["vertex_id"],
                    layer=item["layer"],
                    level=item["level"],
                    sublevel_id=item["sublevel_id"],
                    x=item["x"],
                    y=item["y"],
                    status=VertexStatus.PLACED
                )
            
            logger.info(f"Placed {len(assigned_items)} nodes from component")

    async def _find_connected_components(self) -> List[List[str]]:
        """
        Находит все компоненты связности в графе
        """
        logger.info("Finding connected components")
        
        # Начинаем с узлов, которые не в longest path
        components_query = """
        MATCH (n:Node)
        WHERE n.layout_status = 'unprocessed'
        WITH n LIMIT 1000
        CALL {
            WITH n
            MATCH path = (n)-[:CITES*1..5]-(connected:Node)
            WHERE connected.layout_status = 'unprocessed'
            WITH collect(DISTINCT connected.uid) as connected_uids, n
            RETURN connected_uids + [n.uid] as component
        }
        RETURN component
        """
        
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(components_query)
            self.db_operations += 1
            
        if not result:
            return []
            
        # Убираем дубликаты и сортируем по размеру
        all_components = []
        seen_nodes = set()
        
        for row in result:
            component = list(set(row["component"]))
            # Добавляем только новые узлы
            new_nodes = [n for n in component if n not in seen_nodes]
            if new_nodes:
                all_components.append(new_nodes)
                seen_nodes.update(new_nodes)
        
        # Сортируем по размеру (большие компоненты первыми)
        all_components.sort(key=len, reverse=True)
        
        logger.info(f"Found {len(all_components)} connected components")
        return all_components

    async def _place_vertices_incremental(self, vertices: List[str]):
        """
        Размещает вершины инкрементально с учетом размеров блоков
        """
        logger.info(f"Placing {len(vertices)} vertices incrementally")
        
        # Группируем по (layer, level) для уникальности sublevel_id
        placements = []
        for vertex_id in vertices:
            neighbors = await self._get_vertex_neighbors(vertex_id)
            target_layer, target_level = self._calculate_optimal_level(neighbors), 0
            free_position = await self._find_nearest_position_for_vertex(vertex_id, neighbors)
            
            if free_position:
                layer, level, sublevel = free_position
                x = layer * 20.0 + sublevel * 15.0  # Уменьшаем расстояния
                y = level * 40.0  # Уменьшаем разницу по y
                placements.append({
                    "vertex_id": vertex_id,
                    "layer": layer,
                    "level": level,
                    "sublevel_id": sublevel,
                    "x": x,
                    "y": y
                })
        
        if not placements:
            return
        
        # Группируем по (layer, level) для уникальности sublevel_id
        grouped = {}
        for p in placements:
            key = (p["layer"], p["level"])
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(p)
        
        # Находим максимальные sublevel_id для каждой группы
        max_map = {}
        for key in grouped:
            layer, level = key
            max_query = """
            MATCH (n:Node {layer: $layer, level: $level})
            WHERE n.layout_status IN ['placed', 'in_longest_path']
            RETURN coalesce(max(n.sublevel_id), -1) as max_sub
            """
            async with self.circuit_breaker:
                result = await neo4j_client.execute_query_with_retry(max_query, {"layer": layer, "level": level})
                if self.db_operations is None:
                    self.db_operations = 0
                self.db_operations += 1
            
            max_map[key] = 0
            if result and result[0] and result[0].get("max_sub") is not None:
                max_map[key] = int(result[0]["max_sub"])
            else:
                max_map[key] = 0
        
        # Присваиваем уникальные sublevel_id внутри партии
        assigned_items = []
        for key, items in grouped.items():
            base = max_map[key] + 1
            # Сортируем элементы по приоритету (например, по vertex_id для детерминированности)
            sorted_items = sorted(items, key=lambda x: x["vertex_id"])
            for idx, item in enumerate(sorted_items):
                sub = base + idx
                assigned_items.append({
                    "vertex_id": item["vertex_id"],
                    "layer": item["layer"],
                    "level": item["level"],
                    "sublevel_id": sub,
                    "x": item["layer"] * 20.0 + sub * 15.0,  # Уменьшаем расстояния
                    "y": item["level"] * 40.0,  # Уменьшаем разницу по y
                })
        
        # Обновляем узлы в базе
        update_query = """
        UNWIND $batch AS item
        MATCH (n:Node {uid: item.vertex_id})
        SET n.layout_status = 'placed',
            n.layer = item.layer,
            n.level = item.level,
            n.sublevel_id = item.sublevel_id,
            n.x = item.x,
            n.y = item.y
        """
        
        async with self.circuit_breaker:
            await neo4j_client.execute_query_with_retry(update_query, {"batch": assigned_items})
            if self.db_operations is None:
                self.db_operations = 0
            self.db_operations += 1
        
        # Обновляем кэш
        for item in assigned_items:
            self.vertex_positions_cache[item["vertex_id"]] = VertexPosition(
                vertex_id=item["vertex_id"],
                layer=item["layer"],
                level=item["level"],
                sublevel_id=item["sublevel_id"],
                x=item["x"],
                y=item["y"],
                status=VertexStatus.PLACED
            )
        
        logger.info(f"Placed {len(assigned_items)} vertices incrementally")

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
        RETURN n.layer as layer, n.level as level, n.sublevel_id as sublevel_id
        ORDER BY layer, level, sublevel_id
        LIMIT 1000
        """
        
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(query)
            if self.db_operations is None:
                self.db_operations = 0
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
            if self.db_operations is None:
                self.db_operations = 0
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
            if self.db_operations is None:
                self.db_operations = 0
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
            n.y = $target_level * 40.0
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
            if self.db_operations is None:
                self.db_operations = 0
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
            if self.db_operations is None:
                self.db_operations = 0
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
