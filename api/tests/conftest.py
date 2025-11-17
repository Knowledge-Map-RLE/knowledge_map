"""
Pytest configuration and shared fixtures for dataset-based testing.

This module provides:
- Dataset loading fixtures
- Neo4j test fixtures
- S3 mock fixtures
- Common test utilities
"""

import asyncio
import json
import pytest
from pathlib import Path
from typing import Dict, Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

# Test configuration
# Datasets are stored outside tests directory in data/datasets (managed by DVC)
API_ROOT = Path(__file__).parent.parent  # api/
PROJECT_ROOT = API_ROOT.parent  # Knowledge_Map/
DATASETS_DIR = PROJECT_ROOT / "data" / "datasets"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ============================================================================
# Pytest Configuration
# ============================================================================

def pytest_configure(config):
    """Configure pytest environment"""
    config.addinivalue_line(
        "markers", "dataset: mark test as using dataset fixtures"
    )


# ============================================================================
# Event Loop Fixture (for async tests)
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the entire test session"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Dataset Loading Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def datasets_root() -> Path:
    """Root directory for test datasets"""
    return DATASETS_DIR


@pytest.fixture
def dataset_loader(datasets_root: Path):
    """
    Load dataset files from the datasets directory.

    Usage:
        # Load document metadata
        metadata = dataset_loader("sample_001", "documents/metadata.json")

        # Load markdown content
        markdown = dataset_loader("sample_001", "documents/document.md", as_text=True)

        # Load annotations
        annotations = dataset_loader("sample_001", "annotations/linguistic.json")
    """
    def _loader(
        sample_id: str,
        resource_path: str = None,
        as_text: bool = None
    ) -> Any:
        """
        Load a dataset resource.

        Args:
            sample_id: Sample identifier (e.g., "sample_001")
            resource_path: Relative path to resource within sample
            as_text: If True, return raw text instead of parsed JSON

        Returns:
            Loaded resource (dict for JSON, str for text)
        """
        if resource_path is None:
            # Return the sample directory path
            return datasets_root / sample_id

        # Construct full path
        if resource_path.startswith(("documents/", "annotations/", "expected/")):
            # Path already includes category
            full_path = datasets_root / resource_path.replace(f"{sample_id}/", f"{sample_id}/", 1)
            if sample_id not in resource_path:
                # Insert sample_id if not present
                parts = resource_path.split("/", 1)
                full_path = datasets_root / parts[0] / sample_id / parts[1]
        else:
            # Assume it's relative to sample
            full_path = datasets_root / "documents" / sample_id / resource_path

        if not full_path.exists():
            raise FileNotFoundError(f"Dataset resource not found: {full_path}")

        # Auto-detect format if not specified
        if as_text is None:
            as_text = full_path.suffix not in [".json"]

        if as_text:
            return full_path.read_text(encoding="utf-8")
        else:
            with open(full_path, "r", encoding="utf-8") as f:
                return json.load(f)

    return _loader


@pytest.fixture
def load_document_dataset(dataset_loader):
    """
    Load a complete document dataset (metadata, markdown, PDF path).

    Returns:
        Dict with keys: doc_id, metadata, markdown, pdf_path
    """
    def _load(sample_id: str) -> Dict[str, Any]:
        sample_dir = dataset_loader(sample_id)
        doc_dir = DATASETS_DIR / "documents" / sample_id

        # Load metadata
        metadata_path = doc_dir / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}

        # Load markdown
        md_path = doc_dir / "document.md"
        markdown = md_path.read_text(encoding="utf-8") if md_path.exists() else None

        # Get PDF path
        pdf_path = doc_dir / "document.pdf"

        return {
            "doc_id": metadata.get("doc_id", sample_id),
            "metadata": metadata,
            "markdown": markdown,
            "pdf_path": str(pdf_path) if pdf_path.exists() else None,
            "sample_dir": str(sample_dir)
        }

    return _load


@pytest.fixture
def load_annotations_dataset(dataset_loader):
    """
    Load annotations dataset for a sample.

    Returns:
        Dict with keys: linguistic, relations, chains, patterns
    """
    def _load(sample_id: str) -> Dict[str, Any]:
        ann_dir = DATASETS_DIR / "annotations" / sample_id

        result = {}

        # Load linguistic annotations
        ling_path = ann_dir / "linguistic.json"
        if ling_path.exists():
            result["linguistic"] = json.loads(ling_path.read_text(encoding="utf-8"))

        # Load relations
        rel_path = ann_dir / "relations.json"
        if rel_path.exists():
            result["relations"] = json.loads(rel_path.read_text(encoding="utf-8"))

        # Load chains
        chains_path = ann_dir / "chains.json"
        if chains_path.exists():
            result["chains"] = json.loads(chains_path.read_text(encoding="utf-8"))

        # Load patterns
        patterns_path = ann_dir / "patterns.json"
        if patterns_path.exists():
            result["patterns"] = json.loads(patterns_path.read_text(encoding="utf-8"))

        return result

    return _load


