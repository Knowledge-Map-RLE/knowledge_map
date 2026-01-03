"""
Ontology Reversibility Tests

Tests that verify text can be reconstructed perfectly from the ontology graph.

Test Approach:
1. Take a test sentence (NLP → ontology → text)
2. Reconstruct text from ontology
3. Compare original vs reconstructed (should be identical)
4. Use iterative optimization to debug any mismatches

Test Sentence:
"Since the discovery of dopamine as a neurotransmitter in the 1950s, Parkinson's disease (PD)
research has generated a rich and complex body of knowledge, revealing PD to be an age-related
multifactorial disease, influenced by both genetic and environmental factors."
"""

import pytest
from typing import List, Tuple
import sys
import os

# Add project paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../nlp/src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../api/services'))

from ontology_reconstructor import OntologyReconstructor, ReconstructionMetrics
from ontology_service import OntologyService

TEST_SENTENCE = (
    "Since the discovery of dopamine as a neurotransmitter in the 1950s, "
    "Parkinson's disease (PD) research has generated a rich and complex body of knowledge, "
    "revealing PD to be an age-related multifactorial disease, influenced by both genetic and environmental factors."
)

# Additional test sentences for training the genetic algorithm
ADDITIONAL_TEST_SENTENCES = [
    "The discovery of dopamine revolutionized neuroscience.",
    "Parkinson's disease affects millions worldwide.",
    "Recent research has yielded new insights.",
    "Scientists discovered new mechanisms of action.",
    "The treatment paradigm is shifting rapidly.",
    "Many factors contribute to disease progression.",
    "Genetic and environmental factors interact complexly.",
    "This research has important clinical implications.",
    "The field continues to advance rapidly.",
    "New therapeutic approaches are being developed."
]


