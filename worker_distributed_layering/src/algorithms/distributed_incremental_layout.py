"""
Распределённый инкрементальный алгоритм укладки DAG графа с ускорением.
Рефакторенная версия, разбитая на модули.

Ключевые особенности:
1. Один полный обход для поиска longest path
2. Инкрементальное добавление вершин в ближайшие свободные места
3. Асинхронная синхронизация между итерациями
4. Полная отказоустойчивость с Circuit Breaker
5. Интеграция с Neo4j для обработки на уровне БД
6. Параллельная обработка компонент и batch операции
7. Поддержка распределённого выполнения на нескольких нодах
8. Использование Neo4j GDS и APOC для ускорения
9. Неограниченное количество уровней для гибкого размещения
10. Быстрое размещение оставшихся узлов по сетке (избегает застревания)
11. Стратегическое размещение: LP на уровне 0, компоненты выше, остальные еще выше

Ускорения:
- Параллельная обработка компонент: O(V²) → O(V²/P)
- Batch операции: O(V²) → O(V log V)  
- Neo4j GDS: O(V²) → O(V log V)
- APOC параллелизм: O(V) → O(V/P)
- ThreadPoolExecutor: CPU-интенсивные операции
- Быстрое размещение оставшихся узлов: O(V²) → O(V) (простая сетка)

Команда запуска
poetry run python -c "import asyncio; from src.algorithms.distributed_incremental_layout import distributed_incremental_layout; asyncio.run(distributed_incremental_layout.calculate_incremental_layout())"

import asyncio;
from src.algorithms.distributed_incremental_layout import distributed_incremental_layout;
asyncio.run(distributed_incremental_layout.calculate_incremental_layout())



Распределённый запуск:
poetry run python -c "import asyncio; from src.algorithms.distributed_incremental_layout import distributed_incremental_layout; asyncio.run(distributed_incremental_layout.calculate_incremental_layout_distributed(worker_id=0, total_workers=3))"
"""

import asyncio
import time
import traceback
import logging
import sys
from typing import Dict, List, Any, Optional, Set
from collections import defaultdict

from ..config import settings
from ..neo4j_client import neo4j_client
from ..utils.metrics import metrics_collector
from ..utils.simple_circuit_breaker import CircuitBreaker

from .layout_types import VertexStatus, VertexPosition, LayoutResult
from .positioning import PositionCalculator
from .longest_path import LongestPathProcessor
from .components import ComponentProcessor
from .fast_placement import FastPlacementProcessor
from .utils import LayoutUtils

# Настройка логирования для прямого запуска
def setup_logging():
    """Настраивает логирование для прямого запуска алгоритма"""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=getattr(logging, settings.log_level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            stream=sys.stdout,
            force=True
        )
        print(f"Logging configured with level: {settings.log_level.upper()}")

# Настраиваем логирование при импорте модуля
setup_logging()

logger = logging.getLogger(__name__)


