"""
Base adapter interface for converting NLP tool outputs to unified format.

All adapters must implement this interface to ensure consistent conversion
from tool-specific formats to UnifiedToken, UnifiedDependency, etc.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from ..unified_types import (
    UnifiedToken,
    UnifiedDependency,
    UnifiedEntity,
    UnifiedPhrase,
    UnifiedSemanticRole,
    UnifiedSentence,
    ProcessorOutput,
)


class BaseAdapter(ABC):
    """
    Abstract base class for all NLP adapters.

    Each adapter converts outputs from a specific NLP tool (spaCy, NLTK, UDPipe, etc.)
    into the unified format based on Universal Dependencies.
    """

    def __init__(self, processor_name: str, processor_version: str):
        """
        Initialize adapter.

        Args:
            processor_name: Name of the NLP processor (e.g., 'spacy', 'udpipe')
            processor_version: Version string (e.g., '3.8.7')
        """
        self.processor_name = processor_name
        self.processor_version = processor_version

    # ============================================================================
    # Token-level conversion
    # ============================================================================

    @abstractmethod
    def to_unified_token(
        self,
        native_token: Any,
        sentence_start_char: int = 0,
        confidence: float = 1.0
    ) -> UnifiedToken:
        """
        Convert tool-specific token to UnifiedToken.

        Args:
            native_token: Token object from the NLP tool
            sentence_start_char: Character offset of sentence start in document
            confidence: Confidence score for this token

        Returns:
            UnifiedToken with standardized POS tags and morphological features
        """
        pass

    @abstractmethod
    def get_pos_mapping(self) -> Dict[str, str]:
        """
        Get mapping from tool-specific POS tags to Universal Dependencies tags.

        Returns:
            Dictionary mapping native tags to UD tags
            Example: {'NNP': 'PROPN', 'VBZ': 'VERB', ...}
        """
        pass

    @abstractmethod
    def get_morph_features(self, native_token: Any) -> Dict[str, str]:
        """
        Extract morphological features from native token.

        Returns:
            Dictionary of UD morphological features
            Example: {'Tense': 'Past', 'Number': 'Sing', 'Person': '3'}
        """
        pass

    # ============================================================================
    # Dependency conversion
    # ============================================================================

    @abstractmethod
    def to_unified_dependency(
        self,
        native_dependency: Any,
        confidence: float = 1.0
    ) -> UnifiedDependency:
        """
        Convert tool-specific dependency to UnifiedDependency.

        Args:
            native_dependency: Dependency representation from the NLP tool
            confidence: Confidence score

        Returns:
            UnifiedDependency with UD relation labels
        """
        pass

    @abstractmethod
    def get_dependency_mapping(self) -> Dict[str, str]:
        """
        Get mapping from tool-specific dependency labels to UD labels.

        Returns:
            Dictionary mapping native labels to UD labels
            Example: {'nsubjpass': 'nsubj:pass', 'dobj': 'obj', ...}
        """
        pass

    # ============================================================================
    # Entity conversion
    # ============================================================================

    @abstractmethod
    def to_unified_entity(
        self,
        native_entity: Any,
        tokens: List[UnifiedToken],
        confidence: float = 1.0
    ) -> UnifiedEntity:
        """
        Convert tool-specific entity to UnifiedEntity.

        Args:
            native_entity: Entity object from the NLP tool
            tokens: List of UnifiedTokens that comprise this entity
            confidence: Confidence score

        Returns:
            UnifiedEntity with standardized entity types
        """
        pass

    @abstractmethod
    def get_entity_type_mapping(self) -> Dict[str, str]:
        """
        Get mapping from tool-specific entity types to standard types.

        Returns:
            Dictionary mapping native types to standard types
            Example: {'PER': 'PERSON', 'LOC': 'GPE', ...}
        """
        pass

    # ============================================================================
    # Phrase/constituent conversion (optional)
    # ============================================================================

    def to_unified_phrase(
        self,
        native_phrase: Any,
        tokens: List[UnifiedToken],
        confidence: float = 1.0
    ) -> Optional[UnifiedPhrase]:
        """
        Convert tool-specific phrase/constituent to UnifiedPhrase.

        This is optional - only implement if the tool provides constituency parsing.

        Args:
            native_phrase: Phrase/constituent from the NLP tool
            tokens: Tokens in this phrase
            confidence: Confidence score

        Returns:
            UnifiedPhrase or None if not supported
        """
        return None

    # ============================================================================
    # Semantic role conversion (optional)
    # ============================================================================

    def to_unified_semantic_role(
        self,
        native_role: Any,
        tokens: List[UnifiedToken],
        confidence: float = 1.0
    ) -> Optional[UnifiedSemanticRole]:
        """
        Convert tool-specific semantic role to UnifiedSemanticRole.

        This is optional - only implement if the tool provides SRL.

        Args:
            native_role: Semantic role from the NLP tool
            tokens: All tokens in the sentence
            confidence: Confidence score

        Returns:
            UnifiedSemanticRole or None if not supported
        """
        return None

    # ============================================================================
    # Sentence-level conversion
    # ============================================================================

    @abstractmethod
    def to_unified_sentence(
        self,
        native_sentence: Any,
        sentence_idx: int,
        doc_start_char: int = 0,
        confidence: float = 1.0
    ) -> UnifiedSentence:
        """
        Convert tool-specific sentence to UnifiedSentence.

        This is the main entry point that orchestrates all conversions.

        Args:
            native_sentence: Sentence object from the NLP tool
            sentence_idx: Index of this sentence in the document
            doc_start_char: Character offset of document start
            confidence: Base confidence score

        Returns:
            UnifiedSentence with all linguistic levels populated
        """
        pass

    # ============================================================================
    # Document-level conversion
    # ============================================================================

    def to_processor_output(
        self,
        native_document: Any,
        confidence: float = 1.0
    ) -> ProcessorOutput:
        """
        Convert tool-specific document to ProcessorOutput.

        Args:
            native_document: Document object from the NLP tool
            confidence: Base confidence score

        Returns:
            ProcessorOutput containing all extracted linguistic information
        """
        output = ProcessorOutput(
            processor_name=self.processor_name,
            processor_version=self.processor_version,
            overall_confidence=confidence,
        )

        # Implement in subclass if needed
        return output

    # ============================================================================
    # Utility methods
    # ============================================================================

    def normalize_pos_tag(self, native_tag: str) -> str:
        """
        Normalize a POS tag to Universal Dependencies format.

        Args:
            native_tag: Tool-specific POS tag

        Returns:
            UD POS tag
        """
        mapping = self.get_pos_mapping()
        return mapping.get(native_tag, 'X')  # 'X' for unknown

    def normalize_dependency_relation(self, native_rel: str) -> str:
        """
        Normalize a dependency relation to Universal Dependencies format.

        Args:
            native_rel: Tool-specific dependency label

        Returns:
            UD dependency label
        """
        mapping = self.get_dependency_mapping()
        return mapping.get(native_rel, 'dep')  # 'dep' for unknown

    def normalize_entity_type(self, native_type: str) -> str:
        """
        Normalize an entity type to standard format.

        Args:
            native_type: Tool-specific entity type

        Returns:
            Standard entity type
        """
        mapping = self.get_entity_type_mapping()
        return mapping.get(native_type, native_type.upper())

    def get_confidence_score(self, native_object: Any) -> float:
        """
        Extract confidence score from native object if available.

        Args:
            native_object: Object from the NLP tool

        Returns:
            Confidence score (0.0-1.0), defaults to 1.0
        """
        # Try common attribute names
        for attr in ['confidence', 'score', 'prob', 'probability']:
            if hasattr(native_object, attr):
                score = getattr(native_object, attr)
                if isinstance(score, (int, float)):
                    return float(score)

        return 1.0  # Default confidence

    def create_source_identifier(self) -> str:
        """
        Create a source identifier string.

        Returns:
            String like 'spacy-3.8.7' or 'udpipe-1.3.0'
        """
        return f"{self.processor_name}-{self.processor_version}"
