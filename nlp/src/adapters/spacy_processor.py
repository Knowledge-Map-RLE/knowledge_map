"""
spaCy processor implementation of BaseNLPProcessor interface.

This module provides a concrete implementation of the BaseNLPProcessor
interface for spaCy, allowing it to be used by the NLP manager.
"""

import spacy
from typing import List, Dict, Any, Optional
from src.base import BaseNLPProcessor, ProcessingResult, AnnotationSuggestion, RelationSuggestion, AnnotationCategory, AnnotationSource
from src.adapters.spacy_adapter import SpacyAdapter
from src.unified_types import UnifiedDocument, UnifiedSentence, UnifiedToken, UnifiedEntity
from src.config import get_config


class SpacyProcessor(BaseNLPProcessor):
    """spaCy processor implementation of BaseNLPProcessor interface."""
    
    def __init__(self):
        """Initialize spaCy processor."""
        self.config = get_config()
        self.nlp = None
        self.adapter = SpacyAdapter()
        self._load_model()
    
    def _load_model(self):
        """Load spaCy model."""
        try:
            # Try to load the configured model
            model_name = self.config.spacy_model
            self.nlp = spacy.load(model_name)
            print(f"Loaded spaCy model: {model_name}")
        except Exception as e:
            print(f"Failed to load spaCy model {self.config.spacy_model}: {e}")
            # Try to load a default English model
            try:
                self.nlp = spacy.load("en_core_web_sm")
                print("Loaded default spaCy model: en_core_web_sm")
            except Exception as e2:
                print(f"Failed to load default spaCy model: {e2}")
                # Try to load a medium English model
                try:
                    self.nlp = spacy.load("en_core_web_md")
                    print("Loaded medium spaCy model: en_core_web_md")
                except Exception as e3:
                    print(f"Failed to load medium spaCy model: {e3}")
                    # Try to load a basic English pipeline
                    try:
                        # Create a blank English model as fallback
                        self.nlp = spacy.blank("en")
                        # Add basic pipeline components
                        if "sentencizer" not in self.nlp.pipe_names:
                            self.nlp.add_pipe("sentencizer")
                        print("Loaded blank spaCy model with basic components")
                    except Exception as e4:
                        print(f"Failed to load blank spaCy model: {e4}")
                        raise Exception("Could not load any spaCy model")
    
    @property
    def name(self) -> str:
        """Get processor name."""
        return "spacy"
    
    @property
    def version(self) -> str:
        """Get processor version."""
        return "unknown"  # Fallback version
    
    def process_text(
        self,
        text: str,
        annotation_types: Optional[List[str]] = None,
        min_confidence: float = 0.0
    ) -> ProcessingResult:
        """
        Process full text and return annotations and relations.
        
        Args:
            text: Text to process
            annotation_types: Filter to specific types (None = all types)
            min_confidence: Minimum confidence threshold (0.0-1.0)
            
        Returns:
            ProcessingResult with annotations and relations
        """
        import time
        start_time = time.time()
        
        # Process text with spaCy
        if self.nlp is None:
            raise Exception("spaCy model not loaded")
        doc = self.nlp(text)
        print(f"spaCy processed text, found {len(doc.ents)} entities and {len(list(doc.sents))} sentences")
        
        # Convert to processor output using adapter
        processor_output = self.adapter.to_processor_output(doc)
        print(f"Adapter converted to {len(processor_output.entities)} unified entities")
        
        # Convert to annotation suggestions
        annotations = []
        for entity in processor_output.entities:
            # Convert entity to annotation suggestion
            ann = AnnotationSuggestion(
                text=entity.text(),
                annotation_type=entity.entity_type,
                category=AnnotationCategory.NAMED_ENTITY,
                start_offset=entity.tokens[0].start_char if entity.tokens else 0,
                end_offset=entity.tokens[-1].end_char if entity.tokens else 0,
                confidence=entity.confidence,
                source=AnnotationSource.SPACY,
                color="#FF0000"  # Default color
            )
            annotations.append(ann)
        
        print(f"Converted to {len(annotations)} annotation suggestions")
        
        # Create processing result
        result = ProcessingResult(
            annotations=annotations,
            relations=[],  # TODO: Extract relations
            processor_name=self.name,
            processor_version=self.version,
            processing_time=time.time() - start_time
        )
        
        return result
    
    def process_selection(
        self,
        text: str,
        start: int,
        end: int,
        annotation_types: Optional[List[str]] = None
    ) -> ProcessingResult:
        """
        Process selected text fragment and suggest annotation types.
        
        Args:
            text: Full text
            start: Start offset of selection
            end: End offset of selection
            annotation_types: Filter to specific types (None = all types)
            
        Returns:
            ProcessingResult with annotation suggestions for the selection
        """
        # Extract the selection
        selection = text[start:end]
        
        # Process the selection
        return self.process_text(selection, annotation_types)
    
    def get_supported_types(self) -> Dict[AnnotationCategory, List[str]]:
        """
        Get all annotation types supported by this processor.
        
        Returns:
            Dictionary mapping categories to lists of annotation types
        """
        return {
            AnnotationCategory.NAMED_ENTITY: [
                "PERSON", "ORG", "GPE", "MONEY", "PERCENT", 
                "DATE", "TIME", "PRODUCT", "EVENT", "WORK_OF_ART",
                "LAW", "LANGUAGE", "QUANTITY", "ORDINAL", "CARDINAL"
            ],
            AnnotationCategory.PART_OF_SPEECH: [
                "NOUN", "VERB", "ADJ", "ADV", "PRON", "DET", "ADP",
                "NUM", "CONJ", "PRT", "X", "PUNCT"
            ],
            AnnotationCategory.MORPHOLOGY: [
                "Tense", "Number", "Person", "Case", "Degree",
                "Polarity", "Poss", "Reflex", "Foreign"
            ]
        }