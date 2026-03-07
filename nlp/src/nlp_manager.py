"""
NLP Manager - Main orchestrator for multi-processor NLP analysis.

This module manages multiple NLP processors (spaCy, NLTK, Stanza, UDPipe)
and implements voting/agreement algorithms for consensus-based analysis.
"""

import logging
import time
from typing import List, Optional, Dict, Any
from collections import defaultdict

from src.base import BaseNLPProcessor, ProcessingResult, AnnotationSuggestion, AnnotationCategory, AnnotationSource
from src.unified_types import (
    UnifiedDocument,
    UnifiedSentence,
    UnifiedToken,
    UnifiedDependency,
    UnifiedEntity,
    LinguisticLevel,
    ProcessorOutput,
    VotingResult
)
from src.config import get_config

logger = logging.getLogger(__name__)


class NLPManager:
    """Main orchestrator for multi-processor NLP analysis."""
    
    def __init__(self):
        """Initialize NLP manager with all available processors."""
        self.config = get_config()
        self.processors: Dict[str, BaseNLPProcessor] = {}
        self._load_processors()
    
    def _load_processors(self):
        """Load all enabled NLP processors."""
        # Load spaCy processor if enabled
        if self.config.enable_spacy:
            try:
                from .adapters.spacy_processor import SpacyProcessor
                spacy_processor = SpacyProcessor()
                self.processors['spacy'] = spacy_processor
                logger.info("Loaded spaCy processor")
            except Exception as e:
                logger.warning(f"Failed to load spaCy processor: {e}")
        
        # Load NLTK adapter if enabled
        if self.config.enable_nltk:
            try:
                from .adapters.nltk_adapter import NLTKAdapter
                nltk_adapter = NLTKAdapter()
                self.processors['nltk'] = nltk_adapter
                logger.info("Loaded NLTK adapter")
            except Exception as e:
                logger.warning(f"Failed to load NLTK adapter: {e}")
        
        # Load Stanza adapter if enabled
        if self.config.enable_stanza:
            try:
                from .adapters.stanza_adapter import StanzaAdapter
                stanza_adapter = StanzaAdapter()
                self.processors['stanza'] = stanza_adapter
                logger.info("Loaded Stanza adapter")
            except Exception as e:
                logger.warning(f"Failed to load Stanza adapter: {e}")
        
        # Load UDPipe adapter if enabled (but only if explicitly enabled)
        if self.config.enable_udpipe:
            try:
                from .adapters.udpipe_adapter import UDPipeAdapter
                udpipe_adapter = UDPipeAdapter()
                self.processors['udpipe'] = udpipe_adapter
                logger.info("Loaded UDPipe adapter")
            except Exception as e:
                logger.warning(f"Failed to load UDPipe adapter: {e}")
        
        logger.info(f"Loaded {len(self.processors)} NLP processors: {list(self.processors.keys())}")
    
    def process_text(
        self, 
        text: str, 
        processor_names: Optional[List[str]] = None
    ) -> List[ProcessingResult]:
        """
        Process text with multiple NLP processors.
        
        Args:
            text: Input text to process
            processor_names: List of processor names to use (None = all available)
            
        Returns:
            List of ProcessingResult objects, one per processor
        """
        if not processor_names:
            processor_names = list(self.processors.keys())
        
        results = []
        for name in processor_names:
            if name not in self.processors:
                logger.warning(f"Processor {name} not available")
                continue
                
            processor = self.processors[name]
            try:
                start_time = time.time()
                result = processor.process_text(text)
                processing_time = time.time() - start_time
                print(f"NLP Manager: Processed text with {name}, got {len(result.annotations)} annotations")
                
                # Add timing info
                result.metadata['processing_time'] = processing_time
                result.metadata['processor'] = name
                
                results.append(result)
                logger.info(f"Processed text with {name} in {processing_time:.2f}s")
            except Exception as e:
                logger.error(f"Error processing text with {name}: {e}")
                print(f"NLP Manager: Error processing text with {name}: {e}")
         
        return results
    
    def process_selection(
        self,
        full_text: str,
        selection: str,
        start_offset: int,
        end_offset: int,
        processor_names: Optional[List[str]] = None
    ) -> List[ProcessingResult]:
        """
        Process text selection with multiple NLP processors.
        
        Args:
            full_text: Full document text
            selection: Selected text fragment
            start_offset: Start position of selection in full text
            end_offset: End position of selection in full text
            processor_names: List of processor names to use (None = all available)
            
        Returns:
            List of ProcessingResult objects, one per processor
        """
        if not processor_names:
            processor_names = list(self.processors.keys())
        
        results = []
        for name in processor_names:
            if name not in self.processors:
                logger.warning(f"Processor {name} not available")
                continue
                
            processor = self.processors[name]
            try:
                start_time = time.time()
                result = processor.process_selection(
                    full_text, 
                    start_offset, 
                    end_offset
                )
                processing_time = time.time() - start_time
                
                # Add timing info
                result.metadata['processing_time'] = processing_time
                result.metadata['processor'] = name
                
                results.append(result)
                logger.info(f"Processed selection with {name} in {processing_time:.2f}s")
            except Exception as e:
                logger.error(f"Error processing selection with {name}: {e}")
        
        return results
    
    def merge_results(self, results: List[ProcessingResult]) -> ProcessingResult:
        """
        Merge multiple processing results using voting/agreement algorithms.
        
        Args:
            results: List of ProcessingResult objects
            
        Returns:
            Merged ProcessingResult with consensus annotations
        """
        if not results:
            return ProcessingResult([], [], "merged", "1.0", 0.0)
        
        if len(results) == 1:
            return results[0]
        
        # Convert to ProcessorOutput format for voting
        processor_outputs = []
        for result in results:
            # Convert AnnotationSuggestion to UnifiedEntity for voting
            unified_entities = []
            for ann in result.annotations:
                # Create a basic UnifiedEntity from AnnotationSuggestion
                entity = UnifiedEntity(
                    entity_type=ann.annotation_type,
                    start_idx=ann.start_offset,
                end_idx=ann.end_offset,
                    tokens=[],  # Will be populated later if needed
                    confidence=ann.confidence,
                    sources=[ann.source]
                )
                unified_entities.append(entity)
            
            output = ProcessorOutput(
                processor_name=result.processor_name,
                processor_version=result.processor_version,
                tokens=[],  # Will be populated later
                entities=unified_entities,
                overall_confidence=result.processing_time
            )
            processor_outputs.append(output)
        
        # Perform voting
        voting_result = self._perform_voting(processor_outputs)
        
        # Convert back to ProcessingResult
        # Convert UnifiedEntity back to AnnotationSuggestion
        annotation_suggestions = []
        for entity in voting_result.agreed_entities:
            # Create AnnotationSuggestion from UnifiedEntity
            ann = AnnotationSuggestion(
                text="",  # Will be populated later if needed
                annotation_type=entity.entity_type,
                category=AnnotationCategory.NAMED_ENTITY,  # Default category
                start_offset=entity.start_idx,
                end_offset=entity.end_idx,
                confidence=entity.confidence,
                source=AnnotationSource.SPACY if entity.sources and entity.sources[0] == "spacy" else AnnotationSource.CUSTOM,
                color="#FF0000"  # Default color
            )
            annotation_suggestions.append(ann)
        
        merged_result = ProcessingResult(
            annotations=annotation_suggestions,
            relations=[],  # TODO: Implement relation voting
            processor_name="merged",
            processor_version="1.0",
            processing_time=0.0,
            metadata={
                "agreement_score": voting_result.agreement_score,
                "num_agreements": voting_result.num_agreements,
                "num_disagreements": voting_result.num_disagreements
            }
        )
        
        return merged_result
    
    def _perform_voting(self, outputs: List[ProcessorOutput]) -> VotingResult:
        """
        Perform voting/agreement between multiple processor outputs.
        
        Args:
            outputs: List of ProcessorOutput objects
            
        Returns:
            VotingResult with agreed and disagreed elements
        """
        # Simple majority voting implementation
        voting_result = VotingResult()
        voting_result.participating_sources = [o.processor_name for o in outputs]
        
        if not outputs:
            return voting_result
        
        # For now, just return the first output as "agreed"
        # TODO: Implement proper voting algorithms
        first_output = outputs[0]
        voting_result.agreed_tokens = first_output.tokens
        voting_result.agreed_entities = first_output.entities
        
        return voting_result
    
    def get_supported_types(self) -> Dict[str, List[str]]:
        """
        Get all annotation types supported by all processors.
        
        Returns:
            Dictionary mapping processor names to lists of supported types
        """
        supported = {}
        for name, processor in self.processors.items():
            try:
                types = processor.get_supported_types()
                # Flatten the category-type structure
                all_types = []
                for category_types in types.values():
                    all_types.extend(category_types)
                supported[name] = all_types
            except Exception as e:
                logger.warning(f"Error getting supported types from {name}: {e}")
                supported[name] = []
        
        return supported


# Global NLP manager instance
_nlp_manager: Optional[NLPManager] = None


def get_nlp_manager() -> NLPManager:
    """Get or create global NLP manager instance."""
    global _nlp_manager
    if _nlp_manager is None:
        _nlp_manager = NLPManager()
    return _nlp_manager