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
        MATCH path = (start:Article)-[:BIBLIOGRAPHIC_LINK*]->(end:Article)
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
            WHERE NOT (start)-[:BIBLIOGRAPHIC_LINK]->()
            WITH start
            LIMIT 100  // Ограничиваем для производительности
            
            // Ищем пути от этих узлов
            MATCH path = (start)-[:BIBLIOGRAPHIC_LINK*1..15]->(end:Article)
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
        
        # 2. Размещаем найденный longest path топологически
        placements = []
        longest_path = [row["uid"] for row in find_result]
        
        # Выполняем топологическое размещение
        if longest_path:
            # Сначала получаем топологический порядок
            topological_order = await self._get_topological_order_for_lp(longest_path)
            
            if not topological_order:
                logger.warning("Failed to get topological order, falling back to original order")
                topological_order = longest_path
            
            # Размещаем в топологическом порядке
            db_placement_query = """
            UNWIND $topological_order as vertex_uid
            
            // Сортируем для детерминированного порядка
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
                n.x = CASE 
                    WHEN i * layer_spacing > 100000 THEN 100000  // Защита от огромных X
                    ELSE i * layer_spacing 
                END,
                n.y = 0  // Все LP вершины на уровне 0
            
            RETURN n.uid as uid, n.layer as layer, n.level as level, n.x as x, n.y as y, n.layout_status as status
            ORDER BY n.layer
            """
            
            try:
                async with self.circuit_breaker:
                    result = await neo4j_client.execute_query_with_retry(
                        db_placement_query,
                        {
                            "topological_order": topological_order,
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
                        "y": 0  # Все LP вершины на уровне 0
                    })
                
                fallback_query = """
                UNWIND $placement_data as data
                MATCH (n:Article {uid: data.vertex_id})
                        SET n.layout_status = 'in_longest_path',
                    n.layer = data.layer,
                            n.level = 0,
                    n.x = data.x,
                    n.y = data.y
                        RETURN n.uid as uid, n.layer as layer, n.level as level, n.x as x, n.y as y, n.layout_status as status
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
        
        # Размещаем кэшированный LP топологически
        placements = []
        
        # Выполняем топологическое размещение
        if longest_path:
            # Получаем топологический порядок для кэшированного LP
            topological_order = await self._get_topological_order_for_lp(longest_path)
            
            if not topological_order:
                logger.warning("Failed to get topological order for cached LP, falling back to original order")
                topological_order = longest_path
            
            cached_placement_query = """
            UNWIND $topological_order as vertex_uid
            
            // Сортируем для правильного порядка
            WITH vertex_uid, collect(vertex_uid) as lp_list
            UNWIND range(0, size(lp_list)-1) as i
            WITH lp_list[i] as vertex_uid, i, $layer_spacing as layer_spacing, $level_spacing as level_spacing
            
            // Находим узел и размещаем с вычисленными координатами
            MATCH (n:Article {uid: vertex_uid})
            SET n.layout_status = 'in_longest_path',
                n.layer = i,
                n.level = 0,
                n.x = CASE 
                    WHEN i * layer_spacing > 100000 THEN 100000  // Защита от огромных X
                    ELSE i * layer_spacing 
                END,
                n.y = 0  // Все LP вершины на уровне 0
            
            RETURN n.uid as uid, n.layer as layer, n.level as level, n.x as x, n.y as y, n.layout_status as status
            ORDER BY n.layer
            """
            
            try:
                async with self.circuit_breaker:
                    result = await neo4j_client.execute_query_with_retry(
                        cached_placement_query,
                        {
                            "topological_order": topological_order,
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
                        RETURN n.uid as uid, n.layer as layer, n.level as level, n.x as x, n.y as y, n.layout_status as status
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
        Размещает соседей LP с правильной топологией:
        - Каждый блок должен быть на слое после своего предка и перед своим потомком
        - При необходимости сдвигает LP вершины вправо инкрементально
        - Обеспечивает уникальность позиций (layer, level)
        """
        logger.info("Placing LP neighbors with correct topology and incremental LP shifting")
        
        # Получаем параметры позиционирования
        layer_spacing = self.position_calculator.LAYER_SPACING
        level_spacing = self.position_calculator.LEVEL_SPACING
        
        # 1. Получаем всех соседей LP с их связями
        neighbors_query = """
        // Находим всех соседей LP вершин с их связями
        MATCH (lp:Article)
        WHERE lp.layout_status = 'in_longest_path'
        OPTIONAL MATCH (pred:Article)-[:BIBLIOGRAPHIC_LINK]->(lp)
        OPTIONAL MATCH (lp)-[:BIBLIOGRAPHIC_LINK]->(succ:Article)
        
        // Собираем соседей с информацией о связанных LP блоках
        WITH lp, 
             collect(DISTINCT {neighbor: pred, lp_block: lp, relationship: 'predecessor'}) + 
             collect(DISTINCT {neighbor: succ, lp_block: lp, relationship: 'successor'}) as connections
        UNWIND connections as conn
        WITH conn.neighbor as neighbor, conn.lp_block as lp_block, conn.relationship as rel
        WHERE neighbor IS NOT NULL AND (neighbor.layout_status IS NULL OR neighbor.layout_status <> 'in_longest_path')
        
        // Возвращаем соседей с их связями
        RETURN DISTINCT neighbor.uid as neighbor_id, 
               lp_block.uid as lp_id, 
               lp_block.layer as lp_layer,
               lp_block.level as lp_level,
               rel as relationship
        ORDER BY neighbor_id, lp_id
        """
        
        async with self.circuit_breaker:
            neighbors_result = await neo4j_client.execute_query_with_retry(neighbors_query)
        
        if not neighbors_result:
            logger.info("No LP neighbors found to place")
            return 0
        
        logger.info(f"Found {len(neighbors_result)} neighbor-LP connections")
        
        # 2. Строим граф зависимостей для топологического размещения
        neighbors_map = {}
        for row in neighbors_result:
            neighbor_id = row["neighbor_id"]
            if neighbor_id not in neighbors_map:
                neighbors_map[neighbor_id] = []
            neighbors_map[neighbor_id].append({
                "lp_id": row["lp_id"],
                "lp_layer": row["lp_layer"],
                "lp_level": row["lp_level"],
                "relationship": row["relationship"]
            })
        
        logger.info(f"Processing {len(neighbors_map)} unique neighbors")
        
        # 3. Топологическое размещение с инкрементальным сдвигом LP
        placed_count = 0
        for neighbor_id, connections in neighbors_map.items():
            # Находим топологически корректную позицию
            target_layer = await self._find_topological_position(neighbor_id, connections, longest_path)
            
            # Проверяем, нужно ли сдвигать LP вершины
            if target_layer is not None:
                await self._shift_lp_vertices_if_needed(target_layer, longest_path, layer_spacing, level_spacing)
                
                # Ищем свободное место в целевом слое
                final_layer, final_level = await self._find_free_position_in_layer(target_layer, 1)
                
                # Размещаем соседа
                success = await self._place_single_neighbor(neighbor_id, final_layer, final_level, layer_spacing, level_spacing)
                if success:
                    placed_count += 1
                    
                # Логируем прогресс каждые 10 размещений
                if placed_count % 10 == 0:
                    logger.info(f"Placed {placed_count} LP neighbors so far...")
        
        logger.info(f"Successfully placed {placed_count} LP neighbors with topological placement")
        return placed_count

    async def _find_topological_position(self, neighbor_id: str, connections: List[Dict], longest_path: List[str]) -> Optional[int]:
        """
        Находит топологически корректную позицию для соседа.
        Возвращает target_layer или None если размещение невозможно.
        """
        if not connections:
            return None
        
        # Анализируем связи для определения топологической позиции
        predecessor_layers = []
        successor_layers = []
        
        for conn in connections:
            lp_layer = conn.get("lp_layer")
            if lp_layer is None:
                continue
                
            if conn["relationship"] == "predecessor":
                # Сосед является предком LP блока - должен быть на слое ПЕРЕД LP блоком
                predecessor_layers.append(lp_layer)
            elif conn["relationship"] == "successor":
                # Сосед является потомком LP блока - должен быть на слое ПОСЛЕ LP блока
                successor_layers.append(lp_layer)
        
        # Проверяем, что у нас есть валидные слои
        if not predecessor_layers and not successor_layers:
            return None
        
        # Определяем целевую позицию
        if predecessor_layers and successor_layers:
            # Сосед связан и с предками, и с потомками - нужен промежуточный слой
            min_successor_layer = min(successor_layers)
            max_predecessor_layer = max(predecessor_layers)
            
            if min_successor_layer > max_predecessor_layer + 1:
                # Есть место между предками и потомками
                target_layer = max_predecessor_layer + 1
            else:
                # Нужно сдвинуть LP вершины
                target_layer = max_predecessor_layer + 1
                
        elif predecessor_layers:
            # Только предки - размещаем перед самым левым предком
            target_layer = min(predecessor_layers)
            
        elif successor_layers:
            # Только потомки - размещаем после самого правого потомка
            target_layer = max(successor_layers) + 1
            
        else:
            return None
        
        # Проверяем разумность значения
        if target_layer < 0 or target_layer > 10000:  # Разумные границы
            logger.warning(f"Unreasonable target layer {target_layer} for neighbor {neighbor_id}, using fallback")
            return 10  # Fallback позиция
        
        return target_layer

    async def _shift_lp_vertices_if_needed(self, target_layer: int, longest_path: List[str], layer_spacing: float, level_spacing: float):
        """
        Сдвигает LP вершины вправо, если это необходимо для размещения соседа.
        """
        # Находим максимальный слой среди LP вершин
        max_lp_layer_query = """
        MATCH (n:Article)
        WHERE n.layout_status = 'in_longest_path' AND n.layer IS NOT NULL
        RETURN max(n.layer) as max_layer
        """
        
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(max_lp_layer_query)
        
        max_lp_layer = result[0]["max_layer"] if result and result[0] and result[0]["max_layer"] is not None else 0
        
        # Проверяем разумность max_lp_layer (не должно быть больше 10000)
        if max_lp_layer > 10000:
            logger.warning(f"Unreasonable max_lp_layer: {max_lp_layer}, resetting to 0")
            max_lp_layer = 0
        
        logger.info(f"Target layer: {target_layer}, Max LP layer: {max_lp_layer}")
        
        # Если целевой слой пересекается с LP вершинами, сдвигаем их
        if target_layer <= max_lp_layer:
            # Простой сдвиг на 1 слой - достаточно для размещения соседа
            shift_amount = 1
            logger.info(f"Shifting LP vertices by {shift_amount} layer to make room for neighbor at layer {target_layer}")
            
            # Сдвигаем все LP вершины начиная с target_layer
            shift_query = """
            MATCH (n:Article)
            WHERE n.layout_status = 'in_longest_path' AND n.layer >= $target_layer
            SET n.layer = n.layer + $shift_amount,
                n.x = (n.layer + $shift_amount) * $layer_spacing
            RETURN count(n) as shifted_count
            """
            
            async with self.circuit_breaker:
                shift_result = await neo4j_client.execute_query_with_retry(shift_query, {
                    "target_layer": target_layer,
                    "shift_amount": shift_amount,
                    "layer_spacing": layer_spacing
                })
            
            shifted_count = shift_result[0]["shifted_count"] if shift_result and shift_result[0] else 0
            logger.info(f"Shifted {shifted_count} LP vertices by {shift_amount} layer")

    async def _find_free_position_in_layer(self, target_layer: int, target_level: int) -> Tuple[int, int]:
        """
        Ищет свободное место в целевом слое, начиная с целевого уровня.
        Если место занято, ищет ближайшее свободное место в том же слое.
        """
        # Сначала проверяем целевую позицию
        if await self._is_position_free(target_layer, target_level):
            return (target_layer, target_level)
        
        # Ищем свободное место в том же слое, начиная с целевого уровня
        for level_offset in range(1, 100):  # Максимум 100 уровней вверх
            # Проверяем уровень выше
            if await self._is_position_free(target_layer, target_level + level_offset):
                return (target_layer, target_level + level_offset)
            
            # Проверяем уровень ниже (если target_level > 0)
            if target_level - level_offset >= 0:
                if await self._is_position_free(target_layer, target_level - level_offset):
                    return (target_layer, target_level - level_offset)
        
        # Если не нашли свободное место в слое, создаем новый уровень
        max_level_query = """
        MATCH (n:Article {layer: $layer})
        WHERE n.layout_status IN ['placed', 'in_longest_path', 'lp_neighbor']
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
        WHERE n.layout_status IN ['placed', 'in_longest_path', 'lp_neighbor']
        RETURN count(n) as count
        """
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(query, {"layer": layer, "level": level})
        
        if result and result[0]:
            return int(result[0]["count"]) == 0
        return True

    async def _place_single_neighbor(self, neighbor_id: str, layer: int, level: int, layer_spacing: float, level_spacing: float) -> bool:
        """Размещает одного соседа LP в указанной позиции."""
        x = layer * layer_spacing
        y = level * level_spacing
        
        placement_query = """
        MATCH (n:Article {uid: $neighbor_id})
        SET n.layout_status = 'lp_neighbor',
            n.layer = $layer,
            n.level = $level,
            n.x = $x,
            n.y = $y,
            n.is_lp_neighbor = true,
            n.visual_priority = 100
        RETURN n.uid as placed_id
        """
        
        try:
            async with self.circuit_breaker:
                result = await neo4j_client.execute_query_with_retry(placement_query, {
                    "neighbor_id": neighbor_id,
                    "layer": layer,
                    "level": level,
                    "x": x,
                    "y": y
                })
            
            return result is not None and len(result) > 0
                
        except Exception as e:
            logger.error(f"Failed to place neighbor {neighbor_id}: {str(e)}")
            return False

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
        OPTIONAL MATCH (pred:Article)-[:BIBLIOGRAPHIC_LINK]->(lp)
        OPTIONAL MATCH (lp)-[:BIBLIOGRAPHIC_LINK]->(succ:Article)
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
            n.y = 0
        
        RETURN count(n) as placed_count,
               collect(n.uid)[0..5] as first_five_placed,
               collect({uid: n.uid, x: n.x, y: n.y, layer: n.layer, level: n.level})[0..3] as sample_coords
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
                sample_coords = result[0]["sample_coords"] or []
                
                logger.info(f"Fallback placement completed: {placed_count} neighbors placed using DB-side calculations")
                
                if first_five:
                    logger.info(f"First 5 placed neighbors: {first_five}")
                
                if sample_coords:
                    logger.info("Sample coordinates:")
                    for coord in sample_coords:
                        logger.info(f"  {coord['uid']}: x={coord['x']}, y={coord['y']}, layer={coord['layer']}, level={coord['level']}")
                    
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

    async def _get_topological_order_for_lp(self, longest_path: List[str]) -> Optional[List[str]]:
        """
        Получает топологический порядок для longest path блоков.
        Возвращает список UID в топологическом порядке или None при ошибке.
        """
        if not longest_path or len(longest_path) <= 1:
            return longest_path
        
        logger.info(f"Getting topological order for {len(longest_path)} LP blocks")
        
        try:
            # Получаем связи между блоками longest path
            relationships_query = """
            UNWIND $lp_blocks as block_uid
            MATCH (n:Article {uid: block_uid})
            OPTIONAL MATCH (n)-[:BIBLIOGRAPHIC_LINK]->(target:Article)
            WHERE target.uid IN $lp_blocks
            RETURN n.uid as source, target.uid as target
            """
            
            async with self.circuit_breaker:
                relationships_result = await neo4j_client.execute_query_with_retry(
                    relationships_query, 
                    {"lp_blocks": longest_path}
                )
            
            # Строим граф зависимостей
            in_degree = {uid: 0 for uid in longest_path}
            graph = {uid: [] for uid in longest_path}
            
            for row in relationships_result:
                source = row["source"]
                target = row["target"]
                if target and source != target:  # Избегаем петель
                    graph[source].append(target)
                    in_degree[target] += 1
            
            # Топологическая сортировка (Kahn's algorithm)
            queue = [uid for uid, degree in in_degree.items() if degree == 0]
            topological_order = []
            
            # Защита от бесконечных циклов
            max_iterations = len(longest_path) * 2
            iterations = 0
            
            while queue and iterations < max_iterations:
                iterations += 1
                current = queue.pop(0)
                topological_order.append(current)
                
                # Уменьшаем in_degree для соседей
                for neighbor in graph[current]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)
            
            # Проверяем, что все блоки включены
            if len(topological_order) != len(longest_path):
                logger.warning(f"Topological sort incomplete: {len(topological_order)}/{len(longest_path)} blocks")
                # Добавляем недостающие блоки в конец
                missing = [uid for uid in longest_path if uid not in topological_order]
                topological_order.extend(missing)
            
            # Проверяем разумность результата
            if len(topological_order) > 10000:
                logger.error(f"Topological order too large: {len(topological_order)} blocks")
                return None
            
            logger.info(f"Topological order computed: {len(topological_order)} blocks")
            return topological_order
            
        except Exception as e:
            logger.error(f"Failed to compute topological order: {str(e)}")
            return None
