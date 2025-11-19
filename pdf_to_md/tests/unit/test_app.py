"""Tests for main application"""

import pytest
from fastapi.testclient import TestClient
from src.app import app


class TestApp:
    """Test cases for main FastAPI application"""
    
    def test_app_creation(self):
        """Test that app is created correctly"""
        assert app is not None
        assert app.title == "PDF to Markdown Service"
        assert "Микросервис для преобразования PDF документов в Markdown формат" in app.description
    
    def test_root_endpoint(self):
        """Test root endpoint"""
        client = TestClient(app)
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "version" in data
        assert "status" in data
        assert "architecture" in data
        assert data["architecture"] == "feature-based"
    
    def test_health_endpoint(self):
        """Test health endpoint"""
        client = TestClient(app)
        response = client.get("/api/v1/health/")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "service" in data
        assert "version" in data
        assert "timestamp" in data
    
    def test_conversion_endpoints_exist(self):
        """Test that conversion endpoints are registered"""
        client = TestClient(app)
        
        # Test that conversion endpoints exist (should return 405 Method Not Allowed for GET)
        response = client.get("/api/v1/conversion/convert")
        assert response.status_code == 405  # Method not allowed for GET
    
    def test_file_management_endpoints_exist(self):
        """Test that file management endpoints are registered"""
        client = TestClient(app)
        
        # Test that file endpoints exist
        response = client.get("/api/v1/files/list")
        assert response.status_code in [200, 401]  # 401 if auth required
    
    def test_model_registry_endpoints_exist(self):
        """Test that model registry endpoints are registered"""
        client = TestClient(app)
        
        # Test that model endpoints exist
        response = client.get("/api/v1/models/")
        assert response.status_code in [200, 401]  # 401 if auth required
    
    def test_health_monitoring_endpoints_exist(self):
        """Test that health monitoring endpoints are registered"""
        client = TestClient(app)
        
        # Test that health endpoints exist
        response = client.get("/api/v1/health/status")
        assert response.status_code in [200, 401]  # 401 if auth required
    
    def test_docs_endpoint(self):
        """Test that docs endpoint exists"""
        client = TestClient(app)
        response = client.get("/docs")
        
        # Should return 200 if debug mode, 404 if not
        assert response.status_code in [200, 404]
    
    def test_redoc_endpoint(self):
        """Test that redoc endpoint exists"""
        client = TestClient(app)
        response = client.get("/redoc")
        
        # Should return 200 if debug mode, 404 if not
        assert response.status_code in [200, 404]
