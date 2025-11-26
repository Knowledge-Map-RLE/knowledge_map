"""
DAG builder and analysis functions
"""

import networkx as nx
from typing import List, Dict
from collections import defaultdict

from .models import Action, Dependency


class DAGBuilder:
    """Строит и анализирует DAG из действий и зависимостей"""

    def __init__(self, confidence_threshold: float = 0.7):
        self.confidence_threshold = confidence_threshold

    def build_dag(self, actions: List[Action], dependencies: List[Dependency]) -> nx.DiGraph:
        """Строит направленный ациклический граф"""
        print("Построение DAG...")

        G = nx.DiGraph()

        # Добавляем узлы
        for action in actions:
            G.add_node(
                action.id,
                verb=action.verb,
                verb_text=action.verb_text,
                subject=action.subject,
                object=action.object,
                sentence=action.sentence_text,
                sentence_idx=action.sentence_idx
            )

        # Добавляем рёбра
        for dep in dependencies:
            if dep.confidence >= self.confidence_threshold:
                G.add_edge(
                    dep.source_id,
                    dep.target_id,
                    relation=dep.relation_type,
                    confidence=dep.confidence,
                    markers=dep.markers
                )

        # Объединяем узлы с идентичными триплетами (subject, verb, object)
        G = self._merge_duplicate_nodes(G)

        # Проверяем ацикличность
        if not nx.is_directed_acyclic_graph(G):
            print("[WARNING] Граф содержит циклы! Удаляем рёбра с наименьшей уверенностью...")
            G = self._break_cycles(G)

        print(f"[OK] DAG построен: {G.number_of_nodes()} узлов, {G.number_of_edges()} рёбер")
        return G

    def _break_cycles(self, G: nx.DiGraph) -> nx.DiGraph:
        """Удаляет рёбра для устранения циклов"""
        while not nx.is_directed_acyclic_graph(G):
            try:
                cycle = nx.find_cycle(G)
                min_confidence = float('inf')
                edge_to_remove = None

                for u, v in cycle:
                    confidence = G[u][v].get('confidence', 0.5)
                    if confidence < min_confidence:
                        min_confidence = confidence
                        edge_to_remove = (u, v)

                if edge_to_remove:
                    print(f"  Удаляем: {edge_to_remove} (conf={min_confidence:.2f})")
                    G.remove_edge(*edge_to_remove)
            except nx.NetworkXNoCycle:
                break

        return G

    def _merge_duplicate_nodes(self, G: nx.DiGraph) -> nx.DiGraph:
        """
        Объединяет узлы с идентичными триплетами (subject, verb, object).

        Сохраняет DAG структуру, перенаправляя все входящие и исходящие рёбра
        дубликатов на канонический узел.

        Args:
            G: Граф для обработки

        Returns:
            Граф с объединёнными дубликатами
        """
        from collections import defaultdict

        # Создаём каноническую форму триплета для каждого узла
        triplet_to_nodes = defaultdict(list)

        for node_id in G.nodes():
            node_data = G.nodes[node_id]

            # Нормализуем значения (убираем None, приводим к нижнему регистру)
            subject = str(node_data.get('subject', '')).lower().strip()
            verb = str(node_data.get('verb', '')).lower().strip()
            obj = str(node_data.get('object', '')).lower().strip()

            # Создаём каноническую форму триплета
            triplet = (subject, verb, obj)

            # Группируем узлы по триплетам
            triplet_to_nodes[triplet].append(node_id)

        # Подсчитываем количество дубликатов
        duplicates_count = sum(len(nodes) - 1 for nodes in triplet_to_nodes.values() if len(nodes) > 1)

        if duplicates_count == 0:
            print("  Дубликатов узлов не найдено")
            return G

        print(f"  Найдено {duplicates_count} дубликатов узлов, объединяем...")

        # Для каждой группы дубликатов объединяем узлы
        nodes_to_remove = set()
        merge_mapping = {}  # {duplicate_id: canonical_id}

        for triplet, node_ids in triplet_to_nodes.items():
            if len(node_ids) <= 1:
                continue

            # Выбираем канонический узел (первый по алфавиту)
            canonical_id = sorted(node_ids)[0]

            # Остальные - дубликаты
            for duplicate_id in node_ids[1:]:
                merge_mapping[duplicate_id] = canonical_id
                nodes_to_remove.add(duplicate_id)

                # Переносим все входящие рёбра дубликата на канонический узел
                for predecessor in list(G.predecessors(duplicate_id)):
                    edge_data = G[predecessor][duplicate_id]
                    # Добавляем ребро, если оно ещё не существует
                    if not G.has_edge(predecessor, canonical_id):
                        G.add_edge(predecessor, canonical_id, **edge_data)
                    else:
                        # Если ребро уже есть, берём максимальную уверенность
                        existing_confidence = G[predecessor][canonical_id].get('confidence', 0)
                        new_confidence = edge_data.get('confidence', 0)
                        if new_confidence > existing_confidence:
                            G[predecessor][canonical_id].update(edge_data)

                # Переносим все исходящие рёбра дубликата на канонический узел
                for successor in list(G.successors(duplicate_id)):
                    edge_data = G[duplicate_id][successor]
                    # Добавляем ребро, если оно ещё не существует
                    if not G.has_edge(canonical_id, successor):
                        G.add_edge(canonical_id, successor, **edge_data)
                    else:
                        # Если ребро уже есть, берём максимальную уверенность
                        existing_confidence = G[canonical_id][successor].get('confidence', 0)
                        new_confidence = edge_data.get('confidence', 0)
                        if new_confidence > existing_confidence:
                            G[canonical_id][successor].update(edge_data)

        # Удаляем дубликаты
        G.remove_nodes_from(nodes_to_remove)

        print(f"  Объединено {len(nodes_to_remove)} дубликатов, осталось {G.number_of_nodes()} узлов")

        return G

    def get_statistics(self, dag: nx.DiGraph) -> Dict:
        """Возвращает статистику DAG"""
        # Типы зависимостей
        relation_types = defaultdict(int)
        for u, v, data in dag.edges(data=True):
            relation_types[data.get('relation', 'unknown')] += 1

        # Глубина графа (максимальная длина пути)
        try:
            longest_path_length = nx.dag_longest_path_length(dag) if dag.number_of_edges() > 0 else 0
        except:
            longest_path_length = 0

        return {
            'nodes': dag.number_of_nodes(),
            'edges': dag.number_of_edges(),
            'density': nx.density(dag),
            'is_dag': nx.is_directed_acyclic_graph(dag),
            'relation_types': dict(relation_types),
            'longest_path_length': longest_path_length
        }

    def identify_goals(self, dag: nx.DiGraph) -> List[str]:
        """Идентифицирует РЕАЛЬНЫЕ цели исследования, а не просто листовые узлы"""
        goals = set()

        # Ключевые слова для целей исследования
        GOAL_KEYWORDS = {
            'treatment', 'therapy', 'cure', 'prevention',
            'diagnosis', 'understanding', 'research',
            'discovery', 'development', 'improvement',
            'targeting', 'intervention', 'approach'
        }

        # Целевые глаголы
        GOAL_VERBS = {
            'treat', 'cure', 'prevent', 'diagnose',
            'understand', 'discover', 'develop', 'improve',
            'target', 'intervene', 'explore', 'investigate',
            'achieve', 'obtain', 'reach', 'attain', 'accomplish',
            'result', 'demonstrate', 'show', 'find',
            'prove', 'establish', 'determine', 'identify', 'reveal',
            'restore', 'protect', 'form', 'prepare'
        }

        for node in dag.nodes():
            node_data = dag.nodes[node]

            # 1. Цель если глагол целевой
            if node_data.get('verb') in GOAL_VERBS:
                goals.add(node)
                continue

            # 2. Цель если объект содержит ключевое слово
            obj = node_data.get('object')
            if obj and any(keyword in obj.lower() for keyword in GOAL_KEYWORDS):
                goals.add(node)
                continue

            # 3. Цель если это target PURPOSE зависимости
            for u, v, data in dag.in_edges(node, data=True):
                if data.get('relation') == 'PURPOSE':
                    goals.add(node)
                    break

        # 4. Исключаем высокочастотные промежуточные хабы
        goals_filtered = set()
        for node in goals:
            in_deg = dag.in_degree(node)
            out_deg = dag.out_degree(node)

            # Если это хаб (много входов и выходов), возможно это не цель
            if in_deg >= 3 and out_deg >= 2:
                continue

            goals_filtered.add(node)

        leaf_count = sum(1 for n in dag.nodes() if dag.out_degree(n) == 0)
        print(f"[OK] Идентифицировано {len(goals_filtered)} целей (вместо {leaf_count} листьев)")
        return list(goals_filtered)

    def extract_success_patterns(self, dag: nx.DiGraph, goals: List[str]) -> List[Dict]:
        """Извлекает паттерны успеха (подграфы к целям)"""
        patterns = []

        for goal_id in goals:
            try:
                ancestors = nx.ancestors(dag, goal_id)
            except:
                ancestors = set()

            if len(ancestors) > 0:
                subgraph_nodes = list(ancestors) + [goal_id]
                pattern_subgraph = dag.subgraph(subgraph_nodes).copy()

                # Анализ паттерна
                pattern_info = self._analyze_pattern(pattern_subgraph, goal_id)

                patterns.append({
                    'goal_id': goal_id,
                    'goal_verb': dag.nodes[goal_id].get('verb'),
                    'subgraph': pattern_subgraph,
                    'num_actions': len(subgraph_nodes),
                    'depth': pattern_info['depth'],
                    'width': pattern_info['width'],
                    'critical_path': pattern_info['critical_path'],
                    'relation_types': pattern_info['relation_types']
                })

        # Сортируем по размеру
        patterns.sort(key=lambda p: p['num_actions'], reverse=True)
        return patterns

    def _analyze_pattern(self, subgraph: nx.DiGraph, goal_id: str) -> Dict:
        """Анализирует паттерн"""
        # Глубина
        max_depth = 0
        critical_path = []

        start_nodes = [n for n in subgraph.nodes() if subgraph.in_degree(n) == 0]

        for start in start_nodes:
            if nx.has_path(subgraph, start, goal_id):
                try:
                    paths = list(nx.all_simple_paths(subgraph, start, goal_id, cutoff=10))
                    for path in paths:
                        if len(path) > max_depth:
                            max_depth = len(path)
                            critical_path = path
                except:
                    pass

        # Ширина
        levels = defaultdict(set)
        for node in subgraph.nodes():
            if nx.has_path(subgraph, node, goal_id):
                try:
                    shortest_path_length = nx.shortest_path_length(subgraph, node, goal_id)
                    levels[shortest_path_length].add(node)
                except:
                    pass

        max_width = max(len(nodes) for nodes in levels.values()) if levels else 0

        # Типы отношений
        relation_types = defaultdict(int)
        for u, v, data in subgraph.edges(data=True):
            relation_types[data.get('relation', 'unknown')] += 1

        return {
            'depth': max_depth,
            'width': max_width,
            'critical_path': critical_path,
            'relation_types': dict(relation_types)
        }

    def rank_patterns(self, patterns: List[Dict]) -> List[Dict]:
        """Ранжирует паттерны по важности"""
        for pattern in patterns:
            score = 0
            score += pattern['num_actions'] * 1.0
            score += pattern['depth'] * 2.0

            causal_count = pattern['relation_types'].get('CAUSES', 0) + \
                           pattern['relation_types'].get('ENABLES', 0)
            score += causal_count * 3.0

            pattern['importance_score'] = score

        patterns.sort(key=lambda p: p['importance_score'], reverse=True)
        return patterns
