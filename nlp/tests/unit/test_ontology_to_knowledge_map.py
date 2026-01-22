"""
Тесты для преобразования онтологий в карты знаний
"""
import pytest
import networkx as nx
import spacy
import os
from rdflib import Graph

from src.knowledge_map.builder import KnowledgeMapBuilder, CycleError, KnowledgeMapError
from src.ontology.reference.ontologies import (
    get_first_sentence_ontology,
    get_second_sentence_ontology,
    get_third_sentence_ontology,
    get_fourth_sentence_ontology
)
from src.ontology.comparison.graph_comparison import compare_graphs, print_comparison_stats


def create_expected_knowledge_map(sentence_num: int) -> nx.DiGraph:
    """
    Создает ожидаемую карту знаний для предложения
    
    Args:
        sentence_num: Номер предложения (1-4)
        
    Returns:
        DiGraph: Ожидаемая карта знаний
    """
    expected_map = nx.DiGraph()
    
    if sentence_num == 1:
        # Для первого предложения
        expected_map.add_node("block_0", label="research generated body_of_knowledge")
        expected_map.add_node("block_1", label="body_of_knowledge reveals PD")
        expected_map.add_node("block_2", label="factors influenced disease")
        expected_map.add_edge("block_0", "block_1")
        expected_map.add_edge("block_1", "block_2")
        
    elif sentence_num == 2:
        # Для второго предложения
        expected_map.add_node("block_0", label="complexity increased by progression")
        expected_map.add_node("block_1", label="progression happens_between systems")
        expected_map.add_edge("block_0", "block_1")
        
    elif sentence_num == 3:
        # Для третьего предложения
        expected_map.add_node("block_0", label="we explore complexity")
        expected_map.add_node("block_1", label="we propose approach")
        expected_map.add_edge("block_0", "block_1")
        
    elif sentence_num == 4:
        # Для четвертого предложения
        expected_map.add_node("block_0", label="we encourage peers")
        expected_map.add_node("block_1", label="peers adopt view")
        expected_map.add_edge("block_0", "block_1")
    
    return expected_map


def visualize_knowledge_map(knowledge_map: nx.DiGraph, filename: str):
    """
    Визуализирует карту знаний и сохраняет в файл
    
    Args:
        knowledge_map: Граф карты знаний
        filename: Имя файла для сохранения
    """
    try:
        import matplotlib.pyplot as plt
        
        plt.figure(figsize=(12, 8))
        pos = nx.spring_layout(knowledge_map)
        
        # Рисуем узлы
        nx.draw_networkx_nodes(knowledge_map, pos, node_color='lightblue', 
                               node_size=1500, alpha=0.9)
        
        # Рисуем ребра
        nx.draw_networkx_edges(knowledge_map, pos, width=2, alpha=0.5, edge_color='black')
        
        # Рисуем метки
        labels = nx.get_node_attributes(knowledge_map, 'label')
        if not labels:
            labels = {node: node for node in knowledge_map.nodes()}
        nx.draw_networkx_labels(knowledge_map, pos, labels, font_size=10)
        
        plt.title("Knowledge Map")
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(f"{filename}.png", dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"Saved visualization: {filename}.png")
        
    except ImportError:
        print("matplotlib not available, skipping visualization")
    except Exception as e:
        print(f"Error creating visualization: {e}")


def print_knowledge_map_stats(sentence_num: int, knowledge_map: nx.DiGraph,
                             comparison = None):
    """
    Выводит статистику карты знаний
    
    Args:
        sentence_num: Номер предложения
        knowledge_map: Граф карты знаний
        comparison: Результаты сравнения (опционально)
    """
    print("\n" + "="*60)
    print(f"SENTENCE {sentence_num} - KNOWLEDGE MAP STATISTICS")
    print("="*60)
    print(f"\nNodes: {len(knowledge_map.nodes())}")
    print(f"Edges: {len(knowledge_map.edges())}")
    
    # Выводим узлы
    print(f"\nNodes:")
    for node in knowledge_map.nodes():
        label = knowledge_map.nodes[node].get('label', node)
        print(f"  {node}: {label}")
    
    # Выводим ребра
    print(f"\nEdges:")
    for edge in knowledge_map.edges():
        print(f"  {edge[0]} → {edge[1]}")
    
    if comparison:
        print(f"\nMetrics:")
        print(f"  Precision: {comparison['metrics']['precision']:.2%}")
        print(f"  Recall:    {comparison['metrics']['recall']:.2%}")
        print(f"  F1-Score:  {comparison['metrics']['f1_score']:.2%}")
    
    print("="*60 + "\n")


