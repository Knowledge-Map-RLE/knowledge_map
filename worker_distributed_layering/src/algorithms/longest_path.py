"""
Модуль для работы с longest path в алгоритме укладки
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from ..neo4j_client import neo4j_client
from ..utils.simple_circuit_breaker import CircuitBreaker
from .layout_types import VertexStatus, VertexPosition
from .positioning import PositionCalculator

logger = logging.getLogger(__name__)


class LongestPathProcessor:
    """Обработчик longest path для укладки графа"""
    
    def __init__(self, circuit_breaker: CircuitBreaker, position_calculator: PositionCalculator):
        self.circuit_breaker = circuit_breaker
        self.position_calculator = position_calculator
        self.longest_path_cache = []
    
    async def find_and_place_longest_path(self) -> List[VertexPosition]:
        """
        Объединённая функция: поиск и размещение longest path одним запросом к БД.
        Использует алгоритм динамического программирования в Cypher для поиска LP
        и математическую формулу арифметической прогрессии для размещения.
        Устраняет передачу данных между функциями и ускоряет выполнение.
        """
        logger.info("Finding and placing longest path in one operation")
        
        # Проверяем кэш
        if isinstance(self.longest_path_cache, list) and self.longest_path_cache:
            logger.info("Using cached longest path for placement only")
            return await self._place_cached_longest_path()
        
        # Сначала очищаем все существующие позиции, чтобы избежать конфликтов ограничений
        await self._clear_all_layout_positions()
        
        # Получаем параметры позиционирования из PositionCalculator
        layer_spacing = self.position_calculator.LAYER_SPACING
        level_spacing = self.position_calculator.LEVEL_SPACING
        
        # 0. Сначала полностью очистим все позиции layout в БД
        clear_all_query = """
        MATCH (n:Article)
        REMOVE n.layer, n.level, n.x, n.y, n.layout_status
        RETURN count(n) as cleared_count
        """
        
        async with self.circuit_breaker:
            clear_result = await neo4j_client.execute_query_with_retry(clear_all_query)
            logger.info(f"Cleared layout positions for {clear_result[0]['cleared_count']} articles")
        
        # 1. Найдём longest path для всего графа (между любыми двумя узлами)
        find_query = """
        // Сначала найдем все возможные пути
        MATCH path = (start:Article)-[:CITES*]->(end:Article)
        WHERE start <> end  // Избегаем петель
        
        // Группируем по длине пути и берем самый длинный
        WITH path, length(path) as path_length
        ORDER BY path_length DESC
        LIMIT 1  // Берём только самый длинный путь
        
        // Извлекаем узлы из пути и дедуплицируем
        WITH path, nodes(path) as path_nodes, size(nodes(path)) as path_size
        UNWIND range(0, path_size-1) as i
        WITH path_nodes[i] as node_in_path, i, path_size
        WITH node_in_path, i, path_size
        // Дедуплицируем узлы, сохраняя порядок
        WITH collect(DISTINCT node_in_path) as unique_nodes, path_size
        UNWIND range(0, size(unique_nodes)-1) as new_i
        WITH unique_nodes[new_i] as node_in_path, new_i as i, size(unique_nodes) as total_nodes
        RETURN node_in_path.uid as uid, i as index, total_nodes
        ORDER BY i
        """
        
        async with self.circuit_breaker:
            find_result = await neo4j_client.execute_query_with_retry(find_query)
        
        if not find_result:
            logger.warning("No longest path found with depth limit 20, trying alternative approach...")
            
            # Альтернативный подход: ищем пути от узлов с минимальной степенью исхода
            alternative_query = """
            // Находим узлы с минимальной степенью исхода (листья)
            MATCH (start:Article)
            WHERE NOT (start)-[:CITES]->()
            WITH start
            LIMIT 100  // Ограничиваем для производительности
            
            // Ищем пути от этих узлов
            MATCH path = (start)-[:CITES*1..15]->(end:Article)
            WHERE start <> end
            
            WITH path, length(path) as path_length
            ORDER BY path_length DESC
            LIMIT 1
            
            WITH path, nodes(path) as path_nodes, size(nodes(path)) as path_size
            UNWIND range(0, path_size-1) as i
            WITH path_nodes[i] as node_in_path, i, path_size
            RETURN node_in_path.uid as uid, i as index, path_size as total_nodes
            ORDER BY i
            """
            
            try:
                async with self.circuit_breaker:
                    find_result = await neo4j_client.execute_query_with_retry(alternative_query)
                
                if not find_result:
                    logger.warning("Alternative longest path search also failed")
                    return []
                else:
                    logger.info(f"Found longest path using alternative method with {len(find_result)} nodes")
            except Exception as e:
                logger.error(f"Alternative longest path search failed: {str(e)}")
            return []
        
        # Отладочная информация о найденном longest path
        logger.info(f"Found longest path with {len(find_result)} nodes")
        for row in find_result:
            logger.info(f"LP node: uid={row['uid']}, index={row['index']}, total_nodes={row.get('total_nodes', 'N/A')}")
        
        # 2. Размещаем найденный longest path одним запросом с вычислениями в Cypher
        placements = []
        longest_path = [row["uid"] for row in find_result]
        
        # Выполняем размещение с вычислениями координат в БД
        if longest_path:
            db_placement_query = """
            UNWIND $longest_path as vertex_uid
            
            // Сортируем по uid для детерминированного порядка
            WITH vertex_uid
            ORDER BY vertex_uid
            
            // Собираем в список и присваиваем индексы
            WITH collect(vertex_uid) as lp_list
            UNWIND range(0, size(lp_list)-1) as i
            WITH lp_list[i] as vertex_uid, i, $layer_spacing as layer_spacing, $level_spacing as level_spacing
            
            // Находим узел и размещаем с вычисленными координатами
            MATCH (n:Article {uid: vertex_uid})
            SET n.layout_status = 'in_longest_path',
                n.layer = i,
                n.level = 0,
                n.x = i * layer_spacing,
                n.y = i * 10  // Небольшое смещение по y для видимости
            
            RETURN n.uid as uid, n.layer as layer, n.level as level, n.x as x, n.y as y
            ORDER BY n.layer
            """
            
            try:
                async with self.circuit_breaker:
                    result = await neo4j_client.execute_query_with_retry(
                        db_placement_query,
                        {
                            "longest_path": longest_path,
                            "layer_spacing": layer_spacing,
                            "level_spacing": level_spacing
                        }
                    )
                
                for row_data in result:
                    position = VertexPosition(
                        vertex_id=row_data["uid"],
                        layer=row_data["layer"],
                        level=row_data["level"],
                        x=row_data["x"],
                        y=row_data["y"],
                        status=VertexStatus.IN_LONGEST_PATH
                    )
                    placements.append(position)
                    
                    # Логируем координаты для отладки
                    logger.info(f"LP Article {row_data['uid']}: layer={row_data['layer']}, level=0, x={row_data['x']}, y={row_data['y']}")
                    
            except Exception as e:
                logger.error(f"Failed to place LP nodes with DB-side calculations: {str(e)}")
                # Fallback: простой batch без вычислений
                logger.info("Falling back to simple batch placement...")
                placement_data = []
                for i, vertex_id in enumerate(longest_path):
                    placement_data.append({
                        "vertex_id": vertex_id,
                        "layer": i,
                        "x": i * layer_spacing,
                        "y": i * 10
                    })
                
                fallback_query = """
                UNWIND $placement_data as data
                MATCH (n:Article {uid: data.vertex_id})
                        SET n.layout_status = 'in_longest_path',
                    n.layer = data.layer,
                            n.level = 0,
                    n.x = data.x,
                    n.y = data.y
                        RETURN n.uid as uid, n.layer as layer, n.level as level, n.x as x, n.y as y
                ORDER BY n.layer
                        """
                        
                try:
                    async with self.circuit_breaker:
                        result = await neo4j_client.execute_query_with_retry(
                            fallback_query,
                            {"placement_data": placement_data}
                        )
                    
                    for row_data in result:
                        position = VertexPosition(
                            vertex_id=row_data["uid"],
                            layer=row_data["layer"],
                            level=row_data["level"],
                            x=row_data["x"],
                            y=row_data["y"],
                            status=VertexStatus.IN_LONGEST_PATH
                        )
                        placements.append(position)
                        logger.info(f"LP Article {row_data['uid']}: layer={row_data['layer']}, level=0, x={row_data['x']}, y={row_data['y']}")
                        
                except Exception as fallback_error:
                    logger.error(f"Fallback placement also failed: {str(fallback_error)}")
                    return []
        
        # Обновляем кэш
        self.longest_path_cache = longest_path
        
        logger.info(f"Successfully found and placed {len(placements)} LP nodes in one operation")
        return placements

    async def _place_cached_longest_path(self) -> List[VertexPosition]:
        """
        Размещает кэшированный longest path (для случая когда LP уже найден)
        """
        logger.info("Placing cached longest path")
        
        longest_path = self.longest_path_cache
        if not longest_path:
            logger.warning("Cached longest path is empty")
            return []
        
        # Сначала очищаем все существующие позиции, чтобы избежать конфликтов ограничений
        await self._clear_all_layout_positions()
        
        # Получаем параметры позиционирования
        layer_spacing = self.position_calculator.LAYER_SPACING
        level_spacing = self.position_calculator.LEVEL_SPACING
        
        # Размещаем кэшированный LP одним запросом с вычислениями в Cypher
        placements = []
        
        # Выполняем размещение с вычислениями координат в БД
        if longest_path:
            cached_placement_query = """
            UNWIND $longest_path as vertex_uid
            
            // Сортируем для правильного порядка
            WITH vertex_uid, collect(vertex_uid) as lp_list
            UNWIND range(0, size(lp_list)-1) as i
            WITH lp_list[i] as vertex_uid, i, $layer_spacing as layer_spacing, $level_spacing as level_spacing
            
            // Находим узел и размещаем с вычисленными координатами
            MATCH (n:Article {uid: vertex_uid})
            SET n.layout_status = 'in_longest_path',
                n.layer = i,
                n.level = 0,
                n.x = i * layer_spacing,
                n.y = i * 10  // Небольшое смещение по y для видимости
            
            RETURN n.uid as uid, n.layer as layer, n.level as level, n.x as x, n.y as y
            ORDER BY n.layer
            """
            
            try:
                async with self.circuit_breaker:
                    result = await neo4j_client.execute_query_with_retry(
                        cached_placement_query,
                        {
                            "longest_path": longest_path,
                            "layer_spacing": layer_spacing,
                            "level_spacing": level_spacing
                        }
                    )
                
                for row_data in result:
                    position = VertexPosition(
                        vertex_id=row_data["uid"],
                        layer=row_data["layer"],
                        level=row_data["level"],
                        x=row_data["x"],
                        y=row_data["y"],
                        status=VertexStatus.IN_LONGEST_PATH
                    )
                    placements.append(position)
                    
            except Exception as e:
                logger.error(f"Failed to place cached LP nodes with DB-side calculations: {str(e)}")
                # Fallback: простой batch без вычислений
                logger.info("Falling back to simple batch placement for cached LP...")
                placement_data = []
                for i, vertex_id in enumerate(longest_path):
                    placement_data.append({
                        "vertex_id": vertex_id,
                        "layer": i,
                        "x": i * layer_spacing,
                        "y": i * 10
                    })
                
                fallback_query = """
                UNWIND $placement_data as data
                MATCH (n:Article {uid: data.vertex_id})
                        SET n.layout_status = 'in_longest_path',
                    n.layer = data.layer,
                            n.level = 0,
                    n.x = data.x,
                    n.y = data.y
                        RETURN n.uid as uid, n.layer as layer, n.level as level, n.x as x, n.y as y
                ORDER BY n.layer
                        """
                        
                try:
                    async with self.circuit_breaker:
                        result = await neo4j_client.execute_query_with_retry(
                            fallback_query,
                            {"placement_data": placement_data}
                        )
                    
                    for row_data in result:
                        position = VertexPosition(
                            vertex_id=row_data["uid"],
                            layer=row_data["layer"],
                            level=row_data["level"],
                            x=row_data["x"],
                            y=row_data["y"],
                            status=VertexStatus.IN_LONGEST_PATH
                        )
                        placements.append(position)
                        
                except Exception as fallback_error:
                    logger.error(f"Fallback placement for cached LP also failed: {str(fallback_error)}")
                    return []
        
        logger.info(f"Successfully placed {len(placements)} cached LP nodes")
        return placements

    async def place_lp_neighbors(self, longest_path: List[str]) -> int:
        """
        Размещает предков и потомков вершин LP рядом с ними.
        Вся логика выполняется на стороне БД для максимальной производительности.
        Использует арифметическую прогрессию: y=0, x рассчитывается в БД.
        """
        logger.info("Placing LP neighbors using DB-side arithmetic progression (y=0, x=progression)")
        
        # Получаем параметры позиционирования
        layer_spacing = self.position_calculator.LAYER_SPACING
        level_spacing = self.position_calculator.LEVEL_SPACING
        
        # Вся логика размещения выполняется в одном запросе к БД
        db_placement_query = """
        // 1. Находим всех соседей LP вершин (предков и потомков)
        MATCH (lp:Article)
        WHERE lp.layout_status = 'in_longest_path'
        OPTIONAL MATCH (pred:Article)-[:CITES]->(lp)
        OPTIONAL MATCH (lp)-[:CITES]->(succ:Article)
        
        // 2. Собираем всех уникальных соседей
        WITH collect(DISTINCT pred) + collect(DISTINCT succ) as all_neighbors
        UNWIND all_neighbors as neighbor
        WITH neighbor
        WHERE neighbor IS NOT NULL AND neighbor.layout_status <> 'in_longest_path'
        
        // 3. Получаем количество LP вершин для расчета стартовой позиции
        WITH neighbor, 
             size([(lp:Article) WHERE lp.layout_status = 'in_longest_path']) as lp_count
        
        // 4. Сортируем соседей по uid для детерминированного порядка
        WITH neighbor, lp_count
        ORDER BY neighbor.uid
        
        // 5. Присваиваем индексы и рассчитываем позиции по арифметической прогрессии
        WITH neighbor, lp_count, collect(neighbor) as neighbors_list
        UNWIND range(0, size(neighbors_list)-1) as i
        WITH neighbors_list[i] as neighbor, lp_count, i
        
        // 6. Рассчитываем координаты по арифметической прогрессии
        WITH neighbor, 
             lp_count + i as layer,  // Слои после LP вершин
             0 as level,             // Все на уровне 0
             (lp_count + i) * $layer_spacing as x,  // x по арифметической прогрессии
             i * 10 as y                             // Небольшое смещение по y
        
        // 7. Размещаем соседей
        SET neighbor.layout_status = 'lp_neighbor',
            neighbor.layer = layer,
            neighbor.level = level,
            neighbor.x = x,
            neighbor.y = y
        
        // 8. Возвращаем статистику
        RETURN count(neighbor) as placed_count,
               collect(neighbor.uid)[0..5] as first_five_placed,
               min(neighbor.layer) as min_layer,
               max(neighbor.layer) as max_layer
        """
        
        try:
            async with self.circuit_breaker:
                result = await neo4j_client.execute_query_with_retry(
                    db_placement_query,
                    {
                        "layer_spacing": layer_spacing,
                        "level_spacing": level_spacing
                    }
                )
            
            if result and result[0]:
                placed_count = result[0]["placed_count"]
                first_five = result[0]["first_five_placed"] or []
                min_layer = result[0]["min_layer"]
                max_layer = result[0]["max_layer"]
                
                logger.info(f"Successfully placed {placed_count} LP neighbors using DB-side arithmetic progression")
                logger.info(f"Layer range: {min_layer} to {max_layer}")
                
                if first_five:
                    logger.info(f"First 5 placed neighbors: {first_five}")
                
                if placed_count > 5:
                    logger.info(f"... and {placed_count - 5} more neighbors")
                    
            else:
                placed_count = 0
                logger.info("No LP neighbors found to place")
                
        except Exception as e:
            logger.error(f"Failed to place LP neighbors using DB-side logic: {str(e)}")
            logger.info("Falling back to Python-side placement...")
            
            # Fallback на Python-логику при ошибке
            return await self._place_lp_neighbors_fallback(longest_path)
        
        logger.info(f"LP neighbors placement completed: {placed_count} nodes placed using DB-side arithmetic progression")
        return placed_count

    async def _place_lp_neighbors_fallback(self, longest_path: List[str]) -> int:
        """
        Fallback метод для размещения соседей LP на стороне Python
        (используется при ошибке DB-side логики)
        """
        logger.info("Using Python-side fallback for LP neighbors placement")
        
        # Получаем всех соседей LP вершин
        neighbors_query = """
        MATCH (lp:Article)
        WHERE lp.layout_status = 'in_longest_path'
        OPTIONAL MATCH (pred:Article)-[:CITES]->(lp)
        OPTIONAL MATCH (lp)-[:CITES]->(succ:Article)
        RETURN DISTINCT 
            collect(DISTINCT pred.uid) as predecessors,
            collect(DISTINCT succ.uid) as successors
        """
        
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(neighbors_query)
        
        if not result:
            return 0
            
        # Собираем всех соседей
        all_neighbors = set()
        for row in result:
            predecessors = row["predecessors"] or []
            successors = row["successors"] or []
            all_neighbors.update(predecessors)
            all_neighbors.update(successors)
        
        # Убираем LP вершины
        neighbors_to_place = [n for n in all_neighbors if n not in longest_path]
        
        if not neighbors_to_place:
            return 0
        
        # Размещение всех соседей одним DB-запросом с вычислениями в Cypher
        layer_spacing = self.position_calculator.LAYER_SPACING
        level_spacing = self.position_calculator.LEVEL_SPACING
        start_layer = len(longest_path)
        
        # Передаем список соседей в БД и вычисляем координаты там
        fallback_placement_query = """
        UNWIND $neighbors_to_place as neighbor_uid
        
        // Сортируем для детерминированного порядка
        WITH neighbor_uid
        ORDER BY neighbor_uid
        
        // Присваиваем индексы и вычисляем координаты в БД
        WITH neighbor_uid, collect(neighbor_uid) as neighbors_list
        UNWIND range(0, size(neighbors_list)-1) as i
        WITH neighbors_list[i] as neighbor_uid, i, $start_layer as start_layer, $layer_spacing as layer_spacing
        
        // Находим узел и размещаем с вычисленными координатами
        MATCH (n:Article {uid: neighbor_uid})
        SET n.layout_status = 'lp_neighbor',
            n.layer = start_layer + i,
            n.level = 0,
            n.x = (start_layer + i) * layer_spacing,
            n.y = i * 10
        
        RETURN count(n) as placed_count,
               collect(n.uid)[0..5] as first_five_placed
        """
        
        try:
            async with self.circuit_breaker:
                result = await neo4j_client.execute_query_with_retry(
                    fallback_placement_query,
                    {
                        "neighbors_to_place": neighbors_to_place,
                        "start_layer": start_layer,
                        "layer_spacing": layer_spacing
                    }
                )
            
            if result and result[0]:
                placed_count = result[0]["placed_count"]
                first_five = result[0]["first_five_placed"] or []
                
                logger.info(f"Fallback placement completed: {placed_count} neighbors placed using DB-side calculations")
                
                if first_five:
                    logger.info(f"First 5 placed neighbors: {first_five}")
                    
            else:
                placed_count = 0
                logger.warning("Fallback placement returned no results")
                
        except Exception as e:
            logger.error(f"Fallback placement failed: {str(e)}")
            placed_count = 0
        
        return placed_count

    async def _clear_all_layout_positions(self):
        """
        Очищает все существующие позиции укладки в БД для избежания конфликтов ограничений
        """
        logger.info("Clearing all existing layout positions")
        
        clear_query = """
        MATCH (n:Article)
        WHERE n.layer IS NOT NULL OR n.level IS NOT NULL OR n.x IS NOT NULL OR n.y IS NOT NULL OR n.layout_status IS NOT NULL
        REMOVE n.layer, n.level, n.x, n.y, n.layout_status
        RETURN count(n) as cleared_count
        """
        
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(clear_query)
            cleared_count = result[0]["cleared_count"] if result else 0
            logger.info(f"Cleared layout positions for {cleared_count} articles")
