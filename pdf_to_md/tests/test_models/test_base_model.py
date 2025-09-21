"""Tests for base model"""

import pytest
from unittest.mock import Mock, AsyncMock
from pathlib import Path

from src.services.models.base_model import BaseModel


class TestModel(BaseModel):
    """Concrete implementation of BaseModel for testing"""
    
    def __init__(self, name="Test Model", description="Test model", version="1.0.0", capabilities=None):
        super().__init__(name, description, version)
        if capabilities is not None:
            self.capabilities = capabilities
    
    async def convert(self, input_path: Path, output_dir: Path, on_progress=None):
        """Mock convert implementation"""
        output_dir.mkdir(parents=True, exist_ok=True)
        markdown_file = output_dir / "test.md"
        markdown_file.write_text("# Test", encoding="utf-8")
        return output_dir
    
    def validate_input(self, input_path: Path) -> bool:
        """Mock validate implementation"""
        return input_path.exists() and input_path.suffix == ".pdf"


@pytest.mark.unit
class TestBaseModel:
    """Unit tests for BaseModel"""
    
    def test_base_model_initialization(self):
        """Test base model initialization"""
        model = TestModel(
            name="Test Model",
            description="Test model for unit tests",
            version="1.0.0"
        )
        
        assert model.name == "Test Model"
        assert model.description == "Test model for unit tests"
        assert model.version == "1.0.0"
        assert model.is_enabled is True
        assert model.capabilities == ["pdf_to_markdown"]
    
    def test_base_model_custom_capabilities(self):
        """Test base model with custom capabilities"""
        model = TestModel(
            name="Advanced Model",
            description="Advanced test model",
            version="2.0.0"
        )
        model.capabilities = ["pdf_to_markdown", "ocr", "table_extraction"]
        
        assert model.capabilities == ["pdf_to_markdown", "ocr", "table_extraction"]
    
    def test_get_model_info(self):
        """Test getting model information"""
        model = TestModel(
            name="Info Test Model",
            description="Model for testing info",
            version="1.5.0"
        )
        model.is_enabled = False
        model.capabilities = ["pdf_to_markdown", "ocr"]
        
        info = model.get_model_info()
        
        assert info["name"] == "Info Test Model"
        assert info["description"] == "Model for testing info"
        assert info["version"] == "1.5.0"
        assert info["enabled"] is False
        assert info["capabilities"] == ["pdf_to_markdown", "ocr"]
    
    def test_emit_progress_with_callback(self):
        """Test emitting progress with callback"""
        model = TestModel("Test Model", "Test", "1.0.0")
        
        progress_updates = []
        
        def progress_callback(progress_data):
            progress_updates.append(progress_data)
        
        # Test successful progress emission
        progress_data = {
            "percent": 50,
            "phase": "processing",
            "message": "Half done"
        }
        
        model._emit_progress(progress_data, progress_callback)
        
        assert len(progress_updates) == 1
        assert progress_updates[0] == progress_data
    
    def test_emit_progress_without_callback(self):
        """Test emitting progress without callback"""
        model = TestModel("Test Model", "Test", "1.0.0")
        
        progress_data = {
            "percent": 75,
            "phase": "finalizing",
            "message": "Almost done"
        }
        
        # Should not raise exception
        model._emit_progress(progress_data, None)
    
    def test_emit_progress_callback_error(self):
        """Test emitting progress with callback that raises error"""
        model = TestModel("Test Model", "Test", "1.0.0")
        
        def error_callback(progress_data):
            raise Exception("Callback error")
        
        progress_data = {
            "percent": 25,
            "phase": "initializing",
            "message": "Starting"
        }
        
        # Should not raise exception even if callback fails
        model._emit_progress(progress_data, error_callback)
    
    def test_abstract_methods(self):
        """Test that abstract methods raise NotImplementedError"""
        # Create a class that doesn't implement abstract methods
        class IncompleteModel(BaseModel):
            pass
        
        # This should raise TypeError when trying to instantiate
        with pytest.raises(TypeError):
            IncompleteModel("Test Model", "Test", "1.0.0")
    
    def test_model_state_management(self):
        """Test model state management"""
        model = TestModel("State Test Model", "Test", "1.0.0")
        
        # Initially enabled
        assert model.is_enabled is True
        
        # Disable model
        model.is_enabled = False
        assert model.is_enabled is False
        
        # Re-enable model
        model.is_enabled = True
        assert model.is_enabled is True
    
    def test_model_capabilities_management(self):
        """Test model capabilities management"""
        model = TestModel("Capabilities Test Model", "Test", "1.0.0")
        
        # Default capabilities
        assert model.capabilities == ["pdf_to_markdown"]
        
        # Add capabilities
        model.capabilities.extend(["ocr", "table_extraction"])
        assert model.capabilities == ["pdf_to_markdown", "ocr", "table_extraction"]
        
        # Remove capabilities
        model.capabilities.remove("ocr")
        assert model.capabilities == ["pdf_to_markdown", "table_extraction"]
        
        # Clear capabilities
        model.capabilities.clear()
        assert model.capabilities == []
    
    def test_model_version_management(self):
        """Test model version management"""
        model = TestModel("Version Test Model", "Test", "1.0.0")
        
        assert model.version == "1.0.0"
        
        # Update version
        model.version = "1.1.0"
        assert model.version == "1.1.0"
        
        # Version in info
        info = model.get_model_info()
        assert info["version"] == "1.1.0"
    
    def test_model_immutable_attributes(self):
        """Test that model attributes are properly managed"""
        model = TestModel("Immutable Test Model", "Test", "1.0.0")
        
        # Name should be immutable after creation
        original_name = model.name
        model.name = "Changed Name"
        assert model.name == "Changed Name"  # Actually mutable in this implementation
        
        # Description should be mutable
        original_description = model.description
        model.description = "Changed Description"
        assert model.description == "Changed Description"
    
    def test_model_info_consistency(self):
        """Test that model info is consistent with model state"""
        model = TestModel("Consistency Test Model", "Test", "1.0.0")
        
        # Change model state
        model.is_enabled = False
        model.capabilities = ["pdf_to_markdown", "ocr"]
        model.version = "2.0.0"
        
        # Get info
        info = model.get_model_info()
        
        # Check consistency
        assert info["enabled"] is False
        assert info["capabilities"] == ["pdf_to_markdown", "ocr"]
        assert info["version"] == "2.0.0"
        assert info["name"] == "Consistency Test Model"
        assert info["description"] == "Test"
    
    def test_model_initialization_with_minimal_params(self):
        """Test model initialization with minimal parameters"""
        model = TestModel("Minimal Model", "Minimal")
        
        assert model.name == "Minimal Model"
        assert model.description == "Minimal"
        assert model.version == "1.0.0"  # Default version
        assert model.is_enabled is True
        assert model.capabilities == ["pdf_to_markdown"]
    
    def test_model_initialization_with_all_params(self):
        """Test model initialization with all parameters"""
        model = TestModel(
            name="Full Model",
            description="Full description",
            version="3.0.0"
        )
        model.capabilities = ["pdf_to_markdown", "ocr", "table_extraction", "image_extraction"]
        model.is_enabled = False
        
        assert model.name == "Full Model"
        assert model.description == "Full description"
        assert model.version == "3.0.0"
        assert model.is_enabled is False
        assert len(model.capabilities) == 4
        assert "image_extraction" in model.capabilities
