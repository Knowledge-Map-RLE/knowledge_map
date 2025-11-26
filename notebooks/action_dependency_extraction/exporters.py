"""
Exporters for results in various formats
"""

import os
import json
import pandas as pd
import networkx as nx
from typing import List, Dict

from .models import Action, Dependency


class ResultExporter:
    """Экспортирует результаты в различных форматах"""

    def __init__(self, output_dir: str = 'results'):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def export_all(self, dag: nx.DiGraph, actions: List[Action],
                   dependencies: List[Dependency], goals: List[str],
                   patterns: List[Dict]):
        """Экспортирует все результаты"""
        print(f"\nЭкспорт результатов в '{self.output_dir}/'...")

        self.export_actions(actions)
        self.export_dependencies(dependencies)
        self.export_dag_gml(dag)
        self.export_dag_json(dag)
        self.export_goals(dag, goals)
        self.export_patterns(patterns)

        print(f"[OK] Все результаты экспортированы!")

    def export_actions(self, actions: List[Action]):
        """Экспорт действий в CSV"""
        actions_df = pd.DataFrame([action.to_dict() for action in actions])
        path = f'{self.output_dir}/actions.csv'
        actions_df.to_csv(path, index=False, encoding='utf-8')
        print(f"  [OK] Действия: {path}")

    def export_dependencies(self, dependencies: List[Dependency]):
        """Экспорт зависимостей в CSV"""
        deps_df = pd.DataFrame([dep.to_dict() for dep in dependencies])
        path = f'{self.output_dir}/dependencies.csv'
        deps_df.to_csv(path, index=False, encoding='utf-8')
        print(f"  [OK] Зависимости: {path}")

    def export_dag_gml(self, dag: nx.DiGraph):
        """Экспорт графа в GML с правильными переносами строк"""
        # Создаём маппинг с переносом строки
        mapping = {}
        for node in dag.nodes():
            node_data = dag.nodes[node]
            verb = node_data.get('verb', '?')
            subject = node_data.get('subject') or '?'
            obj = node_data.get('object') or '?'

            predicate_text = f"{subject} -> {verb} -> {obj}"
            new_label = f"{node}\n{predicate_text}"
            mapping[node] = new_label

        # Переименовываем узлы
        dag_clean = nx.relabel_nodes(dag, mapping, copy=True)

        # Очищаем None и списки
        for node in dag_clean.nodes():
            for key in list(dag_clean.nodes[node].keys()):
                value = dag_clean.nodes[node][key]
                if value is None:
                    dag_clean.nodes[node][key] = ""
                elif isinstance(value, list):
                    dag_clean.nodes[node][key] = str(value)

        for u, v in dag_clean.edges():
            for key in list(dag_clean[u][v].keys()):
                value = dag_clean[u][v][key]
                if value is None:
                    dag_clean[u][v][key] = ""
                elif isinstance(value, list):
                    dag_clean[u][v][key] = str(value)

        # Записываем GML
        gml_path = f'{self.output_dir}/dag.gml'
        nx.write_gml(dag_clean, gml_path)

        # Постобработка: заменяем &#10; на реальный \n
        with open(gml_path, 'r', encoding='utf-8') as f:
            gml_content = f.read()

        gml_content = gml_content.replace('&#10;', '\n')

        with open(gml_path, 'w', encoding='utf-8') as f:
            f.write(gml_content)

        print(f"  [OK] Граф (GML): {gml_path}")

    def export_dag_json(self, dag: nx.DiGraph):
        """Экспорт графа в JSON"""
        from networkx.readwrite import json_graph

        dag_json = json_graph.node_link_data(dag)
        path = f'{self.output_dir}/dag.json'

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(dag_json, f, indent=2, ensure_ascii=False)

        print(f"  [OK] Граф (JSON): {path}")

    def export_goals(self, dag: nx.DiGraph, goals: List[str]):
        """Экспорт целей"""
        goals_info = [self._get_goal_info(dag, g) for g in goals]
        path = f'{self.output_dir}/goals.json'

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(goals_info, f, indent=2, ensure_ascii=False, default=str)

        print(f"  [OK] Цели: {path}")

    def export_patterns(self, patterns: List[Dict]):
        """Экспорт паттернов"""
        patterns_export = []
        for pattern in patterns:
            patterns_export.append({
                'goal_id': pattern['goal_id'],
                'goal_verb': pattern['goal_verb'],
                'num_actions': pattern['num_actions'],
                'depth': pattern['depth'],
                'width': pattern['width'],
                'importance_score': pattern.get('importance_score', 0),
                'critical_path': pattern['critical_path'],
                'relation_types': pattern['relation_types']
            })

        path = f'{self.output_dir}/patterns.json'
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(patterns_export, f, indent=2, ensure_ascii=False)

        print(f"  [OK] Паттерны: {path}")

    def _get_goal_info(self, dag: nx.DiGraph, goal_id: str) -> Dict:
        """Получает информацию о цели"""
        node_data = dag.nodes[goal_id]

        # Находим пути к цели
        paths_to_goal = []
        for source in dag.nodes():
            if source != goal_id and nx.has_path(dag, source, goal_id):
                if dag.in_degree(source) == 0:
                    try:
                        paths = list(nx.all_simple_paths(dag, source, goal_id, cutoff=10))
                        paths_to_goal.extend(paths)
                    except:
                        pass

        return {
            'id': goal_id,
            'verb': node_data.get('verb'),
            'subject': node_data.get('subject'),
            'object': node_data.get('object'),
            'sentence': node_data.get('sentence'),
            'num_paths': len(paths_to_goal),
            'paths': paths_to_goal[:5]
        }
