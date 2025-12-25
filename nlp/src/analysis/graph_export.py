"""
Graph export functions for Neo4j and other graph databases.

Pure functions for converting unified documents to graph representation.
"""

from typing import List, Dict, Tuple, Any

from ..types import UnifiedDocument, UnifiedToken, UnifiedDependency, UnifiedEntity


# ============================================================================
# Neo4j export functions
# ============================================================================

def document_to_neo4j_nodes_edges(
    doc: UnifiedDocument
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Convert document to Neo4j nodes and edges.

    Pure function - creates graph representation.

    Args:
        doc: UnifiedDocument

    Returns:
        (nodes, edges) - lists of dictionaries for Neo4j import
    """
    nodes = []
    edges = []

    # Add document node
    doc_node = {
        "id": doc.doc_id,
        "type": "Document",
        "text": doc.text[:100],  # Truncate for readability
        "processed_levels": [level.name for level in doc.processed_levels],
    }
    nodes.append(doc_node)

    # Process each sentence
    for sent_idx, sentence in enumerate(doc.sentences):
        sent_id = f"{doc.doc_id}:sent:{sent_idx}"

        # Add sentence node
        sent_node = {
            "id": sent_id,
            "type": "Sentence",
            "text": sentence.text,
            "sentence_index": sent_idx,
        }
        nodes.append(sent_node)

        # Connect document to sentence
        edges.append({
            "source": doc.doc_id,
            "target": sent_id,
            "relation": "CONTAINS_SENTENCE",
        })

        # Add token nodes and edges
        for token in sentence.tokens:
            token_id = f"{doc.doc_id}:tok:{token.idx}"

            token_node = {
                "id": token_id,
                "type": "Token",
                "text": token.text,
                "lemma": token.lemma,
                "pos": token.pos,
                "pos_fine": token.pos_fine,
                "token_index": token.idx,
                "is_stop": token.is_stop,
                "is_punct": token.is_punct,
                "confidence": token.confidence,
            }
            nodes.append(token_node)

            # Connect sentence to token
            edges.append({
                "source": sent_id,
                "target": token_id,
                "relation": "CONTAINS_TOKEN",
            })

            # Add morphology attributes
            for feature, value in token.morph.items():
                morph_id = f"{token_id}:morph:{feature}"
                morph_node = {
                    "id": morph_id,
                    "type": "MorphFeature",
                    "feature": feature,
                    "value": value,
                }
                nodes.append(morph_node)

                edges.append({
                    "source": token_id,
                    "target": morph_id,
                    "relation": "HAS_MORPH",
                })

        # Add dependency edges
        for dep in sentence.dependencies:
            edges.append({
                "source": f"{doc.doc_id}:tok:{dep.head_idx}",
                "target": f"{doc.doc_id}:tok:{dep.dependent_idx}",
                "relation": f"DEP:{dep.relation}",
                "confidence": dep.confidence,
            })

        # Add entity nodes
        for ent_idx, entity in enumerate(sentence.entities):
            ent_id = f"{doc.doc_id}:ent:{sent_idx}:{ent_idx}"

            ent_node = {
                "id": ent_id,
                "type": "Entity",
                "entity_type": entity.entity_type,
                "text": " ".join(t.text for t in entity.tokens),
                "is_scientific": entity.is_scientific,
                "domain": entity.domain,
                "entity_id": entity.entity_id,
                "canonical_name": entity.canonical_name,
                "confidence": entity.confidence,
            }
            nodes.append(ent_node)

            # Connect entity to tokens
            for token in entity.tokens:
                edges.append({
                    "source": ent_id,
                    "target": f"{doc.doc_id}:tok:{token.idx}",
                    "relation": "MENTIONS_TOKEN",
                })

        # Add phrase nodes
        for phrase_idx, phrase in enumerate(sentence.phrases):
            phrase_id = f"{doc.doc_id}:phrase:{sent_idx}:{phrase_idx}"

            phrase_node = {
                "id": phrase_id,
                "type": "Phrase",
                "phrase_type": phrase.phrase_type,
                "text": " ".join(t.text for t in phrase.tokens),
                "head_idx": phrase.head_idx,
                "confidence": phrase.confidence,
            }
            nodes.append(phrase_node)

            # Connect phrase to tokens
            for token in phrase.tokens:
                edges.append({
                    "source": phrase_id,
                    "target": f"{doc.doc_id}:tok:{token.idx}",
                    "relation": "CONTAINS_TOKEN",
                })

    return nodes, edges


# ============================================================================
# NetworkX graph export
# ============================================================================

def document_to_networkx_graph(doc: UnifiedDocument):
    """
    Convert document to NetworkX directed graph.

    Pure function - creates NetworkX representation.

    Args:
        doc: UnifiedDocument

    Returns:
        NetworkX DiGraph with nodes and edges
    """
    import networkx as nx

    graph = nx.DiGraph()

    # Add document node
    graph.add_node(doc.doc_id, type="Document", text=doc.text[:100])

    # Add sentence, token, and dependency nodes
    for sent_idx, sentence in enumerate(doc.sentences):
        sent_id = f"{doc.doc_id}:sent:{sent_idx}"
        graph.add_node(sent_id, type="Sentence", text=sentence.text)
        graph.add_edge(doc.doc_id, sent_id, relation="CONTAINS_SENTENCE")

        # Add tokens
        for token in sentence.tokens:
            token_id = f"{doc.doc_id}:tok:{token.idx}"
            graph.add_node(
                token_id,
                type="Token",
                text=token.text,
                lemma=token.lemma,
                pos=token.pos,
            )
            graph.add_edge(sent_id, token_id, relation="CONTAINS_TOKEN")

        # Add dependency edges
        for dep in sentence.dependencies:
            head_id = f"{doc.doc_id}:tok:{dep.head_idx}"
            dep_id = f"{doc.doc_id}:tok:{dep.dependent_idx}"
            graph.add_edge(head_id, dep_id, relation=f"DEP:{dep.relation}")

        # Add entities
        for ent_idx, entity in enumerate(sentence.entities):
            ent_id = f"{doc.doc_id}:ent:{sent_idx}:{ent_idx}"
            graph.add_node(
                ent_id,
                type="Entity",
                entity_type=entity.entity_type,
                text=" ".join(t.text for t in entity.tokens),
            )
            # Connect entity to tokens
            for token in entity.tokens:
                token_id = f"{doc.doc_id}:tok:{token.idx}"
                graph.add_edge(ent_id, token_id, relation="MENTIONS")

    return graph


# ============================================================================
# Simple text-based formats
# ============================================================================

def document_to_conllu(doc: UnifiedDocument) -> str:
    """
    Export document to CoNLL-U format (for dependency parsing).

    Pure function - creates standard format string.

    Args:
        doc: UnifiedDocument

    Returns:
        CoNLL-U formatted string
    """
    lines = []

    # Add document metadata
    lines.append(f"# doc_id = {doc.doc_id}")
    lines.append(f"# text = {doc.text}")
    lines.append("")

    for sent_idx, sentence in enumerate(doc.sentences):
        lines.append(f"# sent_id = {doc.doc_id}:{sent_idx}")
        lines.append(f"# text = {sentence.text}")

        for token in sentence.tokens:
            # Find head for this token
            head_idx = 0  # Default to root
            deprel = "root"

            for dep in sentence.dependencies:
                if dep.dependent_idx == token.idx:
                    head_idx = dep.head_idx + 1  # CoNLL-U uses 1-based indexing
                    deprel = dep.relation
                    break

            # CoNLL-U format columns
            columns = [
                str(token.idx + 1),           # ID
                token.text,                   # FORM
                token.lemma,                  # LEMMA
                token.pos,                    # UPOS
                token.pos_fine or "_",        # XPOS
                _morph_to_conllu(token.morph),  # FEATS
                str(head_idx),                # HEAD
                deprel,                       # DEPREL
                "_",                          # DEPS
                "_",                          # MISC
            ]

            lines.append("\t".join(columns))

        lines.append("")  # Blank line between sentences

    return "\n".join(lines)


def _morph_to_conllu(morph: Dict[str, str]) -> str:
    """Helper: convert morphology dict to CoNLL-U FEATS format."""
    if not morph:
        return "_"

    features = [f"{k}={v}" for k, v in sorted(morph.items())]
    return "|".join(features)


def document_to_standoff(doc: UnifiedDocument) -> Tuple[str, str]:
    """
    Export document to Standoff/BRAT format.

    Pure function - useful for annotation tools.

    Args:
        doc: UnifiedDocument

    Returns:
        (text_content, annotations) - two strings
    """
    text_content = doc.text
    annotations = []

    entity_id = 0
    relation_id = 0

    # Export entities
    for sent_idx, sentence in enumerate(doc.sentences):
        for entity in sentence.entities:
            entity_id += 1
            start = entity.tokens[0].start_char
            end = entity.tokens[-1].end_char
            entity_text = text_content[start:end]

            annotations.append(
                f"T{entity_id}\t{entity.entity_type} {start} {end}\t{entity_text}"
            )

    return text_content, "\n".join(annotations)


# ============================================================================
# Statistics export functions
# ============================================================================

def document_statistics_summary(doc: UnifiedDocument) -> Dict[str, Any]:
    """
    Create summary statistics for document.

    Pure function.

    Args:
        doc: UnifiedDocument

    Returns:
        Dictionary with various statistics
    """
    all_tokens = sum(len(s.tokens) for s in doc.sentences)
    all_deps = sum(len(s.dependencies) for s in doc.sentences)
    all_entities = sum(len(s.entities) for s in doc.sentences)

    return {
        "doc_id": doc.doc_id,
        "text_length": len(doc.text),
        "sentence_count": len(doc.sentences),
        "token_count": all_tokens,
        "dependency_count": all_deps,
        "entity_count": all_entities,
        "entity_types": list(set(
            e.entity_type for s in doc.sentences for e in s.entities
        )),
        "processed_levels": [level.name for level in doc.processed_levels],
    }