@pytest.fixture
def load_expected_results(dataset_loader):
    """
    Load expected results for a sample.

    Returns:
        Dict with keys: nlp_analysis, patterns, action_chains
    """
    def _load(sample_id: str) -> Dict[str, Any]:
        exp_dir = DATASETS_DIR / "expected" / sample_id

        result = {}

        # Load NLP analysis results
        nlp_path = exp_dir / "nlp_analysis.json"
        if nlp_path.exists():
            result["nlp_analysis"] = json.loads(nlp_path.read_text(encoding="utf-8"))

        # Load patterns
        patterns_path = exp_dir / "patterns.json"
        if patterns_path.exists():
            result["patterns"] = json.loads(patterns_path.read_text(encoding="utf-8"))

        # Load action chains
        chains_path = exp_dir / "action_chains.json"
        if chains_path.exists():
            result["action_chains"] = json.loads(chains_path.read_text(encoding="utf-8"))

        return result

    return _load


# ============================================================================
# Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_s3_client():
    """Mock S3 client for testing without actual S3 connection"""
    mock_client = MagicMock()

    # Mock common S3 operations
    mock_client.object_exists = AsyncMock(return_value=True)
    mock_client.upload_bytes = AsyncMock(return_value=True)
    mock_client.download_bytes = AsyncMock(return_value=b"mock data")
    mock_client.download_text = AsyncMock(return_value="mock text")
    mock_client.list_objects = AsyncMock(return_value=[])
    mock_client.delete_object = AsyncMock(return_value=True)
    mock_client.get_object_url = AsyncMock(return_value="http://mock.s3.url/object")

    return mock_client


@pytest.fixture
def mock_neo4j_connection():
    """Mock Neo4j connection for testing without actual database"""
    mock_connection = MagicMock()

    # Mock common Neo4j operations
    mock_connection.cypher_query = MagicMock(return_value=([], []))

    return mock_connection


# ============================================================================
# Test Data Fixtures
# ============================================================================

@pytest.fixture
def sample_markdown_text():
    """Sample markdown text for testing"""
    return """# Тестовый документ

## Введение

Мы анализируем данные и извлекаем паттерны. Затем мы строим цепочки действий.

## Методы

Исследователи используют NLP для обработки текста. Система генерирует аннотации автоматически.

## Результаты

Алгоритм обнаружил важные закономерности. Эксперименты подтвердили гипотезу.
"""


@pytest.fixture
def sample_annotations():
    """Sample annotations for testing"""
    return {
        "annotations": [
            {
                "uid": "ann_001",
                "text": "анализируем",
                "annotation_type": "VERB",
                "start_offset": 45,
                "end_offset": 56,
                "confidence": 0.95,
                "metadata": {
                    "pos": "VERB",
                    "lemma": "анализировать",
                    "sent_idx": 1,
                    "token_idx": 2
                }
            },
            {
                "uid": "ann_002",
                "text": "данные",
                "annotation_type": "NOUN",
                "start_offset": 57,
                "end_offset": 63,
                "confidence": 0.92,
                "metadata": {
                    "pos": "NOUN",
                    "lemma": "данные",
                    "sent_idx": 1,
                    "token_idx": 3
                }
            }
        ]
    }


@pytest.fixture
def sample_relations():
    """Sample relations for testing"""
    return {
        "relations": [
            {
                "source_uid": "ann_001",
                "target_uid": "ann_002",
                "relation_type": "obj",
                "confidence": 0.90,
                "metadata": {
                    "dependency": "direct_object"
                }
            }
        ]
    }


# ============================================================================
# Utility Fixtures
# ============================================================================

@pytest.fixture
def assert_annotations_equal():
    """Utility for comparing annotations with tolerance"""
    def _compare(actual: Dict, expected: Dict, confidence_threshold: float = 0.05):
        """
        Compare two annotation dictionaries.

        Args:
            actual: Actual annotation result
            expected: Expected annotation result
            confidence_threshold: Tolerance for confidence comparison
        """
        assert actual["text"] == expected["text"], f"Text mismatch: {actual['text']} != {expected['text']}"
        assert actual["annotation_type"] == expected["annotation_type"]
        assert actual["start_offset"] == expected["start_offset"]
        assert actual["end_offset"] == expected["end_offset"]

        if "confidence" in expected:
            assert abs(actual.get("confidence", 0) - expected["confidence"]) <= confidence_threshold

    return _compare


@pytest.fixture
def assert_chains_equal():
    """Utility for comparing action chains"""
    def _compare(actual: Dict, expected: Dict, tolerance: float = 0.1):
        """
        Compare two action chain dictionaries.

        Args:
            actual: Actual chain result
            expected: Expected chain result
            tolerance: Tolerance for confidence comparison
        """
        assert actual["sequence_type"] == expected["sequence_type"]
        assert set(actual.get("verbs", [])) == set(expected.get("verbs", []))

        if "confidence" in expected:
            assert abs(actual.get("confidence", 0) - expected["confidence"]) <= tolerance

    return _compare


# ============================================================================
# Cleanup Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
async def cleanup_test_data():
    """Automatically cleanup test data after each test"""
    # Setup: nothing to do before test
    yield
    # Teardown: cleanup after test
    # Add cleanup logic here if needed
    pass
