"""
Tests for NLP router endpoints using dataset fixtures.

These tests verify:
- NLP text analysis
- Auto-annotation functionality
- Multi-level analysis with voting
- Annotation creation and validation
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

# Markers
pytestmark = [pytest.mark.nlp, pytest.mark.dataset]


class TestNLPAnalysis:
    """Tests for basic NLP analysis endpoints"""

    @pytest.mark.asyncio
    async def test_analyze_text_basic(self, sample_markdown_text):
        """Test basic text analysis without dataset"""
        from services.nlp_service import NLPService

        nlp_service = NLPService()
        result = nlp_service.analyze_text(sample_markdown_text)

        # Verify result structure
        assert "sentences" in result
        assert "tokens" in result
        assert len(result["sentences"]) > 0

    @pytest.mark.asyncio
    async def test_analyze_text_with_dataset(self, load_document_dataset):
        """Test NLP analysis using dataset markdown"""
        # Load dataset (skip if not available)
        try:
            doc_data = load_document_dataset("sample_001")
        except FileNotFoundError:
            pytest.skip("Dataset sample_001 not available")

        from services.nlp_service import NLPService

        nlp_service = NLPService()
        result = nlp_service.analyze_text(doc_data["markdown"])

        # Verify analysis results
        assert "sentences" in result
        assert "tokens" in result
        assert len(result["sentences"]) > 0

        # Verify linguistic features are extracted
        for token in result["tokens"]:
            assert "text" in token
            assert "pos" in token
            assert "lemma" in token

    @pytest.mark.asyncio
    async def test_analyze_selection(self, sample_markdown_text):
        """Test analysis of text selection"""
        from services.nlp_service import NLPService

        nlp_service = NLPService()

        # Select a fragment
        start = 0
        end = 50

        result = nlp_service.analyze_selection(sample_markdown_text, start, end)

        # Verify result
        assert "suggestions" in result or "tokens" in result

    def test_get_supported_types(self):
        """Test getting supported annotation types"""
        from services.nlp_service import NLPService

        nlp_service = NLPService()
        types = nlp_service.get_all_supported_types()

        # Verify structure
        assert isinstance(types, dict)
        assert "linguistic" in types or "entities" in types


class TestAutoAnnotation:
    """Tests for auto-annotation functionality"""

    @pytest.mark.asyncio
    @pytest.mark.requires_neo4j
    async def test_auto_annotate_with_mock(self, load_document_dataset, mock_s3_client):
        """Test auto-annotation with mocked dependencies"""
        # Skip if dataset not available
        try:
            doc_data = load_document_dataset("sample_001")
        except FileNotFoundError:
            pytest.skip("Dataset sample_001 not available")

        from services.annotation_service import AnnotationService
        from src.models import PDFDocument

        # Mock Neo4j document
        mock_document = MagicMock(spec=PDFDocument)
        mock_document.uid = doc_data["doc_id"]

        with patch("services.annotation_service.PDFDocument") as mock_pdf_class, \
             patch("services.annotation_service.get_s3_client", return_value=mock_s3_client):

            mock_pdf_class.nodes.get_or_none.return_value = mock_document
            mock_s3_client.object_exists.return_value = True
            mock_s3_client.download_text.return_value = doc_data["markdown"]

            annotation_service = AnnotationService()

            # This test verifies the structure, actual Neo4j interaction would require integration test
            # For now, we just verify the service can be instantiated
            assert annotation_service is not None


class TestMultiLevelAnalysis:
    """Tests for multi-level NLP analysis with voting"""

    @pytest.mark.asyncio
    async def test_multilevel_analysis_structure(self, sample_markdown_text):
        """Test multi-level analysis result structure"""
        from services.multilevel_nlp_service import MultiLevelNLPService

        multilevel_service = MultiLevelNLPService()

        # Analyze text
        doc = multilevel_service.analyze_text_to_document(
            text=sample_markdown_text,
            doc_id="test_doc",
            enable_voting=True,
            max_level=2
        )

        # Verify document structure
        assert doc is not None
        assert hasattr(doc, "sentences")
        assert len(doc.sentences) > 0

        # Verify tokens have linguistic features
        for sent in doc.sentences:
            assert hasattr(sent, "tokens")
            for token in sent.tokens:
                assert hasattr(token, "text")
                assert hasattr(token, "pos")

    @pytest.mark.asyncio
    async def test_multilevel_with_dataset(self, load_document_dataset, load_expected_results):
        """Test multi-level analysis against expected results"""
        # Skip if dataset not available
        try:
            doc_data = load_document_dataset("sample_001")
            expected = load_expected_results("sample_001")
        except FileNotFoundError:
            pytest.skip("Dataset sample_001 not available")

        if "nlp_analysis" not in expected:
            pytest.skip("Expected NLP analysis results not available")

        from services.multilevel_nlp_service import MultiLevelNLPService

        multilevel_service = MultiLevelNLPService()

        # Analyze
        doc = multilevel_service.analyze_text_to_document(
            text=doc_data["markdown"],
            doc_id=doc_data["doc_id"],
            enable_voting=True,
            max_level=3
        )

        # Compare with expected results (basic checks)
        expected_nlp = expected["nlp_analysis"]

        # Check sentence count (with tolerance for sentence boundary differences)
        if "sentence_count" in expected_nlp:
            actual_count = len(doc.sentences)
            expected_count = expected_nlp["sentence_count"]
            # Allow 10% tolerance for sentence detection differences
            tolerance = max(1, int(expected_count * 0.1))
            assert abs(actual_count - expected_count) <= tolerance, \
                f"Sentence count mismatch: expected ~{expected_count}, got {actual_count}"

    @pytest.mark.asyncio
    async def test_create_annotations_from_analysis(self, sample_markdown_text):
        """Test creating annotation data structures from analysis"""
        from services.multilevel_nlp_service import MultiLevelNLPService

        multilevel_service = MultiLevelNLPService()

        # Analyze
        doc = multilevel_service.analyze_text_to_document(
            text=sample_markdown_text,
            doc_id="test_doc",
            enable_voting=True,
            max_level=2
        )

        # Create annotation data
        annotations_data = multilevel_service.create_annotations_for_database(
            doc,
            confidence_threshold=0.7
        )

        # Verify structure
        assert isinstance(annotations_data, list)

        for ann_data in annotations_data:
            assert "text" in ann_data
            assert "annotation_type" in ann_data
            assert "start_offset" in ann_data
            assert "end_offset" in ann_data
            assert "confidence" in ann_data
            assert ann_data["confidence"] >= 0.7

    @pytest.mark.asyncio
    async def test_create_relations_from_analysis(self, sample_markdown_text):
        """Test creating relation data structures from analysis"""
        from services.multilevel_nlp_service import MultiLevelNLPService

        multilevel_service = MultiLevelNLPService()

        # Analyze
        doc = multilevel_service.analyze_text_to_document(
            text=sample_markdown_text,
            doc_id="test_doc",
            enable_voting=True,
            max_level=2
        )

        # Create mock annotation UID map
        annotation_uid_map = {}
        for sent_idx, sent in enumerate(doc.sentences):
            for token_idx, token in enumerate(sent.tokens):
                annotation_uid_map[(sent_idx, token_idx)] = f"ann_{sent_idx}_{token_idx}"

        # Create relations data
        relations_data = multilevel_service.create_relations_for_database(
            doc,
            annotation_uid_map,
            confidence_threshold=0.7
        )

        # Verify structure
        assert isinstance(relations_data, list)

        for rel_data in relations_data:
            assert "source_uid" in rel_data
            assert "target_uid" in rel_data
            assert "relation_type" in rel_data
            assert "confidence" in rel_data


class TestNLPDatasetComparison:
    """Tests that compare NLP results with ground truth datasets"""

    @pytest.mark.asyncio
    async def test_compare_annotations_with_dataset(
        self,
        load_document_dataset,
        load_annotations_dataset,
        assert_annotations_equal
    ):
        """Compare auto-generated annotations with dataset ground truth"""
        # Skip if dataset not available
        try:
            doc_data = load_document_dataset("sample_001")
            ann_data = load_annotations_dataset("sample_001")
        except FileNotFoundError:
            pytest.skip("Dataset sample_001 not available")

        if "linguistic" not in ann_data:
            pytest.skip("Linguistic annotations not available in dataset")

        from services.multilevel_nlp_service import MultiLevelNLPService

        multilevel_service = MultiLevelNLPService()

        # Analyze
        doc = multilevel_service.analyze_text_to_document(
            text=doc_data["markdown"],
            doc_id=doc_data["doc_id"],
            enable_voting=True,
            max_level=3
        )

        # Create annotations
        generated_annotations = multilevel_service.create_annotations_for_database(
            doc,
            confidence_threshold=0.0  # Include all for comparison
        )

        # Compare with dataset
        dataset_annotations = ann_data["linguistic"]["annotations"]

        # We can't expect exact match, but we can check coverage
        # Count how many dataset annotations are found in generated ones
        matches = 0
        for expected_ann in dataset_annotations:
            # Try to find matching annotation by text and type
            for generated_ann in generated_annotations:
                if (generated_ann["text"] == expected_ann["text"] and
                    generated_ann["annotation_type"] == expected_ann["annotation_type"]):
                    matches += 1
                    break

        # Calculate coverage (should be reasonably high)
        coverage = matches / len(dataset_annotations) if dataset_annotations else 0

        # We expect at least 70% coverage for basic linguistic features
        assert coverage >= 0.7, \
            f"Annotation coverage too low: {coverage:.1%} ({matches}/{len(dataset_annotations)})"
