"""
Алгоритм укладки графа карты знаний.
Основан на двухпроходном алгоритме оптимизации слоев для направленного ациклического графа.
"""

import networkx as nx
from collections import Counter
import statistics
from typing import Dict, List, Tuple, Set, Any
import logging

logger = logging.getLogger(__name__)

def layout_knowledge_map(blocks: List[str], links: List[Tuple[str, str]], options: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Рассчитывает укладку графа карты знаний.
    
    Args:
        blocks: Список ID блоков
        links: Список кортежей (source_id, target_id) связей между блоками
        options: Словарь с опциями укладки:
            - max_layers: Максимальное количество слоев
            - max_levels: Максимальное количество уровней
            - blocks_per_sublevel: Максимальное количество блоков на подуровень
            - optimize_layout: Применять ли двухпроходную оптимизацию
            
    Returns:
        Dict с результатами укладки:
            - layers: Dict[str, int] - слой каждого блока
            - sublevels: Dict[int, List[str]] - блоки в каждом подуровне
            - levels: Dict[int, List[int]] - подуровни в каждом уровне
            - statistics: Dict[str, Any] - статистика укладки
    """
    # Значения по умолчанию для опций
    options = options or {}
    optimize_layout = options.get('optimize_layout', True)
    
    # 1) Создаем направленный граф
    graph = nx.DiGraph()
    graph.add_nodes_from(blocks)
    graph.add_edges_from(links)
    
    # 2) Проверяем, что граф ациклический
    if not nx.is_directed_acyclic_graph(graph):
        logger.warning("Граф содержит циклы! Будет использована эвристика для удаления циклов.")
        # TODO: Реализовать эвристику Feedback Arc Set для удаления минимального числа ребер
        # Пока просто используем существующие ребра
    
    # 3) Топологическая сортировка
    toposort = list(nx.topological_sort(graph))
    
    # 4) Вычисляем слои
    layers = {v: 0 for v in toposort}
    for block_id in toposort:
        for w in graph.successors(block_id):
            layers[w] = max(layers[w], layers[block_id] + 1)
    
    # 5) Оптимизируем слои если нужно
    if optimize_layout:
        layers = _optimize_layers_two_pass(graph, layers, toposort)
    
    # 6) Группируем блоки по слоям для создания подуровней
    nodes_by_layer = {}
    for block_id, layer in layers.items():
        if layer not in nodes_by_layer:
            nodes_by_layer[layer] = []
        nodes_by_layer[layer].append(block_id)
    
    # 7) Создаем подуровни (каждый слой = один подуровень)
    sublevels = {}
    sublevel_id = 0
    for layer in sorted(nodes_by_layer.keys()):
        sublevels[sublevel_id] = nodes_by_layer[layer]
        sublevel_id += 1
    
    # 8) Группируем подуровни в уровни
    levels = {}
    group_size = 2  # Количество подуровней в уровне
    sorted_sublevel_ids = sorted(sublevels.keys())
    
    for i in range(0, len(sorted_sublevel_ids), group_size):
        level_id = i // group_size
        sublevel_group = sorted_sublevel_ids[i:i + group_size]
        levels[level_id] = sublevel_group
    
    # 9) Собираем статистику
    num_layers = max(layers.values()) if layers else 0
    max_layer_width = Counter(layers.values()).most_common(1)[0][1] if layers else 0
    
    statistics = {
        'total_blocks': len(blocks),
        'total_links': len(links),
        'total_levels': len(levels),
        'total_sublevels': len(sublevels),
        'max_layer': num_layers,
        'is_acyclic': nx.is_directed_acyclic_graph(graph),
        'isolated_blocks': len(list(nx.isolates(graph)))
    }
    
    return {
        'layers': layers,
        'sublevels': sublevels,
        'levels': levels,
        'statistics': statistics
    }

def _optimize_layers_two_pass(graph: nx.DiGraph, initial_layers: Dict[str, int], toposort: List[str]) -> Dict[str, int]:
    """
    Двухпроходный алгоритм O(V + E) оптимизации слоев для DAG.
    """
    layers = initial_layers.copy()
    predecessors = {node: list(graph.predecessors(node)) for node in graph.nodes()}
    successors = {node: list(graph.successors(node)) for node in graph.nodes()}
    
    # Проход 1: Прямой порядок (оптимизация относительно предков)
    for node in toposort:
        if not predecessors[node]:
            continue
            
        min_layer = max(layers[pred] for pred in predecessors[node]) + 1
        max_layer = float('inf')
        
        if successors[node]:
            max_layer = min(layers[succ] for succ in successors[node]) - 1
            
        if min_layer <= max_layer:
            pred_positions = [layers[pred] for pred in predecessors[node]]
            median_preds = statistics.median(pred_positions)
            optimal = max(min_layer, round(median_preds + 1))
            
            if max_layer != float('inf'):
                optimal = min(optimal, max_layer)
                
            layers[node] = optimal
    
    # Проход 2: Обратный порядок (оптимизация относительно потомков)
    for node in reversed(toposort):
        if not successors[node]:
            continue
            
        max_layer = min(layers[succ] for succ in successors[node]) - 1
        min_layer = 0
        
        if predecessors[node]:
            min_layer = max(layers[pred] for pred in predecessors[node]) + 1
            
        if min_layer <= max_layer:
            succ_positions = [layers[succ] for succ in successors[node]]
            median_succs = statistics.median(succ_positions)
            optimal = min(max_layer, round(median_succs - 1))
            optimal = max(min_layer, optimal)
            
            layers[node] = optimal
    
    return layers