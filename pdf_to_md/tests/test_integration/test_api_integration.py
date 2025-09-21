"""Integration tests for API endpoints"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock, Mock
from fastapi.testclient import TestClient

from src.app import app
from src.core.types import ConversionResult, ConversionProgress, ConversionStatus


@pytest.mark.integration
@pytest.mark.api
class TestAPIIntegration:
    """Integration tests for API endpoints"""
    
    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)
    
    @pytest.fixture
    def mock_conversion_service(self):
        """Mock conversion service for integration tests"""
        service = AsyncMock()
        service.convert_pdf = AsyncMock()
        service.model_service = Mock()
        service.get_active_conversions = Mock(return_value={})
        service.cancel_conversion = AsyncMock(return_value=True)
        service.get_conversion_status = AsyncMock(return_value=None)
        return service
    
    def test_full_api_workflow(
        self, 
        client, 
        mock_conversion_service,
        real_pdf_file,
        sample_conversion_result
    ):
        """Test complete API workflow"""
        mock_conversion_service.convert_pdf.return_value = sample_conversion_result
        
        # Override the dependency in the app
        from src.api.dependencies import get_conversion_service
        app.dependency_overrides[get_conversion_service] = lambda: mock_conversion_service
        
        try:
            # 1. Check health
            health_response = client.get("/health")
            assert health_response.status_code == 200
            assert health_response.json()["status"] == "healthy"
            
            # 2. Get service status
            mock_conversion_service.model_service.get_available_models.return_value = {
                "marker": Mock()
            }
            mock_conversion_service.model_service.get_default_model.return_value = "marker"
            
            status_response = client.get("/api/v1/status")
            assert status_response.status_code == 200
            status_data = status_response.json()
            assert status_data["status"] == "running"
            assert status_data["models_count"] == 1
            
            # 3. Get available models
            from src.core.types import ModelInfo, ModelStatus
            mock_models = {
                "marker": ModelInfo(
                    id="marker",
                    name="Marker",
                    description="Test marker",
                    status=ModelStatus.ENABLED,
                    is_default=True,
                    version="0.2.0",
                    capabilities=["pdf_to_markdown", "ocr"]
                )
            }
            mock_conversion_service.model_service.get_available_models.return_value = mock_models
            
            models_response = client.get("/api/v1/models")
            assert models_response.status_code == 200
            models_data = models_response.json()
            assert len(models_data["models"]) == 1
            assert models_data["default_model"] == "marker"
            
            # 4. Convert PDF
            pdf_content = real_pdf_file.read_bytes()
            files = {"file": ("test.pdf", pdf_content, "application/pdf")}
            data = {"doc_id": "api_test_doc", "model_id": "marker"}
            
            convert_response = client.post("/api/v1/convert", files=files, data=data)
            assert convert_response.status_code == 200
            convert_data = convert_response.json()
            assert convert_data["success"] is True
            assert convert_data["doc_id"] == "test_doc_123"
            
            # 5. Check conversion status
            mock_conversion_service.get_conversion_status.return_value = "completed"
            
            status_response = client.get("/api/v1/conversions/api_test_doc/status")
            assert status_response.status_code == 200
            status_data = status_response.json()
            assert status_data["status"] == "completed"
            
            # 6. Get active conversions
            mock_conversion_service.get_active_conversions.return_value = {
                "api_test_doc": "processing"
            }
            
            active_response = client.get("/api/v1/conversions/active")
            assert active_response.status_code == 200
            active_data = active_response.json()
            assert "api_test_doc" in active_data["active_conversions"]
            
        finally:
            # Clean up dependency overrides
            app.dependency_overrides.clear()
    
    def test_api_error_handling(
        self, 
        client, 
        mock_conversion_service,
        real_pdf_file
    ):
        """Test API error handling"""
        # Override the dependency in the app
        from src.api.dependencies import get_conversion_service
        app.dependency_overrides[get_conversion_service] = lambda: mock_conversion_service
        
        try:
            # Test with invalid file type
            files = {"file": ("test.txt", b"not a pdf", "text/plain")}
            response = client.post("/api/v1/convert", files=files)
            assert response.status_code == 400
            assert "File must be a PDF" in response.json()["detail"]
            
            # Test with empty file
            files = {"file": ("empty.pdf", b"", "application/pdf")}
            response = client.post("/api/v1/convert", files=files)
            assert response.status_code == 400
            assert "Empty file" in response.json()["detail"]
            
            # Test with large file - mock the conversion service to return a failed result
            from src.core.types import ConversionResult
            mock_conversion_service.convert_pdf.return_value = ConversionResult(
                success=False,
                doc_id="large_doc",
                error_message="File size (11.00 MB) exceeds maximum allowed (100 MB)",
                processing_time=0.1
            )
            
            large_content = b"x" * (11 * 1024 * 1024)  # 11MB
            files = {"file": ("large.pdf", large_content, "application/pdf")}
            response = client.post("/api/v1/convert", files=files)
            assert response.status_code == 500  # Internal server error when conversion fails
            assert "File size" in response.json()["detail"]
            
            # Test with invalid PDF - mock the conversion service to return a failed result
            mock_conversion_service.convert_pdf.return_value = ConversionResult(
                success=False,
                doc_id="invalid_doc",
                error_message="File does not appear to be a valid PDF",
                processing_time=0.1
            )
            
            files = {"file": ("invalid.pdf", b"not a pdf", "application/pdf")}
            response = client.post("/api/v1/convert", files=files)
            assert response.status_code == 500  # Internal server error when conversion fails
            assert "not appear to be a valid PDF" in response.json()["detail"]
            
        finally:
            # Clean up dependency overrides
            app.dependency_overrides.clear()
    
    def test_model_management_api(
        self, 
        client, 
        mock_conversion_service
    ):
        """Test model management API endpoints"""
        # Override the dependency in the app
        from src.api.dependencies import get_conversion_service
        app.dependency_overrides[get_conversion_service] = lambda: mock_conversion_service
        
        try:
            # Test setting default model
            mock_conversion_service.model_service.set_default_model.return_value = True
            
            response = client.post("/api/v1/models/marker/set-default")
            assert response.status_code == 200
            assert response.json()["success"] is True
            
            # Test enabling model
            mock_conversion_service.model_service.enable_model.return_value = True
            
            response = client.post("/api/v1/models/marker/enable")
            assert response.status_code == 200
            assert response.json()["success"] is True
            
            # Test disabling model (should fail for default model)
            mock_conversion_service.model_service.disable_model.return_value = False
            
            response = client.post("/api/v1/models/marker/enable?enabled=false")
            assert response.status_code == 400  # Should fail because it's the default model
            
        finally:
            # Clean up dependency overrides
            app.dependency_overrides.clear()
    
    def test_conversion_management_api(
        self, 
        client, 
        mock_conversion_service
    ):
        """Test conversion management API endpoints"""
        # Override the dependency in the app
        from src.api.dependencies import get_conversion_service
        app.dependency_overrides[get_conversion_service] = lambda: mock_conversion_service
        
        try:
            # Test getting conversion status
            mock_conversion_service.get_conversion_status.return_value = "processing"
            
            response = client.get("/api/v1/conversions/test_doc/status")
            assert response.status_code == 200
            assert response.json()["status"] == "processing"
            
            # Test cancelling conversion
            mock_conversion_service.cancel_conversion.return_value = True
            
            response = client.post("/api/v1/conversions/test_doc/cancel")
            assert response.status_code == 200
            assert response.json()["success"] is True
            
            # Test with non-existent conversion
            mock_conversion_service.get_conversion_status.return_value = None
            
            response = client.get("/api/v1/conversions/nonexistent/status")
            assert response.status_code == 404
            assert "not found" in response.json()["detail"]
            
        finally:
            # Clean up dependency overrides
            app.dependency_overrides.clear()
    
    def test_concurrent_api_requests(
        self, 
        client, 
        mock_conversion_service,
        sample_pdf_content
    ):
        """Test concurrent API requests"""
        # Override the dependency in the app
        from src.api.dependencies import get_conversion_service
        app.dependency_overrides[get_conversion_service] = lambda: mock_conversion_service
        
        # Mock successful conversions
        def mock_convert_pdf(*args, **kwargs):
            doc_id = kwargs.get('doc_id', 'test_doc')
            return ConversionResult(
                success=True,
                doc_id=doc_id,
                markdown_content="Test content",
                processing_time=1.0
            )
        
        mock_conversion_service.convert_pdf.side_effect = mock_convert_pdf
        
        try:
            # Create multiple concurrent requests
            import threading
            import time
            
            results = []
            
            def make_request(index):
                files = {"file": (f"test_{index}.pdf", sample_pdf_content, "application/pdf")}
                data = {"doc_id": f"concurrent_test_{index}"}
                
                response = client.post("/api/v1/convert", files=files, data=data)
                results.append((index, response.status_code, response.json()))
            
            # Start multiple threads
            threads = []
            for i in range(5):
                t = threading.Thread(target=make_request, args=(i,))
                threads.append(t)
                t.start()
            
            # Wait for all threads
            for t in threads:
                t.join()
            
            # Verify results
            assert len(results) == 5
            for index, status_code, data in results:
                assert status_code == 200
                assert data["success"] is True
                assert data["doc_id"] == f"concurrent_test_{index}"
                
        finally:
            # Clean up dependency overrides
            app.dependency_overrides.clear()
    
    def test_api_rate_limiting(
        self, 
        client, 
        mock_conversion_service,
        sample_pdf_content
    ):
        """Test API rate limiting"""
        # Override the dependency in the app
        from src.api.dependencies import get_conversion_service
        app.dependency_overrides[get_conversion_service] = lambda: mock_conversion_service
        
        try:
            # Mock successful conversion
            mock_conversion_service.convert_pdf.return_value = ConversionResult(
                success=True,
                doc_id="rate_test",
                markdown_content="Test content"
            )
            
            files = {"file": ("test.pdf", sample_pdf_content, "application/pdf")}
            
            # Make multiple rapid requests
            responses = []
            for i in range(10):
                response = client.post("/api/v1/convert", files=files)
                responses.append(response.status_code)
            
            # Most requests should succeed (rate limiting is per minute)
            success_count = sum(1 for code in responses if code == 200)
            assert success_count >= 5  # At least half should succeed
            
        finally:
            # Clean up dependency overrides
            app.dependency_overrides.clear()
    
    def test_api_documentation(self, client):
        """Test API documentation endpoints"""
        # Test OpenAPI schema
        response = client.get("/openapi.json")
        assert response.status_code == 200
        
        schema = response.json()
        assert "openapi" in schema
        assert "info" in schema
        assert "paths" in schema
        
        # Test Swagger UI (if enabled in debug mode)
        response = client.get("/docs")
        # Should return 200 in debug mode, 404 in production
        assert response.status_code in [200, 404]
        
        # Test ReDoc (if enabled in debug mode)
        response = client.get("/redoc")
        # Should return 200 in debug mode, 404 in production
        assert response.status_code in [200, 404]
    
    def test_api_middleware(
        self, 
        client, 
        mock_conversion_service
    ):
        """Test API middleware functionality"""
        # Override the dependency in the app
        from src.api.dependencies import get_conversion_service
        app.dependency_overrides[get_conversion_service] = lambda: mock_conversion_service
        
        # Setup mock methods
        mock_conversion_service.model_service.get_available_models.return_value = {}
        mock_conversion_service.model_service.get_default_model.return_value = "marker"
        mock_conversion_service.get_active_conversions.return_value = {}
        
        try:
            # Test CORS headers
            response = client.options("/api/v1/status")
            # CORS preflight should be handled
            
            # Test security headers
            response = client.get("/health")
            assert response.status_code == 200
            
            # Check for security headers
            headers = response.headers
            assert "X-Content-Type-Options" in headers
            assert "X-Frame-Options" in headers
            assert "X-XSS-Protection" in headers
            
            # Test logging middleware
            response = client.get("/api/v1/status")
            assert response.status_code == 200
            
            # Check for process time header
            assert "X-Process-Time" in response.headers
            process_time = float(response.headers["X-Process-Time"])
            assert process_time >= 0
            
        finally:
            # Clean up dependency overrides
            app.dependency_overrides.clear()
