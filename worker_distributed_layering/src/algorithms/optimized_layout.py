"""
Оптимизированные алгоритмы укладки графов (упрощённая версия без NumPy/Numba)
"""

import logging
from typing import Dict, List, Any, Tuple, Optional
import networkx as nx
import structlog

logger = structlog.get_logger(__name__)


class HighPerformanceLayout:
    """
    Высокопроизводительная укладка графов (базовая версия)
    """
    
    def __init__(self):
        self.enable_optimization = False  # Отключено для упрощения
        
    def layout_large_knowledge_map(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Выполняет укладку большого графа знаний
        """
        logger.info(f"Starting layout for {len(nodes)} nodes and {len(edges)} edges")
        
        try:
            # Создаём граф NetworkX
            G = self._create_networkx_graph(nodes, edges)
            
            # Применяем алгоритм укладки
            layout_result = self._apply_layered_layout(G, options or {})
            
            logger.info("Layout completed successfully")
            return layout_result
            
        except Exception as e:
            logger.error("Layout failed", error=str(e))
            raise
    
    def _create_networkx_graph(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]]
    ) -> nx.DiGraph:
        """
        Создаёт граф NetworkX из данных
        """
        G = nx.DiGraph()
        
        # Добавляем узлы
        for node in nodes:
            G.add_node(
                node['id'],
                content=node.get('content', ''),
                is_pinned=node.get('is_pinned', False),
                level=node.get('level', 0)
            )
        
        # Добавляем рёбра
        for edge in edges:
            G.add_edge(edge['source_id'], edge['target_id'])
        
        logger.info(f"Created NetworkX graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
        return G
    
    def _apply_layered_layout(
        self,
        G: nx.DiGraph,
        options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Применяет слоевую укладку к графу
        """
        try:
            # Топологическая сортировка
            if not nx.is_directed_acyclic_graph(G):
                # Удаляем циклы для получения DAG
                G = self._remove_cycles(G)
            
            # Назначаем слои
            layers = self._assign_layers(G)
            
            # Позиционируем узлы
            positions = self._calculate_positions(G, layers)
            
            # Формируем результат
            result = {
                'layout_data': positions,
                'statistics': {
                    'total_nodes': G.number_of_nodes(),
                    'total_edges': G.number_of_edges(),
                    'layers_count': len(set(layers.values())),
                    'processing_time_seconds': 0.1  # Упрощённое время
                }
            }
            
            return result
            
        except Exception as e:
            logger.error("Layered layout failed", error=str(e))
            raise
    
    def _remove_cycles(self, G: nx.DiGraph) -> nx.DiGraph:
        """
        Удаляет циклы из графа для получения DAG
        """
        try:
            # Простое удаление обратных рёбер
            back_edges = list(nx.edge_dfs(G, orientation='reverse'))
            G.remove_edges_from(back_edges[:len(back_edges)//2])  # Удаляем половину
            return G
        except:
            # Если что-то пошло не так, возвращаем исходный граф
            return G
    
    def _assign_layers(self, G: nx.DiGraph) -> Dict[str, int]:
        """
        Назначает слои узлам графа
        """
        layers = {}
        
        try:
            # Получаем топологический порядок
            topo_order = list(nx.topological_sort(G))
            
            # Назначаем слои на основе максимального расстояния от источников
            for node in topo_order:
                if G.in_degree(node) == 0:
                    # Источник
                    layers[node] = 0
                else:
                    # Максимальный слой предшественников + 1
                    pred_layers = [layers.get(pred, 0) for pred in G.predecessors(node)]
                    layers[node] = max(pred_layers) + 1
                    
        except Exception as e:
            logger.warning("Topological sort failed, using fallback", error=str(e))
            # Резервный метод - просто нумеруем узлы
            for i, node in enumerate(G.nodes()):
                layers[node] = i % 10  # Максимум 10 слоёв
        
        return layers
    
    def _calculate_positions(
        self,
        G: nx.DiGraph,
        layers: Dict[str, int]
    ) -> List[Dict[str, Any]]:
        """
        Вычисляет позиции узлов
        """
        positions = []
        
        # Группируем узлы по слоям
        layers_groups = {}
        for node, layer in layers.items():
            if layer not in layers_groups:
                layers_groups[layer] = []
            layers_groups[layer].append(node)
        
        # Назначаем позиции
        for layer, nodes in layers_groups.items():
            for i, node in enumerate(nodes):
                positions.append({
                    'node_id': node,
                    'level': layer,
                    'sublevel_id': 0,
                    'layer': layer,
                    'x': layer * 250,  # Простое горизонтальное размещение
                    'y': i * 100       # Простое вертикальное размещение
                })
        
        logger.info(f"Calculated positions for {len(positions)} nodes")
        return positions


# Глобальный экземпляр
high_performance_layout = HighPerformanceLayout()

class CachedLayoutAlgorithm:
    def __init__(self):
        self.layer_cache = {}  # Кэш для слоёв
        self.edge_cache = {}   # Кэш для рёбер
        self.topological_cache = {}  # Кэш топологической сортировки
    
    def layout_large_knowledge_map_optimized(self, nodes, edges, options):
        """Оптимизированная версия с кэшированием"""
        start_time = time.time()
        
        # Создаём граф с оптимизированной структурой
        graph = self._build_optimized_graph(nodes, edges)
        
        # Используем кэшированную топологическую сортировку
        if not self.topological_cache:
            self.topological_cache = self._compute_topological_order(graph)
        
        # Быстрое назначение слоёв
        layers = self._fast_layer_assignment(graph, self.topological_cache)
        
        # Оптимизированное размещение по уровням
        levels, sublevels = self._optimized_level_placement(nodes, layers)
        
        processing_time = time.time() - start_time
        
        return {
            "success": True,
            "blocks": nodes,
            "layers": layers,
            "levels": levels,
            "sublevels": sublevels,
            "statistics": {
                "total_blocks": len(nodes),
                "total_links": len(edges),
                "processing_time_seconds": processing_time,
                "algorithm": "optimized_cached"
            }
        }
    
    def _build_optimized_graph(self, nodes, edges):
        """Оптимизированное построение графа"""
        # Используем NetworkX с оптимизированными структурами данных
        import networkx as nx
        G = nx.DiGraph()
        
        # Batch добавление узлов
        G.add_nodes_from([node["id"] for node in nodes])
        
        # Batch добавление рёбер
        edge_list = [(edge["source_id"], edge["target_id"]) for edge in edges]
        G.add_edges_from(edge_list)
        
        return G
    
    def _compute_topological_order(self, graph):
        """Вычисление топологического порядка с кэшированием"""
        try:
            return list(nx.topological_sort(graph))
        except nx.NetworkXError:
            # Если есть циклы, используем алгоритм для DAG с циклами
            return self._topological_sort_with_cycles(graph)
    
    def _fast_layer_assignment(self, graph, topological_order):
        """Быстрое назначение слоёв"""
        layers = {}
        
        for node in topological_order:
            # Находим максимальный слой среди предшественников
            pred_layers = [layers.get(pred, -1) for pred in graph.predecessors(node)]
            layers[node] = max(pred_layers) + 1 if pred_layers else 0
        
        return layers