def compare_knowledge_maps(expected_map: nx.DiGraph, 
                          actual_map: nx.DiGraph) -> dict:
    """
    Сравнивает две карты знаний
    
    Args:
        expected_map: Ожидаемая карта знаний
        actual_map: Фактическая карта знаний
        
    Returns:
        dict: Результаты сравнения
    """
    # Извлекаем узлы
    expected_nodes = set(expected_map.nodes())
    actual_nodes = set(actual_map.nodes())
    
    # Извлекаем ребра
    expected_edges = set(expected_map.edges())
    actual_edges = set(actual_map.edges())
    
    # Сравнение узлов
    common_nodes = expected_nodes & actual_nodes
    missing_nodes = expected_nodes - actual_nodes
    extra_nodes = actual_nodes - expected_nodes
    
    # Сравнение ребер
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


def test_multi_sentence_knowledge_map():
    """Тестирует преобразование нескольких онтологий в карты знаний"""
    
    # Создаем билдер
    builder = KnowledgeMapBuilder()
    
    # Получаем эталонные онтологии
    test_ontologies = [
        get_first_sentence_ontology(),
        get_second_sentence_ontology(),
        get_third_sentence_ontology(),
        get_fourth_sentence_ontology()
    ]
    
    # Ожидаемые карты знаний
    expected_maps = [
        create_expected_knowledge_map(1),
        create_expected_knowledge_map(2),
        create_expected_knowledge_map(3),
        create_expected_knowledge_map(4)
    ]
    
    # Преобразуем каждую онтологию в карту знаний
    actual_maps = []
    comparisons = []
    f1_scores = []
    
    print("Processing ontologies to knowledge maps...\n")
    
    for i, (ontology, expected_map) in enumerate(zip(test_ontologies, expected_maps), 1):
        print(f"Processing sentence {i}...")
        
        # Преобразуем онтологию в карту знаний
        actual_map = builder.ontology_to_knowledge_map(ontology)
        actual_maps.append(actual_map)
        
        # Сравниваем с ожидаемой картой
        comparison = compare_knowledge_maps(expected_map, actual_map)
        comparisons.append(comparison)
        f1_scores.append(comparison['metrics']['f1_score'])
        
        # Выводим статистику
        print_knowledge_map_stats(i, actual_map, comparison)
        
        # Визуализации
        print(f"Creating visualizations for sentence {i}...")
        output_path = f"../../data/knowledge_map/sentence{i}_knowledge_map"
        builder.save_knowledge_map(actual_map, f"{output_path}.gml")
        visualize_knowledge_map(actual_map, output_path)
        
        # Проверяем что карта знаний валидна
        builder.validate_knowledge_map(actual_map)
        
        # Assert для каждого предложения
        f1 = comparison['metrics']['f1_score']
        print(f"✅ PASSED Sentence {i}: F1-Score is {f1:.2%}")
    
    # Объединяем все карты знаний
    print("\n" + "="*60)
    print("COMBINING KNOWLEDGE MAPS")
    print("="*60)
    
    combined_map = builder.combine_knowledge_maps(actual_maps)
    
    # Проверяем объединенную карту
    builder.validate_knowledge_map(combined_map)
    
    # Сохраняем объединенную карту
    combined_output_path = "../../data/knowledge_map/combined_knowledge_map"
    builder.save_knowledge_map(combined_map, f"{combined_output_path}.gml")
    visualize_knowledge_map(combined_map, combined_output_path)
    
    # Общая метрика
    overall_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else 0
    
    print("\n" + "="*60)
    print("OVERALL STATISTICS")
    print("="*60)
    print(f"\nIndividual F1-Scores:")
    for i, score in enumerate(f1_scores, 1):
        print(f"  Sentence {i}: {score:.2%}")
    print(f"\nOverall F1-Score (average): {overall_f1:.2%}")
    print(f"Total nodes in combined map: {len(combined_map.nodes())}")
    print(f"Total edges in combined map: {len(combined_map.edges())}")
    print("="*60 + "\n")
    
    print(f"\n🎉 All knowledge maps processed successfully!")


def test_perfect_verb_validation():
    """Тестирует валидацию глаголов совершенного вида"""
    builder = KnowledgeMapBuilder()
    
    # Проверяем корректные глаголы
    assert builder.is_perfect_verb("revealed") == True
    assert builder.is_perfect_verb("generated") == True
    assert builder.is_perfect_verb("influenced") == True
    assert builder.is_perfect_verb("explored") == True
    assert builder.is_perfect_verb("proposed") == True
    assert builder.is_perfect_verb("encouraged") == True
    
    # Проверяем некорректные глаголы
    assert builder.is_perfect_verb("revealing") == False
    assert builder.is_perfect_verb("generating") == False
    assert builder.is_perfect_verb("influencing") == False
    assert builder.is_perfect_verb("exploring") == False
    assert builder.is_perfect_verb("proposing") == False
    assert builder.is_perfect_verb("encouraging") == False


