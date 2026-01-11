"""
Утилиты для сравнения ожидаемых и фактических графов
"""

from typing import Dict, Set, Tuple
from rdflib import Graph, Literal, RDFS, RDF


def extract_nodes(graph: Graph) -> Set[str]:
    """Извлекает множество узлов из графа"""
    nodes = set()
    for s, p, o in graph:
        if str(p) == str(RDFS.label) or str(p) == str(RDF.type):
            continue
        if not isinstance(o, Literal):
            nodes.add(str(s))
            nodes.add(str(o))
    return nodes


def extract_edges(graph: Graph) -> Set[Tuple[str, str, str]]:
    """Извлекает множество рёбер из графа"""
    edges = set()
    for s, p, o in graph:
        if str(p) == str(RDFS.label) or str(p) == str(RDF.type):
            continue
        if not isinstance(o, Literal):
            edges.add((str(s), str(p), str(o)))
    return edges


def compare_graphs(expected_graph: Graph, actual_graph: Graph) -> Dict:
    """
    Сравнивает два RDF графа
    
    Returns:
        Dict с узлами, рёбрами и метриками
    """
    expected_nodes = extract_nodes(expected_graph)
    actual_nodes = extract_nodes(actual_graph)
    expected_edges = extract_edges(expected_graph)
    actual_edges = extract_edges(actual_graph)
    
    # Сравнение узлов
    common_nodes = expected_nodes & actual_nodes
    missing_nodes = expected_nodes - actual_nodes
    extra_nodes = actual_nodes - expected_nodes
    
    # Сравнение рёбер
    common_edges = expected_edges & actual_edges
    missing_edges = expected_edges - actual_edges
    extra_edges = actual_edges - expected_edges
    
    # Метрики
    precision = len(common_edges) / len(actual_edges) if len(actual_edges) > 0 else 0
    recall = len(common_edges) / len(expected_edges) if len(expected_edges) > 0 else 0
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    node_coverage = len(common_nodes) / len(expected_nodes) if len(expected_nodes) > 0 else 0
    
    return {
        'nodes': {
            'common': common_nodes,
            'missing': missing_nodes,
            'extra': extra_nodes
        },
        'edges': {
            'common': common_edges,
            'missing': missing_edges,
            'extra': extra_edges
        },
        'metrics': {
            'precision': precision,
            'recall': recall,
            'f1_score': f1_score,
            'node_coverage': node_coverage
        }
    }


def print_comparison_stats(sentence_num: int, comparison: Dict):
    """Выводит статистику сравнения"""
    print("\n" + "="*60)
    print(f"SENTENCE {sentence_num} - GRAPH COMPARISON STATISTICS")
    print("="*60)
    print(f"\nNodes:")
    print(f"  Common:  {len(comparison['nodes']['common'])}")
    print(f"  Missing: {len(comparison['nodes']['missing'])}")
    print(f"  Extra:   {len(comparison['nodes']['extra'])}")
    print(f"\nEdges:")
    print(f"  Common:  {len(comparison['edges']['common'])}")
    print(f"  Missing: {len(comparison['edges']['missing'])}")
    print(f"  Extra:   {len(comparison['edges']['extra'])}")
    print(f"\nMetrics:")
    print(f"  Precision: {comparison['metrics']['precision']:.2%}")
    print(f"  Recall:    {comparison['metrics']['recall']:.2%}")
    print(f"  F1-Score:  {comparison['metrics']['f1_score']:.2%}")
    print(f"  Node Coverage: {comparison['metrics']['node_coverage']:.2%}")
    
    if comparison['nodes']['missing']:
        print(f"\nMissing nodes (first 10):")
        for node in list(comparison['nodes']['missing'])[:10]:
            print(f"  - {node.split('#')[-1].split('/')[-1]}")
    
    if comparison['edges']['missing']:
        print(f"\nMissing edges (first 10):")
        for s, p, o in list(comparison['edges']['missing'])[:10]:
            s_short = s.split('#')[-1].split('/')[-1]
            p_short = p.split('#')[-1].split('/')[-1]
            o_short = o.split('#')[-1].split('/')[-1]
            print(f"  - {s_short} --[{p_short}]--> {o_short}")
    
    print("="*60 + "\n")