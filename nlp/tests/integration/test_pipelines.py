"""
Integration tests for NLP pipelines.

Tests complete pipelines from text input to output.
"""

import pytest

from nlp.src.pipelines.tokenization import tokenize
from nlp.src.pipelines.morphology import analyze_morphology
from nlp.src.pipelines.syntax import analyze_syntax
from nlp.src.pipelines.full_analysis import analyze_text
from nlp.src.unified_types import LinguisticLevel


SAMPLE_TEXT = "Apple released a new iPhone. It is very expensive."


class TestTokenizationPipeline:
    """Test tokenization pipeline."""

    def test_tokenize_basic(self):
        """Test basic tokenization."""
        doc = tokenize(SAMPLE_TEXT)

        assert doc.text == SAMPLE_TEXT
        assert len(doc.sentences) == 2
        assert len(doc.sentences[0].tokens) > 0
        assert LinguisticLevel.TOKENIZATION in doc.processed_levels

    def test_tokenize_simple_sentence(self):
        """Test tokenization of simple sentence."""
        text = "Hello world."
        doc = tokenize(text)

        assert len(doc.sentences) == 1
        assert len(doc.sentences[0].tokens) == 3  # Hello, world, .
        assert doc.sentences[0].tokens[0].text == "Hello"
        assert doc.sentences[0].tokens[1].text == "world"
        assert doc.sentences[0].tokens[2].text == "."

    def test_tokenize_with_custom_doc_id(self):
        """Test tokenize with custom doc_id."""
        doc_id = "custom-123"
        doc = tokenize("Test text.", doc_id=doc_id)

        assert doc.doc_id == doc_id

    def test_tokenize_pos_tagging(self):
        """Test that POS tags are assigned."""
        doc = tokenize("The cat ran.")

        tokens = doc.sentences[0].tokens
        # "The" should be DET
        assert tokens[0].pos == "DET"
        # "cat" should be NOUN
        assert tokens[1].pos == "NOUN"
        # "ran" should be VERB
        assert tokens[2].pos == "VERB"


class TestMorphologyPipeline:
    """Test morphology analysis pipeline."""

    def test_analyze_morphology_basic(self):
        """Test basic morphological analysis."""
        doc = analyze_morphology(SAMPLE_TEXT)

        assert doc.text == SAMPLE_TEXT
        assert len(doc.sentences) == 2
        assert LinguisticLevel.TOKENIZATION in doc.processed_levels
        assert LinguisticLevel.MORPHOLOGY in doc.processed_levels

    def test_analyze_morphology_extracts_features(self):
        """Test that morphological features are extracted."""
        text = "The cats ran."
        doc = analyze_morphology(text)

        tokens = doc.sentences[0].tokens
        # "cats" (plural) should have Number feature
        cats_token = tokens[1]
        assert cats_token.text == "cats"
        # morph should be a dict (may be empty if not available)
        assert isinstance(cats_token.morph, dict)


class TestSyntaxPipeline:
    """Test syntax analysis pipeline."""

    def test_analyze_syntax_basic(self):
        """Test basic syntax analysis."""
        doc = analyze_syntax(SAMPLE_TEXT)

        assert doc.text == SAMPLE_TEXT
        assert len(doc.sentences) == 2
        assert LinguisticLevel.TOKENIZATION in doc.processed_levels
        assert LinguisticLevel.MORPHOLOGY in doc.processed_levels
        assert LinguisticLevel.SYNTAX in doc.processed_levels

    def test_analyze_syntax_dependencies(self):
        """Test that dependencies are extracted."""
        text = "The cat sat."
        doc = analyze_syntax(text)

        sentence = doc.sentences[0]
        assert len(sentence.dependencies) > 0
        assert sentence.root_idx is not None

        # Check that all dependencies reference valid indices
        for dep in sentence.dependencies:
            assert 0 <= dep.head_idx < len(sentence.tokens)
            assert 0 <= dep.dependent_idx < len(sentence.tokens)

    def test_analyze_syntax_entities(self):
        """Test named entity recognition."""
        text = "Apple released a new iPhone."
        doc = analyze_syntax(text)

        sentence = doc.sentences[0]
        # Should recognize "Apple" and possibly "iPhone" as entities
        entity_texts = [" ".join(t.text for t in e.tokens) for e in sentence.entities]

        # At least some entities should be found
        assert any("Apple" in text for text in entity_texts) or len(entity_texts) > 0

    def test_analyze_syntax_phrases(self):
        """Test phrase extraction."""
        text = "The quick brown fox jumps over the lazy dog."
        doc = analyze_syntax(text)

        sentence = doc.sentences[0]
        # Should extract noun phrases
        noun_phrases = [p for p in sentence.phrases if p.phrase_type == "NP"]
        assert len(noun_phrases) > 0


