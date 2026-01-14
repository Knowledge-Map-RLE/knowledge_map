import pytest
import spacy
from src.ontology.builder import OntologyBuilder
from src.ontology.reference.ontologies import (
    get_first_sentence_ontology,
    get_second_sentence_ontology,
    get_third_sentence_ontology,
    get_fourth_sentence_ontology
)
from src.ontology.comparison.graph_comparison import compare_graphs, print_comparison_stats
from src.ontology.visualization.graph_viz import (
    visualize_graph_with_comparison,
    visualize_diff_graph
)


def test_multi_sentence_ontology():
    """Тестирует рефакторенный билдер"""
    
    nlp = spacy.load("en_core_web_sm")
    
    builder = OntologyBuilder(
        config_path="src/ontology/config/domain_config.json"
    )
    builder.debug = True  # Для отладки
    
    sentences = [
        "Since the discovery of dopamine as a neurotransmitter in the 1950s, Parkinson's disease (PD) research has generated a rich and complex body of knowledge, revealing PD to be an age-related multifactorial disease, influenced by both genetic and environmental factors.",
        "The tremendous complexity of the disease is increased by a nonlinear progression of the pathogenesis between molecular, cellular and organic systems.",
        "In this minireview, we explore the complexity of PD and propose a systems-based approach, organizing the available information around cellular disease hallmarks.",
        "We encourage our peers to adopt this cell-based view with the aim of improving communication in interdisciplinary research endeavors targeting the molecular events, modulatory cell-to-cell signaling pathways and emerging clinical phenotypes related to PD."
    ]
    
    expected_ontologies = [
        get_first_sentence_ontology(),
        get_second_sentence_ontology(),
        get_third_sentence_ontology(),
        get_fourth_sentence_ontology()
    ]
    
    actual_graphs = []
    comparisons = []
    f1_scores = []
    
    print("Processing sentences with REFACTORED builder...\n")
    
    for i, (text, expected_graph) in enumerate(zip(sentences, expected_ontologies), 1):
        print(f"Sentence {i}: {text[:70]}...")
        
        actual_graph = builder.text_to_ontology(text, nlp)
        actual_graphs.append(actual_graph)
        
        comparison = compare_graphs(expected_graph, actual_graph)
        comparisons.append(comparison)
        f1_scores.append(comparison['metrics']['f1_score'])
        
        print_comparison_stats(i, comparison)
        
        # Визуализации
        print(f"Creating visualizations for sentence {i}...")
        visualize_graph_with_comparison(
            expected_graph, comparison, 'expected', 
            f"../data/nlp/sentence{i}_1_expected_graph"
        )
        visualize_graph_with_comparison(
            actual_graph, comparison, 'actual', 
            f"../data/nlp/sentence{i}_2_actual_graph"
        )
        visualize_diff_graph(
            expected_graph, actual_graph, comparison, 
            f"../data/nlp/sentence{i}_3_diff_graph"
        )
        
        # Assert для каждого предложения
        f1 = comparison['metrics']['f1_score']
        if f1 < 0.70:
            print(f"\n❌ FAILED Sentence {i}: F1-Score is {f1:.2%}, expected >= 70%")
            assert False, f"Sentence {i} failed: F1-Score {f1:.2%} < 70%"
        else:
            print(f"\n✅ PASSED Sentence {i}: F1-Score is {f1:.2%}")
    
    # Межпредложенческие связи
    print("\n" + "="*60)
    print("ADDING CROSS-SENTENCE LINKS")
    print("="*60)
    
    combined_graph = builder.add_cross_sentence_links(actual_graphs)
    
    # Общая метрика
    overall_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else 0
    
    print("\n" + "="*60)
    print("OVERALL STATISTICS (REFACTORED)")
    print("="*60)
    print(f"\nIndividual F1-Scores:")
    for i, score in enumerate(f1_scores, 1):
        print(f"  Sentence {i}: {score:.2%}")
    print(f"\nOverall F1-Score (average): {overall_f1:.2%}")
    print(f"Total triples in combined graph: {len(combined_graph)}")
    print("="*60 + "\n")
    
    # Общий assert
    if overall_f1 < 0.70:
        print(f"\n❌ OVERALL FAILED: Average F1-Score is {overall_f1:.2%}, expected >= 70%")
        assert False, f"Overall test failed: F1-Score {overall_f1:.2%} < 70%"
    else:
        print(f"\n✅ OVERALL PASSED: Average F1-Score is {overall_f1:.2%}")
    
    print("\n🎉 All tests passed successfully with REFACTORED builder!")


if __name__ == '__main__':
    test_multi_sentence_ontology()