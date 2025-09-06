"""
Утилиты для позиционирования узлов в укладке графа
"""

import logging
from typing import Dict, List, Tuple, Optional
from .layout_types import VertexPosition

logger = logging.getLogger(__name__)


class PositionCalculator:
    """Калькулятор позиций для узлов"""
    
    def __init__(self, layer_spacing: float = 100.0, level_spacing: float = 200.0):
        self.LAYER_SPACING = layer_spacing
        self.LEVEL_SPACING = level_spacing
    
    def calculate_optimal_layer(self, neighbor_positions: Dict[str, List[VertexPosition]]) -> int:
        """Оптимальный layer: между предшественниками и потомками, иначе рядом с существующими."""
        pred_layers = [pos.layer for pos in neighbor_positions.get("predecessors", [])]
        succ_layers = [pos.layer for pos in neighbor_positions.get("successors", [])]

        if pred_layers and succ_layers:
            max_pred_layer = max(pred_layers)
            min_succ_layer = min(succ_layers)
            optimal_layer = (max_pred_layer + min_succ_layer) // 2
            logger.info(f"Optimal layer: between pred({max_pred_layer}) and succ({min_succ_layer}) = {optimal_layer}")
            return optimal_layer
        if pred_layers:
            optimal_layer = max(pred_layers) + 1
            logger.info(f"Optimal layer: after pred({pred_layers}) = {optimal_layer}")
            return optimal_layer
        if succ_layers:
            optimal_layer = min(succ_layers) - 1
            logger.info(f"Optimal layer: before succ({succ_layers}) = {optimal_layer}")
            return optimal_layer
        logger.info("Optimal layer: default = 0")
        return 0

    def calculate_optimal_level(self, neighbor_positions: Dict[str, List[VertexPosition]]) -> int:
        """Оптимальный level: без верхнего предела, ближе к потомкам и не накладываясь на предшественников.
        Уровни неограниченны - могут быть любыми положительными числами.

        Правило:
        - Если есть потомки: целевой уровень = min(level потомков) - 1 (чтобы быть над ними)
        - Иначе если есть предшественники: целевой уровень = max(level предшественников) + 1
        - Иначе: 0
        """
        successors = neighbor_positions.get("successors", [])
        predecessors = neighbor_positions.get("predecessors", [])

        if successors:
            # Стараемся быть как можно ближе к ближайшему потомку сверху
            min_succ_level = min(pos.level for pos in successors)
            optimal_level = max(0, min_succ_level - 1)
            logger.info(f"Optimal level: above succ({min_succ_level}) = {optimal_level}")
            return optimal_level

        if predecessors:
            max_pred_level = max(pos.level for pos in predecessors)
            optimal_level = max_pred_level + 1
            logger.info(f"Optimal level: below pred({max_pred_level}) = {optimal_level}")
            return optimal_level

        logger.info("Optimal level: default = 0")
        return 0

    def calculate_optimal_position_batch(self, pred_positions: List[Optional[Tuple[int, int]]], succ_positions: List[Optional[Tuple[int, int]]]) -> Tuple[int, int]:
        """Батчевое вычисление оптимальной позиции"""
        if not pred_positions and not succ_positions:
            return (0, 0)
        
        # Вычисляем оптимальный layer
        pred_layers = [pos[0] for pos in pred_positions if pos is not None]
        succ_layers = [pos[0] for pos in succ_positions if pos is not None]
        
        if pred_layers and succ_layers:
            layer = (max(pred_layers) + min(succ_layers)) // 2
        elif pred_layers:
            layer = max(pred_layers) + 1
        elif succ_layers:
            layer = min(succ_layers) - 1
        else:
            layer = 0
        
        # Вычисляем оптимальный level
        pred_levels = [pos[1] for pos in pred_positions if pos is not None]
        succ_levels = [pos[1] for pos in succ_positions if pos is not None]
        
        if succ_levels:
            level = max(0, min(succ_levels) - 1)
        elif pred_levels:
            level = max(pred_levels) + 1
        else:
            level = 0
        
        return (layer, level)

    def calculate_coordinates(self, layer: int, level: int) -> Tuple[float, float]:
        """Вычисляет координаты x, y на основе слоя и уровня"""
        x = layer * self.LAYER_SPACING
        y = level * self.LEVEL_SPACING
        return x, y
