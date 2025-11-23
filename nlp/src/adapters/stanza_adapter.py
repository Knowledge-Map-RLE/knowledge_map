"""
Stanza NLP adapter for multi-level analysis.

Stanza is a neural NLP library from Stanford that provides state-of-the-art
models for tokenization, POS tagging, lemmatization, and dependency parsing.
"""

import stanza
from typing import Optional
import logging

from src.unified_types import (
    UnifiedDocument, UnifiedSentence, UnifiedToken, UnifiedDependency,
    UnifiedEntity, LinguisticLevel
)
from src.adapters.universal_dependencies_mapper import UniversalDependenciesMapper

logger = logging.getLogger(__name__)


class StanzaAdapter:
    """
    Adapter for Stanza NLP library.

    Uses Stanford's neural models for accurate linguistic analysis.
    """

    def __init__(self, lang: str = 'en', download: bool = True):
        """
        Initialize Stanza adapter.

        Args:
            lang: Language code (default: 'en')
            download: Auto-download models if not present
        """
        self.lang = lang
        self.version = stanza.__version__

        try:
            # Download models if needed
            if download:
                try:
                    stanza.download(lang, verbose=False)
                except Exception as e:
                    logger.warning(f"Failed to download Stanza models: {e}")

            # Initialize pipeline with all processors
            self.nlp = stanza.Pipeline(
                lang=lang,
                processors='tokenize,pos,lemma,depparse,ner',
                verbose=False,
                use_gpu=False  # CPU only for now
            )

            self.mapper = UniversalDependenciesMapper()
            logger.info(f"Stanza adapter initialized (lang={lang}, version={self.version})")

        except Exception as e:
            logger.error(f"Failed to initialize Stanza: {e}")
            raise

    def process_level1(self, text: str, doc_id: Optional[str] = None) -> UnifiedDocument:
        """
        Level 1: Tokenization and sentence segmentation.

        Args:
            text: Input text
            doc_id: Optional document ID

        Returns:
            UnifiedDocument with tokenized sentences
        """
        doc = self.nlp(text)

        unified_doc = UnifiedDocument(
            text=text,
            doc_id=doc_id
        )

        for sent_idx, sent in enumerate(doc.sentences):
            unified_sent = UnifiedSentence(
                idx=sent_idx,
                text=sent.text,
                start_char=sent.tokens[0].start_char if sent.tokens else 0,
                end_char=sent.tokens[-1].end_char if sent.tokens else len(sent.text)
            )

            for token_idx, token in enumerate(sent.tokens):
                # Stanza tokens can be multi-word
                word = token.words[0] if token.words else None
                if not word:
                    continue

                unified_token = UnifiedToken(
                    idx=token_idx,
                    text=word.text,
                    start_char=token.start_char,
                    end_char=token.end_char,
                    lemma=word.text.lower(),  # Basic lemma for Level 1
                    pos='X',  # Placeholder for Level 1 (no POS analysis yet)
                    confidence=1.0,  # Stanza doesn't provide confidence
                    sources=[f'stanza-{self.version}']
                )

                unified_sent.tokens.append(unified_token)

            unified_doc.sentences.append(unified_sent)

        return unified_doc

    def process_level2(self, text: str, doc_id: Optional[str] = None) -> UnifiedDocument:
        """
        Level 2: Morphology and POS tagging.

        Args:
            text: Input text
            doc_id: Optional document ID

        Returns:
            UnifiedDocument with POS tags and morphology
        """
        doc = self.nlp(text)

        unified_doc = UnifiedDocument(
            text=text,
            doc_id=doc_id
        )

        for sent_idx, sent in enumerate(doc.sentences):
            unified_sent = UnifiedSentence(
                idx=sent_idx,
                text=sent.text,
                start_char=sent.tokens[0].start_char if sent.tokens else 0,
                end_char=sent.tokens[-1].end_char if sent.tokens else len(sent.text)
            )

            for token_idx, token in enumerate(sent.tokens):
                word = token.words[0] if token.words else None
                if not word:
                    continue

                # Map Stanza features to Universal Dependencies
                feats_dict = {}
                if word.feats:
                    for feat in word.feats.split('|'):
                        if '=' in feat:
                            key, value = feat.split('=', 1)
                            feats_dict[key] = value

                unified_token = UnifiedToken(
                    idx=token_idx,
                    text=word.text,
                    start_char=token.start_char,
                    end_char=token.end_char,
                    lemma=word.lemma or word.text.lower(),
                    pos=word.upos or 'X',  # Universal POS tag
                    pos_fine=word.xpos or '',  # Penn Treebank POS tag
                    morph=feats_dict,
                    is_stop=word.text.lower() in {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'},
                    is_punct=word.upos == 'PUNCT',
                    is_space=word.text.isspace(),
                    confidence=1.0,
                    sources=[f'stanza-{self.version}']
                )

                unified_sent.tokens.append(unified_token)

            unified_doc.sentences.append(unified_sent)

        return unified_doc

    def process_level3(self, text: str, doc_id: Optional[str] = None) -> UnifiedDocument:
        """
        Level 3: Syntax and dependency parsing.

        Args:
            text: Input text
            doc_id: Optional document ID

        Returns:
            UnifiedDocument with dependencies and entities
        """
        doc = self.nlp(text)

        unified_doc = UnifiedDocument(
            text=text,
            doc_id=doc_id
        )

        for sent_idx, sent in enumerate(doc.sentences):
            unified_sent = UnifiedSentence(
                idx=sent_idx,
                text=sent.text,
                start_char=sent.tokens[0].start_char if sent.tokens else 0,
                end_char=sent.tokens[-1].end_char if sent.tokens else len(sent.text)
            )

            # Process tokens
            for token_idx, token in enumerate(sent.tokens):
                word = token.words[0] if token.words else None
                if not word:
                    continue

                feats_dict = {}
                if word.feats:
                    for feat in word.feats.split('|'):
                        if '=' in feat:
                            key, value = feat.split('=', 1)
                            feats_dict[key] = value

                unified_token = UnifiedToken(
                    idx=token_idx,
                    text=word.text,
                    start_char=token.start_char,
                    end_char=token.end_char,
                    lemma=word.lemma or word.text.lower(),
                    pos=word.upos or 'X',
                    pos_fine=word.xpos or '',
                    morph=feats_dict,
                    is_stop=word.text.lower() in {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'},
                    is_punct=word.upos == 'PUNCT',
                    is_space=word.text.isspace(),
                    confidence=1.0,
                    sources=[f'stanza-{self.version}']
                )

                unified_sent.tokens.append(unified_token)

            # Process dependencies
            for word in sent.words:
                # Stanza uses 1-based indexing, convert to 0-based
                head_idx = word.head - 1 if word.head > 0 else -1
                dependent_idx = word.id - 1

                if head_idx >= 0:  # Skip root dependencies
                    dep = UnifiedDependency(
                        head_idx=head_idx,
                        dependent_idx=dependent_idx,
                        relation=word.deprel or 'dep',
                        confidence=1.0,
                        sources=[f'stanza-{self.version}']
                    )
                    unified_sent.dependencies.append(dep)

            # Process named entities
            for ent in sent.ents:
                # Find token indices for entity
                entity_tokens = []
                for token in unified_sent.tokens:
                    if token.start_char >= ent.start_char and token.end_char <= ent.end_char:
                        entity_tokens.append(token)

                if entity_tokens:
                    unified_ent = UnifiedEntity(
                        entity_type=ent.type,
                        start_idx=entity_tokens[0].idx,
                        end_idx=entity_tokens[-1].idx + 1,  # Exclusive
                        tokens=entity_tokens,
                        confidence=1.0,
                        sources=[f'stanza-{self.version}']
                    )
                    unified_sent.entities.append(unified_ent)

            unified_doc.sentences.append(unified_sent)

        return unified_doc

    def get_version(self) -> str:
        """Get Stanza version."""
        return self.version
