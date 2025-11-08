"""
Base classes and interfaces for NLP processors.

This module defines the abstract interfaces that all NLP processors must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum


class AnnotationSource(str, Enum):
    """Source of annotation."""
    USER = "user"
    SPACY = "spacy"
    CUSTOM = "custom"


class AnnotationCategory(str, Enum):
    """Categories of annotations."""
    PART_OF_SPEECH = "part_of_speech"
    SYNTAX = "syntax"
    NAMED_ENTITY = "named_entity"
    MORPHOLOGY = "morphology"
    SENTENCE_MEMBER = "sentence_member"
    SCIENTIFIC_ENTITY = "scientific_entity"
    GENERAL_ENTITY = "general_entity"


@dataclass
class AnnotationSuggestion:
    """
    Suggestion for annotation from NLP processor.

    Attributes:
        text: The text to annotate
        annotation_type: Type of annotation (e.g., "Существительное", "Подлежащее")
        category: Category of annotation
        start_offset: Start position in text
        end_offset: End position in text
        confidence: Confidence score (0.0-1.0)
        source: Which processor created this suggestion
        color: Default color for this annotation type (hex)
        metadata: Additional metadata (morphology, dependencies, etc.)
    """
    text: str
    annotation_type: str
    category: AnnotationCategory
    start_offset: int
    end_offset: int
    confidence: float
    source: AnnotationSource
    color: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "text": self.text,
            "annotation_type": self.annotation_type,
            "category": self.category.value,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "confidence": self.confidence,
            "source": self.source.value,
            "color": self.color,
            "metadata": self.metadata
        }


@dataclass
class RelationSuggestion:
    """
    Suggestion for relation between annotations.

    Attributes:
        source_text: Text of source annotation
        target_text: Text of target annotation
        source_start: Start offset of source
        source_end: End offset of source
        target_start: Start offset of target
        target_end: End offset of target
        relation_type: Type of relation (e.g., "зависит от", "модифицирует")
        confidence: Confidence score (0.0-1.0)
        source: Which processor created this suggestion
        metadata: Additional metadata
    """
    source_text: str
    target_text: str
    source_start: int
    source_end: int
    target_start: int
    target_end: int
    relation_type: str
    confidence: float
    source: AnnotationSource
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "source_text": self.source_text,
            "target_text": self.target_text,
            "source_start": self.source_start,
            "source_end": self.source_end,
            "target_start": self.target_start,
            "target_end": self.target_end,
            "relation_type": self.relation_type,
            "confidence": self.confidence,
            "source": self.source.value,
            "metadata": self.metadata
        }


@dataclass
class ProcessingResult:
    """
    Result of text processing by NLP processor.

    Attributes:
        annotations: List of annotation suggestions
        relations: List of relation suggestions
        processor_name: Name of processor that produced this result
        processor_version: Version of processor
        processing_time: Time taken to process (seconds)
        metadata: Additional processing metadata
    """
    annotations: List[AnnotationSuggestion]
    relations: List[RelationSuggestion]
    processor_name: str
    processor_version: str
    processing_time: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "annotations": [ann.to_dict() for ann in self.annotations],
            "relations": [rel.to_dict() for rel in self.relations],
            "processor_name": self.processor_name,
            "processor_version": self.processor_version,
            "processing_time": self.processing_time,
            "metadata": self.metadata
        }


class BaseNLPProcessor(ABC):
    """
    Abstract base class for all NLP processors.

    All NLP processors (spaCy, custom models, etc.) must implement this interface.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Get processor name (e.g., 'spacy', 'custom')."""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Get processor version."""
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def get_supported_types(self) -> Dict[AnnotationCategory, List[str]]:
        """
        Get all annotation types supported by this processor.

        Returns:
            Dictionary mapping categories to lists of annotation types
        """
        pass

    def is_type_supported(self, annotation_type: str) -> bool:
        """
        Check if annotation type is supported by this processor.

        Args:
            annotation_type: Type to check

        Returns:
            True if supported, False otherwise
        """
        supported = self.get_supported_types()
        for types_list in supported.values():
            if annotation_type in types_list:
                return True
        return False
