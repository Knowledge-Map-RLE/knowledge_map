"""
spaCy adapter for converting spaCy outputs to unified format.

Converts spaCy Doc, Span, and Token objects to UnifiedSentence, UnifiedToken, etc.
"""

from typing import List, Dict, Any, Optional
import spacy
from spacy.tokens import Doc, Span, Token

from src.adapters.base_adapter import BaseAdapter
from src.adapters.universal_dependencies_mapper import UniversalDependenciesMapper
from src.unified_types import (
    UnifiedToken,
    UnifiedDependency,
    UnifiedEntity,
    UnifiedSentence,
    UnifiedSemanticRole,
    ProcessorOutput,
)


class SpacyAdapter(BaseAdapter):
    """
    Adapter for spaCy NLP processor.

    spaCy already uses Universal Dependencies, so most conversions are straightforward.
    """

    def __init__(self, processor_version: str = None):
        """
        Initialize spaCy adapter.

        Args:
            processor_version: spaCy version (auto-detected if None)
        """
        if processor_version is None:
            processor_version = spacy.__version__

        super().__init__(processor_name='spacy', processor_version=processor_version)
        self.mapper = UniversalDependenciesMapper()

    # ============================================================================
    # Token conversion
    # ============================================================================

    def to_unified_token(
        self,
        native_token: Token,
        sentence_start_char: int = 0,
        confidence: float = 1.0
    ) -> UnifiedToken:
        """Convert spaCy Token to UnifiedToken."""

        # spaCy already provides UD POS tags
        pos = native_token.pos_

        # Get morphological features
        morph = self.get_morph_features(native_token)

        # Create unified token
        unified_token = UnifiedToken(
            idx=native_token.i,
            text=native_token.text,
            start_char=sentence_start_char + native_token.idx,
            end_char=sentence_start_char + native_token.idx + len(native_token.text),
            lemma=native_token.lemma_,
            pos=pos,
            pos_fine=native_token.tag_,
            morph=morph,
            confidence=confidence,
            sources=[self.create_source_identifier()],
            is_stop=native_token.is_stop,
            is_punct=native_token.is_punct,
            is_space=native_token.is_space,
        )

        return unified_token

    def get_pos_mapping(self) -> Dict[str, str]:
        """spaCy already uses UD POS tags, so no mapping needed."""
        # Return identity mapping
        return {tag: tag for tag in self.mapper.PTB_TO_UD_POS.values()}

    def get_morph_features(self, native_token: Token) -> Dict[str, str]:
        """Extract morphological features from spaCy token."""
        morph = {}

        # spaCy provides morphological features directly
        if native_token.morph:
            for feature in native_token.morph:
                # feature is like "Tense=Past"
                if '=' in feature:
                    key, value = feature.split('=', 1)
                    morph[key] = value

        # Fallback: extract from tag if morph is empty
        if not morph and native_token.tag_:
            morph = self.mapper.spacy_tag_to_morph(
                native_token.tag_,
                native_token.pos_
            )

        return morph

    # ============================================================================
    # Dependency conversion
    # ============================================================================

    def to_unified_dependency(
        self,
        native_token: Token,  # spaCy represents deps via tokens
        confidence: float = 1.0
    ) -> UnifiedDependency:
        """Convert spaCy dependency to UnifiedDependency."""

        # spaCy already uses UD relations
        relation = native_token.dep_

        unified_dep = UnifiedDependency(
            head_idx=native_token.head.i,
            dependent_idx=native_token.i,
            relation=relation,
            confidence=confidence,
            sources=[self.create_source_identifier()],
        )

        return unified_dep

    def get_dependency_mapping(self) -> Dict[str, str]:
        """spaCy already uses UD relations, so no mapping needed."""
        return {rel: rel for rel in self.mapper.STANFORD_TO_UD_DEP.values()}

    # ============================================================================
    # Entity conversion
    # ============================================================================

    def to_unified_entity(
        self,
        native_entity: Span,
        tokens: List[UnifiedToken],
        confidence: float = 1.0
    ) -> UnifiedEntity:
        """Convert spaCy Span (entity) to UnifiedEntity."""

        # Filter tokens that belong to this entity
        entity_tokens = [
            t for t in tokens
            if native_entity.start <= t.idx < native_entity.end
        ]

        # Determine if it's a scientific entity
        entity_type = native_entity.label_
        is_scientific = entity_type in self.mapper.BIOMEDICAL_ENTITY_TYPES

        unified_entity = UnifiedEntity(
            entity_type=entity_type,
            start_idx=native_entity.start,
            end_idx=native_entity.end,
            tokens=entity_tokens,
            confidence=confidence,
            sources=[self.create_source_identifier()],
            is_scientific=is_scientific,
        )

        return unified_entity

    def get_entity_type_mapping(self) -> Dict[str, str]:
        """spaCy entity types are already standard (OntoNotes)."""
        # Apply OntoNotes normalization
        return self.mapper.ONTONOTES_TO_STANDARD.copy()

    # ============================================================================
    # Sentence conversion
    # ============================================================================

    def to_unified_sentence(
        self,
        native_sentence: Span,  # spaCy Span representing a sentence
        sentence_idx: int,
        doc_start_char: int = 0,
        confidence: float = 1.0
    ) -> UnifiedSentence:
        """Convert spaCy sentence (Span) to UnifiedSentence."""

        sentence_start_char = doc_start_char + native_sentence.start_char

        # Convert tokens
        tokens = []
        for token in native_sentence:
            unified_token = self.to_unified_token(
                token,
                sentence_start_char=sentence_start_char,
                confidence=confidence
            )
            tokens.append(unified_token)

        # Convert dependencies
        dependencies = []
        root_idx = None
        for token in native_sentence:
            if token.dep_ != 'ROOT':
                # Only add if head is within sentence
                if token.head in native_sentence:
                    unified_dep = self.to_unified_dependency(token, confidence)
                    dependencies.append(unified_dep)
            else:
                root_idx = token.i

        # Convert entities
        entities = []
        for ent in native_sentence.ents:
            unified_entity = self.to_unified_entity(ent, tokens, confidence)
            entities.append(unified_entity)

        # Create unified sentence
        unified_sentence = UnifiedSentence(
            idx=sentence_idx,
            text=native_sentence.text,
            start_char=sentence_start_char,
            end_char=sentence_start_char + len(native_sentence.text),
            tokens=tokens,
            dependencies=dependencies,
            entities=entities,
            root_idx=root_idx,
            confidence=confidence,
        )

        return unified_sentence

    # ============================================================================
    # Document conversion
    # ============================================================================

    def to_processor_output(
        self,
        native_document: Doc,
        confidence: float = 1.0
    ) -> ProcessorOutput:
        """Convert spaCy Doc to ProcessorOutput."""

        output = ProcessorOutput(
            processor_name=self.processor_name,
            processor_version=self.processor_version,
            overall_confidence=confidence,
        )

        # Extract all tokens
        for token in native_document:
            unified_token = self.to_unified_token(
                token,
                sentence_start_char=0,
                confidence=confidence
            )
            output.tokens.append(unified_token)

        # Extract all dependencies
        for token in native_document:
            if token.dep_ != 'ROOT':
                unified_dep = self.to_unified_dependency(token, confidence)
                output.dependencies.append(unified_dep)

        # Extract all entities
        for ent in native_document.ents:
            unified_entity = self.to_unified_entity(
                ent,
                output.tokens,
                confidence
            )
            output.entities.append(unified_entity)

        return output

    # ============================================================================
    # Advanced features (spaCy-specific)
    # ============================================================================

    def extract_noun_chunks(
        self,
        native_sentence: Span,
        tokens: List[UnifiedToken]
    ) -> List:
        """
        Extract noun chunks (phrases) from spaCy sentence.

        Returns list of UnifiedPhrase objects.
        """
        from src.unified_types import UnifiedPhrase

        phrases = []

        for chunk in native_sentence.noun_chunks:
            # Find tokens in this chunk
            chunk_tokens = [
                t for t in tokens
                if chunk.start <= t.idx < chunk.end
            ]

            if chunk_tokens:
                phrase = UnifiedPhrase(
                    phrase_type='NP',  # Noun phrase
                    start_idx=chunk.start,
                    end_idx=chunk.end,
                    tokens=chunk_tokens,
                    head_idx=chunk.root.i,
                    confidence=1.0,
                    sources=[self.create_source_identifier()],
                )
                phrases.append(phrase)

        return phrases

    def extract_verb_phrases(
        self,
        native_sentence: Span,
        tokens: List[UnifiedToken]
    ) -> List:
        """
        Extract verb phrases using dependency structure.

        Returns list of UnifiedPhrase objects.
        """
        from src.unified_types import UnifiedPhrase

        phrases = []

        # Find all verbs
        for token in native_sentence:
            if token.pos_ == 'VERB':
                # Get verb and its immediate children
                vp_tokens_indices = {token.i}

                for child in token.children:
                    # Include auxiliary, negation, particles
                    if child.dep_ in ['aux', 'auxpass', 'neg', 'prt']:
                        vp_tokens_indices.add(child.i)

                # Get unified tokens
                vp_tokens = [t for t in tokens if t.idx in vp_tokens_indices]
                vp_tokens.sort(key=lambda t: t.idx)

                if vp_tokens:
                    phrase = UnifiedPhrase(
                        phrase_type='VP',
                        start_idx=min(t.idx for t in vp_tokens),
                        end_idx=max(t.idx for t in vp_tokens) + 1,
                        tokens=vp_tokens,
                        head_idx=token.i,
                        confidence=0.8,  # Lower confidence for heuristic extraction
                        sources=[self.create_source_identifier()],
                    )
                    phrases.append(phrase)

        return phrases

    def extract_scientific_entities(
        self,
        native_document: Doc,
        tokens: List[UnifiedToken]
    ) -> List[UnifiedEntity]:
        """
        Extract scientific entities (requires scispacy model).

        Returns list of UnifiedEntity objects with scientific types.
        """
        entities = []

        # Check if this is a scispacy model
        if not hasattr(native_document, 'ents'):
            return entities

        for ent in native_document.ents:
            if ent.label_ in self.mapper.BIOMEDICAL_ENTITY_TYPES:
                entity_tokens = [
                    t for t in tokens
                    if ent.start <= t.idx < ent.end
                ]

                unified_entity = UnifiedEntity(
                    entity_type=ent.label_,
                    start_idx=ent.start,
                    end_idx=ent.end,
                    tokens=entity_tokens,
                    confidence=1.0,
                    sources=[self.create_source_identifier()],
                    is_scientific=True,
                    domain='biomedical',
                )
                entities.append(unified_entity)

        return entities
