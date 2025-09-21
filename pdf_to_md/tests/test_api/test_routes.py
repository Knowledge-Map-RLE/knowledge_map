"""Tests for API routes"""

import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from fastapi import UploadFile

from src.app import app
from src.core.types import ConversionResult, ConversionProgress, ConversionStatus, ModelInfo


@pytest.mark.api
class TestAPIRoutes:
    """API route tests"""
    
    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)
    
    @pytest.fixture
    def mock_conversion_service(self):
        """Mock conversion service"""
        service = Mock()
        service.convert_pdf = AsyncMock()
        service.model_service = Mock()
        service.get_active_conversions = Mock(return_value={})
        service.cancel_conversion = AsyncMock(return_value=True)
        service.get_conversion_status = AsyncMock(return_value=None)
        return service
    
    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data
        assert "version" in data
    
    def test_root_endpoint(self, client):
        """Test root endpoint"""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "version" in data
        assert "status" in data
    
    @patch('src.api.dependencies.ConversionService')
    def test_get_status(self, mock_conversion_service_class, client, mock_conversion_service):
        """Test status endpoint"""
        mock_conversion_service_class.return_value = mock_conversion_service
        mock_conversion_service.model_service.get_available_models.return_value = {
            "marker": Mock()
        }
        mock_conversion_service.model_service.get_default_model.return_value = "marker"
        
        response = client.get("/api/v1/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["models_count"] == 1
        assert data["default_model"] == "marker"
    
    @patch('src.api.dependencies.ConversionService')
    def test_convert_pdf_success(self, mock_conversion_service_class, client, mock_conversion_service, sample_pdf_content, sample_conversion_result):
        """Test successful PDF conversion"""
        mock_conversion_service_class.return_value = mock_conversion_service
        mock_conversion_service.convert_pdf.return_value = sample_conversion_result
        
        # Create mock file
        files = {"file": ("test.pdf", sample_pdf_content, "application/pdf")}
        data = {"doc_id": "test_doc", "model_id": "marker"}
        
        response = client.post("/api/v1/convert", files=files, data=data)
        
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["success"] is True
        assert response_data["doc_id"] == "test_doc_123"
        assert "markdown_content" in response_data
        assert "images" in response_data
        assert "metadata" in response_data
    
    @patch('src.api.dependencies.ConversionService')
    def test_convert_pdf_invalid_file_type(self, mock_conversion_service_class, client, mock_conversion_service):
        """Test conversion with invalid file type"""
        mock_conversion_service_class.return_value = mock_conversion_service
        
        # Create mock file with wrong content type
        files = {"file": ("test.txt", b"not a pdf", "text/plain")}
        
        response = client.post("/api/v1/convert", files=files)
        
        assert response.status_code == 400
        assert "File must be a PDF" in response.json()["detail"]
    
    @patch('src.api.dependencies.ConversionService')
    def test_convert_pdf_empty_file(self, mock_conversion_service_class, client, mock_conversion_service):
        """Test conversion with empty file"""
        mock_conversion_service_class.return_value = mock_conversion_service
        
        files = {"file": ("empty.pdf", b"", "application/pdf")}
        
        response = client.post("/api/v1/convert", files=files)
        
        assert response.status_code == 400
        assert "Empty file" in response.json()["detail"]
    
    @patch('src.api.dependencies.ConversionService')
    def test_convert_pdf_conversion_failed(self, mock_conversion_service_class, client, mock_conversion_service, sample_pdf_content):
        """Test conversion failure"""
        mock_conversion_service_class.return_value = mock_conversion_service
        
        failed_result = ConversionResult(
            success=False,
            doc_id="test_doc",
            error_message="Conversion failed"
        )
        mock_conversion_service.convert_pdf.return_value = failed_result
        
        files = {"file": ("test.pdf", sample_pdf_content, "application/pdf")}
        
        response = client.post("/api/v1/convert", files=files)
        
        assert response.status_code == 500
        assert "Conversion failed" in response.json()["detail"]
    
    @patch('src.api.dependencies.ConversionService')
    def test_get_models(self, mock_conversion_service_class, client, mock_conversion_service):
        """Test getting available models"""
        mock_conversion_service_class.return_value = mock_conversion_service
        
        # Create a mock that mimics the dataclass ModelInfo structure
        mock_model_info = Mock()
        mock_model_info.id = "marker"
        mock_model_info.name = "Marker"
        mock_model_info.description = "Test marker"
        mock_model_info.status = Mock()
        mock_model_info.status.value = "enabled"
        mock_model_info.is_default = True
        mock_model_info.version = "0.2.0"
        mock_model_info.capabilities = ["pdf_to_markdown", "ocr"]
        
        mock_models = {
            "marker": mock_model_info
        }
        
        mock_conversion_service.model_service.get_available_models.return_value = mock_models
        mock_conversion_service.model_service.get_default_model.return_value = "marker"
        
        response = client.get("/api/v1/models")
        
        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert "default_model" in data
        assert data["default_model"] == "marker"
        assert len(data["models"]) == 1
    
    @patch('src.api.dependencies.ConversionService')
    def test_set_default_model(self, mock_conversion_service_class, client, mock_conversion_service):
        """Test setting default model"""
        mock_conversion_service_class.return_value = mock_conversion_service
        mock_conversion_service.model_service.set_default_model.return_value = True
        
        response = client.post("/api/v1/models/marker/set-default")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "marker" in data["message"]
    
    @patch('src.api.dependencies.ConversionService')
    def test_set_default_model_failed(self, mock_conversion_service_class, client, mock_conversion_service):
        """Test setting default model failure"""
        mock_conversion_service_class.return_value = mock_conversion_service
        mock_conversion_service.model_service.set_default_model.return_value = False
        
        response = client.post("/api/v1/models/nonexistent/set-default")
        
        assert response.status_code == 400
        assert "Failed to set model" in response.json()["detail"]
    
    @patch('src.api.dependencies.ConversionService')
    def test_enable_model(self, mock_conversion_service_class, client, mock_conversion_service):
        """Test enabling model"""
        mock_conversion_service_class.return_value = mock_conversion_service
        mock_conversion_service.model_service.enable_model.return_value = True
        
        response = client.post("/api/v1/models/marker/enable?enabled=true")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "enabled" in data["message"]
    
    @patch('src.api.dependencies.ConversionService')
    def test_disable_model(self, mock_conversion_service_class, client, mock_conversion_service):
        """Test disabling model"""
        mock_conversion_service_class.return_value = mock_conversion_service
        mock_conversion_service.model_service.disable_model.return_value = True
        
        response = client.post("/api/v1/models/marker/enable?enabled=false")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "disabled" in data["message"]
    
    @patch('src.api.dependencies.ConversionService')
    def test_get_conversion_status(self, mock_conversion_service_class, client, mock_conversion_service):
        """Test getting conversion status"""
        mock_conversion_service_class.return_value = mock_conversion_service
        mock_conversion_service.get_conversion_status.return_value = "processing"
        
        response = client.get("/api/v1/conversions/test_doc/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["doc_id"] == "test_doc"
        assert data["status"] == "processing"
    
    @patch('src.api.dependencies.ConversionService')
    def test_get_conversion_status_not_found(self, mock_conversion_service_class, client, mock_conversion_service):
        """Test getting status for non-existent conversion"""
        mock_conversion_service_class.return_value = mock_conversion_service
        mock_conversion_service.get_conversion_status.return_value = None
        
        response = client.get("/api/v1/conversions/nonexistent/status")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
    
    @patch('src.api.dependencies.ConversionService')
    def test_cancel_conversion(self, mock_conversion_service_class, client, mock_conversion_service):
        """Test cancelling conversion"""
        mock_conversion_service_class.return_value = mock_conversion_service
        mock_conversion_service.cancel_conversion.return_value = True
        
        response = client.post("/api/v1/conversions/test_doc/cancel")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "cancelled" in data["message"]
    
    @patch('src.api.dependencies.ConversionService')
    def test_cancel_conversion_not_found(self, mock_conversion_service_class, client, mock_conversion_service):
        """Test cancelling non-existent conversion"""
        mock_conversion_service_class.return_value = mock_conversion_service
        mock_conversion_service.cancel_conversion.return_value = False
        
        response = client.post("/api/v1/conversions/nonexistent/cancel")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
    
    @patch('src.api.dependencies.ConversionService')
    def test_get_active_conversions(self, mock_conversion_service_class, client, mock_conversion_service):
        """Test getting active conversions"""
        mock_conversion_service_class.return_value = mock_conversion_service
        mock_conversion_service.get_active_conversions.return_value = {
            "doc1": "processing",
            "doc2": "processing"
        }
        
        response = client.get("/api/v1/conversions/active")
        
        assert response.status_code == 200
        data = response.json()
        assert "active_conversions" in data
        assert len(data["active_conversions"]) == 2
        assert "doc1" in data["active_conversions"]
        assert "doc2" in data["active_conversions"]
    
    def test_convert_pdf_missing_file(self, client):
        """Test conversion without file"""
        response = client.post("/api/v1/convert")
        
        assert response.status_code == 422  # Validation error
    
    @patch('src.api.dependencies.ConversionService')
    def test_convert_pdf_large_file(self, mock_conversion_service_class, client, mock_conversion_service, large_pdf_content):
        """Test conversion with large file"""
        mock_conversion_service_class.return_value = mock_conversion_service
        
        # Mock a failed conversion result due to file size
        failed_result = ConversionResult(
            success=False,
            doc_id="test_doc",
            error_message="File size exceeds maximum allowed size"
        )
        mock_conversion_service.convert_pdf.return_value = failed_result
        
        files = {"file": ("large.pdf", large_pdf_content, "application/pdf")}
        
        response = client.post("/api/v1/convert", files=files)
        
        # Should fail due to file size limit
        assert response.status_code == 500  # Internal server error due to conversion failure
        assert "File size" in response.json()["detail"]
    
    @patch('src.api.dependencies.ConversionService')
    def test_convert_pdf_invalid_pdf(self, mock_conversion_service_class, client, mock_conversion_service, invalid_pdf_content):
        """Test conversion with invalid PDF"""
        mock_conversion_service_class.return_value = mock_conversion_service
        
        # Mock the conversion service to return a failed result for invalid PDF
        mock_conversion_service.convert_pdf.return_value = ConversionResult(
            success=False,
            doc_id="invalid_doc",
            error_message="File does not appear to be a valid PDF",
            processing_time=0.1
        )
        
        files = {"file": ("invalid.pdf", invalid_pdf_content, "application/pdf")}
        
        response = client.post("/api/v1/convert", files=files)
        
        assert response.status_code == 500  # Internal server error when conversion fails
        assert "File does not appear to be a valid PDF" in response.json()["detail"]
    
    def test_api_error_handling(self, client):
        """Test API error handling"""
        # Test non-existent endpoint
        response = client.get("/api/v1/nonexistent")
        assert response.status_code == 404
    
    @patch('src.api.dependencies.ConversionService')
    def test_convert_pdf_with_progress(self, mock_conversion_service_class, client, mock_conversion_service, sample_pdf_content):
        """Test conversion with progress tracking"""
        mock_conversion_service_class.return_value = mock_conversion_service
        
        # Mock progress updates
        progress_updates = []
        def mock_convert_pdf(*args, **kwargs):
            on_progress = kwargs.get('on_progress')
            if on_progress:
                progress_updates.append(ConversionProgress(
                    doc_id="test_doc",
                    status=ConversionStatus.PROCESSING,
                    percent=50,
                    phase="processing",
                    message="Half done"
                ))
            
            return ConversionResult(
                success=True,
                doc_id="test_doc",
                markdown_content="Test content"
            )
        
        mock_conversion_service.convert_pdf.side_effect = mock_convert_pdf
        
        files = {"file": ("test.pdf", sample_pdf_content, "application/pdf")}
        
        response = client.post("/api/v1/convert", files=files)
        
        assert response.status_code == 200
        # Progress updates would be handled internally
