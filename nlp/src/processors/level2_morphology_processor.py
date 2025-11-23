"""
Level 2 Processor: Morphology and POS Tagging

Extends Level 1 with detailed morphological analysis.
Combines spaCy, NLTK, and optionally pymorphy2 (for Russian).
"""

from typing import List, Optional, Dict, Any
import spacy
import nltk

from src.adapters.spacy_adapter import SpacyAdapter
from src.adapters.nltk_adapter import NLTKAdapter
from src.voting.voting_engine import VotingEngine
from src.unified_types import (
    UnifiedToken,
    UnifiedSentence,
    UnifiedDocument,
    ProcessorOutput,
    LinguisticLevel,
)
from src.processors.level1_tokenization_processor import Level1TokenizationProcessor


class Level2MorphologyProcessor(Level1TokenizationProcessor):
    """
    Morphology and POS tagging processor with voting.

    Inherits from Level1 and adds morphological analysis.
    """

    def __init__(
        self,
        spacy_model: str = "en_core_sci_lg",
        enable_voting: bool = True,
        min_agreement: int = 1,
    ):
        """Initialize Level 2 processor."""
        super().__init__(
            spacy_model=spacy_model,
            enable_voting=enable_voting,
            min_agreement=min_agreement
        )

    # ============================================================================
    # BaseNLPProcessor interface implementation
    # ============================================================================

    def get_level(self) -> LinguisticLevel:
        """Get the linguistic level this processor handles."""
        return LinguisticLevel.MORPHOLOGY

    # ============================================================================
    # Main processing methods (override)
    # ============================================================================

    def process(self, text: str) -> UnifiedDocument:
        """
        Process text through Level 2 (tokenization + morphology).

        Args:
            text: Input text

        Returns:
            UnifiedDocument with tokens and morphology
        """
        # First run Level 1
        doc = super().process(text)

        # Morphology is already included in tokens from adapters
        # Just update processed levels
        doc.processed_levels.append(LinguisticLevel.MORPHOLOGY)

        return doc

    # ============================================================================
    # Analysis methods
    # ============================================================================

    def get_morphology_statistics(self, doc: UnifiedDocument) -> Dict[str, Any]:
        """
        Get statistics about morphological features.

        Args:
            doc: Unified document

        Returns:
            Dictionary with statistics
        """
        # Count POS tags
        pos_counts = {}
        morph_feature_counts = {}

        for sent in doc.sentences:
            for token in sent.tokens:
                # Count POS
                pos_counts[token.pos] = pos_counts.get(token.pos, 0) + 1

                # Count morphological features
                for feature, value in token.morph.items():
                    key = f"{feature}={value}"
                    morph_feature_counts[key] = morph_feature_counts.get(key, 0) + 1

        # Get top features
        top_pos = sorted(pos_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        top_morph = sorted(morph_feature_counts.items(), key=lambda x: x[1], reverse=True)[:20]

        stats = {
            'pos_distribution': dict(top_pos),
            'top_morphological_features': dict(top_morph),
            'total_pos_types': len(pos_counts),
            'total_morph_feature_types': len(morph_feature_counts),
        }

        # Add Level 1 stats
        stats.update(self.get_tokenization_statistics(doc))

        return stats

    def analyze_pos_patterns(self, doc: UnifiedDocument) -> List[Dict[str, Any]]:
        """
        Analyze POS tag patterns (n-grams).

        Useful for identifying syntactic constructions.

        Args:
            doc: Unified document

        Returns:
            List of common POS patterns
        """
        from collections import Counter

        # Collect bigrams and trigrams
        bigrams = []
        trigrams = []

        for sent in doc.sentences:
            pos_sequence = [token.pos for token in sent.tokens]

            # Bigrams
            for i in range(len(pos_sequence) - 1):
                bigrams.append((pos_sequence[i], pos_sequence[i + 1]))

            # Trigrams
            for i in range(len(pos_sequence) - 2):
                trigrams.append((pos_sequence[i], pos_sequence[i + 1], pos_sequence[i + 2]))

        # Count patterns
        bigram_counts = Counter(bigrams)
        trigram_counts = Counter(trigrams)

        patterns = []

        # Top bigrams
        for pattern, count in bigram_counts.most_common(10):
            patterns.append({
                'type': 'bigram',
                'pattern': ' '.join(pattern),
                'count': count,
            })

        # Top trigrams
        for pattern, count in trigram_counts.most_common(10):
            patterns.append({
                'type': 'trigram',
                'pattern': ' '.join(pattern),
                'count': count,
            })

        return patterns

    def extract_content_words(self, doc: UnifiedDocument) -> List[UnifiedToken]:
        """
        Extract content words (nouns, verbs, adjectives, adverbs).

        Args:
            doc: Unified document

        Returns:
            List of content word tokens
        """
        content_pos = {'NOUN', 'VERB', 'ADJ', 'ADV', 'PROPN'}
        content_words = []

        for sent in doc.sentences:
            for token in sent.tokens:
                if token.pos in content_pos and not token.is_stop:
                    content_words.append(token)

        return content_words

    def extract_function_words(self, doc: UnifiedDocument) -> List[UnifiedToken]:
        """
        Extract function words (determiners, prepositions, conjunctions).

        Args:
            doc: Unified document

        Returns:
            List of function word tokens
        """
        function_pos = {'DET', 'ADP', 'CCONJ', 'SCONJ', 'PART', 'AUX'}
        function_words = []

        for sent in doc.sentences:
            for token in sent.tokens:
                if token.pos in function_pos or token.is_stop:
                    function_words.append(token)

        return function_words

    # ============================================================================
    # Morphological queries
    # ============================================================================

    def find_tokens_by_morph(
        self,
        doc: UnifiedDocument,
        feature: str,
        value: str
    ) -> List[UnifiedToken]:
        """
        Find tokens with specific morphological feature.

        Args:
            doc: Unified document
            feature: Morphological feature name (e.g., 'Tense', 'Number')
            value: Feature value (e.g., 'Past', 'Sing')

        Returns:
            List of matching tokens
        """
        matching_tokens = []

        for sent in doc.sentences:
            for token in sent.tokens:
                if token.morph.get(feature) == value:
                    matching_tokens.append(token)

        return matching_tokens

    def get_verb_forms(self, doc: UnifiedDocument) -> Dict[str, List[str]]:
        """
        Get all verb forms grouped by tense/aspect.

        Args:
            doc: Unified document

        Returns:
            Dictionary mapping form to list of verbs
        """
        verb_forms = {}

        for sent in doc.sentences:
            for token in sent.tokens:
                if token.pos == 'VERB':
                    # Get tense/aspect
                    tense = token.morph.get('Tense', 'Unknown')
                    aspect = token.morph.get('Aspect', '')

                    key = f"{tense}"
                    if aspect:
                        key += f"_{aspect}"

                    if key not in verb_forms:
                        verb_forms[key] = []

                    verb_forms[key].append(token.text)

        return verb_forms

    def get_noun_forms(self, doc: UnifiedDocument) -> Dict[str, List[str]]:
        """
        Get all noun forms grouped by number.

        Args:
            doc: Unified document

        Returns:
            Dictionary mapping number to list of nouns
        """
        noun_forms = {'Singular': [], 'Plural': []}

        for sent in doc.sentences:
            for token in sent.tokens:
                if token.pos in ['NOUN', 'PROPN']:
                    number = token.morph.get('Number', 'Unknown')

                    if number == 'Sing':
                        noun_forms['Singular'].append(token.text)
                    elif number == 'Plur':
                        noun_forms['Plural'].append(token.text)

        return noun_forms

    # ============================================================================
    # BaseNLPProcessor interface implementation
    # ============================================================================

    def process_text(self, text: str, **kwargs) -> Dict[str, Any]:
        """Process text (BaseNLPProcessor interface)."""
        doc = self.process(text)

        # Convert to dict format with morphology
        result = {
            'sentences': [],
            'statistics': self.get_morphology_statistics(doc),
            'pos_patterns': self.analyze_pos_patterns(doc),
            'content_words': [t.text for t in self.extract_content_words(doc)],
            'metadata': doc.metadata,
        }

        for sent in doc.sentences:
            sent_data = {
                'text': sent.text,
                'tokens': [
                    {
                        'text': token.text,
                        'pos': token.pos,
                        'pos_fine': token.pos_fine,
                        'lemma': token.lemma,
                        'morph': token.morph,
                        'start': token.start_char,
                        'end': token.end_char,
                        'confidence': token.confidence,
                        'sources': token.sources,
                    }
                    for token in sent.tokens
                ]
            }
            result['sentences'].append(sent_data)

        return result

    def get_supported_types(self) -> List[str]:
        """Get supported annotation types."""
        return ['TOKEN', 'SENTENCE', 'POS', 'MORPHOLOGY']

    def get_processor_info(self) -> Dict[str, Any]:
        """Get processor information."""
        info = super().get_processor_info()
        info.update({
            'level': 2,
            'name': 'Level2MorphologyProcessor',
            'description': 'Multi-tool morphology and POS tagging with voting',
        })
        return info
