"""Tests for PDF conversion feature"""

import pytest
from unittest.mock import Mock, patch
from src.pdf_conversion.service import ConversionService
from src.pdf_conversion.models import ConversionStatus


class TestConversionService:
    """Test cases for ConversionService"""
    
    def test_conversion_service_initialization(self):
        """Test that ConversionService initializes correctly"""
        service = ConversionService()
        assert service is not None
        assert hasattr(service, 'model_registry')
        assert hasattr(service, 'file_service')
        assert hasattr(service, '_active_conversions')
        assert hasattr(service, '_conversion_results')
    
    def test_get_active_conversions(self):
        """Test getting active conversions"""
        service = ConversionService()
        active = service.get_active_conversions()
        assert isinstance(active, list)
    
    @patch('src.pdf_conversion.service.ModelRegistryService')
    @patch('src.pdf_conversion.service.FileManagementService')
    async def test_convert_pdf_basic(self, mock_file_service, mock_model_registry):
        """Test basic PDF conversion"""
        # Setup mocks
        mock_model = Mock()
        mock_model.convert_pdf.return_value = "# Test content"
        mock_model_registry.return_value.get_model.return_value = mock_model
        mock_model_registry.return_value.is_model_available.return_value = True
        mock_model_registry.return_value.get_default_model_id.return_value = "docling"
        
        mock_file_service.return_value.create_temp_directory.return_value = Mock()
        mock_file_service.return_value.save_pdf.return_value = Mock()
        mock_file_service.return_value.save_result.return_value = Mock()
        
        service = ConversionService()
        
        # Test conversion
        pdf_content = b"fake pdf content"
        result = await service.convert_pdf(pdf_content)
        
        assert result is not None
        assert result.status == ConversionStatus.COMPLETED
        assert result.content == "# Test content"
    
    def test_get_conversion_progress(self):
        """Test getting conversion progress"""
        service = ConversionService()
        progress = service.get_conversion_progress("nonexistent_task")
        assert progress is None
    
    def test_get_conversion_result(self):
        """Test getting conversion result"""
        service = ConversionService()
        result = service.get_conversion_result("nonexistent_task")
        assert result is None
    
    async def test_cancel_conversion(self):
        """Test cancelling conversion"""
        service = ConversionService()
        success = await service.cancel_conversion("nonexistent_task")
        assert success is False
    
    def test_cleanup_old_results(self):
        """Test cleanup of old results"""
        service = ConversionService()
        cleaned_count = service.cleanup_old_results()
        assert isinstance(cleaned_count, int)
        assert cleaned_count >= 0
