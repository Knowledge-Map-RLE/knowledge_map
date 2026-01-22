#!/usr/bin/env python3
"""
Script to run the knowledge map test
"""
import sys
import os

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Fix the imports in the test file
import importlib.util
spec = importlib.util.spec_from_file_location("test_ontology_to_knowledge_map", "tests/unit/test_ontology_to_knowledge_map.py")
if spec is not None:
    test_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(test_module)

    if __name__ == "__main__":
        test_module.test_multi_sentence_knowledge_map()
        print("Test completed successfully!")