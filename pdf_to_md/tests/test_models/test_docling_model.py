"""Tests for Docling model image extraction functionality"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
import io
from PIL import Image
import uuid

try:
    from src.services.models.docling_model import DoclingModel
except ImportError:
    from pdf_to_md.src.services.models.docling_model import DoclingModel


class TestDoclingModelImageExtraction:
    """Test Docling model image extraction capabilities"""
    
    @pytest.fixture
    def docling_model(self):
        """Create Docling model for testing"""
        return DoclingModel()
    
    @pytest.fixture
    def mock_pil_image(self):
        """Create mock PIL Image"""
        image = Mock()
        image.format = "PNG"
        image.mode = "RGB"
        image.save = Mock()
        return image
    
    @pytest.fixture
    def mock_document_result(self, mock_pil_image):
        """Create mock document result with pictures"""
        result = Mock()
        
        # Create mock picture objects
        picture1 = Mock()
        picture1.image = mock_pil_image
        
        picture2 = Mock()
        picture2.image = mock_pil_image
        
        result.pictures = [picture1, picture2]
        result.render_as_markdown = Mock(return_value="# Test Document\n![image](test.png)")
        
        return result
    
    @pytest.fixture
    def mock_s3_client(self):
        """Create mock S3 client"""
        client = AsyncMock()
        client.upload_bytes = AsyncMock(return_value=True)
        client.get_object_url = AsyncMock(return_value="https://example.com/presigned-url")
        return client
    
    def test_detect_image_format(self, docling_model, mock_pil_image):
        """Test image format detection"""
        mock_pil_image.format = "JPEG"
        result = docling_model._detect_image_format(mock_pil_image)
        assert result == "jpeg"
        
        mock_pil_image.format = "PNG"
        result = docling_model._detect_image_format(mock_pil_image)
        assert result == "png"
        
        # Test unknown format
        mock_pil_image.format = None
        result = docling_model._detect_image_format(mock_pil_image)
        assert result == "png"  # Default
    
    def test_image_to_bytes(self, docling_model):
        """Test PIL Image to bytes conversion"""
        # Create a simple test image
        image = Image.new('RGB', (100, 100), color='red')
        
        result = docling_model._image_to_bytes(image, 'png')
        assert isinstance(result, bytes)
        assert len(result) > 0
        
        # Test JPEG conversion
        result = docling_model._image_to_bytes(image, 'jpeg')
        assert isinstance(result, bytes)
        assert len(result) > 0
    
    def test_image_to_bytes_rgba_to_rgb(self, docling_model):
        """Test RGBA to RGB conversion for JPEG"""
        # Create RGBA image
        image = Image.new('RGBA', (100, 100), color=(255, 0, 0, 128))
        
        result = docling_model._image_to_bytes(image, 'jpeg')
        assert isinstance(result, bytes)
        assert len(result) > 0
    
    @pytest.mark.asyncio
    async def test_extract_and_save_images_no_pictures(self, docling_model):
        """Test image extraction when no pictures are present"""
        mock_result = Mock()
        mock_result.pictures = []
        
        output_dir = Path("/tmp/test")
        doc_id = "test-doc"
        
        result = await docling_model._extract_and_save_images(
            mock_result, output_dir, doc_id
        )
        
        assert result == []
    
    @pytest.mark.asyncio
    async def test_extract_and_save_images_with_pictures(self, docling_model, mock_document_result, mock_s3_client):
        """Test image extraction with pictures"""
        output_dir = Path("/tmp/test")
        output_dir.mkdir(parents=True, exist_ok=True)
        doc_id = "test-doc"
        
        # Mock S3 client and settings
        with patch.object(docling_model, 's3_client', mock_s3_client), \
             patch('src.services.models.docling_model.settings') as mock_settings:
            
            mock_settings.s3_bucket_name = "test-bucket"
            
            # Mock uuid generation for consistent testing
            with patch('src.services.models.docling_model.uuid.uuid4') as mock_uuid:
                mock_uuid.side_effect = [
                    Mock(__str__=lambda x: "image-uuid-1"),
                    Mock(__str__=lambda x: "image-uuid-2")
                ]
                
                result = await docling_model._extract_and_save_images(
                    mock_document_result, output_dir, doc_id
                )
        
        assert len(result) == 2
        assert all(isinstance(item, tuple) for item in result)
        assert all(len(item) == 2 for item in result)
        
        # Verify S3 upload was called
        assert mock_s3_client.upload_bytes.call_count == 2
    
    def test_update_image_references(self, docling_model):
        """Test image reference updating in markdown"""
        markdown = "# Test\n![Image 1](image1.png)\nSome text\n![Image 2](image2.jpg)"
        image_files = [("image1.png", "image1.png"), ("image2.jpg", "image2.jpg")]
        doc_id = "test-doc"
        
        result = docling_model._update_image_references(markdown, image_files, doc_id)
        
        # For now, we expect the markdown to remain unchanged
        # as the method leaves references as-is for frontend handling
        assert result == markdown
    
    def test_update_image_references_no_images(self, docling_model):
        """Test image reference updating with no images"""
        markdown = "# Test\nNo images here"
        image_files = []
        doc_id = "test-doc"
        
        result = docling_model._update_image_references(markdown, image_files, doc_id)
        assert result == markdown
    
    @pytest.mark.asyncio
    async def test_convert_with_images(self, docling_model, tmp_path):
        """Test PDF conversion with image extraction"""
        # Create test PDF path
        input_path = tmp_path / "test.pdf"
        input_path.write_bytes(b"fake pdf content")
        
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        # Mock Docling components
        with patch('src.services.models.docling_model.DocumentConverter') as mock_converter_class, \
             patch('src.services.models.docling_model.DocumentConversionInput') as mock_input_class:
            
            # Setup mocks
            mock_converter = Mock()
            mock_converter_class.return_value = mock_converter
            
            mock_input = Mock()
            mock_input_class.from_paths.return_value = mock_input
            
            # Create mock result with images
            mock_result = Mock()
            mock_result.render_as_markdown.return_value = "# Test Document"
            mock_result.pictures = []  # No images for simpler test
            
            mock_converter.convert.return_value = iter([mock_result])
            
            # Call convert method
            result_dir = await docling_model.convert(input_path, output_dir)
            
            # Verify result
            assert result_dir == output_dir
            assert (output_dir / "test.md").exists()
    
    def test_model_capabilities(self, docling_model):
        """Test that model has image extraction capabilities"""
        assert "image_extraction" in docling_model.capabilities
        assert "s3_upload" in docling_model.capabilities
        assert docling_model.version == "2.1.0"
        assert "image extraction" in docling_model.description.lower()
    
    def test_model_initialization_with_s3(self, docling_model):
        """Test model initialization includes S3 client"""
        # The model should attempt to get S3 client during init
        # In test environment, it may be None due to import fallbacks
        assert hasattr(docling_model, 's3_client')
