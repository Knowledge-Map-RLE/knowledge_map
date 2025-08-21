"""
Распределённый алгоритм укладки графа на основе существующего layout_algorithm.py
Оптимизирован для обработки больших графов (30M узлов, 80M рёбер).

Ключевые оптимизации:
1. Интеграция с оптимизированным алгоритмом (optimized_layout.py)
2. Использование Neo4j процедур для предварительной обработки
3. Адаптивные стратегии обработки на основе размера данных
4. Мониторинг производительности и отказоустойчивость
"""

import asyncio
import time
from typing import Dict, List, Tuple, Set, Any, Optional
from collections import Counter, defaultdict
import statistics
import logging

import numpy as np
import networkx as nx
from numba import jit, prange
import structlog

from ..config import settings
from ..neo4j_client import neo4j_client
from ..utils.memory_manager import memory_manager
from ..utils.metrics import metrics_collector
from ..utils.circuit_breaker import CircuitBreaker
from .optimized_layout import high_performance_layout

logger = structlog.get_logger(__name__)


class DistributedLayoutAlgorithm:
    """
    Распределённый алгоритм укладки графа с оптимизациями для больших данных
    """

    def __init__(self):
        self.memory_manager = memory_manager
        self.chunk_size = settings.chunk_size
        self.max_iterations = settings.max_iterations
        self.convergence_threshold = settings.convergence_threshold
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=settings.circuit_breaker_failure_threshold,
            recovery_timeout=settings.circuit_breaker_recovery_timeout,
        )
        self.last_progress_log = 0  # Время последнего логирования прогресса
        self.progress_log_interval = 60  # Интервал логирования в секундах

    async def calculate_distributed_layout(
        self,
        node_labels: List[str] = None,
        filters: Optional[Dict] = None,
        options: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Основной метод для распределённого расчёта укладки
        """
        start_time = time.time()
        options = options or {}
        
        logger.info("Starting distributed layout calculation")
        
        try:
            # 1. Получаем статистику графа для планирования через Circuit Breaker
            async with self.circuit_breaker:
                stats = await neo4j_client.get_graph_statistics()
            logger.info("Graph statistics", **stats)
            
            # 2. Определяем адаптивную стратегию обработки
            processing_strategy = self.memory_manager.adaptive_processing_strategy(stats["node_count"])
            system_info = self.memory_manager.get_system_info()
            memory_available = system_info["memory"]["available_gb"]

            logger.info(
                "Processing strategy determined",
                strategy=processing_strategy,
                memory_available=memory_available,
                nodes=stats["node_count"],
                edges=stats["edge_count"]
            )
            
            # 3. Выполняем укладку в зависимости от стратегии
            if processing_strategy == "single_pass":
                result = await self._optimized_single_pass_layout(node_labels, filters, options)
            elif processing_strategy == "chunked":
                result = await self._optimized_chunked_layout(node_labels, filters, options)
            else:  # distributed
                # Если процедуры распределения не установлены, возвращаемся к chunked
                try:
                    result = await self._fully_distributed_layout(node_labels, filters, options)
                except Exception as e:
                    logger.warning("Distributed strategy unavailable, falling back to chunked", error=str(e))
                    result = await self._optimized_chunked_layout(node_labels, filters, options)
            
            # 5. Сохраняем результаты в Neo4j
            if result.get("success"):
                await self._save_layout_results(result)
            
            processing_time = time.time() - start_time
            result["statistics"]["processing_time_seconds"] = processing_time
            
            # Записываем метрики
            metrics_collector.record_task_execution(
                task_name="distributed_layout",
                duration=processing_time,
                success=result.get("success", False),
                nodes_count=stats.get("node_count", 0),
                edges_count=stats.get("edge_count", 0),
            )
            
            logger.info(
                "Distributed layout calculation completed",
                processing_time=processing_time,
                success=result.get("success", False),
            )
            
            return result
            
        except Exception as e:
            logger.error("Distributed layout calculation failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "statistics": {"processing_time_seconds": time.time() - start_time},
            }

    def _determine_processing_strategy(self, stats: Dict[str, Any]) -> str:
        """
        Определяет стратегию обработки на основе размера графа
        """
        node_count = stats["node_count"]
        edge_count = stats["edge_count"]
        
        # Оценка потребления памяти (примерно)
        estimated_memory_gb = (node_count * 200 + edge_count * 100) / (1024**3)
        
        if estimated_memory_gb < settings.memory_limit_gb * 0.5:
            return "single_pass"
        elif estimated_memory_gb < settings.memory_limit_gb:
            return "chunked"
        else:
            return "distributed"

    async def _optimized_single_pass_layout(
        self, 
        node_labels: List[str], 
        filters: Dict, 
        options: Dict
    ) -> Dict[str, Any]:
        """
        Оптимизированная обработка графа за один проход с использованием высокопроизводительного алгоритма
        """
        logger.info("Using optimized single-pass layout strategy")
        
        start_time = time.time()
        
        # Загружаем данные потоково
        nodes = []
        edges = []
        
        async with self.circuit_breaker:
            async for node_chunk in neo4j_client.stream_nodes_chunked(node_labels or [], filters=filters):
                nodes.extend(node_chunk)
                
            node_ids = [node["id"] for node in nodes]
            
            async for edge_chunk in neo4j_client.stream_edges_chunked(node_ids=node_ids):
                edges.extend(edge_chunk)
        
        load_time = time.time() - start_time
        logger.info(f"Data loaded in {load_time:.2f} seconds")
        
        # Применяем высокопроизводительный алгоритм
        algorithm_start = time.time()
        result = high_performance_layout.layout_large_knowledge_map(nodes, edges, options)
        algorithm_time = time.time() - algorithm_start
        
        logger.info(f"High-performance algorithm completed in {algorithm_time:.2f} seconds")
        
        # Записываем метрики производительности
        if result.get("statistics"):
            result["statistics"]["data_load_time"] = load_time
            result["statistics"]["algorithm_time"] = algorithm_time
        
        return result

    async def _optimized_chunked_layout(
        self, 
        node_labels: List[str], 
        filters: Dict, 
        options: Dict
    ) -> Dict[str, Any]:
        """
        Оптимизированная обработка графа по чанкам с адаптивным размером
        """
        logger.info("Using optimized chunked layout strategy")
        
        # Получаем все узлы для построения списка
        all_nodes = []
        async with self.circuit_breaker:
            async for node_chunk in neo4j_client.stream_nodes_chunked(node_labels or [], filters=filters):
                all_nodes.extend(node_chunk)
        
        # Адаптивно определяем размер чанка
        optimal_chunk_size = self.memory_manager.calculate_optimal_chunk_size(len(all_nodes))
        
        # Разбиваем узлы на чанки
        node_chunks = [
            all_nodes[i:i + optimal_chunk_size] 
            for i in range(0, len(all_nodes), optimal_chunk_size)
        ]
        
        logger.info(
            f"Processing {len(node_chunks)} chunks with adaptive size {optimal_chunk_size}"
        )
        
        # Обрабатываем каждый чанк высокопроизводительным алгоритмом
        chunk_results = []
        save_interval = 50  # Сохраняем каждые 50 чанков
        
        for i, node_chunk in enumerate(node_chunks):
            chunk_start = time.time()
            
            # Вычисляем процент прогресса
            progress_percent = ((i + 1) / len(node_chunks)) * 100
            
            # Логируем прогресс не чаще раза в минуту
            current_time = time.time()
            if current_time - self.last_progress_log >= self.progress_log_interval:
                logger.info(f"Progress: {progress_percent:.1f}% - Processing chunk {i+1}/{len(node_chunks)}")
                self.last_progress_log = current_time
            
            try:
                # Получаем рёбра для текущего чанка
                node_ids = [node["id"] for node in node_chunk]
                chunk_edges = []
                
                async with self.circuit_breaker:
                    async for edge_chunk in neo4j_client.stream_edges_chunked(node_ids=node_ids):
                        chunk_edges.extend(edge_chunk)
                
                # Применяем высокопроизводительный алгоритм к чанку
                chunk_result = high_performance_layout.layout_large_knowledge_map(
                    node_chunk, chunk_edges, options
                )
                
                chunk_time = time.time() - chunk_start
                logger.info(f"Chunk {i+1} processed in {chunk_time:.2f} seconds")
                
                if chunk_result.get("success", True):
                    chunk_results.append(chunk_result)
                    
                    # Сохраняем промежуточные результаты каждые N чанков
                    if (i + 1) % save_interval == 0:
                        logger.info(f"Saving intermediate results after chunk {i+1}")
                        try:
                            await self._save_intermediate_results(chunk_results, i + 1)
                        except Exception as e:
                            logger.warning(f"Failed to save intermediate results: {str(e)}")
                else:
                    logger.warning(f"Chunk {i+1} processing failed: {chunk_result.get('error')}")
                    
            except Exception as e:
                logger.error(f"Chunk {i+1} failed with error: {str(e)}")
                # Пытаемся сохранить то, что уже обработано
                if chunk_results:
                    try:
                        await self._save_intermediate_results(chunk_results, i)
                        logger.info(f"Saved {len(chunk_results)} processed chunks before failure")
                    except Exception as save_error:
                        logger.error(f"Failed to save intermediate results: {str(save_error)}")
                raise
        
        # Объединяем результаты чанков
        return await self._merge_optimized_chunk_results(chunk_results)

    async def _optimized_chunked_layout_parallel(self, node_labels, filters, options):
        """Параллельная обработка чанков"""
        logger.info("Using parallel chunked layout strategy")
        
        # Получаем все узлы
        all_nodes = []
        async with self.circuit_breaker:
            async for node_chunk in neo4j_client.stream_nodes_chunked(node_labels or [], filters=filters):
                all_nodes.extend(node_chunk)
        
        # Разбиваем на чанки
        optimal_chunk_size = self.memory_manager.calculate_optimal_chunk_size(len(all_nodes))
        node_chunks = [all_nodes[i:i + optimal_chunk_size] for i in range(0, len(all_nodes), optimal_chunk_size)]
        
        # Определяем количество параллельных процессов
        max_workers = min(multiprocessing.cpu_count(), 4, len(node_chunks))  # Ограничиваем 4 процессами
        
        logger.info(f"Processing {len(node_chunks)} chunks in parallel with {max_workers} workers")
        
        # Параллельная обработка чанков
        chunk_results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Создаём задачи для каждого чанка
            future_to_chunk = {}
            for i, node_chunk in enumerate(node_chunks):
                future = executor.submit(
                    self._process_chunk_sync, 
                    node_chunk, 
                    i, 
                    len(node_chunks), 
                    options
                )
                future_to_chunk[future] = i
            
            # Обрабатываем результаты по мере завершения
            completed_chunks = 0
            for future in concurrent.futures.as_completed(future_to_chunk):
                chunk_index = future_to_chunk[future]
                try:
                    result = future.result()
                    if result.get("success", True):
                        chunk_results.append(result)
                    
                    completed_chunks += 1
                    progress_percent = (completed_chunks / len(node_chunks)) * 100
                    
                    # Логируем прогресс каждые 10% или каждую минуту
                    current_time = time.time()
                    if (completed_chunks % max(1, len(node_chunks) // 10) == 0 or 
                        current_time - self.last_progress_log >= self.progress_log_interval):
                        logger.info(f"Progress: {progress_percent:.1f}% - Completed {completed_chunks}/{len(node_chunks)} chunks")
                        self.last_progress_log = current_time
                        
                except Exception as e:
                    logger.error(f"Chunk {chunk_index} processing failed: {str(e)}")
        
        return await self._merge_optimized_chunk_results(chunk_results)

    def _process_chunk_sync(self, node_chunk, chunk_index, total_chunks, options):
        """Синхронная обработка чанка (для ThreadPoolExecutor)"""
        chunk_start = time.time()
        
        # Получаем рёбра для чанка (синхронно)
        node_ids = [node["id"] for node in node_chunk]
        chunk_edges = []
        
        # Используем синхронный Neo4j клиент для этого потока
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Получаем рёбра синхронно
            edges_query = """
            MATCH (source)-[r:CITES]->(target)
            WHERE source.uid IN $node_ids OR target.uid IN $node_ids
            RETURN source.uid as source_id, target.uid as target_id
            """
            edges_result = loop.run_until_complete(
                neo4j_client.execute_query_with_retry(edges_query, {"node_ids": node_ids})
            )
            chunk_edges = edges_result
            
            # Применяем алгоритм укладки
            result = high_performance_layout.layout_large_knowledge_map(
                node_chunk, chunk_edges, options
            )
            
            chunk_time = time.time() - chunk_start
            logger.info(f"Chunk {chunk_index + 1}/{total_chunks} processed in {chunk_time:.2f} seconds")
            
            return result
            
        finally:
            loop.close()

    async def _fully_distributed_layout(
        self, 
        node_labels: List[str], 
        filters: Dict, 
        options: Dict
    ) -> Dict[str, Any]:
        """
        Полностью распределённая обработка с использованием Celery задач
        """
        logger.info("Using fully distributed layout strategy")
        
        # Получаем компоненты связности через Neo4j процедуры
        async with self.circuit_breaker:
            # Вызываем Neo4j процедуру для разбиения графа
            partitioning_query = """
            CALL distributed_layout.partition_graph($maxComponentSize)
            YIELD componentId, nodeIds, edgeCount
            RETURN componentId, nodeIds, edgeCount
            ORDER BY edgeCount DESC
            """
            
            max_component_size = self.chunk_size
            components = await neo4j_client.execute_query_with_retry(
                partitioning_query, 
                {"maxComponentSize": max_component_size}
            )
        
        logger.info(f"Graph partitioned into {len(components)} components")
        
        # Создаём Celery задачи для каждой компоненты
        from ..tasks import process_graph_chunk
        
        # Запускаем задачи асинхронно
        task_futures = []
        for component in components:
            component_id = component["componentId"]
            node_ids = component["nodeIds"]
            
            # Получаем данные компоненты
            async with self.circuit_breaker:
                component_query = """
                CALL distributed_layout.get_component_subgraph($componentId, $batchSize)
                YIELD nodes, edges
                RETURN nodes, edges
                """
                
                component_data = await neo4j_client.execute_query_with_retry(
                    component_query,
                    {"componentId": component_id, "batchSize": 1000}
                )
            
            if component_data:
                nodes = component_data[0]["nodes"]
                edges = component_data[0]["edges"]
                
                # Запускаем Celery задачу
                task = process_graph_chunk.delay(
                    nodes=nodes,
                    edges=edges,
                    chunk_id=f"component_{component_id}",
                    options=options
                )
                task_futures.append((component_id, task))
        
        # Ожидаем завершения всех задач
        component_results = []
        for component_id, task in task_futures:
            try:
                result = task.get(timeout=3600)  # 1 час timeout
                if result.get("success", True):
                    component_results.append(result)
                else:
                    logger.error(f"Component {component_id} processing failed: {result.get('error')}")
            except Exception as e:
                logger.error(f"Component {component_id} task failed: {e}")
        
        # Объединяем результаты компонент
        return await self._merge_distributed_results(component_results)

    async def _single_pass_layout(
        self, 
        node_labels: List[str], 
        filters: Dict, 
        options: Dict
    ) -> Dict[str, Any]:
        """
        Обработка графа за один проход (для небольших графов)
        """
        logger.info("Using single-pass layout strategy")
        
        # Загружаем весь граф в память
        nodes = []
        edges = []
        
        async for node_chunk in neo4j_client.stream_nodes_chunked(node_labels or [], filters=filters):
            nodes.extend(node_chunk)
            
        node_ids = [node["id"] for node in nodes]
        
        async for edge_chunk in neo4j_client.stream_edges_chunked(node_ids=node_ids):
            edges.extend(edge_chunk)
        
        # Применяем существующий алгоритм
        return await self._apply_layout_algorithm(nodes, edges, options)

    async def _chunked_layout(
        self, 
        node_labels: List[str], 
        filters: Dict, 
        options: Dict
    ) -> Dict[str, Any]:
        """
        Обработка графа по чанкам (для средних графов)
        """
        logger.info("Using chunked layout strategy")
        
        # Получаем все узлы для построения полного списка ID
        all_nodes = []
        async for node_chunk in neo4j_client.stream_nodes_chunked(node_labels or [], filters=filters):
            all_nodes.extend(node_chunk)
        
        # Разбиваем узлы на чанки для обработки
        node_chunks = [
            all_nodes[i:i + self.chunk_size] 
            for i in range(0, len(all_nodes), self.chunk_size)
        ]
        
        # Обрабатываем каждый чанк
        chunk_results = []
        for i, node_chunk in enumerate(node_chunks):
            logger.info(f"Processing chunk {i+1}/{len(node_chunks)}")
            
            # Получаем рёбра для текущего чанка
            node_ids = [node["id"] for node in node_chunk]
            chunk_edges = []
            
            async for edge_chunk in neo4j_client.stream_edges_chunked(node_ids=node_ids):
                chunk_edges.extend(edge_chunk)
            
            # Применяем алгоритм к чанку
            chunk_result = await self._apply_layout_algorithm(node_chunk, chunk_edges, options)
            chunk_results.append(chunk_result)
        
        # Объединяем результаты чанков
        return await self._merge_chunk_results(chunk_results)

    async def _merge_optimized_chunk_results(self, chunk_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Оптимизированное объединение результатов чанков с улучшенной логикой
        """
        if not chunk_results:
            return {"success": False, "error": "No chunk results to merge"}
        
        logger.info(f"Merging {len(chunk_results)} chunk results")
        
        # Объединяем блоки
        all_blocks = []
        total_stats = defaultdict(int)
        
        for result in chunk_results:
            if result.get("blocks"):
                all_blocks.extend(result["blocks"])
            
            # Агрегируем статистику
            if result.get("statistics"):
                for key, value in result["statistics"].items():
                    if isinstance(value, (int, float)):
                        total_stats[key] += value
        
        # Пересчитываем глобальную укладку
        # Группируем блоки по закреплённости
        pinned_blocks = [block for block in all_blocks if block.get("is_pinned", False)]
        unpinned_blocks = [block for block in all_blocks if not block.get("is_pinned", False)]
        
        # Создаём оптимизированную структуру уровней
        sublevels = {}
        levels = {}
        layers_dict = {}
        
        # Сначала размещаем закреплённые блоки (каждый на своём уровне)
        sublevel_counter = 0
        level_counter = 0
        
        for block in pinned_blocks:
            block_id = block["id"]
            block_layer = block.get("layer", 0)
            
            # Каждый закреплённый блок получает свой уровень и подуровень
            sublevels[sublevel_counter] = [block_id]
            levels[level_counter] = [sublevel_counter]
            layers_dict[block_id] = block_layer
            
            # Обновляем информацию в блоке
            block["level"] = level_counter
            block["sublevel_id"] = sublevel_counter
            
            sublevel_counter += 1
            level_counter += 1
        
        # Затем размещаем незакреплённые блоки (все в одном уровне, сгруппированные по слоям)
        if unpinned_blocks:
            unpinned_by_layer = defaultdict(list)
            for block in unpinned_blocks:
                layer = block.get("layer", 0)
                unpinned_by_layer[layer].append(block["id"])
                layers_dict[block["id"]] = layer
            
            sublevel_ids_for_level = []
            for layer in sorted(unpinned_by_layer.keys()):
                layer_blocks = unpinned_by_layer[layer]
                sublevels[sublevel_counter] = layer_blocks
                sublevel_ids_for_level.append(sublevel_counter)
                
                # Обновляем информацию в блоках
                for block in unpinned_blocks:
                    if block["id"] in layer_blocks:
                        block["level"] = level_counter
                        block["sublevel_id"] = sublevel_counter
                
                sublevel_counter += 1
            
            if sublevel_ids_for_level:
                levels[level_counter] = sublevel_ids_for_level
        
        # Финальная статистика
        final_statistics = {
            "total_blocks": len(all_blocks),
            "total_levels": len(levels),
            "total_sublevels": len(sublevels),
            "pinned_blocks": len(pinned_blocks),
            "unpinned_blocks": len(unpinned_blocks),
            "max_layer": max(layers_dict.values()) if layers_dict else 0,
            "chunks_processed": len(chunk_results),
        }
        
        # Добавляем агрегированную статистику
        final_statistics.update(total_stats)
        
        logger.info("Chunk results merged successfully", **final_statistics)
        
        return {
            "success": True,
            "blocks": all_blocks,
            "layers": layers_dict,
            "sublevels": sublevels,
            "levels": levels,
            "statistics": final_statistics,
        }

    async def _merge_distributed_results(self, component_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Объединение результатов распределённой обработки компонент
        """
        logger.info(f"Merging {len(component_results)} distributed component results")
        
        # Используем тот же алгоритм что и для чанков, но с учётом компонент
        return await self._merge_optimized_chunk_results(component_results)

    async def _distributed_layout(
        self, 
        node_labels: List[str], 
        filters: Dict, 
        options: Dict
    ) -> Dict[str, Any]:
        """
        Полностью распределённая обработка (для очень больших графов)
        """
        logger.info("Using distributed layout strategy")
        
        # Здесь будет интеграция с Celery для распределённой обработки
        # Пока используем упрощённую версию
        return await self._chunked_layout(node_labels, filters, options)

    async def _apply_layout_algorithm(
        self, 
        nodes: List[Dict], 
        edges: List[Dict], 
        options: Dict
    ) -> Dict[str, Any]:
        """
        Применяет алгоритм укладки к подграфу
        """
        # Подготавливаем данные в формате, совместимом с существующим алгоритмом
        blocks = [node["id"] for node in nodes]
        links = [(edge["source_id"], edge["target_id"]) for edge in edges]
        
        # Подготавливаем blocks_data
        blocks_data = {}
        for node in nodes:
            blocks_data[node["id"]] = {
                "is_pinned": bool(node.get("is_pinned", False)),
                "level": int(node.get("level", 0)),
                "physical_scale": int(node.get("physical_scale", 0)),
            }
        
        layout_options = {
            "optimize_layout": options.get("optimize_layout", True),
            "blocks_data": blocks_data,
        }
        
        # Импортируем и применяем существующий алгоритм
        from layering.src.layout_algorithm import layout_knowledge_map
        
        result = layout_knowledge_map(blocks, links, layout_options)
        
        # Дополняем результат информацией об узлах
        if result.get("success", True):  # layout_knowledge_map не возвращает success
            enhanced_blocks = []
            for node in nodes:
                node_id = node["id"]
                enhanced_block = {
                    "id": node_id,
                    "content": node.get("content", ""),
                    "layer": result["layers"].get(node_id, 0),
                    "is_pinned": node.get("is_pinned", False),
                    "physical_scale": node.get("physical_scale", 0),
                    "metadata": {},
                }
                
                # Находим уровень и подуровень
                for level_id, sublevel_ids in result["levels"].items():
                    for sublevel_id in sublevel_ids:
                        if node_id in result["sublevels"].get(sublevel_id, []):
                            enhanced_block["level"] = level_id
                            enhanced_block["sublevel_id"] = sublevel_id
                            break
                
                enhanced_blocks.append(enhanced_block)
            
            result["blocks"] = enhanced_blocks
            result["success"] = True
        
        return result

    async def _merge_chunk_results(self, chunk_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Объединяет результаты обработки чанков
        """
        if not chunk_results:
            return {"success": False, "error": "No chunk results to merge"}
        
        # Объединяем блоки
        all_blocks = []
        for result in chunk_results:
            if result.get("blocks"):
                all_blocks.extend(result["blocks"])
        
        # Объединяем слои
        all_layers = {}
        for result in chunk_results:
            if result.get("layers"):
                all_layers.update(result["layers"])
        
        # Пересчитываем уровни и подуровни глобально
        # Это упрощённая версия - в реальности нужна более сложная логика
        sublevels = {}
        levels = {}
        
        # Группируем блоки по слоям
        blocks_by_layer = defaultdict(list)
        for block in all_blocks:
            layer = block.get("layer", 0)
            blocks_by_layer[layer].append(block["id"])
        
        # Создаём подуровни и уровни
        sublevel_counter = 0
        level_counter = 0
        
        for layer in sorted(blocks_by_layer.keys()):
            block_ids = blocks_by_layer[layer]
            
            # Создаём подуровень для слоя
            sublevels[sublevel_counter] = block_ids
            
            # Создаём уровень
            levels[level_counter] = [sublevel_counter]
            
            # Обновляем информацию в блоках
            for block in all_blocks:
                if block["id"] in block_ids:
                    block["level"] = level_counter
                    block["sublevel_id"] = sublevel_counter
            
            sublevel_counter += 1
            level_counter += 1
        
        # Собираем статистику
        total_statistics = {
            "total_blocks": len(all_blocks),
            "total_links": sum(result.get("statistics", {}).get("total_links", 0) for result in chunk_results),
            "total_levels": len(levels),
            "total_sublevels": len(sublevels),
            "max_layer": max(all_layers.values()) if all_layers else 0,
            "is_acyclic": all(result.get("statistics", {}).get("is_acyclic", True) for result in chunk_results),
            "isolated_blocks": sum(result.get("statistics", {}).get("isolated_blocks", 0) for result in chunk_results),
            "pinned_blocks": sum(1 for block in all_blocks if block.get("is_pinned", False)),
            "unpinned_blocks": sum(1 for block in all_blocks if not block.get("is_pinned", False)),
        }
        
        return {
            "success": True,
            "blocks": all_blocks,
            "layers": all_layers,
            "sublevels": sublevels,
            "levels": levels,
            "statistics": total_statistics,
        }

    async def _save_layout_results(self, result: Dict[str, Any]) -> None:
        """
        Сохраняет результаты укладки в Neo4j
        """
        if not result.get("blocks"):
            return
        
        logger.info("Saving layout results to Neo4j")
        
        # Подготавливаем данные для сохранения
        node_positions = []
        for block in result["blocks"]:
            node_positions.append({
                "id": block["id"],
                "level": block.get("level", 0),
                "sublevel_id": block.get("sublevel_id", 0),
                "layer": block.get("layer", 0),
            })
        
        # Сохраняем батчами
        await neo4j_client.batch_update_positions(node_positions)
        
        logger.info(f"Saved positions for {len(node_positions)} nodes")

    async def _save_intermediate_results(self, chunk_results: List[Dict[str, Any]], current_chunk_index: int) -> None:
        """
        Сохраняет промежуточные результаты укладки после каждого N чанков.
        """
        if not chunk_results:
            return
        
        logger.info(f"Saving intermediate results for chunk {current_chunk_index}")
        
        # Подготавливаем данные для сохранения из всех обработанных чанков
        node_positions = []
        for chunk_result in chunk_results:
            if "blocks" in chunk_result:
                for block in chunk_result["blocks"]:
                    node_positions.append({
                        "id": block["id"],
                        "level": block.get("level", 0),
                        "sublevel_id": block.get("sublevel_id", 0),
                        "layer": block.get("layer", 0),
                    })
        
        # Сохраняем батчами
        if node_positions:
            await neo4j_client.batch_update_positions(node_positions)
            logger.info(f"Saved positions for {len(node_positions)} nodes from {len(chunk_results)} chunks")
        else:
            logger.warning("No node positions to save")


# Оптимизированные функции с Numba JIT
if settings.enable_numba_jit:
    @jit(nopython=True, parallel=True)
    def _optimize_layers_numba(
        layers: np.ndarray, 
        predecessors: np.ndarray, 
        successors: np.ndarray,
        max_iterations: int = 100
    ) -> np.ndarray:
        """
        Оптимизированная версия двухпроходного алгоритма с Numba JIT
        """
        n = len(layers)
        optimized_layers = layers.copy()
        
        for iteration in prange(max_iterations):
            changed = False
            
            # Прямой проход
            for i in prange(n):
                if len(predecessors[i]) > 0:
                    min_layer = np.max(optimized_layers[predecessors[i]]) + 1
                    if optimized_layers[i] < min_layer:
                        optimized_layers[i] = min_layer
                        changed = True
            
            # Обратный проход
            for i in prange(n-1, -1, -1):
                if len(successors[i]) > 0:
                    max_layer = np.min(optimized_layers[successors[i]]) - 1
                    if optimized_layers[i] > max_layer:
                        optimized_layers[i] = max_layer
                        changed = True
            
            if not changed:
                break
        
        return optimized_layers


# Глобальный экземпляр алгоритма
distributed_layout = DistributedLayoutAlgorithm()