class TestFullAnalysisPipeline:
    """Test full analysis pipeline."""

    def test_analyze_text_basic(self):
        """Test basic full analysis."""
        doc = analyze_text(SAMPLE_TEXT)

        assert doc.text == SAMPLE_TEXT
        assert len(doc.sentences) == 2
        assert LinguisticLevel.TOKENIZATION in doc.processed_levels
        assert LinguisticLevel.MORPHOLOGY in doc.processed_levels
        assert LinguisticLevel.SYNTAX in doc.processed_levels

    def test_analyze_text_complete_structure(self):
        """Test that all components are present."""
        text = "The cat sat on the mat."
        doc = analyze_text(text)

        sentence = doc.sentences[0]

        # Check all components
        assert len(sentence.tokens) > 0
        assert len(sentence.dependencies) > 0
        assert sentence.root_idx is not None
        assert isinstance(sentence.phrases, list)
        assert isinstance(sentence.entities, list)

    def test_analyze_text_empty_string(self):
        """Test handling of empty string."""
        doc = analyze_text("")

        assert doc.text == ""
        # May have 0 sentences for empty string
        assert len(doc.sentences) >= 0

    def test_analyze_text_multiple_sentences(self):
        """Test multi-sentence analysis."""
        text = "First sentence. Second sentence. Third sentence."
        doc = analyze_text(text)

        assert len(doc.sentences) == 3
        for sent in doc.sentences:
            assert len(sent.tokens) > 0


class TestPipelineConsistency:
    """Test consistency across pipelines."""

    def test_tokenization_consistency(self):
        """Test that tokenization is consistent."""
        doc1 = tokenize(SAMPLE_TEXT)
        doc2 = tokenize(SAMPLE_TEXT)

        # Same text should produce same tokens
        sent1_tokens = [t.text for t in doc1.sentences[0].tokens]
        sent2_tokens = [t.text for t in doc2.sentences[0].tokens]

        assert sent1_tokens == sent2_tokens

    def test_morphology_consistency(self):
        """Test morphology analysis consistency."""
        doc1 = analyze_morphology(SAMPLE_TEXT)
        doc2 = analyze_morphology(SAMPLE_TEXT)

        # Same text should produce same POS tags
        pos1 = [t.pos for t in doc1.sentences[0].tokens]
        pos2 = [t.pos for t in doc2.sentences[0].tokens]

        assert pos1 == pos2

    def test_syntax_consistency(self):
        """Test syntax analysis consistency."""
        doc1 = analyze_syntax(SAMPLE_TEXT)
        doc2 = analyze_syntax(SAMPLE_TEXT)

        # Same text should produce same dependencies
        deps1 = len(doc1.sentences[0].dependencies)
        deps2 = len(doc2.sentences[0].dependencies)

        assert deps1 == deps2

    def test_all_pipelines_same_tokenization(self):
        """Test that all pipelines produce same tokens."""
        text = "The cat sat."

        doc_tok = tokenize(text)
        doc_morph = analyze_morphology(text)
        doc_syn = analyze_syntax(text)
        doc_full = analyze_text(text)

        tokens_tok = [t.text for t in doc_tok.sentences[0].tokens]
        tokens_morph = [t.text for t in doc_morph.sentences[0].tokens]
        tokens_syn = [t.text for t in doc_syn.sentences[0].tokens]
        tokens_full = [t.text for t in doc_full.sentences[0].tokens]

        assert tokens_tok == tokens_morph == tokens_syn == tokens_full


class TestErrorHandling:
    """Test error handling in pipelines."""

    def test_tokenize_unicode(self):
        """Test handling of unicode text."""
        text = "Héllo wörld. 你好世界."
        doc = tokenize(text)

        assert doc.text == text
        assert len(doc.sentences) >= 1

    def test_analyze_syntax_special_chars(self):
        """Test handling of special characters."""
        text = "Hello!!! How are you??? #hashtag @mention"
        doc = analyze_syntax(text)

        assert doc.text == text
        assert len(doc.sentences) > 0

    def test_analyze_text_very_long_text(self):
        """Test handling of long text."""
        text = "This is a sentence. " * 100
        doc = analyze_text(text)

        assert len(doc.sentences) == 100
