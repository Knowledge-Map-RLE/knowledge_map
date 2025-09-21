"""Tests for API schemas"""

import pytest
from pydantic import ValidationError

from src.api.schemas import (
    ConvertRequest, ConvertResponse, ProgressUpdate, ModelInfo,
    ModelsResponse, SetDefaultModelRequest, EnableModelRequest,
    StatusResponse, ErrorResponse, HealthResponse
)


@pytest.mark.unit
class TestAPISchemas:
    """Unit tests for API schemas"""
    
    def test_convert_request_valid(self):
        """Test valid convert request"""
        request = ConvertRequest(
            doc_id="test_doc_123",
            model_id="marker",
            filename="test.pdf"
        )
        
        assert request.doc_id == "test_doc_123"
        assert request.model_id == "marker"
        assert request.filename == "test.pdf"
    
    def test_convert_request_optional_fields(self):
        """Test convert request with optional fields"""
        request = ConvertRequest()
        
        assert request.doc_id is None
        assert request.model_id is None
        assert request.filename is None
    
    def test_convert_request_invalid_doc_id(self):
        """Test convert request with invalid doc_id"""
        with pytest.raises(ValidationError) as exc_info:
            ConvertRequest(doc_id="x" * 256)  # Too long
        
        assert "Document ID too long" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            ConvertRequest(doc_id="invalid@doc#id")  # Invalid characters
        
        assert "Document ID can only contain" in str(exc_info.value)
    
    def test_convert_request_invalid_model_id(self):
        """Test convert request with invalid model_id"""
        with pytest.raises(ValidationError) as exc_info:
            ConvertRequest(model_id="x" * 101)  # Too long
        
        assert "Model ID too long" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            ConvertRequest(model_id="invalid@model#id")  # Invalid characters
        
        assert "Model ID can only contain" in str(exc_info.value)
    
    def test_convert_response_success(self, sample_markdown_content, sample_images):
        """Test successful convert response"""
        response = ConvertResponse(
            success=True,
            doc_id="test_doc",
            markdown_content=sample_markdown_content,
            images={name: len(data) for name, data in sample_images.items()},
            metadata={"pages": 5},
            processing_time=12.5
        )
        
        assert response.success is True
        assert response.doc_id == "test_doc"
        assert response.markdown_content == sample_markdown_content
        assert len(response.images) == len(sample_images)
        assert response.metadata["pages"] == 5
        assert response.processing_time == 12.5
        assert response.error_message is None
    
    def test_convert_response_failure(self):
        """Test failed convert response"""
        response = ConvertResponse(
            success=False,
            doc_id="test_doc",
            error_message="Conversion failed"
        )
        
        assert response.success is False
        assert response.doc_id == "test_doc"
        assert response.error_message == "Conversion failed"
        assert response.markdown_content == ""
        assert response.images == {}
        assert response.metadata is None
    
    def test_progress_update(self):
        """Test progress update"""
        progress = ProgressUpdate(
            doc_id="test_doc",
            status="processing",
            percent=75,
            phase="processing_pages",
            message="Processing page 3 of 4",
            pages_processed=3,
            total_pages=4,
            processing_time=8.5,
            throughput=0.35
        )
        
        assert progress.doc_id == "test_doc"
        assert progress.status == "processing"
        assert progress.percent == 75
        assert progress.phase == "processing_pages"
        assert progress.message == "Processing page 3 of 4"
        assert progress.pages_processed == 3
        assert progress.total_pages == 4
        assert progress.processing_time == 8.5
        assert progress.throughput == 0.35
    
    def test_progress_update_percent_validation(self):
        """Test progress update percent validation"""
        # Valid percent
        progress = ProgressUpdate(
            doc_id="test_doc",
            status="processing",
            percent=50
        )
        assert progress.percent == 50
        
        # Percent too high
        with pytest.raises(ValidationError):
            ProgressUpdate(
                doc_id="test_doc",
                status="processing",
                percent=150
            )
        
        # Percent too low
        with pytest.raises(ValidationError):
            ProgressUpdate(
                doc_id="test_doc",
                status="processing",
                percent=-10
            )
    
    def test_model_info(self):
        """Test model info"""
        model_info = ModelInfo(
            id="marker",
            name="Marker",
            description="Advanced PDF to Markdown converter",
            status="enabled",
            is_default=False,
            version="0.2.0",
            capabilities=["pdf_to_markdown", "ocr", "table_extraction"]
        )
        
        assert model_info.id == "marker"
        assert model_info.name == "Marker"
        assert model_info.description == "Advanced PDF to Markdown converter"
        assert model_info.status == "enabled"
        assert model_info.is_default is False
        assert model_info.version == "0.2.0"
        assert len(model_info.capabilities) == 3
        assert "pdf_to_markdown" in model_info.capabilities
    
    def test_model_info_default_capabilities(self):
        """Test model info with default capabilities"""
        model_info = ModelInfo(
            id="test_model",
            name="Test Model",
            description="Test model",
            status="enabled"
        )
        
        assert model_info.capabilities == []
        assert model_info.is_default is False
        assert model_info.version is None
    
    def test_models_response(self):
        """Test models response"""
        models = {
            "marker": ModelInfo(
                id="marker",
                name="Marker",
                description="Test marker",
                status="enabled",
                is_default=True
            )
        }
        
        response = ModelsResponse(
            models=models,
            default_model="marker"
        )
        
        assert len(response.models) == 1
        assert "marker" in response.models
        assert response.default_model == "marker"
        assert response.models["marker"].is_default is True
    
    def test_set_default_model_request(self):
        """Test set default model request"""
        request = SetDefaultModelRequest(model_id="marker")
        assert request.model_id == "marker"
    
    def test_enable_model_request(self):
        """Test enable model request"""
        request = EnableModelRequest(model_id="marker", enabled=True)
        assert request.model_id == "marker"
        assert request.enabled is True
        
        request = EnableModelRequest(model_id="marker", enabled=False)
        assert request.model_id == "marker"
        assert request.enabled is False
    
    def test_status_response(self):
        """Test status response"""
        response = StatusResponse(
            status="running",
            service="pdf-to-md-service",
            version="0.1.0",
            models_count=1,
            default_model="marker",
            active_conversions=1
        )
        
        assert response.status == "running"
        assert response.service == "pdf-to-md-service"
        assert response.version == "0.1.0"
        assert response.models_count == 1
        assert response.default_model == "marker"
        assert response.active_conversions == 1
    
    def test_status_response_defaults(self):
        """Test status response with defaults"""
        response = StatusResponse(
            status="running",
            service="test-service",
            version="1.0.0",
            models_count=1,
            default_model="test"
        )
        
        assert response.active_conversions == 0  # Default value
    
    def test_error_response(self):
        """Test error response"""
        response = ErrorResponse(
            error="Test error",
            detail="Detailed error message",
            code="TEST_ERROR"
        )
        
        assert response.error == "Test error"
        assert response.detail == "Detailed error message"
        assert response.code == "TEST_ERROR"
    
    def test_error_response_minimal(self):
        """Test error response with minimal fields"""
        response = ErrorResponse(error="Simple error")
        
        assert response.error == "Simple error"
        assert response.detail is None
        assert response.code is None
    
    def test_health_response(self):
        """Test health response"""
        response = HealthResponse(
            status="healthy",
            service="pdf-to-md-service",
            version="0.1.0",
            timestamp="2024-01-15T10:30:00Z"
        )
        
        assert response.status == "healthy"
        assert response.service == "pdf-to-md-service"
        assert response.version == "0.1.0"
        assert response.timestamp == "2024-01-15T10:30:00Z"
    
    def test_schema_serialization(self, sample_markdown_content):
        """Test schema serialization to JSON"""
        response = ConvertResponse(
            success=True,
            doc_id="test_doc",
            markdown_content=sample_markdown_content,
            images={"image1.jpg": 1024},
            metadata={"pages": 5}
        )
        
        # Test that schema can be serialized
        json_data = response.model_dump()
        assert json_data["success"] is True
        assert json_data["doc_id"] == "test_doc"
        assert "markdown_content" in json_data
        assert "images" in json_data
        assert "metadata" in json_data
    
    def test_schema_deserialization(self):
        """Test schema deserialization from JSON"""
        json_data = {
            "success": True,
            "doc_id": "test_doc",
            "markdown_content": "Test content",
            "images": {"image1.jpg": 1024},
            "metadata": {"pages": 5},
            "processing_time": 12.5
        }
        
        response = ConvertResponse(**json_data)
        assert response.success is True
        assert response.doc_id == "test_doc"
        assert response.markdown_content == "Test content"
        assert response.images == {"image1.jpg": 1024}
        assert response.metadata == {"pages": 5}
        assert response.processing_time == 12.5
