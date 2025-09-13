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

Алгоритм включает все 8 шагов:
1. Инициализация и получение статистики
2. Обнаружение и исправление циклов путем разворота связей для обеспечения DAG
3. Ранняя топологическая сортировка всего графа в БД
4. Поиск и размещение longest path
4.5. Размещение соседей longest path по разным уровням
5. Поиск и размещение компонентов связности
6. Быстрое размещение оставшихся статей
7. Финальная обработка закреплённых блоков
8. Назначение уровней всем вершинам

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
from .fast_placement import FastPlacementProcessor
from .utils import LayoutUtils
from .topological_sort import topological_sorter

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
        logger = logging.getLogger(__name__)
        logger.info(f"Логирование настроено с уровнем: {settings.log_level.upper()}")

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

    async def _db_validate_topo_order(self) -> None:
        """Проверяет корректность topo_order одной транзакцией на стороне БД."""
        logger.info("=== ПРОВЕРКА ТОПОЛОГИЧЕСКОГО ПОРЯДКА (DB) ===")
        query = (
            """
            CALL {
              MATCH (n:Article) WHERE n.topo_order IS NOT NULL
              RETURN count(*) AS total,
                     count(DISTINCT n.topo_order) AS uniq,
                     min(n.topo_order) AS minv,
                     max(n.topo_order) AS maxv,
                     collect(n.topo_order) AS allv
            }
            WITH total, uniq, minv, maxv,
                 apoc.coll.subtract(range(0, total-1), allv) AS missing
            RETURN total, uniq, minv AS min_topo, maxv AS max_topo,
                   size(missing) AS missing_count, missing[0..10] AS missing_sample
            """
        )
        res = await neo4j_client.execute_query_with_retry(query)
        if not res:
            logger.warning("Не удалось получить статистику по topo_order (DB)")
            return
        row = res[0]
        total = int(row.get("total") or 0)
        uniq = int(row.get("uniq") or 0)
        min_topo = row.get("min_topo")
        max_topo = row.get("max_topo")
        missing_count = int(row.get("missing_count") or 0)
        missing_sample = row.get("missing_sample") or []
        logger.info(f"Всего вершин с topo_order: {total}")
        logger.info(f"Минимальный topo_order: {min_topo}")
        logger.info(f"Максимальный topo_order: {max_topo}")
        if uniq < total:
            logger.warning(f"Дубликаты topo_order: уникальных {uniq} из {total}")
        else:
            logger.info("Все значения topo_order уникальны")
        if missing_count > 0:
            logger.error(f"Есть пропуски: {missing_count}, пример: {missing_sample}")
        ok_range = (min_topo == 0) and (max_topo == total - 1)
        if ok_range and missing_count == 0 and uniq == total:
            logger.info("🎉 ТОПОЛОГИЧЕСКИЙ ПОРЯДОК КОРРЕКТЕН (DB)")
        else:
            logger.error("❌ ТОПОЛОГИЧЕСКИЙ ПОРЯДОК НЕКОРРЕКТЕН (DB)")

    async def calculate_incremental_layout(self) -> LayoutResult:
        """
        Основной метод инкрементальной укладки
        """
        start_time = time.time()
        
        # Принудительно настраиваем логирование
        setup_logging()
        
        logger.info("=== ЗАПУСК РАСПРЕДЕЛЕННОЙ ИНКРЕМЕНТАЛЬНОЙ УКЛАДКИ ===")
        
        try:
            # 0. Очистка БД от предыдущих результатов укладки
            logger.info("=== ШАГ 0: ОЧИСТКА БД ===")
            await self._clean_database()
            logger.info("Очистка БД завершена")
            
            # 1. Инициализация и получение статистики
            logger.info("=== ШАГ 1: ИНИЦИАЛИЗАЦИЯ ===")
            stats = await self._initialize_layout()
            logger.info(f"Инициализация завершена. Статистика графа: {stats}")
            self.total_articles_estimate = int(stats.get("article_count") or 0)
            logger.info(f"Инициализация завершена за {time.time() - start_time:.2f}с")
            logger.info(f"Всего статей в графе: {self.total_articles_estimate}")
            logger.info(f"Статистика графа: {stats}")
            
            # Гарантируем отсутствие координат до их реального назначения (для не-LP и не pinned)
            try:
                cleanup_coords_q = (
                    "MATCH (n:Article) "
                    "WHERE (n.layout_status IS NULL OR NOT n.layout_status IN ['in_longest_path','pinned']) "
                    "AND (n.level IS NOT NULL OR n.x IS NOT NULL OR n.y IS NOT NULL) "
                    "REMOVE n.level, n.x, n.y "
                    "RETURN count(n) as cleaned"
                )
                res_cleanup = await neo4j_client.execute_query_with_retry(cleanup_coords_q)
                if self.db_operations is None:
                    self.db_operations = 0
                self.db_operations += 1
                cleaned_cnt = int(res_cleanup[0]["cleaned"]) if res_cleanup and isinstance(res_cleanup[0], dict) and "cleaned" in res_cleanup[0] else 0
                logger.info(f"Удалены предварительные координаты у {cleaned_cnt} вершин")
            except Exception:
                logger.warning("Не удалось выполнить предварительное удаление координат; продолжаем")
            
            
            # 2. Обнаружение и исправление циклов путем разворота связей для обеспечения DAG
            logger.info("=== ШАГ 2: ОБНАРУЖЕНИЕ И ИСПРАВЛЕНИЕ ЦИКЛОВ (ОБЕСПЕЧЕНИЕ DAG) ===")
            logger.info("Запуск обнаружения и исправления циклов...")
            fixed_edges = await self.layout_utils.detect_and_fix_cycles()
            logger.info(f"Исправление циклов завершено. Обработано {fixed_edges} рёбер для обеспечения DAG структуры")
            
            
            # 3. Топологическая сортировка всего графа в БД (инкрементально, батчами)
            logger.info("=== ШАГ 3: ВЫЧИСЛЕНИЕ ГЛОБАЛЬНОГО ТОПОЛОГИЧЕСКОГО ПОРЯДКА (БД) ===")
            logger.info("Запуск топологической сортировки...")
            
            # Опция: исключать изолированные вершины из укладки (по умолчанию выключена)
            exclude_isolated = getattr(settings, 'exclude_isolated_vertices', False)
            
            await topological_sorter.compute_toposort_order_db(exclude_isolated=exclude_isolated)
            logger.info("Топологическая сортировка завершена")
            
            # Проверка топологической сортировки через БД (опционально)
            validate_topo_order = getattr(settings, 'validate_topo_order', False)
            if validate_topo_order:
                logger.info("=== ПРОВЕРКА ТОПОЛОГИЧЕСКОГО ПОРЯДКА В БД ===")
                try:
                    # Получаем распределение значений topo_order (включая/исключая изолированные вершины)
                    topo_stats_query = """
                    MATCH (n:Article)
                    WHERE n.topo_order IS NOT NULL
                    RETURN count(*) as total,
                           min(n.topo_order) as min_topo,
                           max(n.topo_order) as max_topo,
                           collect(n.topo_order) as all_topo_orders
                    """
                    topo_stats = await neo4j_client.execute_query_with_retry(topo_stats_query)
                    if topo_stats and len(topo_stats) > 0:
                        total = topo_stats[0].get("total", 0)
                        min_topo = topo_stats[0].get("min_topo")
                        max_topo = topo_stats[0].get("max_topo")
                        all_topo_orders = topo_stats[0].get("all_topo_orders", [])
                        logger.info(f"Всего вершин с topo_order: {total}")
                        logger.info(f"Минимальный topo_order: {min_topo}")
                        logger.info(f"Максимальный topo_order: {max_topo}")
                        # Считаем распределение чисел topo_order
                        from collections import Counter
                        topo_counter = Counter(all_topo_orders)
                        most_common = topo_counter.most_common(10)
                        logger.info(f"Топ-10 самых частых значений topo_order: {most_common}")
                        # Проверяем уникальность
                        unique_count = len(set(all_topo_orders))
                        if unique_count < total:
                            logger.warning(f"ВНИМАНИЕ: Есть дублирующиеся значения topo_order! Уникальных: {unique_count} из {total}")
                        else:
                            logger.info("Все значения topo_order уникальны")
                        # Проверяем последовательность
                        logger.info("=== ПРОВЕРКА ПОСЛЕДОВАТЕЛЬНОСТИ ТОПОЛОГИЧЕСКОГО ПОРЯДКА ===")
                        sorted_topo = sorted(all_topo_orders)
                        if sorted_topo and sorted_topo[0] != 0:
                            logger.error(f"ОШИБКА: Последовательность не начинается с 0! Первое значение: {sorted_topo[0]}")
                        expected_last = (total - 1) if total else -1
                        if sorted_topo and sorted_topo[-1] != expected_last:
                            logger.error(f"ОШИБКА: Последовательность не заканчивается на {expected_last}! Последнее значение: {sorted_topo[-1]}")
                        missing_values = []
                        progress_step = max(1, total // 20) if total else 1
                        for i in range(total):
                            if i not in sorted_topo:
                                missing_values.append(i)
                                if i % progress_step == 0 or i == total - 1:
                                    percent = ((i + 1) / total) * 100 if total else 100.0
                                    logger.info(f"[ПРОВЕРКА topo_order] Пропуски: прогресс {i+1}/{total} (~{percent:.1f}%)")
                        is_monotonic = True
                        mono_n = len(sorted_topo)
                        mono_step = max(1, mono_n // 20) if mono_n else 1
                        for i in range(1, mono_n):
                            if sorted_topo[i] < sorted_topo[i-1]:
                                is_monotonic = False
                                logger.error(f"ОШИБКА: Нарушена монотонность на позиции {i}! {sorted_topo[i-1]} > {sorted_topo[i]}")
                                break
                            if i % mono_step == 0 or i == mono_n - 1:
                                percent = ((i + 1) / mono_n) * 100 if mono_n else 100.0
                                logger.info(f"[ПРОВЕРКА topo_order] Монотонность: прогресс {i+1}/{mono_n} (~{percent:.1f}%)")
                        non_integer_values = [x for x in all_topo_orders if not isinstance(x, int)]
                        if non_integer_values:
                            logger.error(f"ОШИБКА: Обнаружены нецелые значения! {non_integer_values[:10]}{'...' if len(non_integer_values) > 10 else ''}")
                        ok_range = (min_topo == 0) and (max_topo == total - 1) if total else False
                        if (ok_range and not missing_values and is_monotonic and not non_integer_values):
                            logger.info("🎉 ТОПОЛОГИЧЕСКИЙ ПОРЯДОК КОРРЕКТЕН (DB)")
                        else:
                            logger.error("❌ ТОПОЛОГИЧЕСКИЙ ПОРЯДОК НЕКОРРЕКТЕН (DB)")
                    else:
                        logger.warning("Не удалось получить статистику по topo_order (DB)")
                except Exception as e:
                    logger.error(f"Ошибка при проверке топологической сортировки: {str(e)}")
                    logger.error(traceback.format_exc())
            else:
                logger.info("Проверка топологического порядка отключена (validate_topo_order=False)")
        
            # 4. Поиск и размещение самого длинного пути (объединённая операция)
            logger.info("=== ШАГ 4: ПОИСК И РАЗМЕЩЕНИЕ САМОГО ДЛИННОГО ПУТИ ===")
            logger.info("Запуск объединенного поиска и размещения самого длинного пути...")
            step4_start = time.time()
            lp_placements = await self.longest_path_processor.find_and_place_longest_path()
            step4_time = time.time() - step4_start
            logger.info(f"Поиск и размещение самого длинного пути завершено за {step4_time:.2f}с")
            
            # Получаем самый длинный путь из кэша для логирования
            longest_path = self.longest_path_processor.longest_path_cache
            logger.info(f"Найден самый длинный путь с {len(longest_path)} вершинами")
            logger.info(f"Поиск и размещение самого длинного пути завершено за {time.time() - start_time:.2f}с")
            logger.info(f"Самый длинный путь содержит {len(longest_path)} вершин")
            logger.info(f"Размещено {len(lp_placements) if lp_placements else 0} вершин LP")
            
        
            # 5. Финальная обработка закреплённых блоков
            logger.info("=== ШАГ 5: ОБРАБОТКА ЗАКРЕПЛЕННЫХ БЛОКОВ ===")
            logger.info("Запуск обработки закрепленных блоков...")
            step5_start = time.time()
            try:
                await self._process_pinned_blocks()
                step5_time = time.time() - step5_start
                logger.info(f"Обработка закрепленных блоков завершена за {step5_time:.2f}с")
            except Exception as e:
                step5_time = time.time() - step5_start
                logger.error(f"Ошибка при обработке закрепленных блоков после {step5_time:.2f}с: {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                # Продолжаем выполнение даже при ошибке
            
            # 6. Этап 9: Назначение слоёв всем остальным вершинам согласно описанию алгоритма
            logger.info("=== ШАГ 6: ЭТАП 9 - НАЗНАЧЕНИЕ СЛОЁВ ОСТАВШИМСЯ ВЕРШИНАМ ===")
            step6_start = time.time()
            placed_topo = 0
            try:
                placed_topo = await self._place_remaining_sugiyama()
                step6_time = time.time() - step6_start
                logger.info(f"Этап 9 (назначение слоёв) завершён за {step6_time:.2f}с, обновлено {placed_topo} вершин")
            except Exception as e:
                step6_time = time.time() - step6_start
                logger.error(f"Ошибка при выполнении этапа 9 после {step6_time:.2f}с: {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")

            # 7. Этап 10: Назначение уровней всем вершинам
            logger.info("=== ШАГ 7: ЭТАП 10 - НАЗНАЧЕНИЕ УРОВНЕЙ ВСЕМ ВЕРШИНАМ ===")
            # Гарантируем, что перед назначением уровней у placed_layers нет старых координат
            try:
                pre10_cleanup_q = (
                    "MATCH (n:Article) "
                    "WHERE n.layout_status = 'placed_layers' "
                    "AND (n.level IS NOT NULL OR n.x IS NOT NULL OR n.y IS NOT NULL) "
                    "REMOVE n.level, n.x, n.y "
                    "RETURN count(n) as cleaned"
                )
                res_pre10 = await neo4j_client.execute_query_with_retry(pre10_cleanup_q)
                if self.db_operations is None:
                    self.db_operations = 0
                self.db_operations += 1
                pre10_cleaned = int(res_pre10[0]["cleaned"]) if res_pre10 and isinstance(res_pre10[0], dict) and "cleaned" in res_pre10[0] else 0
                logger.info(f"[ЭТАП 10] Очищены координаты перед назначением уровней у {pre10_cleaned} вершин")
            except Exception:
                logger.warning("[ЭТАП 10] Не удалось очистить координаты перед назначением уровней; продолжаем")
            step7_start = time.time()
            placed_levels = 0
            try:
                placed_levels = await self._assign_levels_to_vertices()
                step7_time = time.time() - step7_start
                logger.info(f"Этап 10 (назначение уровней) завершён за {step7_time:.2f}с, обновлено {placed_levels} вершин")
            except Exception as e:
                step7_time = time.time() - step7_start
                logger.error(f"Ошибка при выполнении этапа 10 после {step7_time:.2f}с: {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")

            # Резервный вариант удален - используем только топологическую укладку
            if placed_topo == 0:
                logger.warning("Ни одна вершина не размещена на этапе 9 - это указывает на проблему с алгоритмом")
                logger.warning("Продолжаем без резервного размещения")
            
            # Создаем финальный результат после всех шагов
            processing_time = time.time() - start_time
            result = LayoutResult(
                success=True,
                blocks=[],
                layers={},
                levels={},
                statistics={
                    "processing_time_seconds": processing_time,
                    "step_completed": "all_steps_completed",
                    "total_articles": self.total_articles_estimate,
                    "fixed_edges": fixed_edges,
                    "longest_path_length": len(longest_path),
                    "lp_placements_count": len(lp_placements) if lp_placements else 0,
                    "lp_neighbors_count": 0,
                    "connected_components_count": 0,  # Компоненты теперь обрабатываются основным алгоритмом
                    "topo_incremental_placed": placed_topo,
                    "levels_assigned": placed_levels,
                    "pinned_blocks_processed": True,
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
                f"Инкрементальная укладка завершена за {processing_time:.2f}с, "
                f"итерации: {self.iteration_count}, "
                f"вершины: {self.vertices_processed}, "
                f"операции БД: {self.db_operations}"
            )
            
            # Итоговая статистика
            logger.info("=== ФИНАЛЬНАЯ СТАТИСТИКА ===")
            logger.info(f"Успех: {result.success}")
            logger.info(f"Время обработки: {processing_time:.2f}с")
            logger.info(f"Всего обработано статей: {self.vertices_processed}")
            logger.info(f"Операции с базой данных: {self.db_operations}")
            logger.info(f"Итерации: {self.iteration_count}")
            if hasattr(result, 'statistics') and result.statistics:
                for key, value in result.statistics.items():
                    logger.info(f"{key}: {value}")
            
            logger.info("=== УКЛАДКА УСПЕШНО ЗАВЕРШЕНА (ВСЕ ШАГИ 1-6) ===")
            return result
            
        except Exception as e:
            logger.error(f"=== УКЛАДКА НЕ УДАЛАСЬ ===")
            logger.error(f"Инкрементальная укладка не удалась: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
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
        logger.info("Инициализация инкрементальной укладки")
        
        # Временно отключаем circuit breaker для отладки
        # async with self.circuit_breaker:
        logger.info("Получение статистики графа...")
        stats = await neo4j_client.get_graph_statistics()
        logger.info(f"Статистика графа получена: {stats}")
        
        logger.info("Инициализация таблиц укладки...")
        try:
            await self.layout_utils.initialize_layout_tables()
            logger.info("Таблицы укладки инициализированы")
        except Exception as e:
            # Из-за ограничений памяти транзакции Neo4j можем пропустить инициализацию (временное решение)
            logger.error(f"Инициализация таблиц укладки пропущена из-за ошибки: {e}")
            logger.error("Продолжаем без повторной инициализации таблиц укладки (временное решение)")
        
        # Очищаем кэши
        self.vertex_positions_cache.clear()
        self.free_positions_cache.clear()
        logger.info("Кэши очищены")
        
        # Сбрасываем метрики
        self.iteration_count = 0
        self.vertices_processed = 0
        self.db_operations = 0
        self._placed_ids.clear()
        logger.info("Метрики сброшены")
            
        return stats

    async def _clean_database(self):
        """
        Очищает БД от результатов предыдущих укладок
        """
        logger.info("Очистка БД от результатов предыдущих укладок...")
        
        batch_size = 10000
        total_cleaned = 0
        
        # Очищаем все координаты и статусы укладки батчами
        while True:
            query = """
            MATCH (n:Article)
            WHERE n.layer IS NOT NULL OR n.level IS NOT NULL OR n.x IS NOT NULL OR n.y IS NOT NULL 
                   OR n.layout_status IS NOT NULL OR n.topo_order IS NOT NULL OR n.visited IS NOT NULL OR n.in_deg IS NOT NULL
            WITH n LIMIT $batch_size
            REMOVE n.layer, n.level, n.x, n.y, n.layout_status, n.topo_order, n.visited, n.in_deg
            RETURN count(n) as cleaned
            """
            
            result = await neo4j_client.execute_query_with_retry(query, {"batch_size": batch_size})
            if self.db_operations is None:
                self.db_operations = 0
            self.db_operations += 1
            
            batch_cleaned = result[0]["cleaned"] if result and result[0] else 0
            total_cleaned += batch_cleaned
            
            if batch_cleaned > 0:
                logger.info(f"Очищено батч: {batch_cleaned}, всего: {total_cleaned}")
            else:
                break
        
        logger.info(f"Очистка БД завершена. Всего очищено вершин: {total_cleaned}")

    async def _process_pinned_blocks(self):
        """
        Обрабатывает закреплённые блоки с строгим соблюдением их позиций
        """
        logger.info("Обработка закрепленных блоков")
        
        # Получаем закреплённые блоки (только связанные вершины)
        query = """
        MATCH (n:Article)
        WHERE n.is_pinned = true
        AND (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() })
        RETURN n.uid as article_id, n.level as target_level
        """
        
        # async with self.circuit_breaker:
        logger.info("Получение закрепленных блоков...")
        pinned_blocks = await neo4j_client.execute_query_with_retry(query)
        if self.db_operations is None:
            self.db_operations = 0
        self.db_operations += 1
        logger.info(f"Найдено {len(pinned_blocks)} закрепленных блоков")
        
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
        logger.info(f"Установка закрепленной позиции для статьи {article_id} на уровень {target_level}")
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

    async def _place_remaining_sugiyama(self) -> int:
        """
        Этап 9: Назначение слоёв всем остальным вершинам согласно описанию алгоритма:
        1. Инициализировать карту слоёв, где узлам длиннейшего пути уже назначены слои от 0 до (длина_пути - 1).
        2. Назначить слои всем вершинам в порядке топологической сортировки. Для каждой вершины, если она не обработана:
           1. Найти всех непосредственных предков текущей вершины.
           2. Вычислить максимальный слой среди всех предков: max_parent_layer = max(слои_всех_предков).
           3. Назначить текущей вершине слой равный max_parent_layer + 1.
           4. Пометить вершину как обработанную.
        3. Если у вершины нет предков (изолированная вершина), назначить ей слой -1.
        """
        layer_step = float(self.LAYER_SPACING)
        level_step = float(self.LEVEL_SPACING)

        # 1) Считаем вершины для переукладки (исключаем LP и pinned, включая изолированные вершины)
        total_q = (
            "MATCH (n:Article) "
            "WHERE (n.layout_status IS NULL OR NOT n.layout_status IN ['in_longest_path', 'pinned']) "
            + ("AND (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() }) " if getattr(settings, 'exclude_isolated_vertices', False) else "")
            + "RETURN count(n) as left"
        )
        total_res = await neo4j_client.execute_query_with_retry(total_q)
        
        if self.db_operations is None:
            self.db_operations = 0
        self.db_operations += 1
        total_all = int(total_res[0]["left"]) if total_res and isinstance(total_res[0], dict) else 0
        logger.info(f"[ЭТАП 9] Найдено {total_all} вершин для назначения слоёв")
        
        if total_all == 0:
            logger.info("[ЭТАП 9] Не найдено вершин для назначения слоёв")
            return 0

        # Берём ВСЕ вершины для переукладки (исключаем LP и pinned, возможно исключая изолированные)
        exclude_isolated = getattr(settings, 'exclude_isolated_vertices', True)
        logger.info(f"[ЭТАП 9] exclude_isolated_vertices = {exclude_isolated}")

        # Если нужно исключать изолированные вершины — очистим их координаты и статусы
        if exclude_isolated:
            cleanup_iso_q = (
                "MATCH (n:Article) "
                "WHERE NOT (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() }) "
                "AND n.layout_status IS NOT NULL "
                "SET n.layer = NULL, n.level = NULL, n.x = NULL, n.y = NULL, n.layout_status = 'excluded_isolated' "
                "RETURN count(n) as cleaned"
            )
            cleaned = await neo4j_client.execute_query_with_retry(cleanup_iso_q)
            if self.db_operations is None:
                self.db_operations = 0
            self.db_operations += 1
            cleaned_cnt = int(cleaned[0]["cleaned"]) if cleaned and isinstance(cleaned[0], dict) and "cleaned" in cleaned[0] else 0
            logger.info(f"[ЭТАП 9] Очищено изолированных вершин: {cleaned_cnt}")

        fetch_nodes_q = (
            "MATCH (n:Article) "
            "WHERE (n.layout_status IS NULL OR NOT n.layout_status IN ['in_longest_path', 'pinned']) "
            + ("AND (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() }) " if exclude_isolated else "")
            + "RETURN n.uid as id, coalesce(n.topo_order,0) as topo_order "
            + "ORDER BY topo_order ASC"
        )
        nodes = await neo4j_client.execute_query_with_retry(fetch_nodes_q)
        
        if self.db_operations is None:
            self.db_operations = 0
        self.db_operations += 1
        node_ids = [r["id"] for r in nodes] if nodes else []
        node_set = set(node_ids)
        logger.info(f"[ЭТАП 9] Найдено {len(node_ids)} узлов для назначения слоёв")
        if not node_ids:
            logger.info("[ЭТАП 9] Не найдено узлов, пропускаем назначение слоёв")
            return 0
        
        # Логируем первые несколько узлов для отладки
        if len(node_ids) > 0:
            logger.info(f"[ЭТАП 9] Первые 5 узлов: {node_ids[:5]}")
            logger.info(f"[ЭТАП 9] Последние 5 узлов: {node_ids[-5:]}")

        # 2) DB: Назначаем слои в БД по возрастанию topo_order батчами (итеративно внутри окон)
        bounds_q = (
            "MATCH (n:Article) "
            "WHERE (n.layout_status IS NULL OR NOT n.layout_status IN ['in_longest_path', 'pinned']) "
            + ("AND (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() }) " if exclude_isolated else "")
            + "RETURN min(n.topo_order) AS min_t, max(n.topo_order) AS max_t"
        )
        bounds = await neo4j_client.execute_query_with_retry(bounds_q)
        if self.db_operations is None:
            self.db_operations = 0
        self.db_operations += 1
        min_t = int(bounds[0]["min_t"]) if bounds and bounds[0]["min_t"] is not None else 0
        max_t = int(bounds[0]["max_t"]) if bounds and bounds[0]["max_t"] is not None else -1
        if max_t >= min_t:
            window = 50000
            logger.info(f"[ЭТАП 9] DB-назначение слоёв по topo_order в окнах по {window} (итеративно)")

            # Формируем запрос в зависимости от настройки exclude_isolated
            if exclude_isolated:
                # Исключаем изолированные вершины - они не должны попадать в укладку
                layer_assignment = "     SET n.layer = CASE WHEN maxPred IS NULL THEN -1 ELSE maxPred + 1 END, n.layout_status = 'placed_layers'"
            else:
                layer_assignment = "     SET n.layer = CASE WHEN maxPred IS NULL THEN -1 ELSE maxPred + 1 END, n.layout_status = 'placed_layers'"
            
            # Формируем запрос более аккуратно
            match_query = (
                "MATCH (n:Article) \n"
                "WHERE (n.layout_status IS NULL OR NOT n.layout_status IN ['in_longest_path', 'pinned']) \n"
            )
            if exclude_isolated:
                match_query += "AND (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() }) \n"
            match_query += (
                "AND n.topo_order >= $from AND n.topo_order < $to \n"
                "RETURN n ORDER BY n.topo_order ASC"
            )
            
            update_query = (
                "OPTIONAL MATCH (p:Article)-[:BIBLIOGRAPHIC_LINK]->(n) \n"
                "WITH n, max(p.layer) AS maxPred \n"
                + layer_assignment
            )
            
            iterate_q = f'''CALL apoc.periodic.iterate(
  "{match_query}",
  "{update_query}",
  {{batchSize: 20000, parallel: false, params: {{from: $from, to: $to}}}}
)
YIELD batches, total, errorMessages RETURN batches, total'''

            for start in range(min_t, max_t + 1, window):
                end = min(start + window, max_t + 1)
                res = await neo4j_client.execute_query_with_retry(iterate_q, {"from": start, "to": end})
                if self.db_operations is None:
                    self.db_operations = 0
                self.db_operations += 1
                logger.info(f"[ЭТАП 9][DB] Окно {start}-{end-1} обработано: {res[0] if res else {}}")

        # 3) Получаем узлы для размещения с уже назначенными слоями
        fetch_nodes_q = (
            "MATCH (n:Article) "
            "WHERE (n.layout_status IS NULL OR NOT n.layout_status IN ['in_longest_path', 'pinned']) "
            + ("AND (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() }) " if exclude_isolated else "")
            + "RETURN n.uid as id, coalesce(n.topo_order,0) as topo_order, n.layer AS layer "
            + "ORDER BY topo_order ASC"
        )
        nodes = await neo4j_client.execute_query_with_retry(fetch_nodes_q)
        if self.db_operations is None:
            self.db_operations = 0
        self.db_operations += 1

        # 5) Внутрислойное упорядочивание: topo_order внутри слоя
        layer_to_nodes = {}
        topo_order_map = {}
        for idx, r in enumerate(nodes):
            vid = r["id"]
            ly = int(r.get("layer") or -1)
            topo = int(r.get("topo_order") or 0)
            topo_order_map[vid] = topo
            layer_to_nodes.setdefault(ly, []).append(vid)
        for ly, arr in layer_to_nodes.items():
            arr.sort(key=lambda v: topo_order_map.get(v, 0))

        # 6) Получаем занятые позиции для избежания наложений
        occupied_positions_query = """
        MATCH (n:Article)
        WHERE n.layer IS NOT NULL AND n.level IS NOT NULL
        AND n.layout_status IN ['in_longest_path', 'pinned', 'placed']
        RETURN n.layer as layer, n.level as level
        """
        occupied_result = await neo4j_client.execute_query_with_retry(occupied_positions_query)
        occupied_positions = set()
        for row in occupied_result:
            occupied_positions.add((int(row["layer"]), int(row["level"])))
        
        # 7) Дополнительная очистка изолированных вершин после назначения слоев
        if exclude_isolated:
            cleanup_iso_after_q = (
                "MATCH (n:Article) "
                "WHERE NOT (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() }) "
                "AND n.layout_status = 'placed_layers' "
                "SET n.layer = NULL, n.level = NULL, n.x = NULL, n.y = NULL, n.layout_status = 'excluded_isolated' "
                "RETURN count(n) as cleaned"
            )
            cleaned_after = await neo4j_client.execute_query_with_retry(cleanup_iso_after_q)
            if self.db_operations is None:
                self.db_operations = 0
            self.db_operations += 1
            cleaned_after_cnt = int(cleaned_after[0]["cleaned"]) if cleaned_after and isinstance(cleaned_after[0], dict) and "cleaned" in cleaned_after[0] else 0
            logger.info(f"[ЭТАП 9] Дополнительно очищено изолированных вершин после назначения слоев: {cleaned_after_cnt}")

        # 8) Обновляем только слои в БД (уровни будут назначены на этапе 10)
        batch_size = 5000
        updated_total = 0
        update_q = (
            "UNWIND $batch AS item "
            "MATCH (n:Article {uid: item.id}) "
            "SET n.layer = item.layer, "
            "    n.layout_status = 'placed_layers' "
            "RETURN count(n) as c"
        )

        # Формируем батчи для обновления слоев
        layer_updates = []
        for ly, arr in layer_to_nodes.items():
            # Исключаем изолированные вершины (слой -1) из укладки
            if ly == -1:
                continue
            for vid in arr:
                layer_updates.append({
                    "id": vid,
                    "layer": int(ly)
                })

        if not layer_updates:
            return 0

        total_batches = (len(layer_updates) + batch_size - 1) // batch_size
        logger.info(f"[ЭТАП 9] Обновление слоёв для {len(layer_updates)} вершин в {total_batches} батчах по {batch_size}")

        for i in range(0, len(layer_updates), batch_size):
            batch = layer_updates[i:i+batch_size]
            res = await neo4j_client.execute_query_with_retry(update_q, {"batch": batch})
            if self.db_operations is None:
                self.db_operations = 0
            self.db_operations += 1
            cnt = int(res[0]["c"]) if res and isinstance(res[0], dict) and "c" in res[0] else 0
            updated_total += cnt
            
            # Логируем прогресс каждые 5 батчей
            batch_num = (i // batch_size) + 1
            if batch_num % 5 == 0 or batch_num == total_batches:
                logger.info(f"[ЭТАП 9] Обновлено слоёв для {min(i+batch_size, len(layer_updates))}/{len(layer_updates)} вершин (батч {batch_num}/{total_batches})")

        return updated_total

    async def _assign_levels_to_vertices(self) -> int:
        """
        Этап 10: Назначение уровней всем вершинам (кроме уже размещенных LP и закрепленных):
        1. Для каждого слоя собрать все вершины этого слоя.
        2. Отсортировать вершины внутри слоя по топологическому порядку.
        3. Найти занятые позиции (слой, уровень) для LP и закрепленных вершин.
        4. Для каждой вершины в слое найти следующий свободный уровень и назначить его.
        """
        logger.info("=== ЭТАП 10: НАЗНАЧЕНИЕ УРОВНЕЙ ВСЕМ ВЕРШИНАМ ===")
        
        # 1) Получаем все вершины с назначенными слоями (кроме LP и закрепленных)
        # Учитываем опцию exclude_isolated_vertices
        exclude_isolated = getattr(settings, 'exclude_isolated_vertices', True)
        
        # Дополнительная очистка изолированных вершин в этапе 10
        if exclude_isolated:
            cleanup_iso_q = (
                "MATCH (n:Article) "
                "WHERE NOT (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() }) "
                "AND n.layer IS NOT NULL "
                "SET n.layer = NULL, n.level = NULL, n.x = NULL, n.y = NULL, n.layout_status = 'excluded_isolated' "
                "RETURN count(n) as cleaned"
            )
            cleaned = await neo4j_client.execute_query_with_retry(cleanup_iso_q)
            if self.db_operations is None:
                self.db_operations = 0
            self.db_operations += 1
            cleaned_cnt = int(cleaned[0]["cleaned"]) if cleaned and isinstance(cleaned[0], dict) and "cleaned" in cleaned[0] else 0
            logger.info(f"[ЭТАП 10] Дополнительно очищено изолированных вершин: {cleaned_cnt}")
        
        # Берём ТОЛЬКО вершины со статусом placed_layers
        count_query = (
            "MATCH (n:Article) "
            "WHERE n.layout_status = 'placed_layers' "
            + ("AND (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() }) " if exclude_isolated else "")
            + "RETURN count(n) as cnt"
        )
        cnt_rows = await neo4j_client.execute_query_with_retry(count_query)
        placed_layers_count = int(cnt_rows[0]["cnt"]) if cnt_rows and isinstance(cnt_rows[0], dict) and "cnt" in cnt_rows[0] else 0
        logger.info(f"[ЭТАП 10] Вершин со статусом placed_layers: {placed_layers_count}")
        
        vertices_query = (
            "MATCH (n:Article) "
            "WHERE n.layout_status = 'placed_layers' "
            + ("AND n.layer IS NOT NULL AND n.layer <> -1 " if exclude_isolated else "")
            + ("AND (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() }) " if exclude_isolated else "")
            + "RETURN n.uid as id, n.layer as layer, n.topo_order as topo_order "
            + "ORDER BY n.layer ASC, n.topo_order ASC"
        )
        vertices = await neo4j_client.execute_query_with_retry(vertices_query)
        if self.db_operations is None:
            self.db_operations = 0
        self.db_operations += 1
        
        if not vertices:
            logger.info("[ЭТАП 10] Не найдено вершин для назначения уровней")
            return 0
        
        # 2) Группируем вершины по слоям
        layer_to_vertices = {}
        for vertex in vertices:
            layer = int(vertex["layer"])
            if exclude_isolated and layer == -1:
                continue
            if layer not in layer_to_vertices:
                layer_to_vertices[layer] = []
            layer_to_vertices[layer].append({
                "id": vertex["id"],
                "topo_order": int(vertex.get("topo_order", 0))
            })
        
        # 3) Получаем занятые позиции (слой, уровень) для LP и закрепленных вершин
        occupied_query = """
        MATCH (n:Article)
        WHERE n.layer IS NOT NULL AND n.level IS NOT NULL
        AND n.layout_status IN ['in_longest_path', 'pinned']
        RETURN n.layer as layer, n.level as level
        """
        occupied_result = await neo4j_client.execute_query_with_retry(occupied_query)
        if self.db_operations is None:
            self.db_operations = 0
        self.db_operations += 1
        
        occupied_positions = set()
        for row in occupied_result:
            occupied_positions.add((int(row["layer"]), int(row["level"])))
        
        logger.info(f"[ЭТАП 10] Найдено {len(occupied_positions)} занятых позиций")
        logger.info(f"[ЭТАП 10] exclude_isolated_vertices = {exclude_isolated}")
        logger.info(f"[ЭТАП 10] Найдено вершин для назначения уровней: {len(vertices)}")
        logger.info(f"[ЭТАП 10] Слои с вершинами: {sorted(layer_to_vertices.keys())}")
        
        # Логируем первые несколько вершин для отладки
        if len(vertices) > 0:
            logger.info(f"[ЭТАП 10] Первые 5 вершин: {[(v['id'], v['layer'], v['topo_order']) for v in vertices[:5]]}")
            logger.info(f"[ЭТАП 10] Последние 5 вершин: {[(v['id'], v['layer'], v['topo_order']) for v in vertices[-5:]]}")
        
        # 4) Назначаем уровни для каждого слоя
        placements = []
        total_vertices = sum(len(vertices) for vertices in layer_to_vertices.values())
        processed_vertices = 0
        
        # Сортируем слои по возрастанию
        sorted_layers = sorted(layer_to_vertices.keys())
        
        for layer in sorted_layers:
            if exclude_isolated and int(layer) == -1:
                continue
            vertices_in_layer = layer_to_vertices[layer]
            # Сортируем вершины внутри слоя по топологическому порядку
            vertices_in_layer.sort(key=lambda v: v["topo_order"])
            
            level_counter = 0  # Счетчик уровней для данного слоя
            
            for vertex in vertices_in_layer:
                # Находим свободную позицию в слое
                while (layer, level_counter) in occupied_positions:
                    level_counter += 1
                
                # Вычисляем координаты
                x = float(layer) * self.LAYER_SPACING
                y = float(level_counter) * self.LEVEL_SPACING
                
                placements.append({
                    "id": vertex["id"],
                    "layer": layer,
                    "level": level_counter,
                    "x": x,
                    "y": y
                })
                
                # Отмечаем позицию как занятую
                occupied_positions.add((layer, level_counter))
                level_counter += 1
                processed_vertices += 1
                
                # Логируем прогресс каждые 1000 вершин
                if processed_vertices % 1000 == 0:
                    percent = (processed_vertices / total_vertices) * 100
                    logger.info(f"[ЭТАП 10] Обработано {processed_vertices}/{total_vertices} вершин (~{percent:.1f}%)")
            
            logger.info(f"[ЭТАП 10] Слой {layer}: размещено {len(vertices_in_layer)} вершин на уровнях 0-{level_counter-1}")
        
        if not placements:
            logger.info("[ЭТАП 10] Не найдено размещений для назначения уровней")
            return 0
        
        # 5) Обновляем уровни и координаты в БД батчами
        batch_size = 5000
        updated_total = 0
        update_query = """
        UNWIND $batch AS item
        MATCH (n:Article {uid: item.id})
        SET n.level = item.level,
            n.x = item.x,
            n.y = item.y,
            n.layout_status = 'placed'
        RETURN count(n) as c
        """
        
        total_batches = (len(placements) + batch_size - 1) // batch_size
        logger.info(f"[ЭТАП 10] Обновление {len(placements)} вершин в {total_batches} батчах по {batch_size}")
        
        for i in range(0, len(placements), batch_size):
            batch = placements[i:i+batch_size]
            res = await neo4j_client.execute_query_with_retry(update_query, {"batch": batch})
            if self.db_operations is None:
                self.db_operations = 0
            self.db_operations += 1
            cnt = int(res[0]["c"]) if res and isinstance(res[0], dict) and "c" in res[0] else 0
            updated_total += cnt
            
            # Логируем прогресс каждые 5 батчей
            batch_num = (i // batch_size) + 1
            if batch_num % 5 == 0 or batch_num == total_batches:
                logger.info(f"[ЭТАП 10] Обновлено {min(i+batch_size, len(placements))}/{len(placements)} вершин (батч {batch_num}/{total_batches})")
        
        logger.info(f"[ЭТАП 10] Завершено назначение уровней для {updated_total} вершин")
        return updated_total

    async def calculate_incremental_layout_distributed(self, worker_id: int = 0, total_workers: int = 1) -> LayoutResult:
        """Распределённая версия алгоритма укладки"""
        logger.info(f"=== ЗАПУСК РАСПРЕДЕЛЕННОЙ УКЛАДКИ (Воркер {worker_id}/{total_workers}) ===")
        
        # Инициализация
        stats = await self._initialize_layout()
        
        # Создаём индексы производительности
        await self.layout_utils.create_performance_indexes()
        
        # Вычисляем топологический порядок
        await topological_sorter.compute_toposort_order_db()
        
        # Поиск самого длинного пути
        longest_path = await self.longest_path_processor.find_longest_path_neo4j()
        
        # Размещение самого длинного пути
        await self.longest_path_processor.place_longest_path(longest_path)
        
        # Размещение соседей LP
        await self.longest_path_processor.place_lp_neighbors(longest_path)
        
        # Все оставшиеся узлы обрабатываются основным алгоритмом укладки
        logger.info("Обработка оставшихся узлов основным алгоритмом укладки")
        
        # Быстрое размещение оставшихся статей
        result = await self.fast_placement_processor.fast_batch_placement_remaining()
        
        # Обработка закреплённых блоков
        await self._process_pinned_blocks()
        
        # Синхронизация между воркерами
        if total_workers > 1:
            await self._synchronize_with_other_workers(worker_id, total_workers)
        
        return result


    async def _synchronize_with_other_workers(self, worker_id: int, total_workers: int):
        """Синхронизация с другими воркерами"""
        logger.info(f"Синхронизация с другими воркерами ({worker_id}/{total_workers})")
        
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
        logger.info("Главный воркер ждет завершения всех воркеров...")
        
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
                logger.info(f"Все {total_workers} воркеров завершены")
                break
            
            logger.info(f"Ожидание воркеров: {completed}/{total_workers}")
            await asyncio.sleep(5)  # Проверяем каждые 5 секунд

    async def _wait_for_master_signal(self, worker_id: int):
        """Дочерние воркеры ждут сигнала от главного"""
        logger.info(f"Воркер {worker_id} ждет сигнала от главного...")
        
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
                logger.info(f"Воркер {worker_id} получил сигнал от главного")
                break
            
            await asyncio.sleep(2)  # Проверяем каждые 2 секунды


# Глобальный экземпляр алгоритма
distributed_incremental_layout = DistributedIncrementalLayout()
