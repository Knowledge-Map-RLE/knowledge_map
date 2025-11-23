"""
Level 1 Processor: Tokenization and Sentence Segmentation

Combines multiple tokenizers (spaCy, NLTK) and uses voting to determine
the most reliable tokenization.
"""

from typing import List, Optional, Dict, Any
import spacy
import nltk
from nltk import word_tokenize, sent_tokenize

from src.adapters.spacy_adapter import SpacyAdapter
from src.adapters.nltk_adapter import NLTKAdapter
from src.adapters.stanza_adapter import StanzaAdapter
from src.voting.voting_engine import VotingEngine
from src.unified_types import (
    UnifiedToken,
    UnifiedSentence,
    UnifiedDocument,
    ProcessorOutput,
    VotingResult,
    LinguisticLevel,
)
from src.processors.base import BaseNLPProcessor


class Level1TokenizationProcessor(BaseNLPProcessor):
    """
    Multi-tool tokenization processor with voting.

    Uses:
    - spaCy tokenizer
    - NLTK tokenizer
    - (Optional) Other tokenizers

    Accepts tokens only if at least 2 tokenizers agree.
    """

    def __init__(
        self,
        spacy_model: str = "en_core_sci_lg",
        enable_voting: bool = True,
        min_agreement: int = 1,  # Allow single source for dependencies until UDPipe/Stanza work
    ):
        """
        Initialize Level 1 processor.

        Args:
            spacy_model: spaCy model name (default: en_core_sci_lg for scientific texts)
            enable_voting: Whether to use voting (True) or just use spaCy (False)
            min_agreement: Minimum number of tokenizers that must agree
        """
        super().__init__()

        self.spacy_model_name = spacy_model
        self.enable_voting = enable_voting
        self.min_agreement = min_agreement

        # Load spaCy model with priority: requested model -> en_core_sci_lg -> en_core_web_sm
        try:
            import warnings
            # Suppress version warnings
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                self.spacy_nlp = spacy.load(spacy_model)
            print(f"Loaded spaCy model: {spacy_model}")
        except OSError:
            # Try scientific model first
            if spacy_model != "en_core_sci_lg":
                print(f"Model {spacy_model} not found, trying en_core_sci_lg...")
                try:
                    import warnings
                    with warnings.catch_warnings():
                        warnings.filterwarnings("ignore", category=UserWarning)
                        self.spacy_nlp = spacy.load("en_core_sci_lg")
                    self.spacy_model_name = "en_core_sci_lg"
                    print("Loaded fallback spaCy model: en_core_sci_lg")
                except OSError:
                    # Try to install it
                    print("en_core_sci_lg not found, attempting to download...")
                    try:
                        import subprocess
                        import sys
                        subprocess.check_call(
                            [sys.executable, "-m", "pip", "install",
                             "https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_lg-0.5.4.tar.gz"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        self.spacy_nlp = spacy.load("en_core_sci_lg")
                        self.spacy_model_name = "en_core_sci_lg"
                        print("Successfully downloaded and loaded en_core_sci_lg")
                    except Exception as e:
                        # Final fallback to web_sm
                        print(f"Failed to download en_core_sci_lg: {e}")
                        print("Falling back to en_core_web_sm")
                        import warnings
                        with warnings.catch_warnings():
                            warnings.filterwarnings("ignore", category=UserWarning)
                            self.spacy_nlp = spacy.load("en_core_web_sm")
                        self.spacy_model_name = "en_core_web_sm"
            else:
                # en_core_sci_lg was requested but not found, try web_sm
                print("en_core_sci_lg not found, falling back to en_core_web_sm")
                import warnings
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=UserWarning)
                    self.spacy_nlp = spacy.load("en_core_web_sm")
                self.spacy_model_name = "en_core_web_sm"

        # Initialize adapters
        self.spacy_adapter = SpacyAdapter(processor_version=spacy.__version__)
        self.nltk_adapter = NLTKAdapter()

        # Initialize UDPipe adapter (for dependency parsing voting)
        if enable_voting:
            try:
                from src.adapters.udpipe_adapter import UDPipeAdapter
                self.udpipe_adapter = UDPipeAdapter(lang='en')
            except Exception as e:
                print(f"Warning: Failed to initialize UDPipe: {e}")
                self.udpipe_adapter = None
        else:
            self.udpipe_adapter = None

        # Initialize Stanza adapter (for 3-way voting)
        if enable_voting:
            try:
                self.stanza_adapter = StanzaAdapter(lang='en', download=True)
            except Exception as e:
                print(f"Warning: Failed to initialize Stanza: {e}")
                self.stanza_adapter = None
        else:
            self.stanza_adapter = None

        # Initialize voting engine
        if enable_voting:
            self.voting_engine = VotingEngine(
                min_agreement=min_agreement,
                similarity_threshold=0.8
            )

        # Download NLTK data if needed
        self._ensure_nltk_data()

    def _ensure_nltk_data(self):
        """Ensure required NLTK data is downloaded."""
        try:
            nltk.data.find('tokenizers/punkt')
            nltk.data.find('taggers/averaged_perceptron_tagger')
            nltk.data.find('taggers/universal_tagset')
        except LookupError:
            print("Downloading required NLTK data...")
            try:
                nltk.download('punkt', quiet=True)
                nltk.download('averaged_perceptron_tagger', quiet=True)
                nltk.download('universal_tagset', quiet=True)
                nltk.download('wordnet', quiet=True)
            except Exception as e:
                print(f"Warning: Could not download NLTK data: {e}")

    # ============================================================================
    # Main processing methods
    # ============================================================================

    def process(self, text: str) -> UnifiedDocument:
        """
        Process text through Level 1 (tokenization).

        Args:
            text: Input text

        Returns:
            UnifiedDocument with tokenized sentences
        """
        if not self.enable_voting:
            # Fast path: just use spaCy
            return self._process_with_spacy_only(text)

        # Multi-tool path with voting
        return self._process_with_voting(text)

    def _process_with_spacy_only(self, text: str) -> UnifiedDocument:
        """Process using only spaCy (faster, no voting)."""
        doc = self.spacy_nlp(text)

        sentences = []
        for sent_idx, sent_span in enumerate(doc.sents):
            unified_sent = self.spacy_adapter.to_unified_sentence(
                sent_span,
                sentence_idx=sent_idx,
                confidence=1.0
            )
            sentences.append(unified_sent)

        unified_doc = UnifiedDocument(
            doc_id="",  # Will be set by caller
            text=text,
            sentences=sentences,
            processed_levels=[LinguisticLevel.TOKENIZATION],
        )

        return unified_doc

    def _process_with_voting(self, text: str) -> UnifiedDocument:
        """Process using multiple tokenizers with voting."""

        # 1. Process with primary spaCy model (en_core_sci_lg)
        spacy_doc = self.spacy_nlp(text)
        spacy_output = self.spacy_adapter.to_processor_output(
            spacy_doc,
            confidence=0.95
        )

        processor_outputs = [spacy_output]

        # 2. Tokenize with NLTK
        nltk_output = self._tokenize_with_nltk(text)
        processor_outputs.append(nltk_output)

        # 3. Process with UDPipe (if available)
        if hasattr(self, 'udpipe_adapter') and self.udpipe_adapter:
            try:
                udpipe_output = self.udpipe_adapter.process_text(text)
                processor_outputs.append(udpipe_output)
            except Exception as e:
                print(f"UDPipe processing failed: {e}")

        # 4. Process with Stanza (if available)
        if self.stanza_adapter:
            try:
                # Use level3 to get dependencies
                stanza_doc = self.stanza_adapter.process_level3(text)
                stanza_output = ProcessorOutput(
                    processor_name='stanza',
                    processor_version=self.stanza_adapter.version,
                    tokens=[],
                    dependencies=[],
                    entities=[]
                )
                # Collect all tokens, dependencies, and entities from all sentences
                token_offset = 0  # Track global token index
                for sent in stanza_doc.sentences:
                    # Add tokens
                    stanza_output.tokens.extend(sent.tokens)

                    # Add dependencies with adjusted indices (make them global)
                    for dep in sent.dependencies:
                        # Create a copy with adjusted indices
                        from src.unified_types import UnifiedDependency
                        adjusted_dep = UnifiedDependency(
                            head_idx=dep.head_idx + token_offset,
                            dependent_idx=dep.dependent_idx + token_offset,
                            relation=dep.relation,
                            confidence=dep.confidence,
                            sources=dep.sources
                        )
                        stanza_output.dependencies.append(adjusted_dep)

                    # Add entities
                    stanza_output.entities.extend(sent.entities)

                    # Update offset for next sentence
                    token_offset += len(sent.tokens)
                processor_outputs.append(stanza_output)
            except Exception as e:
                print(f"Stanza processing failed: {e}")

        # 5. Vote on tokens, dependencies, and entities
        voting_result = self.voting_engine.vote_all(processor_outputs)

        # 6. Build unified document from agreed tokens
        unified_doc = self._build_document_from_voting(
            text,
            voting_result,
            spacy_doc  # Use spaCy for sentence boundaries
        )

        return unified_doc

    def _tokenize_with_nltk(self, text: str) -> ProcessorOutput:
        """
        Tokenize text using NLTK.

        Args:
            text: Input text

        Returns:
            ProcessorOutput with NLTK tokens
        """
        # Sentence tokenization
        sentences = sent_tokenize(text)

        # Word tokenization and POS tagging with universal tagset
        tagged_sentences = []
        for sent in sentences:
            tokens = word_tokenize(sent)
            # Use tagset='universal' for direct UD POS tags
            tagged = nltk.pos_tag(tokens, tagset='universal')
            tagged_sentences.append(tagged)

        # Convert to ProcessorOutput with original text for accurate offsets
        output = self.nltk_adapter.to_processor_output(
            tagged_sentences,
            confidence=0.85,
            original_text=text
        )

        return output

    def _build_document_from_voting(
        self,
        text: str,
        voting_result: VotingResult,
        spacy_doc: Any
    ) -> UnifiedDocument:
        """
        Build UnifiedDocument from voting results.

        Uses agreed tokens from voting and sentence boundaries from spaCy.

        Args:
            text: Original text
            voting_result: Voting results
            spacy_doc: spaCy Doc for sentence boundaries

        Returns:
            UnifiedDocument
        """
        # Get agreed tokens (high confidence)
        agreed_tokens = voting_result.agreed_tokens
        agreed_dependencies = voting_result.agreed_dependencies
        agreed_entities = voting_result.agreed_entities

        # Group tokens by sentences using spaCy sentence boundaries
        sentences = []

        for sent_idx, sent_span in enumerate(spacy_doc.sents):
            # Find tokens that belong to this sentence
            sent_tokens = [
                token for token in agreed_tokens
                if sent_span.start_char <= token.start_char < sent_span.end_char
            ]

            # Find dependencies for this sentence (by checking if tokens are in sentence)
            sent_token_indices = {token.idx for token in sent_tokens}
            sent_deps = [
                dep for dep in agreed_dependencies
                if dep.head_idx in sent_token_indices and dep.dependent_idx in sent_token_indices
            ]

            # Find entities for this sentence (by checking if entity tokens are in sentence)
            sent_entities = [
                entity for entity in agreed_entities
                if entity.tokens and sent_span.start_char <= entity.tokens[0].start_char < sent_span.end_char
            ]

            # Create unified sentence
            if sent_tokens:
                unified_sent = UnifiedSentence(
                    idx=sent_idx,
                    text=sent_span.text,
                    start_char=sent_span.start_char,
                    end_char=sent_span.end_char,
                    tokens=sent_tokens,
                    dependencies=sent_deps,
                    entities=sent_entities,
                    confidence=voting_result.agreement_score,
                )
                sentences.append(unified_sent)

        # Create document
        unified_doc = UnifiedDocument(
            doc_id="",
            text=text,
            sentences=sentences,
            processed_levels=[LinguisticLevel.TOKENIZATION],
            metadata={
                'agreement_score': voting_result.agreement_score,
                'num_agreements': voting_result.num_agreements,
                'num_disagreements': voting_result.num_disagreements,
                'participating_sources': voting_result.participating_sources,
            }
        )

        return unified_doc

    # ============================================================================
    # Analysis methods
    # ============================================================================

    def get_tokenization_statistics(self, doc: UnifiedDocument) -> Dict[str, Any]:
        """
        Get statistics about tokenization.

        Args:
            doc: Unified document

        Returns:
            Dictionary with statistics
        """
        total_tokens = sum(len(sent.tokens) for sent in doc.sentences)
        total_sentences = len(doc.sentences)

        # Count tokens by source agreement
        high_confidence_tokens = 0
        low_confidence_tokens = 0

        for sent in doc.sentences:
            for token in sent.tokens:
                if len(token.sources) >= 2:
                    high_confidence_tokens += 1
                else:
                    low_confidence_tokens += 1

        stats = {
            'total_sentences': total_sentences,
            'total_tokens': total_tokens,
            'avg_tokens_per_sentence': total_tokens / total_sentences if total_sentences > 0 else 0,
            'high_confidence_tokens': high_confidence_tokens,
            'low_confidence_tokens': low_confidence_tokens,
            'agreement_score': doc.metadata.get('agreement_score', 0.0),
        }

        return stats

    # ============================================================================
    # BaseNLPProcessor interface implementation
    # ============================================================================

    def get_level(self) -> LinguisticLevel:
        """Get the linguistic level this processor handles."""
        return LinguisticLevel.TOKENIZATION

    def process_text(self, text: str, **kwargs) -> Dict[str, Any]:
        """
        Process text (BaseNLPProcessor interface).

        Args:
            text: Input text
            **kwargs: Additional options

        Returns:
            Dictionary with results
        """
        doc = self.process(text)

        # Convert to dict format
        result = {
            'sentences': [],
            'statistics': self.get_tokenization_statistics(doc),
            'metadata': doc.metadata,
        }

        for sent in doc.sentences:
            sent_data = {
                'text': sent.text,
                'tokens': [
                    {
                        'text': token.text,
                        'pos': token.pos,
                        'lemma': token.lemma,
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
        return ['TOKEN', 'SENTENCE']

    def get_processor_info(self) -> Dict[str, Any]:
        """Get processor information."""
        return {
            'level': 1,
            'name': 'Level1TokenizationProcessor',
            'description': 'Multi-tool tokenization with voting',
            'tools': ['spacy', 'nltk'],
            'spacy_model': self.spacy_model_name,
            'voting_enabled': self.enable_voting,
            'min_agreement': self.min_agreement,
        }
