"""
Утилиты для визуализации RDF графов
"""

from graphviz import Digraph
from rdflib import Graph, Literal, RDFS, RDF
from typing import Dict


def short_name(uri: str) -> str:
    """Извлекает короткое имя из URI"""
    return uri.split("#")[-1].split("/")[-1]


def visualize_graph_with_comparison(graph: Graph, comparison: Dict, graph_type: str, filename: str):
    """
    Визуализирует граф с раскраской узлов и рёбер
    
    Args:
        graph: RDF граф
        comparison: Результат сравнения
        graph_type: 'expected' или 'actual'
        filename: Путь для сохранения
    """
    dot = Digraph(
        name=graph_type.capitalize(),
        format="png",
        graph_attr={
            "rankdir": "LR",
            "fontsize": "10",
            "label": f"{graph_type.capitalize()} Graph"
        },
        node_attr={"shape": "box", "style": "rounded,filled"}
    )

    # Подготовка данных для раскраски
    common_nodes = {short_name(n) for n in comparison['nodes']['common']}
    missing_nodes = {short_name(n) for n in comparison['nodes']['missing']}
    extra_nodes = {short_name(n) for n in comparison['nodes']['extra']}
    common_edges = {(short_name(s), short_name(p), short_name(o)) 
                   for s, p, o in comparison['edges']['common']}
    missing_edges = {(short_name(s), short_name(p), short_name(o)) 
                    for s, p, o in comparison['edges']['missing']}
    extra_edges = {(short_name(s), short_name(p), short_name(o)) 
                  for s, p, o in comparison['edges']['extra']}

    added_nodes = set()

    for s, p, o in graph:
        if str(p) == str(RDF.type) or str(p) == str(RDFS.label):
            continue
        if isinstance(o, Literal):
            continue

        s_id = short_name(s)
        o_id = short_name(o)
        p_label = short_name(p)

        # Цвета узлов
        if graph_type == 'expected':
            s_color = "lightgreen" if s_id in common_nodes else "lightcoral"
            o_color = "lightgreen" if o_id in common_nodes else "lightcoral"
        else:  # actual
            s_color = "lightgreen" if s_id in common_nodes else "lightyellow"
            o_color = "lightgreen" if o_id in common_nodes else "lightyellow"

        if s_id not in added_nodes:
            dot.node(s_id, s_id, fillcolor=s_color)
            added_nodes.add(s_id)
        if o_id not in added_nodes:
            dot.node(o_id, o_id, fillcolor=o_color)
            added_nodes.add(o_id)

        # Цвета рёбер
        edge_tuple = (s_id, p_label, o_id)
        if edge_tuple in common_edges:
            dot.edge(s_id, o_id, label=p_label, color="green", penwidth="2")
        elif graph_type == 'expected':
            dot.edge(s_id, o_id, label=p_label, color="red", style="dashed")
        else:  # actual
            dot.edge(s_id, o_id, label=p_label, color="orange", style="dashed")

    dot.render(filename, view=False)
    print(f"Saved: {filename}.png")


def visualize_diff_graph(expected_graph: Graph, actual_graph: Graph, 
                         comparison: Dict, filename: str):
    """
    Создаёт объединённую визуализацию различий
    """
    dot = Digraph(
        name="Diff",
        format="png",
        graph_attr={
            "rankdir": "LR",
            "fontsize": "10",
            "label": "Difference Graph (Green=Match, Red=Missing, Orange=Extra)"
        },
        node_attr={"shape": "box", "style": "rounded,filled"}
    )

    common_nodes = {short_name(n) for n in comparison['nodes']['common']}
    missing_nodes = {short_name(n) for n in comparison['nodes']['missing']}
    extra_nodes = {short_name(n) for n in comparison['nodes']['extra']}
    common_edges = {(short_name(s), short_name(p), short_name(o)) 
                   for s, p, o in comparison['edges']['common']}
    missing_edges = {(short_name(s), short_name(p), short_name(o)) 
                    for s, p, o in comparison['edges']['missing']}
    extra_edges = {(short_name(s), short_name(p), short_name(o)) 
                  for s, p, o in comparison['edges']['extra']}

    all_nodes = common_nodes | missing_nodes | extra_nodes
    
    # Узлы
    for node in all_nodes:
        if node in common_nodes:
            dot.node(node, node, fillcolor="lightgreen")
        elif node in missing_nodes:
            dot.node(node, node, fillcolor="lightcoral")
        else:
            dot.node(node, node, fillcolor="lightyellow")
    
    # Рёбра
    for s_id, p_label, o_id in common_edges:
        dot.edge(s_id, o_id, label=p_label, color="green", penwidth="2")
    
    for s_id, p_label, o_id in missing_edges:
        dot.edge(s_id, o_id, label=p_label, color="red", style="dashed")
    
    for s_id, p_label, o_id in extra_edges:
        dot.edge(s_id, o_id, label=p_label, color="orange", style="dotted")

    # Легенда
    with dot.subgraph(name='cluster_legend') as legend:
        legend.attr(label='Legend', fontsize='12', style='filled', color='lightgray')
        legend.node('leg_match', 'Green: Correct Match', shape='plaintext', fontcolor='green')
        legend.node('leg_missing', 'Red: Missing in Actual', shape='plaintext', fontcolor='red')
        legend.node('leg_extra', 'Orange: Extra in Actual', shape='plaintext', fontcolor='orange')

    dot.render(filename, view=False)
    print(f"Saved: {filename}.png")