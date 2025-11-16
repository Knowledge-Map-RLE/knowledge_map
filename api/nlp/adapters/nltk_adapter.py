"""
NLTK adapter for converting NLTK outputs to unified format.

NLTK provides tokenization and POS tagging, but limited dependency parsing.
"""

from typing import List, Dict, Any, Optional, Tuple
import nltk
from nltk import word_tokenize, pos_tag, sent_tokenize
from nltk.corpus import wordnet as wn

from .base_adapter import BaseAdapter
from .universal_dependencies_mapper import UniversalDependenciesMapper
from ..unified_types import (
    UnifiedToken,
    UnifiedDependency,
    UnifiedEntity,
    UnifiedSentence,
    ProcessorOutput,
)


class NLTKAdapter(BaseAdapter):
    """
    Adapter for NLTK NLP processor.

    NLTK uses Penn Treebank tags, so we need to map them to UD.
    """

    def __init__(self, processor_version: str = None):
        """
        Initialize NLTK adapter.

        Args:
            processor_version: NLTK version (auto-detected if None)
        """
        if processor_version is None:
            processor_version = nltk.__version__

        super().__init__(processor_name='nltk', processor_version=processor_version)
        self.mapper = UniversalDependenciesMapper()

        # Ensure required NLTK data is available
        self._ensure_nltk_data()

    def _ensure_nltk_data(self):
        """Download required NLTK data if not present."""
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            pass  # Will handle in processor

        try:
            nltk.data.find('taggers/averaged_perceptron_tagger')
        except LookupError:
            pass

        try:
            nltk.data.find('corpora/wordnet')
        except LookupError:
            pass

    # ============================================================================
    # Token conversion
    # ============================================================================

    def to_unified_token(
        self,
        native_token: Tuple[str, str],  # (word, tag)
        token_idx: int,
        sentence_start_char: int = 0,
        confidence: float = 1.0
    ) -> UnifiedToken:
        """
        Convert NLTK token (word, tag) to UnifiedToken.

        Args:
            native_token: Tuple of (word, universal_tag)
            token_idx: Index of token in sentence
            sentence_start_char: Character offset of sentence start
            confidence: Confidence score
        """
        word, universal_tag = native_token

        # Tag is already in Universal Dependencies format (from tagset='universal')
        pos = universal_tag if universal_tag else 'X'

        # Get morphological features (basic inference from universal POS)
        morph = self._infer_morph_from_universal_pos(word, pos)

        # Lemmatize using WordNet
        lemma = self._lemmatize_word(word, pos)

        # Estimate character positions (NLTK doesn't provide char offsets natively)
        # This is approximate - will be refined in processor
        start_char = sentence_start_char
        end_char = start_char + len(word)

        unified_token = UnifiedToken(
            idx=token_idx,
            text=word,
            start_char=start_char,
            end_char=end_char,
            lemma=lemma,
            pos=pos,
            pos_fine=universal_tag,  # Store universal tag in pos_fine
            morph=morph,
            confidence=confidence,
            sources=[self.create_source_identifier()],
            is_stop=word.lower() in self._get_stopwords(),
            is_punct=self._is_punctuation(word),
            is_space=word.isspace(),
        )

        return unified_token

    def _infer_morph_from_universal_pos(self, word: str, pos: str) -> Dict[str, str]:
        """
        Infer basic morphological features from universal POS and word form.

        Args:
            word: Word text
            pos: Universal POS tag

        Returns:
            Dictionary of morphological features
        """
        morph = {}

        # Verb tense inference
        if pos == 'VERB':
            if word.endswith('ed'):
                morph['Tense'] = 'Past'
                morph['VerbForm'] = 'Part'
            elif word.endswith('ing'):
                morph['Tense'] = 'Pres'
                morph['VerbForm'] = 'Part'
                morph['Aspect'] = 'Prog'
            elif word.endswith('s') and not word.endswith('ss'):
                morph['Tense'] = 'Pres'
                morph['Number'] = 'Sing'
                morph['Person'] = '3'

        # Noun number inference
        elif pos == 'NOUN':
            if word.endswith('s') and not word.endswith('ss'):
                morph['Number'] = 'Plur'
            else:
                morph['Number'] = 'Sing'

        # Adjective degree
        elif pos == 'ADJ':
            if word.endswith('est'):
                morph['Degree'] = 'Sup'
            elif word.endswith('er'):
                morph['Degree'] = 'Cmp'
            else:
                morph['Degree'] = 'Pos'

        # Pronoun features
        elif pos == 'PRON':
            word_lower = word.lower()
            if word_lower in ['i', 'we']:
                morph['Person'] = '1'
            elif word_lower in ['you']:
                morph['Person'] = '2'
            elif word_lower in ['he', 'she', 'it', 'they']:
                morph['Person'] = '3'

            if word_lower in ['i', 'he', 'she', 'it']:
                morph['Number'] = 'Sing'
            elif word_lower in ['we', 'they']:
                morph['Number'] = 'Plur'

        return morph

    def get_pos_mapping(self) -> Dict[str, str]:
        """Get mapping from Penn Treebank tags to UD tags."""
        return self.mapper.PTB_TO_UD_POS.copy()

    def get_morph_features(self, native_token: Tuple[str, str]) -> Dict[str, str]:
        """Extract morphological features from NLTK token."""
        word, universal_tag = native_token
        return self._infer_morph_from_universal_pos(word, universal_tag)

    def _lemmatize_word(self, word: str, pos: str) -> str:
        """
        Lemmatize word using WordNet.

        Args:
            word: Word to lemmatize
            pos: UD POS tag

        Returns:
            Lemmatized form
        """
        try:
            # Map UD POS to WordNet POS
            wn_pos = self._ud_to_wordnet_pos(pos)

            if wn_pos:
                from nltk.stem import WordNetLemmatizer
                lemmatizer = WordNetLemmatizer()
                return lemmatizer.lemmatize(word.lower(), pos=wn_pos)
            else:
                return word.lower()

        except Exception:
            # Fallback: just lowercase
            return word.lower()

    def _ud_to_wordnet_pos(self, ud_pos: str) -> Optional[str]:
        """Map UD POS tag to WordNet POS tag."""
        mapping = {
            'NOUN': wn.NOUN,
            'VERB': wn.VERB,
            'ADJ': wn.ADJ,
            'ADV': wn.ADV,
        }
        return mapping.get(ud_pos)

    def _get_stopwords(self) -> set:
        """Get English stopwords."""
        try:
            from nltk.corpus import stopwords
            return set(stopwords.words('english'))
        except:
            # Basic fallback
            return {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or', 'but'}

    def _is_punctuation(self, word: str) -> bool:
        """Check if word is punctuation."""
        import string
        return all(c in string.punctuation for c in word)

    # ============================================================================
    # Dependency conversion (NLTK has limited dependency parsing)
    # ============================================================================

    def to_unified_dependency(
        self,
        native_dependency: Any,
        confidence: float = 1.0
    ) -> UnifiedDependency:
        """
        NLTK doesn't provide dependency parsing by default.

        This method is a placeholder. For real dependency parsing with NLTK,
        you'd need to use Stanford Parser or similar.
        """
        raise NotImplementedError(
            "NLTK doesn't provide dependency parsing. "
            "Use spaCy or Stanford Parser for dependencies."
        )

    def get_dependency_mapping(self) -> Dict[str, str]:
        """NLTK doesn't provide dependencies."""
        return {}

    # ============================================================================
    # Entity conversion (NLTK has basic NER with ne_chunk)
    # ============================================================================

    def to_unified_entity(
        self,
        native_entity: Any,  # nltk.Tree from ne_chunk
        tokens: List[UnifiedToken],
        confidence: float = 0.7  # Lower confidence for NLTK NER
    ) -> UnifiedEntity:
        """
        Convert NLTK named entity (from ne_chunk) to UnifiedEntity.

        Args:
            native_entity: nltk.Tree with entity label
            tokens: List of UnifiedTokens
            confidence: Confidence score
        """
        from nltk import Tree

        if not isinstance(native_entity, Tree):
            raise ValueError("native_entity must be an nltk.Tree")

        entity_type = native_entity.label()
        entity_words = [word for word, tag in native_entity.leaves()]

        # Find corresponding tokens
        entity_tokens = []
        for token in tokens:
            if token.text in entity_words:
                entity_tokens.append(token)

        if not entity_tokens:
            # Fallback: create minimal entity
            entity_tokens = tokens[0:1]

        start_idx = entity_tokens[0].idx
        end_idx = entity_tokens[-1].idx + 1

        # Normalize entity type
        normalized_type = self.normalize_entity_type(entity_type)

        unified_entity = UnifiedEntity(
            entity_type=normalized_type,
            start_idx=start_idx,
            end_idx=end_idx,
            tokens=entity_tokens,
            confidence=confidence,
            sources=[self.create_source_identifier()],
        )

        return unified_entity

    def get_entity_type_mapping(self) -> Dict[str, str]:
        """
        Get mapping from NLTK entity types to standard types.

        NLTK uses: PERSON, ORGANIZATION, LOCATION, DATE, TIME, MONEY, PERCENT, FACILITY, GPE
        """
        return {
            'PERSON': 'PERSON',
            'ORGANIZATION': 'ORG',
            'LOCATION': 'LOC',
            'GPE': 'GPE',  # Geo-political entity
            'FACILITY': 'FAC',
            'DATE': 'DATE',
            'TIME': 'TIME',
            'MONEY': 'MONEY',
            'PERCENT': 'PERCENT',
        }

    # ============================================================================
    # Sentence conversion
    # ============================================================================

    def to_unified_sentence(
        self,
        native_sentence: List[Tuple[str, str]],  # List of (word, tag)
        sentence_idx: int,
        doc_start_char: int = 0,
        confidence: float = 1.0
    ) -> UnifiedSentence:
        """
        Convert NLTK sentence (list of (word, tag)) to UnifiedSentence.

        Args:
            native_sentence: List of (word, PTB_tag) tuples
            sentence_idx: Sentence index in document
            doc_start_char: Document start character offset
            confidence: Confidence score
        """
        # Estimate sentence text (reconstruct from tokens)
        sentence_text = ' '.join(word for word, tag in native_sentence)
        sentence_start_char = doc_start_char

        # Convert tokens
        tokens = []
        char_offset = sentence_start_char

        for token_idx, (word, tag) in enumerate(native_sentence):
            unified_token = UnifiedToken(
                idx=token_idx,
                text=word,
                start_char=char_offset,
                end_char=char_offset + len(word),
                lemma=self._lemmatize_word(word, self.normalize_pos_tag(tag)),
                pos=self.normalize_pos_tag(tag),
                pos_fine=tag,
                morph=self.get_morph_features((word, tag)),
                confidence=confidence,
                sources=[self.create_source_identifier()],
                is_stop=word.lower() in self._get_stopwords(),
                is_punct=self._is_punctuation(word),
                is_space=word.isspace(),
            )
            tokens.append(unified_token)

            # Update character offset (word + space)
            char_offset += len(word) + 1

        # NLTK doesn't provide dependencies
        dependencies = []

        # Extract entities using ne_chunk
        entities = self._extract_entities_from_sentence(native_sentence, tokens)

        unified_sentence = UnifiedSentence(
            idx=sentence_idx,
            text=sentence_text,
            start_char=sentence_start_char,
            end_char=sentence_start_char + len(sentence_text),
            tokens=tokens,
            dependencies=dependencies,
            entities=entities,
            confidence=confidence,
        )

        return unified_sentence

    def _extract_entities_from_sentence(
        self,
        tagged_sentence: List[Tuple[str, str]],
        tokens: List[UnifiedToken]
    ) -> List[UnifiedEntity]:
        """
        Extract entities using NLTK's ne_chunk.

        Args:
            tagged_sentence: List of (word, tag)
            tokens: Corresponding UnifiedTokens

        Returns:
            List of UnifiedEntity
        """
        try:
            from nltk import ne_chunk, Tree

            # Run NER
            tree = ne_chunk(tagged_sentence)

            entities = []

            # Extract named entities
            for subtree in tree:
                if isinstance(subtree, Tree):
                    entity = self.to_unified_entity(subtree, tokens, confidence=0.7)
                    entities.append(entity)

            return entities

        except Exception:
            # If ne_chunk fails, return empty list
            return []

    # ============================================================================
    # Document conversion
    # ============================================================================

    def to_processor_output(
        self,
        native_document: List[List[Tuple[str, str]]],  # List of sentences
        confidence: float = 1.0,
        original_text: Optional[str] = None
    ) -> ProcessorOutput:
        """
        Convert NLTK document (list of tagged sentences) to ProcessorOutput.

        Args:
            native_document: List of sentences, each sentence is list of (word, tag)
            confidence: Base confidence score
            original_text: Original text for accurate character offset calculation

        Returns:
            ProcessorOutput
        """
        output = ProcessorOutput(
            processor_name=self.processor_name,
            processor_version=self.processor_version,
            overall_confidence=confidence,
        )

        # Calculate character offsets if original text is provided
        char_offset = 0
        if original_text:
            # Process each sentence with accurate offsets
            for sent_idx, sentence in enumerate(native_document):
                # Extract tokens with accurate character positions
                for token_idx, (word, tag) in enumerate(sentence):
                    # Find the word in the original text starting from char_offset
                    word_start = original_text.find(word, char_offset)

                    if word_start == -1:
                        # Fallback: continue from last position
                        word_start = char_offset

                    word_end = word_start + len(word)

                    # Tag is already in Universal Dependencies format (from tagset='universal')
                    # But NLTK sometimes returns punctuation symbols instead of 'PUNCT'
                    if tag in {'.', ',', ':', ';', '!', '?', '-', '(', ')', '[', ']', '{', '}', '"', "'", '`'}:
                        pos = 'PUNCT'
                    else:
                        pos = tag if tag else 'X'

                    unified_token = UnifiedToken(
                        idx=token_idx,
                        text=word,
                        start_char=word_start,
                        end_char=word_end,
                        lemma=self._lemmatize_word(word, pos),
                        pos=pos,
                        pos_fine=tag,
                        morph=self.get_morph_features((word, tag)),
                        confidence=confidence,
                        sources=[self.create_source_identifier()],
                        is_stop=word.lower() in self._get_stopwords(),
                        is_punct=self._is_punctuation(word),
                        is_space=word.isspace(),
                    )
                    output.tokens.append(unified_token)

                    # Update offset for next token
                    char_offset = word_end

                # Extract entities
                entities = self._extract_entities_from_sentence(
                    sentence,
                    output.tokens[-len(sentence):]  # Last N tokens
                )
                output.entities.extend(entities)
        else:
            # Fallback: approximate offsets (old behavior)
            for sent_idx, sentence in enumerate(native_document):
                # Extract tokens
                for token_idx, (word, tag) in enumerate(sentence):
                    unified_token = self.to_unified_token(
                        (word, tag),
                        token_idx=token_idx,
                        confidence=confidence
                    )
                    output.tokens.append(unified_token)

                # Extract entities
                entities = self._extract_entities_from_sentence(
                    sentence,
                    output.tokens[-len(sentence):]  # Last N tokens
                )
                output.entities.extend(entities)

        # NLTK doesn't provide dependencies
        output.dependencies = []

        return output

    # ============================================================================
    # NLTK-specific helpers
    # ============================================================================

    def get_wordnet_synsets(self, word: str, pos: str) -> List[Any]:
        """
        Get WordNet synsets for a word.

        Useful for lexical semantics (Level 5).

        Args:
            word: Word to look up
            pos: UD POS tag

        Returns:
            List of WordNet synsets
        """
        wn_pos = self._ud_to_wordnet_pos(pos)

        if wn_pos:
            return wn.synsets(word, pos=wn_pos)
        else:
            return wn.synsets(word)

    def get_word_similarity(self, word1: str, word2: str, pos: str = None) -> float:
        """
        Calculate semantic similarity between two words using WordNet.

        Args:
            word1: First word
            word2: Second word
            pos: Optional POS tag for disambiguation

        Returns:
            Similarity score (0.0-1.0), or 0.0 if not comparable
        """
        try:
            synsets1 = wn.synsets(word1)
            synsets2 = wn.synsets(word2)

            if not synsets1 or not synsets2:
                return 0.0

            # Use path similarity (shortest path in taxonomy)
            max_sim = 0.0

            for syn1 in synsets1:
                for syn2 in synsets2:
                    sim = syn1.path_similarity(syn2)
                    if sim and sim > max_sim:
                        max_sim = sim

            return max_sim

        except Exception:
            return 0.0
