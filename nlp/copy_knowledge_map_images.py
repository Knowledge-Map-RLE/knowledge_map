#!/usr/bin/env python3
"""
Script to copy knowledge map images to match the expected structure
"""
import os
import shutil

def main():
    """Основная функция для копирования изображений"""
    # Определяем пути
    nlp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "nlp")
    knowledge_map_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "knowledge_map")
    
    print(f"Copying images from: {nlp_dir}")
    print(f"To: {knowledge_map_dir}")
    
    # Словарь для копирования изображений
    copy_map = {
        "sentence1_1_expected_graph.png": "sentence1_1_expected_graph.png",
        "sentence2_1_expected_graph.png": "sentence2_1_expected_graph.png", 
        "sentence3_1_expected_graph.png": "sentence3_1_expected_graph.png",
        "sentence4_1_expected_graph.png": "sentence4_1_expected_graph.png"
    }
    
    # Копируем изображения
    for source_name, target_name in copy_map.items():
        source_path = os.path.join(nlp_dir, source_name)
        target_path = os.path.join(knowledge_map_dir, target_name)
        
        if os.path.exists(source_path):
            shutil.copy2(source_path, target_path)
            print(f"Copied: {source_name} -> {target_name}")
        else:
            print(f"Warning: {source_name} not found")
    
    print(f"\n🎉 All images copied successfully!")
    print(f"Images are now available in: {knowledge_map_dir}")

if __name__ == "__main__":
    main()