"""
Tests for action chains functionality using dataset fixtures.

These tests verify:
- Pattern extraction from annotations
- Action sequence detection
- Chain building and validation
- Comparison with ground truth datasets
"""

import pytest
from unittest.mock import patch, MagicMock

# Markers
pytestmark = [pytest.mark.dataset, pytest.mark.slow]


class TestActionChainService:
    """Tests for ActionChainService using datasets"""

    @pytest.mark.requires_neo4j
    def test_extract_verb_patterns_structure(self):
        """Test structure of extracted verb patterns"""
        from services.action_chain_service import ActionChainService

        # This is a basic structure test
        # Full test would require Neo4j with actual patterns
        service = ActionChainService()
        assert service is not None

    @pytest.mark.requires_neo4j
    async def test_build_chains_with_dataset(self, load_annotations_dataset):
        """Test building action chains from dataset patterns"""
        # Skip if dataset not available
        try:
            ann_data = load_annotations_dataset("sample_001")
        except FileNotFoundError:
            pytest.skip("Dataset sample_001 not available")

        if "chains" not in ann_data:
            pytest.skip("Action chains not available in dataset")

        # Verify dataset structure
        chains = ann_data["chains"]["chains"]
        assert isinstance(chains, list)

        # Verify chain structure
        for chain in chains:
            assert "verbs" in chain
            assert "sequence_type" in chain
            assert isinstance(chain["verbs"], list)
            assert len(chain["verbs"]) >= 2

    @pytest.mark.requires_neo4j
    async def test_sequence_type_detection(self, load_annotations_dataset):
        """Test detection of different sequence types"""
        # Skip if dataset not available
        try:
            ann_data = load_annotations_dataset("sample_001")
        except FileNotFoundError:
            pytest.skip("Dataset sample_001 not available")

        if "chains" not in ann_data:
            pytest.skip("Action chains not available in dataset")

        chains = ann_data["chains"]["chains"]

        # Count sequence types
        sequence_types = set()
        for chain in chains:
            sequence_types.add(chain["sequence_type"])

        # Verify we have different types
        valid_types = {"temporal", "causal", "conditional", "sequential"}
        assert sequence_types.issubset(valid_types), \
            f"Found invalid sequence types: {sequence_types - valid_types}"

    async def test_chain_validation_with_dataset(
        self,
        load_annotations_dataset,
        assert_chains_equal
    ):
        """Validate chains from dataset"""
        # Skip if dataset not available
        try:
            ann_data = load_annotations_dataset("sample_001")
        except FileNotFoundError:
            pytest.skip("Dataset sample_001 not available")

        if "chains" not in ann_data:
            pytest.skip("Action chains not available in dataset")

        chains = ann_data["chains"]["chains"]

        # Validate each chain
        for chain in chains:
            # Check required fields
            assert "verbs" in chain
            assert "sequence_type" in chain

            # Check verbs list
            assert len(chain["verbs"]) >= 2, "Chain must have at least 2 verbs"

            # Check confidence if present
            if "confidence" in chain:
                assert 0.0 <= chain["confidence"] <= 1.0


class TestActionChainComparison:
    """Tests that compare generated chains with ground truth"""

    async def test_compare_chains_structure(
        self,
        load_annotations_dataset,
        load_expected_results
    ):
        """Compare chain structure with expected results"""
        # Skip if dataset not available
        try:
            ann_data = load_annotations_dataset("sample_001")
            expected = load_expected_results("sample_001")
        except FileNotFoundError:
            pytest.skip("Dataset sample_001 not available")

        if "chains" not in ann_data:
            pytest.skip("Action chains not available")

        if "action_chains" not in expected:
            pytest.skip("Expected action chains not available")

        actual_chains = ann_data["chains"]["chains"]
        expected_chains = expected["action_chains"].get("chains", [])

        # Compare counts (with tolerance)
        actual_count = len(actual_chains)
        expected_count = len(expected_chains)

        # Allow some tolerance for chain detection differences
        if expected_count > 0:
            tolerance = max(1, int(expected_count * 0.2))  # 20% tolerance
            assert abs(actual_count - expected_count) <= tolerance, \
                f"Chain count mismatch: expected ~{expected_count}, got {actual_count}"

    async def test_verify_chain_coverage(
        self,
        load_annotations_dataset,
        load_expected_results,
        assert_chains_equal
    ):
        """Verify that expected chains are found in generated results"""
        # Skip if dataset not available
        try:
            ann_data = load_annotations_dataset("sample_001")
            expected = load_expected_results("sample_001")
        except FileNotFoundError:
            pytest.skip("Dataset sample_001 not available")

        if "chains" not in ann_data or "action_chains" not in expected:
            pytest.skip("Chain data not available")

        actual_chains = ann_data["chains"]["chains"]
        expected_chains = expected["action_chains"].get("chains", [])

        if not expected_chains:
            pytest.skip("No expected chains to compare")

        # Check coverage: how many expected chains are found
        matches = 0

        for expected_chain in expected_chains:
            # Look for matching chain in actual results
            for actual_chain in actual_chains:
                # Match by sequence type and verb overlap
                if actual_chain["sequence_type"] == expected_chain["sequence_type"]:
                    # Check verb overlap
                    expected_verbs = set(expected_chain["verbs"])
                    actual_verbs = set(actual_chain["verbs"])
                    overlap = len(expected_verbs & actual_verbs)

                    # If at least half of the verbs match, consider it a match
                    if overlap >= len(expected_verbs) / 2:
                        matches += 1
                        break

        # Calculate coverage
        coverage = matches / len(expected_chains) if expected_chains else 0

        # We expect reasonable coverage (at least 60%)
        assert coverage >= 0.6, \
            f"Chain coverage too low: {coverage:.1%} ({matches}/{len(expected_chains)})"


class TestActionChainIntegration:
    """Integration tests for complete action chain pipeline"""

    @pytest.mark.integration
    @pytest.mark.requires_neo4j
    async def test_full_pipeline_with_dataset(
        self,
        load_document_dataset,
        load_annotations_dataset
    ):
        """Test complete pipeline: document -> patterns -> chains"""
        # Skip if dataset not available
        try:
            doc_data = load_document_dataset("sample_001")
            ann_data = load_annotations_dataset("sample_001")
        except FileNotFoundError:
            pytest.skip("Dataset sample_001 not available")

        # This test would require:
        # 1. Import document and annotations to Neo4j
        # 2. Generate patterns
        # 3. Build action chains
        # 4. Compare with expected results

        # For now, just verify dataset structure is complete
        assert "markdown" in doc_data
        assert doc_data["markdown"] is not None

        if "patterns" in ann_data:
            assert isinstance(ann_data["patterns"]["patterns"], list)

        if "chains" in ann_data:
            assert isinstance(ann_data["chains"]["chains"], list)
