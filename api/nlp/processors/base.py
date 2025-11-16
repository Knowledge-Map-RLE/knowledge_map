"""
Base processor for NLP analysis.
"""

from abc import ABC, abstractmethod
from typing import Optional
from ..unified_types import UnifiedDocument, LinguisticLevel


class BaseNLPProcessor(ABC):
    """
    Abstract base class for NLP processors.
    """

    def __init__(self):
        """Initialize processor."""
        self.name = self.__class__.__name__

    @abstractmethod
    def process(self, text: str, doc_id: Optional[str] = None) -> UnifiedDocument:
        """
        Process text and return unified document.

        Args:
            text: Input text
            doc_id: Optional document ID

        Returns:
            UnifiedDocument with processed annotations
        """
        pass

    @abstractmethod
    def get_level(self) -> LinguisticLevel:
        """
        Get the linguistic level this processor handles.

        Returns:
            LinguisticLevel enum value
        """
        pass

    def get_info(self) -> dict:
        """
        Get information about this processor.

        Returns:
            Dictionary with processor metadata
        """
        return {
            'name': self.name,
            'level': self.get_level().name,
        }
