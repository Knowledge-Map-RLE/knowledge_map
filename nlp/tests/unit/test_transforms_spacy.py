"""
Unit tests for spaCy transformation functions.

Tests pure transformation functions from spacy_to_unified module.
"""

import pytest
import spacy

from nlp.src.transforms.spacy_to_unified import (
    token_to_unified,
    dependency_to_unified,
    entity_to_unified,
    sentence_to_unified,
    document_to_unified,
)
from nlp.src.unified_types import LinguisticLevel


@pytest.fixture(scope="session")
def spacy_model():
    """Load spaCy model once for all tests."""
    return spacy.load("en_core_web_sm")


@pytest.fixture
def sample_doc(spacy_model):
    """Process sample text."""
    return spacy_model("The cat sat on the mat.")


@pytest.fixture
def sample_sent(sample_doc):
    """Get first sentence."""
    return list(sample_doc.sents)[0]


# ============================================================================
# Token transformation tests
# ============================================================================

def test_token_to_unified_basic(sample_doc):
    """Test basic token transformation."""
    token = sample_doc[1]  # "cat"
    unified = token_to_unified(token, sentence_start_char=0, token_idx=1)

    assert unified.text == "cat"
    assert unified.lemma == "cat"
    assert unified.pos == "NOUN"
    assert unified.idx == 1
    assert unified.confidence == 1.0
    assert "spacy" in unified.sources


def test_token_to_unified_preserves_morphology(sample_doc):
    """Test that morphological features are extracted."""
    # Process text with more morphological variation
    doc = spacy_model("The cats ran.")
    token = doc[1]  # "cats" (plural)

    unified = token_to_unified(token, sentence_start_char=0, token_idx=1)

    assert unified.pos == "NOUN"
    # spaCy should provide morphology
    assert isinstance(unified.morph, dict)


def test_token_to_unified_stop_word(sample_doc):
    """Test stop word marking."""
    token = sample_doc[0]  # "The" (stop word)
    unified = token_to_unified(token, sentence_start_char=0, token_idx=0)

    assert unified.is_stop == True
    assert unified.text == "The"


def test_token_to_unified_punctuation(sample_doc):
    """Test punctuation marking."""
    token = sample_doc[-1]  # "." (punctuation)
    unified = token_to_unified(token, sentence_start_char=0, token_idx=6)

    assert unified.is_punct == True


# ============================================================================
# Sentence transformation tests
# ============================================================================

def test_sentence_to_unified_basic(sample_sent):
    """Test basic sentence transformation."""
    unified_sent = sentence_to_unified(sample_sent, sent_idx=0, doc_start_char=0)

    assert unified_sent.text == "The cat sat on the mat."
    assert unified_sent.idx == 0
    assert len(unified_sent.tokens) == 7
    assert len(unified_sent.dependencies) > 0
    assert unified_sent.root_idx is not None


def test_sentence_to_unified_tokens(sample_sent):
    """Test that all tokens are converted."""
    unified_sent = sentence_to_unified(sample_sent, sent_idx=0, doc_start_char=0)

    token_texts = [t.text for t in unified_sent.tokens]
    expected_texts = ["The", "cat", "sat", "on", "the", "mat", "."]

    assert token_texts == expected_texts


def test_sentence_to_unified_dependencies(sample_sent):
    """Test that dependencies are extracted."""
    unified_sent = sentence_to_unified(sample_sent, sent_idx=0, doc_start_char=0)

    assert len(unified_sent.dependencies) > 0

    # Check that dependencies have required fields
    for dep in unified_sent.dependencies:
        assert dep.head_idx >= 0
        assert dep.dependent_idx >= 0
        assert dep.relation is not None


# ============================================================================
# Document transformation tests
# ============================================================================

def test_document_to_unified_basic(spacy_model):
    """Test basic document transformation."""
    spacy_doc = spacy_model("Hello world. How are you?")
    unified_doc = document_to_unified(spacy_doc)

    assert unified_doc.text == "Hello world. How are you?"
    assert len(unified_doc.sentences) == 2
    assert LinguisticLevel.TOKENIZATION in unified_doc.processed_levels
    assert LinguisticLevel.MORPHOLOGY in unified_doc.processed_levels
    assert LinguisticLevel.SYNTAX in unified_doc.processed_levels


def test_document_to_unified_multiple_sentences(spacy_model):
    """Test multi-sentence document."""
    spacy_doc = spacy_model("First sentence. Second sentence. Third sentence.")
    unified_doc = document_to_unified(spacy_doc)

    assert len(unified_doc.sentences) == 3
    assert unified_doc.sentences[0].text == "First sentence."
    assert unified_doc.sentences[1].text == "Second sentence."
    assert unified_doc.sentences[2].text == "Third sentence."


def test_document_to_unified_with_entities(spacy_model):
    """Test entity extraction."""
    spacy_doc = spacy_model("Apple released a new iPhone.")
    unified_doc = document_to_unified(spacy_doc)

    # Should have at least one entity (Apple or iPhone)
    all_entities = sum(len(s.entities) for s in unified_doc.sentences)
    assert all_entities > 0


def test_document_to_unified_doc_id(spacy_model):
    """Test custom doc_id."""
    spacy_doc = spacy_model("Test text.")
    custom_id = "custom-doc-123"
    unified_doc = document_to_unified(spacy_doc, doc_id=custom_id)

    assert unified_doc.doc_id == custom_id


def test_document_to_unified_auto_doc_id(spacy_model):
    """Test auto-generated doc_id."""
    spacy_doc = spacy_model("Test text.")
    unified_doc = document_to_unified(spacy_doc)

    assert unified_doc.doc_id is not None
    assert len(unified_doc.doc_id) > 0


# ============================================================================
# Integration tests for full pipeline
# ============================================================================

def test_full_pipeline_sentence_to_document(spacy_model):
    """Test full pipeline from sentence to document."""
    text = "The quick brown fox jumps over the lazy dog."
    spacy_doc = spacy_model(text)
    unified_doc = document_to_unified(spacy_doc)

    # Verify complete structure
    assert len(unified_doc.sentences) == 1
    assert len(unified_doc.sentences[0].tokens) == 9
    assert len(unified_doc.sentences[0].dependencies) > 0
    assert unified_doc.sentences[0].root_idx is not None


def test_token_indices_consistent(spacy_model):
    """Test that token indices are consistent throughout."""
    text = "The cat sat."
    spacy_doc = spacy_model(text)
    unified_doc = document_to_unified(spacy_doc)

    sentence = unified_doc.sentences[0]

    # Check token indices
    for i, token in enumerate(sentence.tokens):
        assert token.idx == i

    # Check dependencies reference valid token indices
    for dep in sentence.dependencies:
        assert 0 <= dep.head_idx < len(sentence.tokens)
        assert 0 <= dep.dependent_idx < len(sentence.tokens)
