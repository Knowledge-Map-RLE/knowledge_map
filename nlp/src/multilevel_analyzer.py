"""
Multi-level analyzer using only spaCy processor.

This module implements the main analysis pipeline that uses only spaCy
for linguistic analysis without voting between multiple processors.
"""

import logging
import time
from typing import List, Optional, Dict, Any
from collections import defaultdict
import spacy

from src.nlp_manager import get_nlp_manager
from src.base import AnnotationSuggestion, RelationSuggestion
from src.unified_types import (
    UnifiedDocument,
    UnifiedSentence,
    UnifiedToken,
    UnifiedDependency,
    UnifiedEntity,
    LinguisticLevel
)
from src.config import get_config
from src.adapters.spacy_adapter import SpacyAdapter
from src.adapters.spacy_processor import SpacyProcessor

logger = logging.getLogger(__name__)


class MultiLevelAnalyzer:
    """Multi-level analyzer using only spaCy processor."""
    
    def __init__(self):
        """Initialize multi-level analyzer."""
        self.config = get_config()
        self.nlp_manager = get_nlp_manager()
        self.spacy_processor = SpacyProcessor()
        self.spacy_adapter = SpacyAdapter()
    
    def analyze(
        self,
        text: str,
        levels: Optional[List[LinguisticLevel]] = None,
        enable_voting: bool = False,  # Disable voting by default
        min_agreement: int = 1  # Only need 1 processor (spaCy)
    ) -> UnifiedDocument:
        """
        Perform multi-level linguistic analysis using only spaCy processor.
        
        Args:
            text: Input text to analyze
            levels: Linguistic levels to process (None = all levels)
            enable_voting: Whether to use voting system (disabled by default)
            min_agreement: Minimum number of processors (1 for spaCy only)
            
        Returns:
            UnifiedDocument with analysis results
        """
        start_time = time.time()
        
        if levels is None:
            levels = [
                LinguisticLevel.TOKENIZATION,
                LinguisticLevel.MORPHOLOGY,
                LinguisticLevel.SYNTAX,
                LinguisticLevel.SEMANTIC_ROLES,
                LinguisticLevel.LEXICAL_SEMANTICS,
                LinguisticLevel.DISCOURSE
            ]
        
        # Process text directly with spaCy
        if self.spacy_processor.nlp is None:
            raise Exception("spaCy model not loaded")
        
        doc = self.spacy_processor.nlp(text)
        print(f"spaCy processed text, found {len(doc.ents)} entities and {len(list(doc.sents))} sentences")
        
        # Convert to unified format using adapter
        unified_sentences = []
        for i, sent in enumerate(doc.sents):
            unified_sent = self.spacy_adapter.to_unified_sentence(sent, i, 0, 1.0)
            unified_sentences.append(unified_sent)
        
        # Convert entities
        unified_entities = []
        for ent in doc.ents:
            # Get tokens for this entity
            entity_tokens = []
            for unified_sent in unified_sentences:
                for token in unified_sent.tokens:
                    if ent.start <= token.idx < ent.end:
                        entity_tokens.append(token)
            
            unified_entity = self.spacy_adapter.to_unified_entity(ent, entity_tokens, 1.0)
            unified_entities.append(unified_entity)
        
        # Create document structure
        unified_doc = UnifiedDocument(
            doc_id=f"doc_{int(time.time())}",
            text=text,
            sentences=unified_sentences,
            entities=unified_entities
        )
        unified_doc.processed_levels = levels
        unified_doc.processing_time = time.time() - start_time
        unified_doc.processors_used = ['spacy']
        
        logger.info(f"Analysis completed in {unified_doc.processing_time:.2f}s")
        return unified_doc


# Global analyzer instance
_analyzer: Optional[MultiLevelAnalyzer] = None


def get_analyzer() -> MultiLevelAnalyzer:
    """Get or create global analyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = MultiLevelAnalyzer()
    return _analyzer