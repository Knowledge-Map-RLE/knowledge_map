"""
Модуль для быстрого размещения оставшихся узлов по сетке
"""

import logging
from typing import List, Dict, Any
from ..neo4j_client import neo4j_client
from ..utils.simple_circuit_breaker import CircuitBreaker
from .layout_types import LayoutResult
from .positioning import PositionCalculator

logger = logging.getLogger(__name__)


class FastPlacementProcessor:
    """Обработчик быстрого размещения оставшихся узлов"""
    
    def __init__(self, circuit_breaker: CircuitBreaker, position_calculator: PositionCalculator):
        self.circuit_breaker = circuit_breaker
        self.position_calculator = position_calculator
    
    async def fast_batch_placement_remaining(self) -> LayoutResult:
        """
        Быстрое размещение всех оставшихся неразмещённых статей одним большим батчем.
        Вместо медленного инкрементального размещения использует простую сетку.
        """
        logger.info("Starting fast batch placement of remaining articles")
        
        # Получаем все неразмещённые статьи, отсортированные по топологическому порядку
        remaining_query = """
        MATCH (n:Article)
        WHERE n.layout_status = 'unprocessed'
        AND (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() })
        RETURN n.uid as article_id, coalesce(n.topo_order, 0) as topo_order
        ORDER BY topo_order ASC
        """
        
        async with self.circuit_breaker:
            remaining_nodes = await neo4j_client.execute_query_with_retry(remaining_query)
        
        if not remaining_nodes:
            logger.info("No remaining nodes to place")
            return await self._build_final_result()
        
        remaining_count = len(remaining_nodes)
        logger.info(f"Found {remaining_count} remaining nodes to place")
        
        # Быстрое размещение по сетке с учетом уже размещенных узлов
        # Оставшиеся узлы размещаются выше LP и компонент для избежания конфликтов
        all_placements = []
        
        # Начинаем с высоких слоев и уровней, чтобы не пересекаться с LP и компонентами
        start_layer = 50  # Начинаем с 50-го слоя
        start_level = 20  # Начинаем с 20-го уровня
        nodes_per_layer = 15  # Размещаем по 15 статей на слой для лучшего распределения
        
        for i, row in enumerate(remaining_nodes):
            article_id = row["article_id"]
            
            # Простое размещение по сетке с отступом от уже размещенных
            layer = start_layer + (i % nodes_per_layer)
            level = start_level + (i // nodes_per_layer)
            
            x, y = self.position_calculator.calculate_coordinates(layer, level)
            
            all_placements.append({
                "article_id": article_id,
                "layer": layer,
                "level": level,
                "x": x,
                "y": y
            })
            
            # Логируем прогресс каждые 1000 статей
            if (i + 1) % 1000 == 0:
                logger.info(f"Prepared {i + 1}/{remaining_count} placements")
        
        logger.info(f"Prepared {len(all_placements)} placements, starting batch update")
        
        # Размещаем узлы батчами для лучшей производительности
        if all_placements:
            batch_size = 5000  # Размер батча для обновления
            total_batches = (len(all_placements) + batch_size - 1) // batch_size
            
            logger.info(f"Processing {len(all_placements)} placements in {total_batches} batches of {batch_size}")
            
            for i in range(0, len(all_placements), batch_size):
                batch = all_placements[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                
                logger.info(f"Processing batch {batch_num}/{total_batches} with {len(batch)} articles")
                await self._update_nodes_batch(batch, status="placed")
                
                logger.info(f"Completed batch {batch_num}/{total_batches}, placed {len(batch)} articles")
            
            logger.info(f"Successfully placed all {len(all_placements)} remaining articles in {total_batches} batches")
        
        return await self._build_final_result()

    async def _update_nodes_batch(self, items: List[Dict[str, Any]], status: str):
        """Обновляет статьи батчем"""
        if not items:
            return
        
        # Логируем координаты для отладки
        logger.info(f"Setting coordinates for {len(items)} articles:")
        for item in items[:5]:  # Показываем первые 5 элементов
            logger.info(f"  Article {item['article_id']}: layer={item['layer']}, level={item['level']}, x={item['x']}, y={item['y']}")
        
        query = """
        UNWIND $batch AS item
        MATCH (n:Article {uid: item.article_id})
        SET n.layout_status = $status,
            n.layer = item.layer,
            n.level = item.level,
            n.x = item.x,
            n.y = item.y
        RETURN n.uid as uid, n.x as x, n.y as y, n.layer as layer, n.level as level
        """
        params = {"batch": items, "status": status}
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(query, params)
            # Логируем результат для отладки
            if result:
                logger.info(f"Updated {len(result)} articles with status '{status}'")
                for row in result[:3]:  # Показываем первые 3 для отладки
                    logger.info(f"  {row['uid']}: x={row['x']}, y={row['y']}, layer={row['layer']}, level={row['level']}")

    async def _build_final_result(self) -> LayoutResult:
        """Строит финальный результат укладки"""
        logger.info("Building final layout result")
        
        # Получаем все размещённые статьи, отсортированные по топологическому порядку (только связанные вершины)
        query = """
        MATCH (n:Article)
        WHERE n.layout_status IN ['placed', 'in_longest_path', 'pinned']
        AND (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() })
        RETURN n.uid as article_id, n.layer as layer, n.level as level, 
               n.x as x, n.y as y,
               n.layout_status as status, n.is_pinned as is_pinned,
               coalesce(n.topo_order, 0) as topo_order
        ORDER BY topo_order ASC
        """
        
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(query)
        
        # Строим структуры данных
        blocks = []
        layers = {}
        levels = {}
        
        for row in result:
            article_id = row["article_id"]
            layer = row["layer"]
            level = row["level"]
            
            # Добавляем блок
            blocks.append({
                "id": article_id,
                "layer": layer,
                "level": level,
                "x": row["x"],
                "y": row["y"],
                "is_pinned": row["is_pinned"]
            })
            
            # Обновляем слои
            layers[article_id] = layer
            
            # Обновляем уровни
            if level not in levels:
                levels[level] = []
            if article_id not in levels[level]:
                levels[level].append(article_id)
        
        # Статистика
        statistics = {
            "total_blocks": len(blocks),
            "total_layers": len(set(layers.values())),
            "total_levels": len(levels),
            "placement_method": "fast_batch_grid"
        }
        
        return LayoutResult(
            success=True,
            blocks=blocks,
            layers=layers,
            levels=levels,
            statistics=statistics
        )
