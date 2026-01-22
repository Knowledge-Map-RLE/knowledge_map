#!/usr/bin/env python3
"""
Test script to validate knowledge map conversion for the 4 sample ontologies.
"""

import os
import sys
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from nlp.src.knowledge_map.builder import KnowledgeMapBuilder
from rdflib import Graph


def test_sample_ontologies():
    """Test the knowledge map conversion for the 4 sample ontologies."""
    # Define the test files
    test_files = [
        'data/nlp/sentence1_1_expected_graph',
        'data/nlp/sentence2_1_expected_graph',
        'data/nlp/sentence3_1_expected_graph',
        'data/nlp/sentence4_1_expected_graph'
    ]
    
    # Create the knowledge map builder
    builder = KnowledgeMapBuilder()
    
    print("Testing knowledge map conversion for 4 test ontologies:")
    print("=" * 50)
    
    success_count = 0
    
    # Test each file
    for i, file_path in enumerate(test_files, 1):
        print(f"\nTest {i}: {os.path.basename(file_path)}")
        
        try:
            # Load the ontology
            g = Graph()
            g.parse(file_path, format='ttl')
            
            # Convert to knowledge map
            km = builder.ontology_to_knowledge_map(g)
            
            print(f"  Status: SUCCESS")
            print(f"  Nodes: {len(km.nodes())}")
            print(f"  Edges: {len(km.edges())}")
            
            # Validate DAG property
            is_dag = nx.is_directed_acyclic_graph(km)
            print(f"  Is DAG: {is_dag}")
            
            # Check if all validations pass
            if is_dag:
                success_count += 1
                print(f"  Overall: PASSED")
            else:
                print(f"  Overall: FAILED")
                
        except Exception as e:
            print(f"  Status: FAILED - {str(e)}")
    
    print("\n" + "=" * 50)
    print(f"Overall Results: {success_count}/4 tests passed")
    
    if success_count == 4:
        print("All tests passed!")
        return True
    else:
        print("Some tests failed.")
        return False


if __name__ == "__main__":
    # Import networkx here to avoid import issues
    import networkx as nx
    success = test_sample_ontologies()
    sys.exit(0 if success else 1)