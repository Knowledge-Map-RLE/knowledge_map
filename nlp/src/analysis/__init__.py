"""
Analysis functions for detailed linguistic and statistical analysis.

All functions are pure and produce no side effects.
"""

from .morphology_stats import (
    get_document_pos_distribution,
    get_document_morphology_features,
    get_document_morphology_statistics,
    get_sentence_morphology_stats,
    find_tokens_with_feature,
    get_pos_tag_statistics,
    get_morphology_patterns,
    compare_sentences_morphology,
)

from .syntax_analysis import (
    get_document_syntax_statistics,
    get_document_entity_statistics,
    analyze_sentence_syntax,
    extract_svo_triples,
    extract_clauses,
    find_common_dependency_patterns,
    analyze_phrases,
    is_projective,
    get_projectivity_analysis,
)

from .graph_export import (
    document_to_neo4j_nodes_edges,
    document_to_networkx_graph,
    document_to_conllu,
    document_to_standoff,
    document_statistics_summary,
)

__all__ = [
    # morphology_stats
    "get_document_pos_distribution",
    "get_document_morphology_features",
    "get_document_morphology_statistics",
    "get_sentence_morphology_stats",
    "find_tokens_with_feature",
    "get_pos_tag_statistics",
    "get_morphology_patterns",
    "compare_sentences_morphology",

    # syntax_analysis
    "get_document_syntax_statistics",
    "get_document_entity_statistics",
    "analyze_sentence_syntax",
    "extract_svo_triples",
    "extract_clauses",
    "find_common_dependency_patterns",
    "analyze_phrases",
    "is_projective",
    "get_projectivity_analysis",

    # graph_export
    "document_to_neo4j_nodes_edges",
    "document_to_networkx_graph",
    "document_to_conllu",
    "document_to_standoff",
    "document_statistics_summary",
]