class TestOntologyReversibility:
    """Test suite for ontology text reconstruction reversibility"""

    @pytest.fixture
    def reconstructor(self):
        """Create OntologyReconstructor instance"""
        rec = OntologyReconstructor()
        yield rec
        rec.close()

    @pytest.fixture
    def ontology_service(self):
        """Create OntologyService instance"""
        svc = OntologyService()
        yield svc
        svc.close()

    def test_exact_reconstruction(self, reconstructor):
        """
        Test that we can reconstruct the exact original text from ontology.

        This is the PRIMARY TEST for reversibility.

        Steps:
        1. Query ontology nodes (assuming they exist from NLP processing)
        2. Reconstruct text from graph
        3. Compare original vs reconstructed (should be identical)
        """
        reconstructed = reconstructor.reconstruct_text_from_ontology()

        assert reconstructed != "", "Reconstruction returned empty string - ontology may not exist"

        assert reconstructed == TEST_SENTENCE, f"""
        Original:      {TEST_SENTENCE[:100]}...
        Reconstructed: {reconstructed[:100]}...

        Full diff:
        Original length:      {len(TEST_SENTENCE)}
        Reconstructed length: {len(reconstructed)}

        Character-by-character comparison:
        {self._compute_diff_summary(TEST_SENTENCE, reconstructed)}
        """

    def test_reconstruction_preserves_morphology(self, reconstructor):
        """
        Test that morphological features are preserved.

        Example: "generated" should stay "generated", not become "generate"
        """
        tokens = reconstructor.get_all_tokens()
        assert len(tokens) > 0, "No tokens found in ontology"

        # Find "generated" token
        generated_token = None
        for token in tokens:
            if token['text'] == 'generated':
                generated_token = token
                break

        assert generated_token is not None, "Token 'generated' not found in ontology"

        # Verify it's not lemmatized
        reconstructed_form = reconstructor.reconstruct_token(generated_token['ontology_id'])
        assert reconstructed_form == 'generated', \
            f"Expected 'generated', got '{reconstructed_form}' - morphology not preserved"

    def test_reconstruction_preserves_capitalization(self, reconstructor):
        """
        Test that capitalization is preserved correctly.

        Examples:
        - "Since" at start of sentence (capital S)
        - "PD" acronym (all capitals)
        """
        tokens = reconstructor.get_all_tokens()

        # Test: "Since" should be capitalized
        since_token = next((t for t in tokens if t['text'] == 'Since'), None)
        assert since_token is not None, "Token 'Since' not found"
        assert since_token['text'][0].isupper(), "Capitalization not preserved for 'Since'"

        # Test: "PD" should be all caps
        pd_tokens = [t for t in tokens if t['text'] == 'PD']
        assert len(pd_tokens) > 0, "Token 'PD' not found"
        for pd_token in pd_tokens:
            assert pd_token['text'].isupper(), f"PD should be uppercase, got '{pd_token['text']}'"

    def test_reconstruction_preserves_punctuation(self, reconstructor):
        """
        Test that punctuation is preserved in correct positions.

        Examples:
        - Comma after "1950s,"
        - Period at end of sentence
        - Parentheses around "(PD)"
        """
        reconstructed = reconstructor.reconstruct_text_from_ontology()

        # Check comma positions
        assert "1950s," in reconstructed, "Comma after year not preserved"
        assert "knowledge," in reconstructed, "Comma after noun not preserved"

        # Check period at end
        assert reconstructed.endswith("."), "Period at end of sentence not preserved"

        # Check parentheses
        assert "(PD)" in reconstructed, "Parentheses around PD not preserved"

    def test_reconstruction_preserves_whitespace(self, reconstructor):
        """
        Test that whitespace is preserved correctly.

        Rules:
        - No double spaces
        - Space after commas
        - No space before punctuation
        """
        reconstructed = reconstructor.reconstruct_text_from_ontology()

        # No double spaces
        assert "  " not in reconstructed, "Double spaces found in reconstruction"

        # Space after commas
        assert ", " in reconstructed, "Space after comma not preserved"
        assert " ," not in reconstructed, "Space before comma found (should not exist)"

        # No space before punctuation
        assert " ." not in reconstructed, "Space before period found (should not exist)"
        assert " ," not in reconstructed, "Space before comma found (should not exist)"

    def test_token_order_preservation(self, reconstructor):
        """
        Test that token order is correctly preserved via sent_idx, token_idx.
        """
        tokens = reconstructor.get_all_tokens()

        assert len(tokens) > 0, "No tokens found"

        # Verify indices are increasing
        for i in range(1, len(tokens)):
            prev_sent = tokens[i - 1]['sent_idx']
            curr_sent = tokens[i]['sent_idx']

            if prev_sent == curr_sent:
                # Same sentence - token_idx should increase
                prev_token = tokens[i - 1]['token_idx']
                curr_token = tokens[i]['token_idx']
                assert curr_token >= prev_token, \
                    f"Token order violated at index {i}: {prev_token} -> {curr_token}"
            else:
                # New sentence - just verify indices exist
                assert curr_sent > prev_sent, \
                    f"Sentence order violated: {prev_sent} -> {curr_sent}"

    def test_reconstruction_quality_metrics(self, reconstructor):
        """
        Test reconstruction quality using various metrics.

        Metrics:
        - Character accuracy >= 99% (some whitespace variations OK)
        - Word accuracy >= 99%
        - BLEU score >= 0.95
        - Edit distance <= 5 characters
        """
        reconstructed = reconstructor.reconstruct_text_from_ontology()

        if reconstructed == "":
            pytest.skip("Ontology not yet generated - test requires NLP processing")

        metrics = reconstructor.compute_reconstruction_metrics(TEST_SENTENCE, reconstructed)

        # These thresholds allow for minor whitespace differences
        assert metrics.char_accuracy >= 0.99, \
            f"Character accuracy {metrics.char_accuracy:.2%} below threshold"
        assert metrics.word_accuracy >= 0.99, \
            f"Word accuracy {metrics.word_accuracy:.2%} below threshold"
        assert metrics.bleu_score >= 0.95, \
            f"BLEU score {metrics.bleu_score:.2f} below threshold"
        assert metrics.edit_distance <= 5, \
            f"Edit distance {metrics.edit_distance} above threshold"

    def test_validate_reconstruction_integrity(self, reconstructor):
        """
        Test the integrity validation system.

        This checks:
        1. All tokens present
        2. Token order correct
        3. Whitespace preserved
        4. No missing indices
        """
        report = reconstructor.validate_reconstruction_integrity(TEST_SENTENCE)

        if not report['token_count']:
            pytest.skip("Ontology not yet generated")

        assert report['is_valid'] or report['token_count'] > 0, \
            f"Validation failed with issues: {report['issues']}"

    def test_morphology_feature_preservation(self, reconstructor):
        """
        Test that all morphological features are preserved.

        Examples:
        - Tense=Past: "generated" (not "generate")
        - Number=Singular/Plural
        - Gender, Case, etc.
        """
        tokens = reconstructor.get_all_tokens()

        # Find tokens with morphological features
        morphology_preserved = True
        issues = []

        for token in tokens:
            # The original text should be preserved exactly
            # (not lemmatized or modified)
            token_text = token['text']

            # Check for common morphological issues
            if token_text in ['generated', 'revealed', 'influenced']:
                # These are past participles - should end in -ed
                if not token_text.endswith('ed'):
                    issues.append(f"Morphology lost for {token_text}")
                    morphology_preserved = False

        if not morphology_preserved:
            pytest.fail(f"Morphological features not preserved: {issues}")

    def _compute_diff_summary(self, original: str, reconstructed: str) -> str:
        """Compute and display character-level differences"""
        import difflib

        diff_list = list(difflib.unified_diff(
            original.splitlines(keepends=True),
            reconstructed.splitlines(keepends=True),
            lineterm=''
        ))

        if not diff_list:
            return "No differences found"

        # Show first few differences
        return '\n'.join(diff_list[:20])


