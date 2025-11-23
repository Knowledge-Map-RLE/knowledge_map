"""
Multi-Level Analyzer - Main entry point for the hybrid NLP system.

Combines all 6 levels of linguistic analysis with voting and unified output.
"""

from typing import List, Dict, Any, Optional
import time

from src.unified_types import UnifiedDocument, LinguisticLevel
from src.processors.level1_tokenization_processor import Level1TokenizationProcessor
from src.processors.level2_morphology_processor import Level2MorphologyProcessor
from src.processors.level3_syntax_processor import Level3SyntaxProcessor


class MultiLevelAnalyzer:
    """
    Main analyzer that orchestrates multi-level NLP processing.

    Levels:
    1. Tokenization & Segmentation
    2. Morphology & POS Tagging
    3. Syntax & Dependencies
    4. Semantic Roles (TODO)
    5. Lexical Semantics (TODO)
    6. Discourse & Relations (TODO)
    """

    def __init__(
        self,
        spacy_model: str = "en_core_web_trf",
        enable_voting: bool = True,
        min_agreement: int = 2,
        max_level: int = 3,  # Currently implemented up to Level 3
    ):
        """
        Initialize multi-level analyzer.

        Args:
            spacy_model: spaCy model name
            enable_voting: Whether to use voting between processors
            min_agreement: Minimum processors that must agree
            max_level: Maximum level to process (1-6, currently up to 3)
        """
        self.spacy_model = spacy_model
        self.enable_voting = enable_voting
        self.min_agreement = min_agreement
        self.max_level = min(max_level, 3)  # Cap at implemented level

        # Initialize processors
        self.processors = {}
        self._initialize_processors()

    def _initialize_processors(self):
        """Initialize processors for each level."""
        if self.max_level >= 1:
            self.processors[1] = Level1TokenizationProcessor(
                spacy_model=self.spacy_model,
                enable_voting=self.enable_voting,
                min_agreement=self.min_agreement
            )

        if self.max_level >= 2:
            self.processors[2] = Level2MorphologyProcessor(
                spacy_model=self.spacy_model,
                enable_voting=self.enable_voting,
                min_agreement=self.min_agreement
            )

        if self.max_level >= 3:
            self.processors[3] = Level3SyntaxProcessor(
                spacy_model=self.spacy_model,
                enable_voting=self.enable_voting,
                min_agreement=self.min_agreement
            )

        # TODO: Add levels 4-6
        # if self.max_level >= 4:
        #     self.processors[4] = Level4SemanticRoleProcessor(...)
        # if self.max_level >= 5:
        #     self.processors[5] = Level5LexicalSemanticProcessor(...)
        # if self.max_level >= 6:
        #     self.processors[6] = Level6DiscourseProcessor(...)

    # ============================================================================
    # Main analysis methods
    # ============================================================================

    def analyze(
        self,
        text: str,
        doc_id: Optional[str] = None,
        levels: Optional[List[int]] = None
    ) -> UnifiedDocument:
        """
        Analyze text through all levels.

        Args:
            text: Input text
            doc_id: Optional document ID
            levels: Specific levels to process (None = all up to max_level)

        Returns:
            UnifiedDocument with all linguistic analysis
        """
        start_time = time.time()

        # Determine which levels to process
        if levels is None:
            levels = list(range(1, self.max_level + 1))
        else:
            levels = [l for l in levels if l <= self.max_level]

        # Process through highest requested level
        # (Each level processor includes all lower levels)
        highest_level = max(levels) if levels else self.max_level
        processor = self.processors.get(highest_level)

        if processor is None:
            raise ValueError(f"Level {highest_level} not implemented")

        # Run processing
        doc = processor.process(text)

        # Set document ID
        if doc_id:
            doc.doc_id = doc_id

        # Set processing time
        doc.processing_time = time.time() - start_time

        return doc

    def analyze_batch(
        self,
        texts: List[str],
        doc_ids: Optional[List[str]] = None
    ) -> List[UnifiedDocument]:
        """
        Analyze multiple texts.

        Args:
            texts: List of input texts
            doc_ids: Optional list of document IDs

        Returns:
            List of UnifiedDocuments
        """
        if doc_ids is None:
            doc_ids = [f"doc_{i}" for i in range(len(texts))]

        results = []

        for text, doc_id in zip(texts, doc_ids):
            doc = self.analyze(text, doc_id=doc_id)
            results.append(doc)

        return results

    # ============================================================================
    # Export methods
    # ============================================================================

    def to_dict(self, doc: UnifiedDocument) -> Dict[str, Any]:
        """
        Convert UnifiedDocument to dictionary.

        Args:
            doc: Unified document

        Returns:
            Dictionary representation
        """
        return {
            'doc_id': doc.doc_id,
            'text': doc.text,
            'processing_time': doc.processing_time,
            'processed_levels': [level.value for level in doc.processed_levels],
            'metadata': doc.metadata,
            'sentences': [
                {
                    'idx': sent.idx,
                    'text': sent.text,
                    'start_char': sent.start_char,
                    'end_char': sent.end_char,
                    'tokens': [
                        {
                            'idx': token.idx,
                            'text': token.text,
                            'lemma': token.lemma,
                            'pos': token.pos,
                            'pos_fine': token.pos_fine,
                            'morph': token.morph,
                            'confidence': token.confidence,
                            'sources': token.sources,
                            'is_stop': token.is_stop,
                            'is_punct': token.is_punct,
                        }
                        for token in sent.tokens
                    ],
                    'dependencies': [
                        {
                            'head_idx': dep.head_idx,
                            'dependent_idx': dep.dependent_idx,
                            'relation': dep.relation,
                            'confidence': dep.confidence,
                            'sources': dep.sources,
                        }
                        for dep in sent.dependencies
                    ],
                    'entities': [
                        {
                            'entity_type': ent.entity_type,
                            'start_idx': ent.start_idx,
                            'end_idx': ent.end_idx,
                            'text': ent.text(),
                            'confidence': ent.confidence,
                            'sources': ent.sources,
                        }
                        for ent in sent.entities
                    ],
                    'phrases': [
                        {
                            'phrase_type': phrase.phrase_type,
                            'start_idx': phrase.start_idx,
                            'end_idx': phrase.end_idx,
                            'text': phrase.text(),
                            'head_idx': phrase.head_idx,
                        }
                        for phrase in sent.phrases
                    ],
                }
                for sent in doc.sentences
            ],
            'entities': [
                {
                    'entity_type': ent.entity_type,
                    'start_idx': ent.start_idx,
                    'end_idx': ent.end_idx,
                    'text': ent.text(),
                    'confidence': ent.confidence,
                    'sources': ent.sources,
                    'is_scientific': ent.is_scientific,
                }
                for ent in doc.entities
            ],
        }

    def to_neo4j_graph(self, doc: UnifiedDocument) -> Dict[str, Any]:
        """
        Convert UnifiedDocument to Neo4j-compatible graph structure.

        Returns nodes and relationships for importing to Neo4j.

        Args:
            doc: Unified document

        Returns:
            Dictionary with 'nodes' and 'relationships'
        """
        nodes = []
        relationships = []

        # Document node
        doc_node = {
            'id': f"doc:{doc.doc_id}",
            'labels': ['Document'],
            'properties': {
                'doc_id': doc.doc_id,
                'text': doc.text,
                'processing_time': doc.processing_time,
            }
        }
        nodes.append(doc_node)

        # Sentence nodes
        for sent in doc.sentences:
            sent_node = {
                'id': f"sent:{doc.doc_id}:{sent.idx}",
                'labels': ['Sentence'],
                'properties': {
                    'text': sent.text,
                    'idx': sent.idx,
                    'start_char': sent.start_char,
                    'end_char': sent.end_char,
                }
            }
            nodes.append(sent_node)

            # Relationship: Document -> Sentence
            relationships.append({
                'type': 'HAS_SENTENCE',
                'start': doc_node['id'],
                'end': sent_node['id'],
                'properties': {'order': sent.idx}
            })

            # Token nodes
            for token in sent.tokens:
                token_node = {
                    'id': f"token:{doc.doc_id}:{sent.idx}:{token.idx}",
                    'labels': ['Token'],
                    'properties': {
                        'text': token.text,
                        'lemma': token.lemma,
                        'pos': token.pos,
                        'confidence': token.confidence,
                        'sources': ','.join(token.sources),
                    }
                }
                nodes.append(token_node)

                # Relationship: Sentence -> Token
                relationships.append({
                    'type': 'HAS_TOKEN',
                    'start': sent_node['id'],
                    'end': token_node['id'],
                    'properties': {'order': token.idx}
                })

            # Dependency relationships
            for dep in sent.dependencies:
                relationships.append({
                    'type': 'DEPENDS_ON',
                    'start': f"token:{doc.doc_id}:{sent.idx}:{dep.dependent_idx}",
                    'end': f"token:{doc.doc_id}:{sent.idx}:{dep.head_idx}",
                    'properties': {
                        'relation': dep.relation,
                        'confidence': dep.confidence,
                    }
                })

        return {
            'nodes': nodes,
            'relationships': relationships
        }

    # ============================================================================
    # Statistics and reporting
    # ============================================================================

    def get_summary(self, doc: UnifiedDocument) -> Dict[str, Any]:
        """
        Get summary statistics for document.

        Args:
            doc: Unified document

        Returns:
            Summary dictionary
        """
        # Get processor for highest level
        highest_level = max((level.value for level in doc.processed_levels), default=1)
        processor = self.processors.get(highest_level)

        if processor:
            return processor.process_text(doc.text)
        else:
            return {}

    def get_info(self) -> Dict[str, Any]:
        """
        Get analyzer information.

        Returns:
            Info dictionary
        """
        return {
            'spacy_model': self.spacy_model,
            'enable_voting': self.enable_voting,
            'min_agreement': self.min_agreement,
            'max_level': self.max_level,
            'implemented_levels': list(self.processors.keys()),
            'processors': {
                level: processor.get_processor_info()
                for level, processor in self.processors.items()
            }
        }
