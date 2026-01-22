#!/usr/bin/env python3
"""
Script to run the knowledge map generation and save files to data/knowledge_map
"""
import sys
import os

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the test function directly
from tests.unit.test_ontology_to_knowledge_map import test_multi_sentence_knowledge_map

if __name__ == "__main__":
    # Убедимся, что директория существует
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "knowledge_map")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")
    
    test_multi_sentence_knowledge_map()
    print("Knowledge map generation completed successfully!")