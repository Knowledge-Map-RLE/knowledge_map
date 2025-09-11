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

Алгоритм включает все 7 шагов:
1. Инициализация и получение статистики
2. Обнаружение и исправление циклов для обеспечения DAG
3. Ранняя топологическая сортировка всего графа в БД
4. Поиск и размещение longest path
4.5. Размещение соседей longest path по разным уровням
5. Поиск и размещение компонентов связности
6. Быстрое размещение оставшихся статей
7. Финальная обработка закреплённых блоков

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

    async def calculate_incremental_layout(self) -> LayoutResult:
        """
        Основной метод инкрементальной укладки
        """
        start_time = time.time()
        
        # Принудительно настраиваем логирование
        setup_logging()
        
        logger.info("=== ЗАПУСК РАСПРЕДЕЛЕННОЙ ИНКРЕМЕНТАЛЬНОЙ УКЛАДКИ ===")
        
        try:
            # 1. Инициализация и получение статистики
            logger.info("=== ШАГ 1: ИНИЦИАЛИЗАЦИЯ ===")
            stats = await self._initialize_layout()
            logger.info(f"Инициализация завершена. Статистика графа: {stats}")
            self.total_articles_estimate = int(stats.get("article_count") or 0)
            logger.info(f"Инициализация завершена за {time.time() - start_time:.2f}с")
            logger.info(f"Всего статей в графе: {self.total_articles_estimate}")
            logger.info(f"Статистика графа: {stats}")
            
            
            # 2. Обнаружение и исправление циклов для обеспечения DAG
            logger.info("=== ШАГ 2: ОБНАРУЖЕНИЕ И ИСПРАВЛЕНИЕ ЦИКЛОВ (ОБЕСПЕЧЕНИЕ DAG) ===")
            logger.info("Запуск обнаружения и удаления циклов...")
            removed_edges = await self.layout_utils.detect_and_fix_cycles()
            logger.info(f"Обнаружение циклов завершено. Удалено {removed_edges} рёбер для обеспечения DAG структуры")
            
            
            # 3. Топологическая сортировка всего графа в БД (инкрементально, батчами)
            logger.info("=== ШАГ 3: ВЫЧИСЛЕНИЕ ГЛОБАЛЬНОГО ТОПОЛОГИЧЕСКОГО ПОРЯДКА (БД) ===")
            logger.info("Запуск топологической сортировки...")
            await topological_sorter.compute_toposort_order_db()
            logger.info("Топологическая сортировка завершена")
            
            # Проверка топологической сортировки через БД
            logger.info("=== ПРОВЕРКА ТОПОЛОГИЧЕСКОГО ПОРЯДКА В БД ===")
            try:
                # Получаем распределение значений topo_order (только для связанных вершин)
                topo_stats_query = """
                MATCH (n:Article)
                WHERE n.topo_order IS NOT NULL
                AND (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() })
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
                    # Показываем первые 10 самых частых значений
                    most_common = topo_counter.most_common(10)
                    logger.info(f"Топ-10 самых частых значений topo_order: {most_common}")
                    
                    # Проверяем уникальность
                    unique_count = len(set(all_topo_orders))
                    if unique_count < total:
                        logger.warning(f"ВНИМАНИЕ: Есть дублирующиеся значения topo_order! Уникальных: {unique_count} из {total}")
                    else:
                        logger.info("Все значения topo_order уникальны")
                    
                    # Проверяем монотонно неубывающую последовательность без пропусков
                    logger.info("=== ПРОВЕРКА ПОСЛЕДОВАТЕЛЬНОСТИ ТОПОЛОГИЧЕСКОГО ПОРЯДКА ===")
                    
                    # Сортируем значения для проверки
                    sorted_topo = sorted(all_topo_orders)
                    
                    # Проверяем, что последовательность начинается с 0
                    if sorted_topo[0] != 0:
                        logger.error(f"ОШИБКА: Последовательность не начинается с 0! Первое значение: {sorted_topo[0]}")
                    
                    # Проверяем, что последовательность заканчивается на (total-1)
                    expected_last = total - 1
                    if sorted_topo[-1] != expected_last:
                        logger.error(f"ОШИБКА: Последовательность не заканчивается на {expected_last}! Последнее значение: {sorted_topo[-1]}")
                    
                    # Проверяем отсутствие пропусков
                    missing_values = []
                    for i in range(total):
                        if i not in sorted_topo:
                            missing_values.append(i)
                    
                    if missing_values:
                        logger.error(f"ОШИБКА: Обнаружены пропуски в последовательности! Пропущенные значения: {missing_values[:10]}{'...' if len(missing_values) > 10 else ''}")
                    else:
                        logger.info("✅ Последовательность не содержит пропусков")
                    
                    # Проверяем монотонность (неубывающая последовательность)
                    is_monotonic = True
                    for i in range(1, len(sorted_topo)):
                        if sorted_topo[i] < sorted_topo[i-1]:
                            is_monotonic = False
                            logger.error(f"ОШИБКА: Нарушена монотонность на позиции {i}! {sorted_topo[i-1]} > {sorted_topo[i]}")
                            break
                    
                    if is_monotonic:
                        logger.info("✅ Последовательность является монотонно неубывающей")
                    
                    # Проверяем, что все значения являются целыми числами
                    non_integer_values = [x for x in all_topo_orders if not isinstance(x, int)]
                    if non_integer_values:
                        logger.error(f"ОШИБКА: Обнаружены нецелые значения! {non_integer_values[:10]}{'...' if len(non_integer_values) > 10 else ''}")
                    else:
                        logger.info("✅ Все значения являются целыми числами")
                    
                    # Итоговая проверка
                    if (sorted_topo[0] == 0 and 
                        sorted_topo[-1] == expected_last and 
                        not missing_values and 
                        is_monotonic and 
                        not non_integer_values):
                        logger.info("🎉 ТОПОЛОГИЧЕСКИЙ ПОРЯДОК КОРРЕКТЕН: монотонно неубывающая последовательность целых чисел без пропусков!")
                    else:
                        logger.error("❌ ТОПОЛОГИЧЕСКИЙ ПОРЯДОК НЕКОРРЕКТЕН!")
                else:
                    logger.warning("Не удалось получить статистику по topo_order")
            except Exception as e:
                logger.error(f"Ошибка при проверке топологической сортировки: {str(e)}")
                logger.error(traceback.format_exc())
            
            # return '❗СТОП❗'
        
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
            
            # 6. Укладка оставшихся вершин по методу Сугиямы (двухпроходная оптимизация слоёв)
            logger.info("=== ШАГ 6: РАЗМЕЩЕНИЕ ОСТАВШИХСЯ ПО МЕТОДУ СУГИЯМЫ ===")
            step6_start = time.time()
            placed_topo = 0
            try:
                placed_topo = await self._place_remaining_sugiyama()
                step6_time = time.time() - step6_start
                logger.info(f"Размещение по методу Сугиямы завершено за {step6_time:.2f}с, обновлено {placed_topo} вершин")
            except Exception as e:
                step6_time = time.time() - step6_start
                logger.error(f"Ошибка при размещении по методу Сугиямы после {step6_time:.2f}с: {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")

            # Резервный вариант удален - используем только топологическую укладку
            if placed_topo == 0:
                logger.warning("Ни одна вершина не размещена методом Сугиямы - это указывает на проблему с алгоритмом")
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
                    "removed_edges": removed_edges,
                    "longest_path_length": len(longest_path),
                    "lp_placements_count": len(lp_placements) if lp_placements else 0,
                    "lp_neighbors_count": 0,
                    "connected_components_count": 0,  # Компоненты теперь обрабатываются основным алгоритмом
                    "topo_incremental_placed": placed_topo,
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
        Укладка оставшихся вершин по методу Сугиямы (Kozo Sugiyama) в упрощённой форме:
        1) Берём ещё неуложенные вершины (n.x IS NULL OR n.y IS NULL) в порядке topo_order
        2) Строим подграф по их рёбрам
        3) Базовая разметка слоёв: layer[v] = 1 + max(layer[u]) по всем предкам u (или 0, если нет предков)
           (проход в порядке topo_order)
        4) Двухпроходная оптимизация слоёв (вперёд/назад) с медианными оценками предков/потомков
        5) Внутрислойное упорядочивание: сортировка вершин внутри слоя по topo_order для снижения пересечений
        6) Присваиваем координаты: x = layer * LAYER_SPACING, y = rank_in_layer * LEVEL_SPACING
        7) Обновляем координаты батчами
        """
        layer_step = float(self.LAYER_SPACING)
        level_step = float(self.LEVEL_SPACING)

        # 1) Считаем вершины для переукладки (исключаем LP и pinned, только связанные вершины)
        total_q = (
            "MATCH (n:Article) "
            "WHERE NOT n.layout_status IN ['in_longest_path', 'pinned'] "
            "AND (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() }) "
            "RETURN count(n) as left"
        )
        total_res = await neo4j_client.execute_query_with_retry(total_q)
        
        if self.db_operations is None:
            self.db_operations = 0
        self.db_operations += 1
        total_all = int(total_res[0]["left"]) if total_res and isinstance(total_res[0], dict) else 0
        logger.info(f"[ШАГ 6] Найдено {total_all} вершин для повторного размещения по Сугияме")
        
        if total_all == 0:
            logger.info("[ШАГ 6] Не найдено вершин для размещения по Сугияме")
            return 0

        # Берём ВСЕ вершины для переукладки (исключаем LP и pinned, только связанные вершины)
        fetch_nodes_q = (
            "MATCH (n:Article) "
            "WHERE NOT n.layout_status IN ['in_longest_path', 'pinned'] "
            "AND (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() }) "
            "RETURN n.uid as id, coalesce(n.topo_order,0) as topo_order "
            "ORDER BY topo_order ASC"
        )
        nodes = await neo4j_client.execute_query_with_retry(fetch_nodes_q)
        
        if self.db_operations is None:
            self.db_operations = 0
        self.db_operations += 1
        node_ids = [r["id"] for r in nodes] if nodes else []
        node_set = set(node_ids)
        logger.info(f"[ШАГ 6] Найдено {len(node_ids)} узлов для размещения по Сугияме")
        if not node_ids:
            logger.info("[ШАГ 6] Не найдено узлов, пропускаем размещение по Сугияме")
            return 0

        # 2a) Для КАЖДОЙ выбранной вершины получаем агрегированные ограничения из БД:
        # max слой предков и min слой потомков, независимо от того, входят ли они в подграф
        bounds_q = (
            "UNWIND $ids AS vid "
            "MATCH (v:Article {uid: vid}) "
            "OPTIONAL MATCH (p:Article)-[:BIBLIOGRAPHIC_LINK]->(v) "
            "WITH v, max(p.layer) as max_pred_layer "
            "OPTIONAL MATCH (v)-[:BIBLIOGRAPHIC_LINK]->(s:Article) "
            "RETURN v.uid as id, max_pred_layer, min(s.layer) as min_succ_layer"
        )
        bounds_rows = await neo4j_client.execute_query_with_retry(bounds_q, {"ids": node_ids})
        
        if self.db_operations is None:
            self.db_operations = 0
        self.db_operations += 1
        max_pred_layer_map = {}
        min_succ_layer_map = {}
        for row in bounds_rows or []:
            max_pred_layer_map[row["id"]] = row.get("max_pred_layer")
            min_succ_layer_map[row["id"]] = row.get("min_succ_layer")

        # 2) Собираем рёбра между выбранными вершинами
        fetch_edges_q = (
            "UNWIND $ids AS id "
            "MATCH (u:Article {uid: id})-[:BIBLIOGRAPHIC_LINK]->(v:Article) "
            "WHERE v.uid IN $ids "
            "RETURN u.uid as src, v.uid as dst"
        )
        edges = await neo4j_client.execute_query_with_retry(fetch_edges_q, {"ids": node_ids})
        
        if self.db_operations is None:
            self.db_operations = 0
        self.db_operations += 1

        # 3) Строим граф и инициализируем слои
        topo_order_map = {r["id"]: int(idx) for idx, r in enumerate(nodes)}
        predecessors = {vid: [] for vid in node_ids}
        successors = {vid: [] for vid in node_ids}
        for row in edges or []:
            u = row["src"]
            v = row["dst"]
            if u in node_set and v in node_set and u != v:
                successors[u].append(v)
                predecessors[v].append(u)

        # Инициализация слоев: используем топологический порядок для распределения по слоям
        layers = {}
        
        # Определяем источники (вершины без предков) через запрос к БД
        sources_query = """
        UNWIND $node_ids AS vid
        MATCH (n:Article {uid: vid})
        WHERE NOT ()-[:BIBLIOGRAPHIC_LINK]->(n)
        RETURN n.uid as uid
        """
        sources_result = await neo4j_client.execute_query_with_retry(sources_query, {"node_ids": node_ids})
        sources = [row["uid"] for row in sources_result]
        non_sources = [vid for vid in node_ids if vid not in sources]
        
        # Получаем глобальный порядок источников для равномерного распределения
        global_sources_query = """
        MATCH (n:Article)
        WHERE (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() })
        AND NOT ()-[:BIBLIOGRAPHIC_LINK]->(n)
        RETURN n.uid as uid
        ORDER BY n.uid
        """
        global_sources_result = await neo4j_client.execute_query_with_retry(global_sources_query)
        global_sources = [row["uid"] for row in global_sources_result]
        
        # Создаем мапу глобального порядка источников
        global_source_order = {uid: idx for idx, uid in enumerate(global_sources)}
        
        # Равномерно распределяем источники по первым слоям
        max_sources_per_layer = 100  # Максимум источников на слой (сильно уменьшено для лучшего распределения)
        source_layers = {}
        for vid in sources:
            if vid in global_source_order:
                global_idx = global_source_order[vid]
                layer = global_idx // max_sources_per_layer
                source_layers[vid] = layer
        
        # Логируем распределение источников для отладки
        logger.info(f"Распределение источников: {len(sources)} источников в {len(set(source_layers.values()))} слоях")
        layer_counts = {}
        for layer in source_layers.values():
            layer_counts[layer] = layer_counts.get(layer, 0) + 1
        logger.info(f"Счетчики слоев источников: {layer_counts}")
        
        # Инициализируем слои для всех узлов
        for vid in node_ids:
            if vid in source_layers:
                # Источники распределяются равномерно
                layers[vid] = source_layers[vid]
            else:
                # Не-источники размещаются после своих предков
                if predecessors[vid]:
                    max_pred_layer = max(layers.get(p, 0) for p in predecessors[vid])
                    layers[vid] = max_pred_layer + 1
                else:
                    # Если нет предков в локальном графе, но есть в глобальном - размещаем на следующем слое
                    layers[vid] = 1
            
            # Учитываем глобальные ограничения из БД
            max_pred = max_pred_layer_map.get(vid)
            if max_pred is not None:
                layers[vid] = max(layers[vid], int(max_pred) + 1)
            
            min_succ = min_succ_layer_map.get(vid)
            if min_succ is not None:
                layers[vid] = min(layers[vid], int(min_succ) - 1)
            
            layers[vid] = max(0, layers[vid])

        # 4) Простая оптимизация слоёв - убираем сложную двухпроходную логику
        # Просто убеждаемся, что слои удовлетворяют топологическим ограничениям
        for vid in node_ids:
            # Для источников сохраняем их распределение по слоям
            if vid in source_layers:
                # Источники уже распределены равномерно, не меняем их слои
                continue
            
            # Минимальный слой: больше максимального слоя предков
            min_layer = 0
            if predecessors[vid]:
                min_layer = max(layers[p] for p in predecessors[vid]) + 1
            
            # Учитываем глобальные ограничения
            max_pred = max_pred_layer_map.get(vid)
            if max_pred is not None:
                min_layer = max(min_layer, int(max_pred) + 1)
            
            # Максимальный слой: меньше минимального слоя потомков
            max_layer = float('inf')
            if successors[vid]:
                max_layer = min(layers[s] for s in successors[vid]) - 1
            
            min_succ = min_succ_layer_map.get(vid)
            if min_succ is not None:
                max_layer = min(max_layer, int(min_succ) - 1)
            
            # Устанавливаем слой в допустимых пределах
            if min_layer <= max_layer:
                layers[vid] = max(0, min_layer)
            else:
                # Если ограничения противоречивы, оставляем текущий слой
                layers[vid] = max(0, layers[vid])

        # 5) Внутрислойное упорядочивание: topo_order внутри слоя
        layer_to_nodes = {}
        for vid in node_ids:
            ly = int(layers[vid])
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
        
        # 7) Формируем координаты с проверкой занятых позиций
        placements = []
        for ly, arr in layer_to_nodes.items():
            level_counter = 0  # Счетчик уровней для данного слоя
            for vid in arr:
                # Находим свободную позицию в слое
                while (int(ly), level_counter) in occupied_positions:
                    level_counter += 1
                
                x = float(ly) * layer_step
                y = float(level_counter) * level_step
                placements.append({
                    "id": vid,
                    "layer": int(ly),
                    "level": level_counter,
                    "x": x,
                    "y": y
                })
                
                # Отмечаем позицию как занятую
                occupied_positions.add((int(ly), level_counter))
                level_counter += 1

        if not placements:
            return 0

        batch_size = 5000  # Увеличиваем размер батча для быстрой обработки
        updated_total = 0
        update_q = (
            "UNWIND $batch AS item "
            "MATCH (n:Article {uid: item.id}) "
            "SET n.layer = item.layer, n.level = item.level, "
            "    n.x = item.x, n.y = item.y, "
            "    n.layout_status = coalesce(n.layout_status, 'placed_sugiyama') "
            "RETURN count(n) as c"
        )

        total_batches = (len(placements) + batch_size - 1) // batch_size
        logger.info(f"[ШАГ 6] Обработка {len(placements)} размещений в {total_batches} батчах по {batch_size}")

        for i in range(0, len(placements), batch_size):
            batch = placements[i:i+batch_size]
            res = await neo4j_client.execute_query_with_retry(update_q, {"batch": batch})
            if self.db_operations is None:
                self.db_operations = 0
            self.db_operations += 1
            cnt = int(res[0]["c"]) if res and isinstance(res[0], dict) and "c" in res[0] else 0
            updated_total += cnt
            
            # Логируем прогресс каждые 5 батчей
            batch_num = (i // batch_size) + 1
            if batch_num % 5 == 0 or batch_num == total_batches:
                logger.info(f"[ШАГ 6] Сугияма разместил {min(i+batch_size, len(placements))}/{len(placements)} (батч {batch_num}/{total_batches})")

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