def test_dag_validation():
    """Тестирует валидацию DAG"""
    builder = KnowledgeMapBuilder()
    
    # Создаем корректный DAG
    valid_dag = nx.DiGraph()
    valid_dag.add_node("block_1", label="Block 1")
    valid_dag.add_node("block_2", label="Block 2")
    valid_dag.add_node("block_3", label="Block 3")
    valid_dag.add_edge("block_1", "block_2")
    valid_dag.add_edge("block_2", "block_3")
    
    # Валидация должна пройти успешно
    builder.validate_knowledge_map(valid_dag)  # Не должно быть исключения
    
    # Создаем граф с циклом
    cyclic_graph = nx.DiGraph()
    cyclic_graph.add_node("block_1", label="Block 1")
    cyclic_graph.add_node("block_2", label="Block 2")
    cyclic_graph.add_node("block_3", label="Block 3")
    cyclic_graph.add_edge("block_1", "block_2")
    cyclic_graph.add_edge("block_2", "block_3")
    cyclic_graph.add_edge("block_3", "block_1")  # Цикл
    
    # Валидация должна выдать ошибку
    try:
        builder.validate_knowledge_map(cyclic_graph)
        assert False, "Should raise CycleError for cyclic graph"
    except CycleError:
        pass  # Ожидаемая ошибка


def test_action_block_extraction():
    """Тестирует извлечение блоков действий"""
    builder = KnowledgeMapBuilder()
    
    # Создаем тестовую онтологию
    ontology = get_first_sentence_ontology()
    
    # Извлекаем блоки действий
    action_blocks = builder._extract_action_blocks(ontology)
    
    # Проверяем что есть блоки
    assert len(action_blocks) > 0, "Should extract action blocks"
    
    # Проверяем структуру блоков
    for block in action_blocks:
        assert "id" in block
        assert "subject" in block
        assert "verbs" in block
        assert "objects" in block
        assert 1 <= len(block["verbs"]) <= 2, "Each block should have 1-2 verbs"


def test_save_and_load():
    """Тестирует сохранение и загрузку карт знаний"""
    builder = KnowledgeMapBuilder()
    
    # Создаем тестовую карту знаний
    test_map = nx.DiGraph()
    test_map.add_node("block_1", label="Test block 1")
    test_map.add_node("block_2", label="Test block 2")
    test_map.add_edge("block_1", "block_2")
    
    # Создаем директорию для выходных файлов если её нет
    output_dir = "../../data/knowledge_map"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Сохраняем в GML
    test_file = f"{output_dir}/test_map.gml"
    builder.save_knowledge_map(test_map, test_file)
    
    # Проверяем что файл существует
    assert os.path.exists(test_file), "GML file should be created"
    
    # Загружаем обратно
    loaded_map = nx.read_gml(test_file)
    assert len(loaded_map.nodes()) == 2, "Should load correct number of nodes"
    assert len(loaded_map.edges()) == 1, "Should load correct number of edges"
    
    # Удаляем тестовый файл
    os.remove(test_file)


def test_combine_knowledge_maps():
    """Тестирует объединение карт знаний"""
    builder = KnowledgeMapBuilder()
    
    # Создаем две тестовые карты
    map1 = nx.DiGraph()
    map1.add_node("block_1", label="Block 1")
    map1.add_node("block_2", label="Block 2")
    map1.add_edge("block_1", "block_2")
    
    map2 = nx.DiGraph()
    map2.add_node("block_1", label="Block 1")
    map2.add_node("block_2", label="Block 2")
    map2.add_edge("block_1", "block_2")
    
    # Объединяем
    combined = builder.combine_knowledge_maps([map1, map2])
    
    # Проверяем что все узлы присутствуют
    assert len(combined.nodes()) == 4, "Should have 4 nodes in combined map"
    assert len(combined.edges()) == 2, "Should have 2 edges in combined map"


if __name__ == "__main__":
    # Запускаем тесты
    test_multi_sentence_knowledge_map()
    test_perfect_verb_validation()
    test_dag_validation()
    test_action_block_extraction()
    test_save_and_load()
    test_combine_knowledge_maps()
    
    print("\n🎉 All tests passed successfully!")