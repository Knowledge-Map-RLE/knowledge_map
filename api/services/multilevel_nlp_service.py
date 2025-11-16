"""
Multi-level NLP service for Knowledge Map.

Provides advanced linguistic analysis with voting and confidence scores.
"""

from typing import List, Dict, Any, Optional
import logging
import sys
import os
import warnings

# Suppress spaCy warnings
warnings.filterwarnings("ignore", category=FutureWarning, module="spacy")
warnings.filterwarnings("ignore", category=UserWarning, module="spacy")

# Add the api directory to the path if needed
api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

from nlp.multilevel_analyzer import MultiLevelAnalyzer
from nlp.unified_types import UnifiedDocument
from services.markdown_filter import MarkdownFilter

logger = logging.getLogger(__name__)


class MultiLevelNLPService:
    """
    Service for multi-level NLP analysis.
    """

    def __init__(self):
        """Initialize service with default analyzer."""
        self.analyzer = None  # Lazy initialization
        self.markdown_filter = MarkdownFilter()

    def _get_analyzer(self, enable_voting: bool = True, max_level: int = 3) -> MultiLevelAnalyzer:
        """Get or create analyzer with specified settings."""
        if self.analyzer is None or \
           self.analyzer.enable_voting != enable_voting or \
           self.analyzer.max_level != max_level:
            self.analyzer = MultiLevelAnalyzer(
                spacy_model="en_core_sci_lg",  # Use large scientific model for better accuracy
                enable_voting=enable_voting,
                min_agreement=2,
                max_level=max_level
            )
        return self.analyzer

    def analyze_text(
        self,
        text: str,
        doc_id: Optional[str] = None,
        enable_voting: bool = True,
        max_level: int = 3
    ) -> Dict[str, Any]:
        """
        Analyze text with multi-level NLP.

        Args:
            text: Input text
            doc_id: Optional document ID
            enable_voting: Use voting between processors
            max_level: Maximum analysis level (1-3)

        Returns:
            Dictionary with analysis results
        """
        logger.info(f"Starting multi-level analysis (voting={enable_voting}, level={max_level})")

        # Analyze and get UnifiedDocument
        doc = self.analyze_text_to_document(text, doc_id, enable_voting, max_level)

        # Get analyzer for conversion
        analyzer = self._get_analyzer(enable_voting, max_level)

        # Convert to dict
        result = analyzer.to_dict(doc)

        # Add summary statistics
        summary = analyzer.get_summary(doc)
        result['summary'] = summary.get('statistics', {})

        # Add graph data for visualization
        result['graph'] = self._prepare_graph_data(doc)

        logger.info(f"Analysis complete in {doc.processing_time:.2f}s, agreement={result['summary'].get('agreement_score', 0):.2f}")

        return result

    def analyze_text_to_document(
        self,
        text: str,
        doc_id: Optional[str] = None,
        enable_voting: bool = True,
        max_level: int = 3
    ) -> UnifiedDocument:
        """
        Analyze text and return UnifiedDocument object (with filtering applied).

        Args:
            text: Input text
            doc_id: Optional document ID
            enable_voting: Use voting between processors
            max_level: Maximum analysis level (1-3)

        Returns:
            UnifiedDocument with analyzed data
        """
        # Filter markdown text (skip metadata, tables, references, etc.)
        filtered_result = self.markdown_filter.filter_text(text)
        filtered_text = filtered_result.filtered_text
        offset_map = filtered_result.offset_map

        logger.info(f"Filtered text: {len(text)} -> {len(filtered_text)} characters")

        # Get analyzer
        analyzer = self._get_analyzer(enable_voting, max_level)

        # Analyze filtered text
        doc = analyzer.analyze(filtered_text, doc_id=doc_id)

        # Map offsets back to original text
        doc = self._remap_offsets_to_original(doc, offset_map)

        # Store original text for validation
        doc.metadata['original_text'] = text

        return doc

    def _remap_offsets_to_original(
        self,
        doc: UnifiedDocument,
        offset_map: List[int]
    ) -> UnifiedDocument:
        """
        Remap token offsets from filtered text back to original text.

        Args:
            doc: UnifiedDocument with offsets in filtered text
            offset_map: Mapping from filtered to original offsets

        Returns:
            UnifiedDocument with remapped offsets
        """
        if not offset_map:
            return doc

        for sent in doc.sentences:
            for token in sent.tokens:
                # Remap token start offset
                if token.start_char < len(offset_map):
                    token.start_char = offset_map[token.start_char]
                elif offset_map:
                    # Beyond map, extrapolate
                    token.start_char = offset_map[-1] + (token.start_char - len(offset_map) + 1)

                # Remap token end offset (end_char points to position AFTER last character)
                # So we need to remap (end_char - 1) and then add 1
                end_pos_in_filtered = token.end_char - 1
                if end_pos_in_filtered < len(offset_map):
                    # Get the position of the last character in original text
                    last_char_pos = offset_map[end_pos_in_filtered]
                    token.end_char = last_char_pos + 1
                elif offset_map:
                    # Beyond map, extrapolate
                    token.end_char = offset_map[-1] + (token.end_char - len(offset_map) + 1)

            # Remap sentence offsets
            if sent.start_char < len(offset_map):
                sent.start_char = offset_map[sent.start_char]
            elif offset_map:
                sent.start_char = offset_map[-1] + (sent.start_char - len(offset_map) + 1)

            # Same logic for sentence end
            end_pos_in_filtered = sent.end_char - 1
            if end_pos_in_filtered < len(offset_map):
                last_char_pos = offset_map[end_pos_in_filtered]
                sent.end_char = last_char_pos + 1
            elif offset_map:
                sent.end_char = offset_map[-1] + (sent.end_char - len(offset_map) + 1)

        return doc

    def _prepare_graph_data(self, doc: UnifiedDocument) -> Dict[str, Any]:
        """
        Prepare graph data for Pixi.js visualization.

        Args:
            doc: Unified document

        Returns:
            Graph data with nodes and edges
        """
        nodes = []
        edges = []

        node_id = 0
        token_to_node = {}  # Map token idx to node id

        for sent in doc.sentences:
            # Create nodes for tokens
            for token in sent.tokens:
                # Only include content words for cleaner graph
                if not token.is_stop and not token.is_punct:
                    node = {
                        'id': node_id,
                        'label': token.text,
                        'type': 'token',
                        'pos': token.pos,
                        'lemma': token.lemma,
                        'confidence': token.confidence,
                        'sources': token.sources,
                        'sentence_idx': sent.idx,
                    }
                    nodes.append(node)
                    token_to_node[(sent.idx, token.idx)] = node_id
                    node_id += 1

            # Create edges for dependencies
            for dep in sent.dependencies:
                head_key = (sent.idx, dep.head_idx)
                dep_key = (sent.idx, dep.dependent_idx)

                if head_key in token_to_node and dep_key in token_to_node:
                    edge = {
                        'source': token_to_node[dep_key],
                        'target': token_to_node[head_key],
                        'relation': dep.relation,
                        'confidence': dep.confidence,
                        'sources': dep.sources,
                    }
                    edges.append(edge)

            # Add entity nodes
            for entity in sent.entities:
                if entity.confidence >= 0.7:  # Only high-confidence entities
                    node = {
                        'id': node_id,
                        'label': entity.text(),
                        'type': 'entity',
                        'entity_type': entity.entity_type,
                        'confidence': entity.confidence,
                        'sources': entity.sources,
                        'sentence_idx': sent.idx,
                    }
                    nodes.append(node)

                    # Link entity to its tokens
                    if entity.tokens:
                        first_token_key = (sent.idx, entity.tokens[0].idx)
                        if first_token_key in token_to_node:
                            edge = {
                                'source': node_id,
                                'target': token_to_node[first_token_key],
                                'relation': 'is_entity',
                                'confidence': entity.confidence,
                            }
                            edges.append(edge)

                    node_id += 1

        return {
            'nodes': nodes,
            'edges': edges,
            'metadata': {
                'total_nodes': len(nodes),
                'total_edges': len(edges),
                'sentences': len(doc.sentences),
            }
        }

    def create_annotations_for_database(
        self,
        doc: UnifiedDocument,
        confidence_threshold: float = 0.8
    ) -> List[Dict[str, Any]]:
        """
        Convert UnifiedDocument to annotation format for database.

        Args:
            doc: Unified document
            confidence_threshold: Minimum confidence to include

        Returns:
            List of annotation dictionaries
        """
        annotations = []
        original_text = doc.metadata.get('original_text', '')
        skipped_count = 0

        for sent in doc.sentences:
            # POS annotations
            for token in sent.tokens:
                # Include all tokens (even punct/space) but lower threshold for relations
                # Skip only spaces, keep punctuation for dependency relations
                if token.confidence >= 0.5 and not token.is_space:
                    # Validate that the text at remapped offsets matches the token
                    if original_text and token.start_char < len(original_text) and token.end_char <= len(original_text):
                        actual_text = original_text[token.start_char:token.end_char]
                        if actual_text != token.text:
                            # Skip this annotation - offset points to filtered content
                            skipped_count += 1
                            continue
                    elif original_text:
                        # Out of bounds offset
                        skipped_count += 1
                        continue

                    annotation = {
                        'text': token.text,
                        'annotation_type': token.pos,  # Use UD POS tag directly
                        'start_offset': token.start_char,
                        'end_offset': token.end_char,
                        'color': self._get_color_for_pos(token.pos),
                        'metadata': {
                            'lemma': token.lemma,
                            'pos': token.pos,
                            'pos_fine': token.pos_fine,
                            'morph': token.morph,
                            'sources': token.sources,
                            'sent_idx': sent.idx,
                            'token_idx': token.idx,
                        },
                        'confidence': token.confidence,
                        'source': 'multilevel_nlp',
                        'processor_version': ','.join(token.sources),
                    }
                    annotations.append(annotation)

            # Entity annotations
            for entity in sent.entities:
                if entity.confidence >= 0.7:  # Lower threshold for entities
                    # Calculate offsets
                    start_offset = entity.tokens[0].start_char if entity.tokens else 0
                    end_offset = entity.tokens[-1].end_char if entity.tokens else 0
                    entity_text = entity.text()

                    # Validate that the text at remapped offsets matches the entity
                    if original_text and start_offset < len(original_text) and end_offset <= len(original_text):
                        actual_text = original_text[start_offset:end_offset]
                        if actual_text != entity_text:
                            # Skip this annotation - offset points to filtered content
                            skipped_count += 1
                            continue
                    elif original_text:
                        # Out of bounds offset
                        skipped_count += 1
                        continue

                    annotation = {
                        'text': entity_text,
                        'annotation_type': entity.entity_type,
                        'start_offset': start_offset,
                        'end_offset': end_offset,
                        'color': self._get_color_for_entity(entity.entity_type),
                        'metadata': {
                            'entity_type': entity.entity_type,
                            'is_scientific': entity.is_scientific,
                            'sources': entity.sources,
                        },
                        'confidence': entity.confidence,
                        'source': 'multilevel_nlp',
                        'processor_version': ','.join(entity.sources),
                    }
                    annotations.append(annotation)

        logger.info(f"Created {len(annotations)} annotations (threshold={confidence_threshold}, skipped={skipped_count})")
        return annotations

    def create_relations_for_database(
        self,
        doc: UnifiedDocument,
        annotation_uid_map: Dict[int, str],
        confidence_threshold: float = 0.8
    ) -> List[Dict[str, Any]]:
        """
        Convert dependencies to annotation relations.

        Args:
            doc: Unified document
            annotation_uid_map: Mapping from (sent_idx, token_idx) to annotation UID
            confidence_threshold: Minimum confidence to include

        Returns:
            List of relation dictionaries
        """
        relations = []
        missing_annotations = 0

        for sent in doc.sentences:
            for dep in sent.dependencies:
                # Lower threshold for dependencies - accept more relations
                if dep.confidence >= 0.5:  # Lower than annotation threshold
                    # Get annotation UIDs
                    head_key = (sent.idx, dep.head_idx)
                    dependent_key = (sent.idx, dep.dependent_idx)

                    head_uid = annotation_uid_map.get(head_key)
                    dependent_uid = annotation_uid_map.get(dependent_key)

                    if head_uid and dependent_uid:
                        relation = {
                            'source_uid': dependent_uid,
                            'target_uid': head_uid,
                            'relation_type': dep.relation,
                            'confidence': dep.confidence,
                            'source': 'multilevel_nlp',
                            'metadata': {
                                'confidence': dep.confidence,
                                'sources': dep.sources,
                            }
                        }
                        relations.append(relation)
                    else:
                        missing_annotations += 1

        logger.info(f"Created {len(relations)} relations (threshold=0.5, missing_annotations={missing_annotations})")
        return relations

    def _get_color_for_pos(self, pos: str) -> str:
        """Get color for POS tag."""
        colors = {
            'NOUN': '#4CAF50',      # Green
            'VERB': '#2196F3',      # Blue
            'ADJ': '#FF9800',       # Orange
            'ADV': '#9C27B0',       # Purple
            'PROPN': '#00BCD4',     # Cyan
            'PRON': '#FFEB3B',      # Yellow
            'DET': '#795548',       # Brown
            'ADP': '#607D8B',       # Blue Grey
            'NUM': '#FFC107',       # Amber
            'CONJ': '#E91E63',      # Pink
            'AUX': '#3F51B5',       # Indigo
        }
        return colors.get(pos, '#9E9E9E')  # Grey default

    def _get_color_for_entity(self, entity_type: str) -> str:
        """Get color for entity type."""
        colors = {
            'PERSON': '#E91E63',    # Pink
            'ORG': '#3F51B5',       # Indigo
            'GPE': '#009688',       # Teal
            'LOC': '#4CAF50',       # Green
            'DATE': '#FFC107',      # Amber
            'TIME': '#FF9800',      # Orange
            'MONEY': '#8BC34A',     # Light Green
            'PERCENT': '#CDDC39',   # Lime
            # Scientific entities
            'GENE': '#8BC34A',
            'PROTEIN': '#CDDC39',
            'DISEASE': '#F44336',   # Red
            'CHEMICAL': '#9C27B0',  # Purple
        }
        return colors.get(entity_type, '#795548')  # Brown default
