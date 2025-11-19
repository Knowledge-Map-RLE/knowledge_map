"""Tests for image-related API routes"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from fastapi import status

try:
    from src.app import app
    from src.api.dependencies import get_current_user, get_conversion_service
except ImportError:
    from pdf_to_md.src.app import app
    from pdf_to_md.src.api.dependencies import get_current_user, get_conversion_service


class TestImageRoutes:
    """Test image-related API endpoints"""
    
    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)
    
    @pytest.fixture
    def mock_current_user(self):
        """Mock current user dependency"""
        return {"user_id": "test-user", "username": "testuser"}
    
    @pytest.fixture
    def mock_s3_client(self):
        """Create mock S3 client"""
        client = AsyncMock()
        client.list_objects = AsyncMock(return_value=[
            {
                "Key": "documents/test-doc/image1.jpg",
                "Size": 1024,
                "LastModified": "2023-01-01T00:00:00Z"
            },
            {
                "Key": "documents/test-doc/image2.png", 
                "Size": 2048,
                "LastModified": "2023-01-01T00:00:00Z"
            }
        ])
        client.object_exists = AsyncMock(return_value=True)
        client.download_bytes = AsyncMock(return_value=b"fake image data")
        client.get_object_url = AsyncMock(return_value="https://example.com/presigned-url")
        return client
    
    @pytest.fixture(autouse=True)
    def setup_dependencies(self, mock_current_user):
        """Setup dependency overrides"""
        app.dependency_overrides[get_current_user] = lambda: mock_current_user
        yield
        app.dependency_overrides.clear()
    
    def test_list_document_images_success(self, client, mock_s3_client):
        """Test successful image listing"""
        with patch('src.api.routes.get_s3_client', return_value=mock_s3_client), \
             patch('src.api.routes.settings') as mock_settings:
            
            mock_settings.s3_bucket_name = "test-bucket"
            
            response = client.get("/api/v1/documents/test-doc/images")
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["doc_id"] == "test-doc"
            assert data["count"] == 2
            assert len(data["images"]) == 2
            
            # Check image data structure
            image = data["images"][0]
            assert "filename" in image
            assert "s3_key" in image
            assert "size" in image
    
    def test_list_document_images_s3_unavailable(self, client):
        """Test image listing when S3 is unavailable"""
        with patch('src.api.routes.get_s3_client', return_value=None):
            response = client.get("/api/v1/documents/test-doc/images")
            
            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert "S3 service not available" in response.json()["detail"]
    
    def test_get_document_image_success(self, client, mock_s3_client):
        """Test successful image retrieval"""
        with patch('src.api.routes.get_s3_client', return_value=mock_s3_client), \
             patch('src.api.routes.settings') as mock_settings:
            
            mock_settings.s3_bucket_name = "test-bucket"
            
            response = client.get("/api/v1/documents/test-doc/images/image1.jpg")
            
            assert response.status_code == status.HTTP_200_OK
            assert response.headers["content-type"] == "image/jpeg"
            assert response.content == b"fake image data"
    
    def test_get_document_image_not_found(self, client, mock_s3_client):
        """Test image retrieval when image doesn't exist"""
        mock_s3_client.object_exists = AsyncMock(return_value=False)
        
        with patch('src.api.routes.get_s3_client', return_value=mock_s3_client), \
             patch('src.api.routes.settings') as mock_settings:
            
            mock_settings.s3_bucket_name = "test-bucket"
            
            response = client.get("/api/v1/documents/test-doc/images/nonexistent.jpg")
            
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert "Image not found" in response.json()["detail"]
    
    def test_get_document_image_png_content_type(self, client, mock_s3_client):
        """Test PNG image content type"""
        with patch('src.api.routes.get_s3_client', return_value=mock_s3_client), \
             patch('src.api.routes.settings') as mock_settings:
            
            mock_settings.s3_bucket_name = "test-bucket"
            
            response = client.get("/api/v1/documents/test-doc/images/image1.png")
            
            assert response.status_code == status.HTTP_200_OK
            assert response.headers["content-type"] == "image/png"
    
    def test_get_document_image_url_success(self, client, mock_s3_client):
        """Test successful presigned URL generation"""
        with patch('src.api.routes.get_s3_client', return_value=mock_s3_client), \
             patch('src.api.routes.settings') as mock_settings:
            
            mock_settings.s3_bucket_name = "test-bucket"
            
            response = client.get("/api/v1/documents/test-doc/images/image1.jpg/url")
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["doc_id"] == "test-doc"
            assert data["image_name"] == "image1.jpg"
            assert data["presigned_url"] == "https://example.com/presigned-url"
            assert data["expiration"] == 3600
    
    def test_get_document_image_url_custom_expiration(self, client, mock_s3_client):
        """Test presigned URL with custom expiration"""
        with patch('src.api.routes.get_s3_client', return_value=mock_s3_client), \
             patch('src.api.routes.settings') as mock_settings:
            
            mock_settings.s3_bucket_name = "test-bucket"
            
            response = client.get("/api/v1/documents/test-doc/images/image1.jpg/url?expiration=7200")
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["expiration"] == 7200
            
            # Verify S3 client was called with correct expiration
            mock_s3_client.get_object_url.assert_called_with(
                bucket_name="test-bucket",
                object_key="documents/test-doc/image1.jpg",
                expiration=7200
            )
    
    def test_get_document_image_url_not_found(self, client, mock_s3_client):
        """Test presigned URL for non-existent image"""
        mock_s3_client.object_exists = AsyncMock(return_value=False)
        
        with patch('src.api.routes.get_s3_client', return_value=mock_s3_client), \
             patch('src.api.routes.settings') as mock_settings:
            
            mock_settings.s3_bucket_name = "test-bucket"
            
            response = client.get("/api/v1/documents/test-doc/images/nonexistent.jpg/url")
            
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert "Image not found" in response.json()["detail"]
    
    def test_get_document_image_url_generation_failed(self, client, mock_s3_client):
        """Test presigned URL when generation fails"""
        mock_s3_client.get_object_url = AsyncMock(return_value=None)
        
        with patch('src.api.routes.get_s3_client', return_value=mock_s3_client), \
             patch('src.api.routes.settings') as mock_settings:
            
            mock_settings.s3_bucket_name = "test-bucket"
            
            response = client.get("/api/v1/documents/test-doc/images/image1.jpg/url")
            
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "Failed to generate presigned URL" in response.json()["detail"]
    
    def test_image_routes_require_authentication(self, client):
        """Test that image routes require authentication"""
        # Remove user dependency override to test authentication
        app.dependency_overrides.clear()
        
        # These should return 401 or 403 depending on auth implementation
        response = client.get("/api/v1/documents/test-doc/images")
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]
        
        response = client.get("/api/v1/documents/test-doc/images/image1.jpg")
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]
        
        response = client.get("/api/v1/documents/test-doc/images/image1.jpg/url")
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]
