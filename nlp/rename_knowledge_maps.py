#!/usr/bin/env python3
"""
Script to rename knowledge map files to match the expected structure
"""
import os
import shutil

def main():
    """Основная функция для переименования файлов"""
    # Определяем пути
    knowledge_map_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "knowledge_map")
    
    print(f"Renaming files in: {knowledge_map_dir}")
    
    # Словарь для переименования файлов
    rename_map = {
        "sentence1_knowledge_map.gml": "sentence1_1_expected_graph",
        "sentence2_knowledge_map.gml": "sentence2_1_expected_graph", 
        "sentence3_knowledge_map.gml": "sentence3_1_expected_graph",
        "sentence4_knowledge_map.gml": "sentence4_1_expected_graph",
        "sentence1_knowledge_map.png": "sentence1_1_expected_graph.png",
        "sentence2_knowledge_map.png": "sentence2_1_expected_graph.png", 
        "sentence3_knowledge_map.png": "sentence3_1_expected_graph.png",
        "sentence4_knowledge_map.png": "sentence4_1_expected_graph.png"
    }
    
    # Переименовываем файлы
    for old_name, new_name in rename_map.items():
        old_path = os.path.join(knowledge_map_dir, old_name)
        new_path = os.path.join(knowledge_map_dir, new_name)
        
        if os.path.exists(old_path):
            shutil.copy2(old_path, new_path)
            print(f"Copied: {old_name} -> {new_name}")
        else:
            print(f"Warning: {old_name} not found")
    
    print(f"\n🎉 All files renamed successfully!")
    print(f"Files are now available in: {knowledge_map_dir}")

if __name__ == "__main__":
    main()