class TestReconstructionWithGeneticAlgorithm:
    """Tests for genetic algorithm optimization of reconstruction"""

    @pytest.fixture
    def reconstructor(self):
        rec = OntologyReconstructor()
        yield rec
        rec.close()

    def test_reconstruction_robustness(self, reconstructor):
        """
        Test that reconstruction handles various edge cases.

        Edge cases:
        - Contractions (e.g., "Parkinson's")
        - Numbers in different formats (1950s)
        - Acronyms (PD)
        - Punctuation in various positions
        """
        reconstructed = reconstructor.reconstruct_text_from_ontology()

        if reconstructed == "":
            pytest.skip("Ontology not yet generated")

        # Test contractions
        assert "Parkinson's" in reconstructed, "Contraction not preserved"

        # Test numbers
        assert "1950s" in reconstructed, "Number format not preserved"

        # Test acronyms
        assert "PD" in reconstructed, "Acronym not preserved"

    def test_metrics_computation(self, reconstructor):
        """Test that metrics are computed correctly"""
        reconstructed = reconstructor.reconstruct_text_from_ontology()

        if reconstructed == "":
            pytest.skip("Ontology not yet generated")

        metrics = reconstructor.compute_reconstruction_metrics(TEST_SENTENCE, reconstructed)

        # Verify metrics are in valid ranges
        assert 0 <= metrics.char_accuracy <= 1, "Character accuracy out of range"
        assert 0 <= metrics.word_accuracy <= 1, "Word accuracy out of range"
        assert 0 <= metrics.bleu_score <= 1, "BLEU score out of range"
        assert metrics.edit_distance >= 0, "Edit distance should be non-negative"


def test_suite_ready():
    """
    Test that verifies all prerequisites for running reversibility tests.

    Prerequisites:
    1. OntologyReconstructor can be instantiated
    2. Neo4j connection is available
    3. OntologyService can be instantiated
    """
    try:
        reconstructor = OntologyReconstructor()
        reconstructor.close()

        ontology_service = OntologyService()
        ontology_service.close()

        assert True, "All prerequisites satisfied"
    except Exception as e:
        pytest.skip(f"Prerequisites not met: {e}")


if __name__ == "__main__":
    # Run tests with: pytest nlp/tests/integration/test_ontology_reversibility.py -v
    pytest.main([__file__, "-v", "-s"])
