#!/usr/bin/env python3
"""
Script to generate knowledge maps and save them to data/knowledge_map
"""
import sys
import os
import networkx as nx

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.knowledge_map.builder import KnowledgeMapBuilder
from src.ontology.reference.ontologies import (
    get_first_sentence_ontology,
    get_second_sentence_ontology,
    get_third_sentence_ontology,
    get_fourth_sentence_ontology
)

def visualize_knowledge_map_graphviz(knowledge_map: nx.DiGraph, filename: str):
    """
    Визуализирует карту знаний с использованием graphviz
    
    Args:
        knowledge_map: Граф карты знаний (NetworkX DiGraph)
        filename: Путь для сохранения изображения (без расширения)
    """
    try:
        from graphviz import Digraph
        
        # Создаем графviz объект
        dot = Digraph(
            name="KnowledgeMap",
            format="png",
            graph_attr={
                "rankdir": "LR",
                "fontsize": "12",
                "label": "Knowledge Map"
            },
            node_attr={
                "shape": "box", 
                "style": "rounded,filled",
                "fillcolor": "lightblue"
            }
        )
        
        # Добавляем узлы
        for node in knowledge_map.nodes():
            label = knowledge_map.nodes[node].get('label', node)
            dot.node(node, label, fillcolor="lightblue")
        
        # Добавляем ребра
        for edge in knowledge_map.edges():
            dot.edge(edge[0], edge[1])
        
        # Сохраняем изображение
        dot.render(filename, view=False)
        print(f"Saved visualization: {filename}.png")
        return True
        
    except ImportError:
        print("graphviz not available, skipping visualization")
        return False
    except Exception as e:
        print(f"Error creating visualization: {e}")
        return False

def print_knowledge_map_stats(sentence_num: int, knowledge_map: nx.DiGraph):
    """
    Выводит статистику карты знаний
    
    Args:
        sentence_num: Номер предложения
        knowledge_map: Граф карты знаний
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
    
    print("="*60 + "\n")

def main():
    """Основная функция для генерации карт знаний"""
    # Создаем билдер
    builder = KnowledgeMapBuilder()
    
    # Получаем эталонные онтологии
    test_ontologies = [
        get_first_sentence_ontology(),
        get_second_sentence_ontology(),
        get_third_sentence_ontology(),
        get_fourth_sentence_ontology()
    ]
    
    # Преобразуем каждую онтологию в карту знаний
    actual_maps = []
    
    print("Processing ontologies to knowledge maps...\n")
    
    # Создаем директорию для выходных файлов если её нет
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "knowledge_map")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")
    
    for i, ontology in enumerate(test_ontologies, 1):
        print(f"Processing sentence {i}...")
        
        # Преобразуем онтологию в карту знаний
        actual_map = builder.ontology_to_knowledge_map(ontology)
        actual_maps.append(actual_map)
        
        # Выводим статистику
        print_knowledge_map_stats(i, actual_map)
        
        # Сохраняем файлы
        print(f"Saving files for sentence {i}...")
        output_path = os.path.join(output_dir, f"sentence{i}_knowledge_map")
        builder.save_knowledge_map(actual_map, f"{output_path}.gml")
        print(f"Saved GML file: {output_path}.gml")
        
        # Создаем изображение
        image_path = os.path.join(output_dir, f"sentence{i}_knowledge_map")
        if visualize_knowledge_map_graphviz(actual_map, image_path):
            print(f"Saved image file: {image_path}.png")
        
        # Проверяем что карта знаний валидна
        builder.validate_knowledge_map(actual_map)
        
        print(f"✅ PASSED Sentence {i}")
    
    # Объединяем все карты знаний
    print("\n" + "="*60)
    print("COMBINING KNOWLEDGE MAPS")
    print("="*60)
    
    combined_map = builder.combine_knowledge_maps(actual_maps)
    
    # Проверяем объединенную карту
    builder.validate_knowledge_map(combined_map)
    
    # Сохраняем объединенную карту
    combined_output_path = os.path.join(output_dir, "combined_knowledge_map")
    builder.save_knowledge_map(combined_map, f"{combined_output_path}.gml")
    print(f"Saved combined GML file: {combined_output_path}.gml")
    
    # Создаем изображение для объединенной карты
    combined_image_path = os.path.join(output_dir, "combined_knowledge_map")
    if visualize_knowledge_map_graphviz(combined_map, combined_image_path):
        print(f"Saved combined image file: {combined_image_path}.png")
    
    print(f"\n🎉 All knowledge maps processed successfully!")
    print(f"Files saved to: {output_dir}")

if __name__ == "__main__":
    main()