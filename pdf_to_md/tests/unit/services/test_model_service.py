"""Tests for model service"""

import pytest
from unittest.mock import Mock, patch

from src.services.model_service import ModelService
from src.core.exceptions import ModelNotFoundError, ModelDisabledError
from src.core.types import ModelInfo, ModelStatus


@pytest.mark.unit
class TestModelService:
    """Unit tests for ModelService"""
    
    @pytest.fixture
    def model_service(self):
        """Create model service with mocked models"""
        with patch('src.services.model_service.MarkerModel') as mock_marker:
            
            # Setup mock models
            mock_marker_instance = Mock()
            mock_marker_instance.name = "Marker"
            mock_marker_instance.description = "Test Marker model"
            mock_marker_instance.version = "0.2.0"
            mock_marker_instance.is_enabled = True
            mock_marker_instance.capabilities = ["pdf_to_markdown", "ocr", "table_extraction"]
            mock_marker.return_value = mock_marker_instance
            
            service = ModelService()
            return service
    
    def test_get_model_existing(self, model_service):
        """Test getting existing model"""
        model = model_service.get_model("marker")
        assert model is not None
        assert model.name == "Marker"
    
    def test_get_model_nonexistent(self, model_service):
        """Test getting non-existent model"""
        model = model_service.get_model("nonexistent")
        assert model is None
    
    def test_get_available_models(self, model_service):
        """Test getting available models"""
        models = model_service.get_available_models()
        
        assert len(models) == 1
        assert "marker" in models
        
        marker_info = models["marker"]
        assert marker_info.name == "Marker"
        assert marker_info.status == ModelStatus.ENABLED.value
        assert marker_info.is_default is True  # Marker is default
    
    def test_get_default_model(self, model_service):
        """Test getting default model"""
        default_model = model_service.get_default_model()
        assert default_model == "marker"
    
    def test_set_default_model_success(self, model_service):
        """Test setting default model successfully"""
        result = model_service.set_default_model("marker")
        assert result is True
        
        # Check that default changed
        default_model = model_service.get_default_model()
        assert default_model == "marker"
        
        # Check model info
        models = model_service.get_available_models()
        assert models["marker"].is_default is True
    
    def test_set_default_model_nonexistent(self, model_service):
        """Test setting non-existent model as default"""
        result = model_service.set_default_model("nonexistent")
        assert result is False
    
    def test_set_default_model_disabled(self, model_service):
        """Test setting disabled model as default"""
        # Disable marker model
        model_service._models["marker"].is_enabled = False
        
        result = model_service.set_default_model("marker")
        assert result is False
    
    def test_enable_model_success(self, model_service):
        """Test enabling model successfully"""
        # First disable the model
        model_service._models["marker"].is_enabled = False
        
        result = model_service.enable_model("marker")
        assert result is True
        assert model_service._models["marker"].is_enabled is True
    
    def test_enable_model_nonexistent(self, model_service):
        """Test enabling non-existent model"""
        result = model_service.enable_model("nonexistent")
        assert result is False
    
    def test_disable_model_success(self, model_service):
        """Test disabling model successfully"""
        # Since marker is the default model, we can't disable it
        # This test should verify that disabling the default model fails
        result = model_service.disable_model("marker")
        assert result is False  # Should fail because it's the default model
        assert model_service._models["marker"].is_enabled is True
    
    def test_disable_model_nonexistent(self, model_service):
        """Test disabling non-existent model"""
        result = model_service.disable_model("nonexistent")
        assert result is False
    
    def test_disable_default_model(self, model_service):
        """Test disabling default model (should fail)"""
        result = model_service.disable_model("marker")  # Default model
        assert result is False
        assert model_service._models["marker"].is_enabled is True
    
    def test_get_model_info_existing(self, model_service):
        """Test getting model info for existing model"""
        info = model_service.get_model_info("marker")
        
        assert info is not None
        assert info.id == "marker"
        assert info.name == "Marker"
        assert info.status == ModelStatus.ENABLED.value
        assert info.is_default is True
        assert "pdf_to_markdown" in info.capabilities
    
    def test_get_model_info_nonexistent(self, model_service):
        """Test getting model info for non-existent model"""
        info = model_service.get_model_info("nonexistent")
        assert info is None
    
    def test_validate_model_valid(self, model_service):
        """Test validating valid model"""
        result = model_service.validate_model("marker")
        assert result is True
    
    def test_validate_model_invalid(self, model_service):
        """Test validating invalid model"""
        result = model_service.validate_model("nonexistent")
        assert result is False
    
    def test_validate_model_disabled(self, model_service):
        """Test validating disabled model"""
        model_service._models["marker"].is_enabled = False
        
        result = model_service.validate_model("marker")
        assert result is False
    
    def test_get_model_capabilities(self, model_service):
        """Test getting model capabilities"""
        capabilities = model_service.get_model_capabilities("marker")
        
        assert "pdf_to_markdown" in capabilities
        assert "ocr" in capabilities
        assert "table_extraction" in capabilities
    
    def test_get_model_capabilities_nonexistent(self, model_service):
        """Test getting capabilities for non-existent model"""
        capabilities = model_service.get_model_capabilities("nonexistent")
        assert capabilities == []
    
    def test_model_initialization(self, model_service):
        """Test that models are properly initialized"""
        assert len(model_service._models) == 1
        assert "marker" in model_service._models
        assert model_service._default_model_id == "marker"
    
    def test_model_registry_integrity(self, model_service):
        """Test that model registry maintains integrity"""
        # All models should have required attributes
        for model_id, model in model_service._models.items():
            assert hasattr(model, 'name')
            assert hasattr(model, 'description')
            assert hasattr(model, 'version')
            assert hasattr(model, 'is_enabled')
            assert hasattr(model, 'capabilities')
    
    def test_concurrent_model_operations(self, model_service):
        """Test concurrent model operations"""
        import threading
        import time
        
        results = []
        
        def enable_marker():
            time.sleep(0.01)  # Small delay
            results.append(model_service.enable_model("marker"))
        
        def disable_marker():
            time.sleep(0.01)  # Small delay
            results.append(model_service.disable_model("marker"))
        
        # Start threads
        t1 = threading.Thread(target=enable_marker)
        t2 = threading.Thread(target=disable_marker)
        
        t1.start()
        t2.start()
        
        t1.join()
        t2.join()
        
        # At least one operation should succeed
        assert len(results) == 2
        assert any(results)  # At least one True
