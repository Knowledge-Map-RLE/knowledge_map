"""
Stanza NLP processors for multi-level analysis.
"""

from typing import Optional
import logging

from .base import BaseNLPProcessor
from ..unified_types import UnifiedDocument, LinguisticLevel
from ..adapters.stanza_adapter import StanzaAdapter

logger = logging.getLogger(__name__)


class StanzaLevel1Processor(BaseNLPProcessor):
    """Level 1 processor using Stanza (Tokenization)."""

    def __init__(self):
        """Initialize Stanza Level 1 processor."""
        super().__init__()
        self.adapter = StanzaAdapter(lang='en')
        logger.info("Stanza Level 1 processor initialized")

    def process(self, text: str, doc_id: Optional[str] = None) -> UnifiedDocument:
        """Process text at Level 1 (Tokenization)."""
        return self.adapter.process_level1(text, doc_id)

    def get_level(self) -> LinguisticLevel:
        """Get linguistic level."""
        return LinguisticLevel.TOKENIZATION


class StanzaLevel2Processor(BaseNLPProcessor):
    """Level 2 processor using Stanza (Morphology)."""

    def __init__(self):
        """Initialize Stanza Level 2 processor."""
        super().__init__()
        self.adapter = StanzaAdapter(lang='en')
        logger.info("Stanza Level 2 processor initialized")

    def process(self, text: str, doc_id: Optional[str] = None) -> UnifiedDocument:
        """Process text at Level 2 (Morphology)."""
        return self.adapter.process_level2(text, doc_id)

    def get_level(self) -> LinguisticLevel:
        """Get linguistic level."""
        return LinguisticLevel.MORPHOLOGY


class StanzaLevel3Processor(BaseNLPProcessor):
    """Level 3 processor using Stanza (Syntax)."""

    def __init__(self):
        """Initialize Stanza Level 3 processor."""
        super().__init__()
        self.adapter = StanzaAdapter(lang='en')
        logger.info("Stanza Level 3 processor initialized")

    def process(self, text: str, doc_id: Optional[str] = None) -> UnifiedDocument:
        """Process text at Level 3 (Syntax)."""
        return self.adapter.process_level3(text, doc_id)

    def get_level(self) -> LinguisticLevel:
        """Get linguistic level."""
        return LinguisticLevel.SYNTAX
