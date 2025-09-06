"""
Типы и перечисления для алгоритма укладки графа
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Tuple, Set, Any, Optional


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
    x: float
    y: float
    status: VertexStatus
    is_pinned: bool = False


@dataclass
class LayoutResult:
    """Результат укладки"""
    success: bool
    blocks: List[Dict[str, Any]]
    layers: Dict[str, int]
    levels: Dict[int, List[str]]
    statistics: Dict[str, Any]
    error: Optional[str] = None