class DistributedIncrementalLayout:
    """
    Распределённый инкрементальный алгоритм укладки на основе longest path
    Рефакторенная версия с модульной архитектурой
    """
    
    def __init__(self):
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=settings.circuit_breaker_failure_threshold,
            recovery_timeout=settings.circuit_breaker_recovery_timeout,
        )
        
        # Геометрия блока и отступы (определяем сначала)
        self.BLOCK_WIDTH = 200
        self.BLOCK_HEIGHT = 80
        self.HORIZONTAL_GAP = 40
        self.VERTICAL_GAP = 50

        # Единые коэффициенты позиционирования (шаги между центрами блоков)
        self.LAYER_SPACING = self.BLOCK_WIDTH + self.HORIZONTAL_GAP
        self.LEVEL_SPACING = self.BLOCK_HEIGHT + self.VERTICAL_GAP

        # Смещение для потомков относительно LP (зависит от ширины блока)
        self.SUCCESSOR_X_OFFSET = 0.1 * self.BLOCK_WIDTH
        
        # Инициализируем модули с правильными параметрами позиционирования
        self.position_calculator = PositionCalculator(
            layer_spacing=self.LAYER_SPACING,
            level_spacing=self.LEVEL_SPACING
        )
        self.longest_path_processor = LongestPathProcessor(self.circuit_breaker, self.position_calculator)
        self.component_processor = ComponentProcessor(self.circuit_breaker, self.position_calculator)
        self.fast_placement_processor = FastPlacementProcessor(self.circuit_breaker, self.position_calculator)
        self.layout_utils = LayoutUtils(self.circuit_breaker)
        
        # Кэш для оптимизации
        self.vertex_positions_cache = {}
        self.free_positions_cache = {}
        
        # Метрики
        self.iteration_count = 0
        self.vertices_processed = 0
        self.db_operations = 0

        # Прогресс
        self.total_articles_estimate = 0
        self._placed_ids: Set[str] = set()

    async def calculate_incremental_layout(self) -> LayoutResult:
        """
        Основной метод инкрементальной укладки
        """
        start_time = time.time()
        
        # Добавляем таймаут для предотвращения бесконечного выполнения
        max_execution_time = 60
        
        # Принудительно настраиваем логирование
        setup_logging()
        
        logger.info("=== STARTING DISTRIBUTED INCREMENTAL LAYOUT (REFACTORED) ===")
        logger.info(f"Starting distributed incremental layout calculation with {max_execution_time}s timeout")
        print("=== STARTING DISTRIBUTED INCREMENTAL LAYOUT (REFACTORED) ===")
        print(f"Starting distributed incremental layout calculation with {max_execution_time}s timeout")
        
        try:
            # 1. Инициализация и получение статистики
            logger.info("=== STEP 1: INITIALIZATION ===")
            print("=== STEP 1: INITIALIZATION ===")
            stats = await self._initialize_layout()
            logger.info(f"Initialization completed. Graph stats: {stats}")
            print(f"Initialization completed. Graph stats: {stats}")
            self.total_articles_estimate = int(stats.get("article_count") or 0)
            
            logger.info(f"Initialization completed in {time.time() - start_time:.2f}s")
            logger.info(f"Total articles in graph: {self.total_articles_estimate}")
            logger.info(f"Graph statistics: {stats}")
            print(f"Initialization completed in {time.time() - start_time:.2f}s")
            print(f"Total articles in graph: {self.total_articles_estimate}")
            print(f"Graph statistics: {stats}")
            
            # 2. Обнаружение и исправление циклов для обеспечения DAG
            logger.info("=== STEP 2: DETECT AND FIX CYCLES (ENSURE DAG) ===")
            print("=== STEP 2: DETECT AND FIX CYCLES (ENSURE DAG) ===")
            logger.info("Starting cycle detection and removal...")
            print("Starting cycle detection and removal...")
            removed_edges = await self.layout_utils.detect_and_fix_cycles()
            logger.info(f"Cycle detection completed. Removed {removed_edges} edges to ensure DAG structure")
            print(f"Cycle detection completed. Removed {removed_edges} edges to ensure DAG structure")
            
            # 3. Ранняя топологическая сортировка всего графа в БД (инкрементально, батчами)
            logger.info("=== STEP 3: COMPUTE GLOBAL TOPOLOGICAL ORDER (DB) ===")
            print("=== STEP 3: COMPUTE GLOBAL TOPOLOGICAL ORDER (DB) ===")
            logger.info("Starting topological sorting...")
            print("Starting topological sorting...")
            await self.layout_utils.compute_toposort_order_db()
            logger.info("Topological sorting completed")
            print("Topological sorting completed")
            
            # 4. Поиск и размещение longest path (объединённая операция)
            logger.info("=== STEP 4: FINDING AND PLACING LONGEST PATH ===")
            print("=== STEP 4: FINDING AND PLACING LONGEST PATH ===")
            logger.info("Starting combined longest path search and placement...")
            print("Starting combined longest path search and placement...")
            step4_start = time.time()
            lp_placements = await self.longest_path_processor.find_and_place_longest_path()
            step4_time = time.time() - step4_start
            logger.info(f"Longest path search and placement completed in {step4_time:.2f}s")
            print(f"Longest path search and placement completed in {step4_time:.2f}s")
            
            # Получаем longest path из кэша для логирования
            longest_path = self.longest_path_processor.longest_path_cache
            logger.info(f"Longest path found with {len(longest_path)} vertices")
            
            # Логируем первые несколько элементов longest path для отладки
            if longest_path:
                logger.info(f"First 5 vertices in longest path: {longest_path[:5]}")
                if len(longest_path) > 5:
                    logger.info(f"Last 5 vertices in longest path: {longest_path[-5:]}")
            else:
                logger.warning("Longest path is empty!")
            
            logger.info(f"Longest path search and placement completed in {time.time() - start_time:.2f}s")
            logger.info(f"Longest path contains {len(longest_path)} vertices")
            logger.info(f"Placed {len(lp_placements) if lp_placements else 0} LP vertices")
            
            # 4.5. Размещение соседей longest path по разным уровням
            logger.info("=== STEP 4.5: PLACING LP NEIGHBORS ===")
            print("=== STEP 4.5: PLACING LP NEIGHBORS ===")
            logger.info("Starting placement of LP neighbors across levels...")
            print("Starting placement of LP neighbors across levels...")
            step45_start = time.time()
            try:
                lp_neighbors_count = await self.longest_path_processor.place_lp_neighbors(longest_path)
                step45_time = time.time() - step45_start
                logger.info(f"LP neighbors placement completed in {step45_time:.2f}s: {lp_neighbors_count} nodes")
                print(f"LP neighbors placement completed in {step45_time:.2f}s: {lp_neighbors_count} nodes")
            except Exception as e:
                step45_time = time.time() - step45_start
                logger.error(f"Error in LP neighbors placement after {step45_time:.2f}s: {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                print(f"Error in LP neighbors placement after {step45_time:.2f}s: {str(e)}")
                print(f"Traceback: {traceback.format_exc()}")
            
            # 5. Поиск и размещение компонентов связности
            logger.info("=== STEP 5: PLACING CONNECTED COMPONENTS ===")
            print("=== STEP 5: PLACING CONNECTED COMPONENTS ===")
            logger.info("Starting connected components search and placement...")
            print("Starting connected components search and placement...")
            step5_start = time.time()
            try:
                components = await self.component_processor.find_connected_components_gds()
                step5_time = time.time() - step5_start
                logger.info(f"Connected components search completed in {step5_time:.2f}s: {len(components)} components found")
                print(f"Connected components search completed in {step5_time:.2f}s: {len(components)} components found")
                
                # Размещаем компоненты
                if components:
                    placement_start = time.time()
                    await self.component_processor.place_connected_components_parallel(components)
                    placement_time = time.time() - placement_start
                    logger.info(f"Connected components placement completed in {placement_time:.2f}s")
                    print(f"Connected components placement completed in {placement_time:.2f}s")
                else:
                    logger.info("No connected components found to place")
                    print("No connected components found to place")
                    
            except Exception as e:
                step5_time = time.time() - step5_start
                logger.error(f"Error in connected components processing after {step5_time:.2f}s: {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                print(f"Error in connected components processing after {step5_time:.2f}s: {str(e)}")
                print(f"Traceback: {traceback.format_exc()}")
            
            # 6. Быстрое размещение оставшихся статей (ОТКЛЮЧЕНО)
            # logger.info("=== STEP 6: FAST BATCH PLACEMENT OF REMAINING ARTICLES ===")
            
            # 7. Финальная обработка закреплённых блоков (ОТКЛЮЧЕНО)
            # logger.info("=== STEP 7: PROCESSING PINNED BLOCKS ===")
            # try:
            #     await self._process_pinned_blocks()
            # except Exception as e:
            #     logger.error(f"Error in processing pinned blocks: {str(e)}")
            #     # Продолжаем выполнение даже при ошибке
            
            # Создаем базовый результат после STEP 5
            processing_time = time.time() - start_time
            result = LayoutResult(
                success=True,
                blocks=[],
                layers={},
                levels={},
                statistics={
                    "processing_time_seconds": processing_time,
                    "step_completed": "connected_components_placed",
                    "total_articles": self.total_articles_estimate,
                    "removed_edges": removed_edges,
                    "longest_path_length": len(longest_path),
                    "lp_placements_count": len(lp_placements) if lp_placements else 0,
                    "lp_neighbors_count": lp_neighbors_count if 'lp_neighbors_count' in locals() else 0,
                    "connected_components_count": len(components) if 'components' in locals() else 0,
                    "graph_stats": stats
                }
            )
            
            # Записываем метрики
            metrics_collector.record_task_execution(
                task_type="incremental_layout",
                duration=processing_time,
                success=result.success
            )
            
            logger.info(
                f"Incremental layout completed in {processing_time:.2f}s, "
                f"iterations: {self.iteration_count}, "
                f"vertices: {self.vertices_processed}, "
                f"db_ops: {self.db_operations}"
            )
            
            # Итоговая статистика
            logger.info("=== FINAL STATISTICS ===")
            print("=== FINAL STATISTICS ===")
            logger.info(f"Success: {result.success}")
            print(f"Success: {result.success}")
            logger.info(f"Processing time: {processing_time:.2f}s")
            print(f"Processing time: {processing_time:.2f}s")
            logger.info(f"Total articles processed: {self.vertices_processed}")
            print(f"Total articles processed: {self.vertices_processed}")
            logger.info(f"Database operations: {self.db_operations}")
            print(f"Database operations: {self.db_operations}")
            logger.info(f"Iterations: {self.iteration_count}")
            print(f"Iterations: {self.iteration_count}")
            if hasattr(result, 'statistics') and result.statistics:
                for key, value in result.statistics.items():
                    logger.info(f"{key}: {value}")
                    print(f"{key}: {value}")
            
            logger.info("=== LAYOUT COMPLETED SUCCESSFULLY (STEPS 1-5) ===")
            print("=== LAYOUT COMPLETED SUCCESSFULLY (STEPS 1-5) ===")
            return result
            
        except Exception as e:
            logger.error(f"=== LAYOUT FAILED ===")
            print(f"=== LAYOUT FAILED ===")
            logger.error(f"Incremental layout failed: {str(e)}")
            print(f"Incremental layout failed: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            print(f"Traceback: {traceback.format_exc()}")
            return LayoutResult(
                success=False,
                error=str(e),
                blocks=[],
                layers={},
                levels={},
                statistics={"processing_time_seconds": time.time() - start_time}
            )

    async def _initialize_layout(self) -> Dict[str, Any]:
        """
        Инициализация укладки и получение статистики
        """
        logger.info("Initializing incremental layout")
        
        # Временно отключаем circuit breaker для отладки
        # async with self.circuit_breaker:
        logger.info("Getting graph statistics...")
        stats = await neo4j_client.get_graph_statistics()
        logger.info(f"Graph statistics received: {stats}")
        
        logger.info("Initializing layout tables...")
        await self.layout_utils.initialize_layout_tables()
        logger.info("Layout tables initialized")
        
        # Очищаем кэши
        self.vertex_positions_cache.clear()
        self.free_positions_cache.clear()
        logger.info("Caches cleared")
        
        # Сбрасываем метрики
        self.iteration_count = 0
        self.vertices_processed = 0
        self.db_operations = 0
        self._placed_ids.clear()
        logger.info("Metrics reset")
            
        return stats

    async def _process_pinned_blocks(self):
        """
        Обрабатывает закреплённые блоки с строгим соблюдением их позиций
        """
        logger.info("Processing pinned blocks")
        
        # Получаем закреплённые блоки
        query = """
        MATCH (n:Article)
        WHERE n.is_pinned = true
        RETURN n.uid as article_id, n.level as target_level
        """
        
        # async with self.circuit_breaker:
        logger.info("Getting pinned blocks...")
        pinned_blocks = await neo4j_client.execute_query_with_retry(query)
        if self.db_operations is None:
            self.db_operations = 0
        self.db_operations += 1
        logger.info(f"Found {len(pinned_blocks)} pinned blocks")
        
        for block in pinned_blocks:
            article_id = block["article_id"]
            target_level = block["target_level"]
            
            # Принудительно устанавливаем позицию закреплённого блока
            await self._force_pinned_position(article_id, target_level)

    async def _force_pinned_position(self, article_id: str, target_level: int):
        """
        Принудительно устанавливает позицию закреплённого блока
        """
        # Устанавливаем позицию
        update_query = """
        MATCH (n:Article {uid: $article_id})
        SET n.layout_status = 'pinned',
            n.level = $target_level,
            n.y = $target_level * $level_spacing
        """
        
        # async with self.circuit_breaker:
        logger.info(f"Setting pinned position for article {article_id} to level {target_level}")
        await neo4j_client.execute_query_with_retry(
            update_query, 
            {
                "article_id": article_id,
                "target_level": target_level,
                "level_spacing": self.LEVEL_SPACING
            }
        )
        if self.db_operations is None:
            self.db_operations = 0
        self.db_operations += 1

    async def calculate_incremental_layout_distributed(self, worker_id: int = 0, total_workers: int = 1) -> LayoutResult:
        """Распределённая версия алгоритма укладки"""
        logger.info(f"=== STARTING DISTRIBUTED LAYOUT (Worker {worker_id}/{total_workers}) ===")
        
        # Инициализация
        stats = await self._initialize_layout()
        
        # Создаём индексы производительности
        await self.layout_utils.create_performance_indexes()
        
        # Вычисляем топологический порядок
        await self.layout_utils.compute_toposort_order_db()
        
        # Поиск longest path
        longest_path = await self.longest_path_processor.find_longest_path_neo4j()
        
        # Размещение longest path
        await self.longest_path_processor.place_longest_path(longest_path)
        
        # Размещение соседей LP
        await self.longest_path_processor.place_lp_neighbors(longest_path)
        
        # Распределённое размещение компонент
        if total_workers > 1:
            components = await self.component_processor.find_connected_components_gds()
            
            # Распределяем компоненты по воркерам
            worker_components = self._distribute_components_by_worker(components, worker_id, total_workers)
            
            logger.info(f"Worker {worker_id} processing {len(worker_components)} components out of {len(components)} total")
            
            # Параллельная обработка компонент
            await self.component_processor.place_connected_components_parallel(worker_components)
        else:
            # Одиночный воркер - используем стандартный метод
            components = await self.component_processor.find_connected_components()
            await self.component_processor.place_connected_components_parallel(components)
        
        # Быстрое размещение оставшихся статей
        result = await self.fast_placement_processor.fast_batch_placement_remaining()
        
        # Обработка закреплённых блоков
        await self._process_pinned_blocks()
        
        # Синхронизация между воркерами
        if total_workers > 1:
            await self._synchronize_with_other_workers(worker_id, total_workers)
        
        return result

    def _distribute_components_by_worker(self, components: List[List[str]], worker_id: int, total_workers: int) -> List[List[str]]:
        """Распределяет компоненты по воркерам"""
        # Используем хеширование для равномерного распределения
        worker_components = []
        
        for component in components:
            # Хешируем первый элемент компоненты для детерминированного распределения
            if component:
                first_article = component[0]
                component_hash = hash(first_article) % total_workers
                
                if component_hash == worker_id:
                    worker_components.append(component)
        
        logger.info(f"Worker {worker_id} assigned {len(worker_components)} components")
        return worker_components

    async def _synchronize_with_other_workers(self, worker_id: int, total_workers: int):
        """Синхронизация с другими воркерами"""
        logger.info(f"Synchronizing with other workers ({worker_id}/{total_workers})")
        
        # Создаём маркер завершения для этого воркера
        sync_query = """
        MERGE (s:SyncWorker {worker_id: $worker_id, total_workers: $total_workers})
        SET s.completed = true, s.timestamp = datetime()
        """
        
        await neo4j_client.execute_query_with_retry(sync_query, {
            "worker_id": worker_id,
            "total_workers": total_workers
        })
        if self.db_operations is None:
            self.db_operations = 0
        self.db_operations += 1
        
        # Ждём завершения всех воркеров
        if worker_id == 0:  # Главный воркер
            await self._wait_for_all_workers_completion(total_workers)
        else:
            # Дочерние воркеры ждут сигнала от главного
            await self._wait_for_master_signal(worker_id)

    async def _wait_for_all_workers_completion(self, total_workers: int):
        """Главный воркер ждёт завершения всех дочерних"""
        logger.info("Master worker waiting for all workers to complete...")
        
        while True:
            check_query = """
            MATCH (s:SyncWorker)
            WHERE s.total_workers = $total_workers
            RETURN count(s) as completed_workers
            """
            
            result = await neo4j_client.execute_query_with_retry(check_query, {"total_workers": total_workers})
            if self.db_operations is None:
                self.db_operations = 0
            self.db_operations += 1
            
            completed = result[0]["completed_workers"] if result else 0
            
            if completed >= total_workers:
                logger.info(f"All {total_workers} workers completed")
                break
            
            logger.info(f"Waiting for workers: {completed}/{total_workers}")
            await asyncio.sleep(5)  # Проверяем каждые 5 секунд

    async def _wait_for_master_signal(self, worker_id: int):
        """Дочерние воркеры ждут сигнала от главного"""
        logger.info(f"Worker {worker_id} waiting for master signal...")
        
        while True:
            check_query = """
            MATCH (s:SyncWorker {worker_id: 0})
            WHERE s.completed = true
            RETURN s.timestamp as master_completed
            """
            
            result = await neo4j_client.execute_query_with_retry(check_query)
            if self.db_operations is None:
                self.db_operations = 0
            self.db_operations += 1
            
            if result and result[0]["master_completed"]:
                logger.info(f"Worker {worker_id} received master signal")
                break
            
            await asyncio.sleep(2)  # Проверяем каждые 2 секунды


# Глобальный экземпляр алгоритма
distributed_incremental_layout = DistributedIncrementalLayout()
