"""Tests for model registry feature"""

import pytest
from unittest.mock import Mock, patch
from src.model_registry.service import ModelRegistryService
from src.model_registry.models import ModelStatus, ModelType


class TestModelRegistryService:
    """Test cases for ModelRegistryService"""
    
    def test_model_registry_initialization(self):
        """Test that ModelRegistryService initializes correctly"""
        service = ModelRegistryService()
        assert service is not None
        assert hasattr(service, '_models')
        assert hasattr(service, '_model_info')
        assert hasattr(service, '_default_model_id')
        assert hasattr(service, '_model_performance')
    
    def test_get_available_models(self):
        """Test getting available models"""
        service = ModelRegistryService()
        models_data = service.get_available_models()
        
        assert isinstance(models_data, dict)
        assert "models" in models_data
        assert "default_model" in models_data
        assert "total_count" in models_data
        assert "available_count" in models_data
        assert isinstance(models_data["models"], list)
    
    def test_get_model_info(self):
        """Test getting model information"""
        service = ModelRegistryService()
        model_info = service.get_model_info("nonexistent_model")
        assert model_info is None
    
    def test_is_model_available(self):
        """Test checking if model is available"""
        service = ModelRegistryService()
        # Test with non-existent model
        is_available = service.is_model_available("nonexistent_model")
        assert is_available is False
    
    def test_get_default_model_id(self):
        """Test getting default model ID"""
        service = ModelRegistryService()
        default_id = service.get_default_model_id()
        # Should have a default model after initialization
        assert default_id is not None
    
    def test_set_default_model(self):
        """Test setting default model"""
        service = ModelRegistryService()
        # Get available models first
        models_data = service.get_available_models()
        if models_data["models"]:
            first_model = models_data["models"][0]
            model_id = first_model["model_id"]
            
            success = service.set_default_model(model_id)
            assert success is True
            assert service.get_default_model_id() == model_id
    
    def test_enable_model(self):
        """Test enabling model"""
        service = ModelRegistryService()
        # Get available models first
        models_data = service.get_available_models()
        if models_data["models"]:
            first_model = models_data["models"][0]
            model_id = first_model["model_id"]
            
            success = service.enable_model(model_id)
            assert success is True
    
    def test_disable_model(self):
        """Test disabling model"""
        service = ModelRegistryService()
        # Get available models first
        models_data = service.get_available_models()
        if models_data["models"]:
            first_model = models_data["models"][0]
            model_id = first_model["model_id"]
            
            success = service.disable_model(model_id)
            assert success is True
    
    def test_update_model_config(self):
        """Test updating model configuration"""
        service = ModelRegistryService()
        # Get available models first
        models_data = service.get_available_models()
        if models_data["models"]:
            first_model = models_data["models"][0]
            model_id = first_model["model_id"]
            
            new_config = {"test_param": "test_value"}
            success = service.update_model_config(model_id, new_config)
            assert success is True
    
    def test_get_model_performance(self):
        """Test getting model performance"""
        service = ModelRegistryService()
        performance = service.get_model_performance("nonexistent_model")
        assert performance is None
    
    def test_update_model_performance(self):
        """Test updating model performance"""
        service = ModelRegistryService()
        # Get available models first
        models_data = service.get_available_models()
        if models_data["models"]:
            first_model = models_data["models"][0]
            model_id = first_model["model_id"]
            
            service.update_model_performance(model_id, 1.5, True)
            performance = service.get_model_performance(model_id)
            assert performance is not None
            assert performance.model_id == model_id
            assert performance.total_conversions == 1
            assert performance.success_rate == 1.0
    
    def test_get_all_model_performance(self):
        """Test getting all model performance"""
        service = ModelRegistryService()
        all_performance = service.get_all_model_performance()
        assert isinstance(all_performance, dict)
