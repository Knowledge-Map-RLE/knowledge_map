"""Test configuration and fixtures"""

import pytest
import tempfile
import asyncio
import json
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any, List

from src.core.config import Settings
from src.core.types import ConversionResult, ConversionProgress, ConversionStatus
from src.services.conversion_service import ConversionService
from src.services.model_service import ModelService
from src.services.file_service import FileService


@pytest.fixture
def test_settings():
    """Test settings"""
    return Settings(
        service_name="test-pdf-to-md-service",
        debug=True,
        max_file_size_mb=10,
        conversion_timeout_seconds=60,
        temp_dir=Path(tempfile.gettempdir()) / "test_pdf_to_md",
        output_dir=Path(tempfile.gettempdir()) / "test_output"
    )


@pytest.fixture
def temp_dir():
    """Temporary directory for tests"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def sample_pdf_content():
    """Sample PDF content for testing"""
    # This is a minimal PDF content (just the header)
    return b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n174\n%%EOF'


@pytest.fixture
def mock_model():
    """Mock model for testing"""
    model = Mock()
    model.name = "Test Model"
    model.description = "Test model for unit tests"
    model.version = "1.0.0"
    model.is_enabled = True
    model.capabilities = ["pdf_to_markdown"]
    model.convert = AsyncMock()
    model.validate_input = Mock(return_value=True)
    return model


@pytest.fixture
def mock_conversion_service(mock_model_service, mock_file_service):
    """Mock conversion service"""
    service = Mock(spec=ConversionService)
    service.model_service = mock_model_service
    service.file_service = mock_file_service
    service.convert_pdf = AsyncMock()
    service.get_active_conversions = Mock(return_value={})
    service.cancel_conversion = AsyncMock(return_value=True)
    service.get_conversion_status = AsyncMock(return_value=None)
    return service


@pytest.fixture
def mock_model_service():
    """Mock model service"""
    service = Mock(spec=ModelService)
    service.get_model = Mock()
    service.get_available_models = Mock(return_value={})
    service.get_default_model = Mock(return_value="test_model")
    service.set_default_model = Mock(return_value=True)
    service.enable_model = Mock(return_value=True)
    service.disable_model = Mock(return_value=True)
    return service


@pytest.fixture
def mock_file_service():
    """Mock file service"""
    service = Mock(spec=FileService)
    service.create_temp_directory = Mock()
    service.save_pdf = Mock()
    service.save_markdown = Mock()
    service.save_images = Mock(return_value=[])
    service.save_metadata = Mock()
    service.cleanup_temp_directory = Mock()
    return service


@pytest.fixture
def sample_markdown_content():
    """Sample markdown content for testing"""
    return """# Test Document

This is a test document converted from PDF.

## Section 1

Some content here.

### Subsection

More content.

## Section 2

- Item 1
- Item 2
- Item 3

**Bold text** and *italic text*.

[Link](https://example.com)

```python
def hello():
    print("Hello, World!")
```

> This is a quote.

---

End of document.
"""


@pytest.fixture
def sample_images():
    """Sample image data for testing"""
    return {
        "image1.jpg": b"fake_jpeg_data_1",
        "image2.png": b"fake_png_data_2",
        "diagram.svg": b"fake_svg_data_3"
    }


@pytest.fixture
def sample_metadata():
    """Sample metadata for testing"""
    return {
        "pages_processed": 5,
        "processing_time": 12.5,
        "throughput": 0.4,
        "file_size_mb": 2.1,
        "images_count": 3,
        "model_used": "marker",
        "conversion_date": "2024-01-15T10:30:00Z"
    }


@pytest.fixture
def sample_conversion_result(sample_markdown_content, sample_images, sample_metadata):
    """Sample conversion result"""
    return ConversionResult(
        success=True,
        doc_id="test_doc_123",
        markdown_content=sample_markdown_content,
        images=sample_images,
        metadata=sample_metadata,
        processing_time=12.5
    )


@pytest.fixture
def sample_conversion_progress():
    """Sample conversion progress"""
    return ConversionProgress(
        doc_id="test_doc_123",
        status=ConversionStatus.PROCESSING,
        percent=75,
        phase="processing_pages",
        message="Processing page 3 of 4",
        pages_processed=3,
        total_pages=4,
        processing_time=8.5,
        throughput=0.35
    )


@pytest.fixture
def real_pdf_file(temp_dir):
    """Create a real PDF file for integration tests"""
    # Create a minimal valid PDF file
    pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
72 720 Td
(Hello World) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000200 00000 n 
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
294
%%EOF"""
    
    pdf_path = temp_dir / "test_document.pdf"
    pdf_path.write_bytes(pdf_content)
    return pdf_path


@pytest.fixture
def large_pdf_content():
    """Large PDF content for testing file size limits"""
    # Create content larger than 10MB for testing
    header = b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n'
    footer = b'xref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \ntrailer\n<<\n/Size 3\n/Root 1 0 R\n>>\nstartxref\n100\n%%EOF'
    
    # Add content to make it large
    large_content = b'x' * (11 * 1024 * 1024)  # 11MB
    return header + large_content + footer


@pytest.fixture
def invalid_pdf_content():
    """Invalid PDF content for testing error handling"""
    return b"This is not a PDF file content"


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_progress_callback():
    """Mock progress callback for testing"""
    progress_updates = []
    
    def callback(progress: ConversionProgress):
        progress_updates.append(progress)
    
    callback.updates = progress_updates
    return callback


@pytest.fixture
def mock_file_upload():
    """Mock file upload for API testing"""
    class MockUploadFile:
        def __init__(self, content: bytes, filename: str, content_type: str = "application/pdf"):
            self.content = content
            self.filename = filename
            self.content_type = content_type
        
        async def read(self):
            return self.content
    
    return MockUploadFile


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "api: mark test as API test"
    )
    config.addinivalue_line(
        "markers", "grpc: mark test as gRPC test"
    )


# Test data generators
@pytest.fixture
def generate_test_pdfs(temp_dir):
    """Generate multiple test PDF files"""
    pdfs = []
    for i in range(3):
        content = f"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 50
>>
stream
BT
/F1 12 Tf
72 720 Td
(Test Document {i+1}) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000200 00000 n 
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
300
%%EOF""".encode()
        
        pdf_path = temp_dir / f"test_document_{i+1}.pdf"
        pdf_path.write_bytes(content)
        pdfs.append(pdf_path)
    
    return pdfs
