"""
Модуль для работы с компонентами связности в алгоритме укладки
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from ..neo4j_client import neo4j_client
from ..utils.simple_circuit_breaker import CircuitBreaker
from .layout_types import VertexStatus, VertexPosition
from .positioning import PositionCalculator

logger = logging.getLogger(__name__)


class ComponentProcessor:
    """Обработчик компонент связности для укладки графа"""
    
    def __init__(self, circuit_breaker: CircuitBreaker, position_calculator: PositionCalculator):
        self.circuit_breaker = circuit_breaker
        self.position_calculator = position_calculator
    
    async def find_connected_components(self) -> List[List[str]]:
        """
        Находит все компоненты связности в графе
        """
        logger.info("Finding connected components")
        
        # Начинаем со статей, которые не в longest path
        components_query = """
        MATCH (n:Article)
        WHERE n.layout_status = 'unprocessed'
        CALL {
            WITH n
            MATCH path = (n)-[:CITES*1..6]-(connected:Article)
            WHERE connected.layout_status = 'unprocessed'
            WITH collect(DISTINCT connected.uid) as connected_uids, n
            RETURN connected_uids + [n.uid] as component
        }
        RETURN component
        """
        
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(components_query)
            
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

    async def find_connected_components_gds(self) -> List[List[str]]:
        """Используем Neo4j GDS для быстрого поиска компонент"""
        logger.info("Using Neo4j GDS for connected components")
        
        try:
            # Сначала проверяем, доступен ли GDS
            check_gds_query = """
            CALL gds.list() YIELD name
            WHERE name = 'wcc'
            RETURN count(*) as gds_available
            """
            
            gds_check = await neo4j_client.execute_query_with_retry(check_gds_query)
            
            if gds_check and gds_check[0]["gds_available"] > 0:
                # Используем GDS WCC
                gds_query = """
                CALL gds.wcc.stream('citation_graph')
                YIELD nodeId, componentId
                RETURN gds.util.asNode(nodeId).uid as uid, componentId
                ORDER BY componentId, uid
                """
                
                result = await neo4j_client.execute_query_with_retry(gds_query)
                
                # Группируем по componentId
                from collections import defaultdict
                components = defaultdict(list)
                for row in result:
                    components[row["componentId"]].append(row["uid"])
                
                component_list = list(components.values())
                logger.info(f"GDS found {len(component_list)} connected components")
                return component_list
            else:
                logger.info("GDS not available, falling back to standard method")
                return await self.find_connected_components()
                
        except Exception as e:
            logger.warning(f"GDS failed: {e}, falling back to standard method")
            return await self.find_connected_components()

    async def place_connected_components_parallel(self, components: List[List[str]]) -> int:
        """Параллельное размещение компонент"""
        logger.info(f"Starting parallel placement of {len(components)} components")
        
        # Группируем компоненты по потокам
        max_workers = min(4, len(components))  # Максимум 4 потока
        chunk_size = max(1, len(components) // max_workers)
        chunks = [components[i:i + chunk_size] for i in range(0, len(components), chunk_size)]
        
        logger.info(f"Split into {len(chunks)} chunks for parallel processing")
        
        # Запускаем параллельно
        tasks = []
        for i, chunk in enumerate(chunks):
            start_layer = 20 + (i * 10)  # Начинаем с 20-го слоя для параллельных чанков
            start_level = 5 + (i * 5)    # Начинаем с 5-го уровня, чтобы быть выше компонент
            task = asyncio.create_task(
                self._process_component_chunk(chunk, start_layer, start_level)
            )
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        logger.info("Parallel component placement completed")
        return len(components)

    async def _process_component_chunk(self, components: List[List[str]], start_layer: int, start_level: int):
        """Обрабатывает чанк компонент"""
        logger.info(f"Processing chunk with {len(components)} components starting at layer {start_layer}")
        
        for i, component in enumerate(components):
            layer = start_layer + (i % 10)
            level = start_level + (i * 2)  # Каждая компонента на своем уровне с отступом
            try:
                await self._place_connected_component(component, layer, level)
            except Exception as e:
                logger.error(f"Error placing component {i}: {e}")

    async def _place_connected_component(self, component: List[str], start_layer: int, start_level: int):
        """
        Размещает компонент связности рядом с основным (LP)
        """
        logger.info(f"Placing component with {len(component)} articles at layer {start_layer}, level {start_level}")
        
        # Находим соседей компонента для определения оптимального размещения
        neighbors_query = """
        MATCH (n:Article)-[:CITES]-(m:Article)
        WHERE n.uid IN $component_ids AND m.layout_status IN ['placed', 'in_longest_path']
        RETURN m.layer as layer, m.level as level, m.x as x, m.y as y
        """
        
        async with self.circuit_breaker:
            neighbors = await neo4j_client.execute_query_with_retry(neighbors_query, {"component_ids": component})
        
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
        
        # Размещаем узлы компонента
        placements = []
        
        # Ограничиваем количество узлов для детального размещения
        max_detailed_placement = 100
        if len(component) > max_detailed_placement:
            logger.info(f"Component too large ({len(component)} nodes), using batch placement")
            # Для больших компонент используем упрощённое размещение
            for i, vertex_id in enumerate(component):
                # Простое размещение по сетке с учетом уникальности
                layer = target_layer + (i % 10)
                level = target_level + (i // 10)  # Переходим на следующий уровень каждые 10 узлов
                x, y = self.position_calculator.calculate_coordinates(layer, level)
                placements.append({
                    "vertex_id": vertex_id,
                    "layer": layer,
                    "level": level,
                    "x": x,
                    "y": y
                })
        else:
            # Детальное размещение для небольших компонент
            for i, vertex_id in enumerate(component):
                # Находим свободную позицию около target_layer, target_level
                free_pos = await self._find_free_position_near(target_layer, target_level)
                if free_pos:
                    layer, level = free_pos
                    x, y = self.position_calculator.calculate_coordinates(layer, level)
                    placements.append({
                        "vertex_id": vertex_id,
                        "layer": layer,
                        "level": level,
                        "x": x,
                        "y": y
                    })
                else:
                    # Fallback: простое размещение с учетом уникальности
                    layer = target_layer + (i % 10)
                    level = target_level + (i // 10)  # Переходим на следующий уровень каждые 10 узлов
                    x, y = self.position_calculator.calculate_coordinates(layer, level)
                    placements.append({
                        "vertex_id": vertex_id,
                        "layer": layer,
                        "level": level,
                        "x": x,
                        "y": y
                    })
                
                # Прогресс внутри компоненты (каждые 10 узлов)
                if i % 10 == 0 or i == len(component) - 1:
                    logger.info(f"Component placement progress: {i+1}/{len(component)} nodes")
        
        if placements:
            await self._update_nodes_batch(placements, status="placed")
            logger.info(f"Placed {len(placements)} nodes from component")

    async def _find_free_position_near(self, target_layer: int, target_level: int) -> Optional[Tuple[int, int]]:
        """
        Упрощённый быстрый поиск: точное место или новый уровень в целевом слое.
        Уровни неограниченны - создаются новые по мере необходимости.
        """
        # Пробуем точное место
        if await self._is_position_free(target_layer, target_level):
            return (target_layer, target_level)

        # Создаём новый уровень выше существующих
        max_level_query = """
        MATCH (n:Article {layer: $layer})
        WHERE n.layout_status IN ['placed', 'in_longest_path']
        RETURN max(n.level) as max_level
        """
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(max_level_query, {"layer": target_layer})
        
        new_level = 0
        if result and result[0] and result[0]["max_level"] is not None:
            new_level = int(result[0]["max_level"]) + 1
        
        return (target_layer, new_level)

    async def _is_position_free(self, layer: int, level: int) -> bool:
        """Проверяет, свободна ли позиция (layer, level)."""
        query = """
        MATCH (n:Article {layer: $layer, level: $level})
        WHERE n.layout_status IN ['placed', 'in_longest_path']
        RETURN count(n) as count
        """
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(query, {"layer": layer, "level": level})
        
        if result and result[0]:
            return int(result[0]["count"]) == 0
        return True

    async def _update_nodes_batch(self, items: List[Dict[str, Any]], status: str):
        """Обновляет узлы батчем"""
        if not items:
            return
        
        query = """
        UNWIND $batch AS item
        MATCH (n:Article {uid: item.article_id})
        SET n.layout_status = $status,
            n.layer = item.layer,
            n.level = item.level,
            n.x = item.x,
            n.y = item.y
        """
        params = {"batch": items, "status": status}
        async with self.circuit_breaker:
            await neo4j_client.execute_query_with_retry(query, params)
