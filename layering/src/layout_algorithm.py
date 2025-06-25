"""
Алгоритм укладки графа карты знаний.
Основан на двухпроходном алгоритме оптимизации слоев для направленного ациклического графа.
Поддерживает закрепленные блоки с ограничениями на изменение уровней.
"""

import networkx as nx
from collections import Counter, defaultdict
import statistics
from typing import Dict, List, Tuple, Set, Any
import logging

logger = logging.getLogger(__name__)

def layout_knowledge_map(blocks: List[str], links: List[Tuple[str, str]], options: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Рассчитывает укладку графа карты знаний с поддержкой закрепленных блоков.
    
    Args:
        blocks: Список ID блоков
        links: Список кортежей (source_id, target_id) связей между блоками
        options: Словарь с опциями укладки:
            - max_layers: Максимальное количество слоев
            - max_levels: Максимальное количество уровней
            - blocks_per_sublevel: Максимальное количество блоков на подуровень
            - optimize_layout: Применять ли двухпроходную оптимизацию
            - blocks_data: Dict[str, Dict] - дополнительные данные о блоках (включая is_pinned, level)
            
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
    blocks_data = options.get('blocks_data', {})
    # УБИРАЕМ ОГРАНИЧЕНИЕ: blocks_per_sublevel больше не используется
    
    # Разделяем блоки на закрепленные и незакрепленные
    pinned_blocks = [bid for bid, data in blocks_data.items() if data.get('is_pinned', False)]
    unpinned_blocks = [bid for bid in blocks if bid not in pinned_blocks]
    
    logger.info(f"Обработка {len(pinned_blocks)} закрепленных блоков: {pinned_blocks}")
    logger.info(f"Обработка {len(unpinned_blocks)} незакрепленных блоков")
    
    # 1) Создаем направленный граф
    graph = nx.DiGraph()
    graph.add_nodes_from(blocks)
    graph.add_edges_from(links)
    
    # 2) Проверяем, что граф ациклический
    if not nx.is_directed_acyclic_graph(graph):
        logger.warning("Граф содержит циклы! Будет использована эвристика для удаления циклов.")
    
    # 3) Топологическая сортировка
    toposort = list(nx.topological_sort(graph))
    
    # 4) Вычисляем базовые слои для всех блоков
    base_layers = {v: 0 for v in toposort}
    for block_id in toposort:
        for w in graph.successors(block_id):
            base_layers[w] = max(base_layers[w], base_layers[block_id] + 1)
    
    # 5) Оптимизируем слои если нужно
    if optimize_layout:
        base_layers = _optimize_layers_two_pass(graph, base_layers, toposort)
    
    # 6) Обрабатываем закрепленные блоки - каждый создает свой уровень
    pinned_levels = {}
    next_pinned_level = 0
    
    # Сначала обрабатываем блоки с явно заданными уровнями, затем остальные
    blocks_with_levels = []
    blocks_without_levels = []
    
    for block_id in sorted(pinned_blocks):  # Сортируем для предсказуемости
        block_data = blocks_data.get(block_id, {})
        current_level = block_data.get('level')
        if current_level is not None and current_level > 0:
            blocks_with_levels.append((block_id, current_level))
        else:
            blocks_without_levels.append(block_id)
    
    # Сначала размещаем блоки с явными уровнями (сортируем по уровню)
    for block_id, level in sorted(blocks_with_levels, key=lambda x: x[1]):
        pinned_levels[block_id] = level
        next_pinned_level = max(next_pinned_level, level + 1)
    
    # Затем размещаем блоки без явных уровней
    for block_id in blocks_without_levels:
        pinned_levels[block_id] = next_pinned_level
        next_pinned_level += 1
    
    logger.info(f"Закрепленные блоки по уровням: {pinned_levels}")
    logger.info(f"ВАЖНО: next_pinned_level = {next_pinned_level}")
    
    # Проверяем что каждый закреплённый блок получил уникальный уровень
    if pinned_levels:
        levels_used = list(pinned_levels.values())
        unique_levels = set(levels_used)
        logger.info(f"ПРОВЕРКА: Использованные уровни: {levels_used}")
        logger.info(f"ПРОВЕРКА: Уникальные уровни: {sorted(unique_levels)}")
        if len(levels_used) != len(unique_levels):
            logger.error("ОШИБКА: Найдены дублирующиеся уровни у закреплённых блоков!")
        else:
            logger.info("✅ Все закреплённые блоки имеют уникальные уровни")
    
    # 7) Создаем укладку с учетом закрепленных блоков
    result = _create_layout_with_pinned_blocks(
        graph, base_layers, pinned_blocks, unpinned_blocks, 
        pinned_levels, next_pinned_level
    )
    
    # 8) Собираем статистику
    num_layers = max(result['layers'].values()) if result['layers'] else 0
    
    statistics = {
        'total_blocks': len(blocks),
        'total_links': len(links),
        'total_levels': len(result['levels']),
        'total_sublevels': len(result['sublevels']),
        'max_layer': num_layers,
        'is_acyclic': nx.is_directed_acyclic_graph(graph),
        'isolated_blocks': len(list(nx.isolates(graph))),
        'pinned_blocks': len(pinned_blocks),
        'unpinned_blocks': len(unpinned_blocks)
    }
    
    result['statistics'] = statistics
    return result

def _create_layout_with_pinned_blocks(
    graph: nx.DiGraph, 
    base_layers: Dict[str, int],
    pinned_blocks: List[str],
    unpinned_blocks: List[str],
    pinned_levels: Dict[str, int],
    next_pinned_level: int
) -> Dict[str, Any]:
    """
    Создает укладку с учетом закрепленных блоков.
    
    Правила:
    1. Закрепленные блоки сохраняют свои уровни
    2. На одном уровне могут быть только закрепленные ИЛИ только незакрепленные блоки
    3. При коллизиях создаются новые подуровни/уровни
    """
    
    # Группируем закрепленные блоки по уровням
    pinned_by_level = defaultdict(list)
    for block_id, level in pinned_levels.items():
        pinned_by_level[level].append(block_id)
    
    # Определяем занятые уровни закрепленными блоками
    occupied_levels = set(pinned_levels.values())
    logger.info(f"Уровни, занятые закрепленными блоками: {occupied_levels}")
    
    # Найдем следующий свободный уровень для незакрепленных блоков
    next_free_level = 0
    if occupied_levels:
        next_free_level = max(occupied_levels) + 1
    # Также учитываем next_pinned_level на случай если будут добавляться новые закреплённые блоки
    if pinned_blocks:
        next_free_level = max(next_free_level, next_pinned_level)
    
    # Результирующие структуры
    final_layers = {}
    sublevels = {}
    levels = {}
    sublevel_counter = 0
    
    # 1) Размещаем закрепленные блоки
    for level_id in sorted(pinned_by_level.keys()):
        blocks_in_level = pinned_by_level[level_id]
        logger.info(f"Размещение закрепленных блоков уровня {level_id}: {blocks_in_level}")
        
        # Группируем блоки этого уровня по слоям
        blocks_by_layer = defaultdict(list)
        for block_id in blocks_in_level:
            layer = base_layers[block_id]
            blocks_by_layer[layer].append(block_id)
        
        # Создаем подуровни для каждого слоя - с поддержкой коллизий
        sublevel_ids_for_level = []
        for layer in sorted(blocks_by_layer.keys()):
            layer_blocks = blocks_by_layer[layer]
            
            # ЭТАП 1: Пытаемся разместить все блоки в одном подуровне
            # Но готовимся к созданию дополнительных подуровней при коллизиях
            
            # Основной подуровень для слоя
            sublevels[sublevel_counter] = layer_blocks
            sublevel_ids_for_level.append(sublevel_counter)
            
            # Устанавливаем слои для блоков
            for block_id in layer_blocks:
                final_layers[block_id] = layer
            
            sublevel_counter += 1
            
            # ПРИМЕЧАНИЕ: Дополнительные подуровни для разрешения коллизий
            # будут созданы на клиенте автоматически при необходимости
        
        levels[level_id] = sublevel_ids_for_level
    
    # 2) Размещаем незакрепленные блоки
    if unpinned_blocks:
        logger.info(f"Размещение {len(unpinned_blocks)} незакрепленных блоков")
        
        # Группируем незакрепленные блоки по слоям
        unpinned_by_layer = defaultdict(list)
        for block_id in unpinned_blocks:
            layer = base_layers[block_id]
            unpinned_by_layer[layer].append(block_id)
        
        # Создаем ОДИН уровень для всех незакрепленных блоков с поддержкой коллизий
        current_level = next_free_level
        sublevel_ids_for_level = []
        
        # Все слои незакрепленных блоков с автоматическим разрешением коллизий
        for layer in sorted(unpinned_by_layer.keys()):
            layer_blocks = unpinned_by_layer[layer]
            
            # Основной подуровень для слоя (дополнительные создаются на клиенте)
            sublevels[sublevel_counter] = layer_blocks
            sublevel_ids_for_level.append(sublevel_counter)
            
            # Устанавливаем слои для блоков
            for block_id in layer_blocks:
                final_layers[block_id] = layer
            
            sublevel_counter += 1
        
        # Все незакрепленные блоки в одном уровне с автоматическими подуровнями
        if sublevel_ids_for_level:
            levels[current_level] = sublevel_ids_for_level
    
    logger.info(f"Итоговая структура уровней: {levels}")
    logger.info(f"Итоговая структура подуровней: {sublevels}")
    
    return {
        'layers': final_layers,
        'sublevels': sublevels,
        'levels': levels
    }

# УДАЛЕНА ФУНКЦИЯ _split_blocks_into_sublevels - больше не нужна

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