"""Tests for conversion service"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

from src.services.conversion_service import ConversionService
from src.core.exceptions import (
    PDFConversionError, ModelNotFoundError, ModelDisabledError,
    ConversionTimeoutError
)
from src.core.types import ConversionResult, ConversionProgress, ConversionStatus


@pytest.mark.unit
class TestConversionService:
    """Unit tests for ConversionService"""
    
    @pytest.fixture
    def conversion_service(self, mock_model_service, mock_file_service):
        """Create conversion service with mocked dependencies"""
        service = ConversionService()
        service.model_service = mock_model_service
        service.file_service = mock_file_service
        return service
    
    @pytest.mark.asyncio
    async def test_convert_pdf_success(
        self, 
        conversion_service, 
        sample_pdf_content, 
        sample_conversion_result,
        mock_progress_callback
    ):
        """Test successful PDF conversion"""
        # Setup mocks
        conversion_service.model_service.get_model.return_value = Mock(
            is_enabled=True,
            convert=AsyncMock(return_value=Path("/tmp/result"))
        )
        
        # Mock file operations
        with patch('src.services.conversion_service._collect_marker_outputs') as mock_collect:
            mock_collect.return_value = {
                "markdown": Path("/tmp/result/test.md"),
                "images_dir": Path("/tmp/result"),
                "meta": Path("/tmp/result/metadata.json")
            }
            
            with patch('builtins.open', mock_open_file_with_content()):
                result = await conversion_service.convert_pdf(
                    pdf_content=sample_pdf_content,
                    doc_id="test_doc",
                    on_progress=mock_progress_callback
                )
        
        assert result.success is True
        assert result.doc_id == "test_doc"
        assert result.markdown_content == "Test markdown content"
        assert len(result.images) == 0  # No images in mock
        assert result.processing_time is not None
    
    @pytest.mark.asyncio
    async def test_convert_pdf_model_not_found(self, conversion_service, sample_pdf_content):
        """Test conversion with non-existent model"""
        conversion_service.model_service.get_model.return_value = None
        
        result = await conversion_service.convert_pdf(
            pdf_content=sample_pdf_content,
            doc_id="test_doc",
            model_id="non_existent_model"
        )
        
        assert result.success is False
        assert "Model non_existent_model not found" in result.error_message
    
    @pytest.mark.asyncio
    async def test_convert_pdf_model_disabled(self, conversion_service, sample_pdf_content):
        """Test conversion with disabled model"""
        conversion_service.model_service.get_model.return_value = Mock(is_enabled=False)
        
        result = await conversion_service.convert_pdf(
            pdf_content=sample_pdf_content,
            doc_id="test_doc",
            model_id="disabled_model"
        )
        
        assert result.success is False
        assert "Model disabled_model is disabled" in result.error_message
    
    @pytest.mark.asyncio
    async def test_convert_pdf_with_progress_updates(
        self, 
        conversion_service, 
        sample_pdf_content,
        mock_progress_callback
    ):
        """Test conversion with progress updates"""
        # Setup mock model that calls progress callback
        mock_model = Mock(is_enabled=True)
        
        async def mock_convert(input_path, output_dir, on_progress=None):
            if on_progress:
                on_progress({
                    'percent': 50,
                    'phase': 'processing',
                    'message': 'Half done'
                })
            return Path("/tmp/result")
        
        mock_model.convert = mock_convert
        conversion_service.model_service.get_model.return_value = mock_model
        
        with patch('src.services.conversion_service._collect_marker_outputs') as mock_collect:
            mock_collect.return_value = {
                "markdown": Path("/tmp/result/test.md"),
                "images_dir": Path("/tmp/result")
            }
            
            with patch('builtins.open', mock_open_file_with_content()):
                result = await conversion_service.convert_pdf(
                    pdf_content=sample_pdf_content,
                    doc_id="test_doc",
                    on_progress=mock_progress_callback
                )
        
        assert result.success is True
        assert len(mock_progress_callback.updates) > 0
        assert mock_progress_callback.updates[0].percent == 50
    
    @pytest.mark.asyncio
    async def test_convert_pdf_timeout(self, conversion_service, sample_pdf_content):
        """Test conversion timeout"""
        # Setup mock model that takes too long
        mock_model = Mock(is_enabled=True)
        mock_model.convert = AsyncMock(side_effect=asyncio.TimeoutError())
        conversion_service.model_service.get_model.return_value = mock_model
        
        with patch('src.core.config.settings') as mock_settings:
            mock_settings.conversion_timeout_seconds = 0.1  # Very short timeout
            
            result = await conversion_service.convert_pdf(
                pdf_content=sample_pdf_content,
                doc_id="test_doc"
            )
        
        assert result.success is False
        assert "timeout" in result.error_message.lower()
    
    @pytest.mark.asyncio
    async def test_convert_pdf_generates_doc_id(self, conversion_service, sample_pdf_content):
        """Test that doc_id is generated if not provided"""
        conversion_service.model_service.get_model.return_value = Mock(
            is_enabled=True,
            convert=AsyncMock(return_value=Path("/tmp/result"))
        )
        
        with patch('src.services.conversion_service._collect_marker_outputs') as mock_collect:
            mock_collect.return_value = {
                "markdown": Path("/tmp/result/test.md"),
                "images_dir": Path("/tmp/result")
            }
            
            with patch('builtins.open', mock_open_file_with_content()):
                result = await conversion_service.convert_pdf(
                    pdf_content=sample_pdf_content,
                    doc_id=None  # No doc_id provided
                )
        
        assert result.success is True
        assert result.doc_id.startswith("doc_")
        assert len(result.doc_id) == 20  # "doc_" + 16 char hash
    
    @pytest.mark.asyncio
    async def test_cancel_conversion(self, conversion_service):
        """Test cancelling active conversion"""
        # Add a mock active conversion
        mock_task = AsyncMock()
        conversion_service._active_conversions["test_doc"] = mock_task
        
        result = await conversion_service.cancel_conversion("test_doc")
        
        assert result is True
        mock_task.cancel.assert_called_once()
        assert "test_doc" not in conversion_service._active_conversions
    
    @pytest.mark.asyncio
    async def test_cancel_nonexistent_conversion(self, conversion_service):
        """Test cancelling non-existent conversion"""
        result = await conversion_service.cancel_conversion("nonexistent_doc")
        assert result is False
    
    def test_get_active_conversions(self, conversion_service):
        """Test getting active conversions"""
        # Add mock active conversions
        conversion_service._active_conversions = {
            "doc1": Mock(),
            "doc2": Mock()
        }
        
        active = conversion_service.get_active_conversions()
        
        assert len(active) == 2
        assert "doc1" in active
        assert "doc2" in active
        assert active["doc1"] == "processing"
    
    @pytest.mark.asyncio
    async def test_get_conversion_status(self, conversion_service):
        """Test getting conversion status"""
        # Test with active conversion
        mock_task = AsyncMock()
        mock_task.done.return_value = False
        conversion_service._active_conversions["test_doc"] = mock_task
        
        status = await conversion_service.get_conversion_status("test_doc")
        assert status == "processing"
        
        # Test with completed conversion
        mock_task.done.return_value = True
        mock_task.cancelled.return_value = False
        mock_task.exception.return_value = None
        
        status = await conversion_service.get_conversion_status("test_doc")
        assert status == "completed"
        
        # Test with cancelled conversion
        mock_task.cancelled.return_value = True
        
        status = await conversion_service.get_conversion_status("test_doc")
        assert status == "cancelled"
        
        # Test with failed conversion
        mock_task.cancelled.return_value = False
        mock_task.exception.return_value = Exception("Test error")
        
        status = await conversion_service.get_conversion_status("test_doc")
        assert status == "failed"
        
        # Test with non-existent conversion
        del conversion_service._active_conversions["test_doc"]
        status = await conversion_service.get_conversion_status("test_doc")
        assert status is None


def mock_open_file_with_content(content="Test markdown content"):
    """Helper function to mock file reading"""
    def mock_open(path, mode='r', **kwargs):
        if 'r' in mode:
            return Mock(read_text=Mock(return_value=content))
        return Mock()
    return mock_open
