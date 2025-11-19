"""Tests for Docling integration"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from src.services.models.docling_model import DoclingModel
from src.models.model_registry import ModelRegistry, DOCLING_AVAILABLE


class TestDoclingIntegration:
    """Test Docling model integration"""
    
    def test_docling_model_initialization(self):
        """Test Docling model can be initialized"""
        if not DOCLING_AVAILABLE:
            pytest.skip("Docling is not available")
        
        model = DoclingModel()
        assert model.name == "Docling"
        assert model.description == "Docling PDF to Markdown conversion with advanced document understanding"
        assert "pdf_to_markdown" in model.capabilities
        assert "document_structure_analysis" in model.capabilities
    
    def test_docling_model_validation(self):
        """Test PDF validation"""
        if not DOCLING_AVAILABLE:
            pytest.skip("Docling is not available")
        
        model = DoclingModel()
        
        # Test with non-existent file
        with pytest.raises(FileNotFoundError):
            model.validate_input(Path("nonexistent.pdf"))
        
        # Test with non-PDF file
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"Not a PDF")
            f.flush()
            
            with pytest.raises(ValueError, match="Input file must be a PDF"):
                model.validate_input(Path(f.name))
            
            Path(f.name).unlink()
        
        # Test with empty file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            with pytest.raises(ValueError, match="Input file is empty"):
                model.validate_input(Path(f.name))
            
            Path(f.name).unlink()
    
    @patch('src.services.models.docling_model.DoclingModel._get_converter')
    def test_docling_conversion_mock(self, mock_get_converter):
        """Test Docling conversion with mocked converter"""
        if not DOCLING_AVAILABLE:
            pytest.skip("Docling is not available")
        
        # Mock converter and result
        mock_converter = Mock()
        mock_result = Mock()
        mock_result.document.export_to_markdown.return_value = "# Test Document\n\nThis is a test."
        mock_converter.convert.return_value = mock_result
        mock_get_converter.return_value = mock_converter
        
        model = DoclingModel()
        
        # Create test PDF file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000010 00000 n \n0000000079 00000 n \n0000000136 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n189\n%%EOF")
            f.flush()
            
            with tempfile.TemporaryDirectory() as temp_dir:
                output_dir = Path(temp_dir) / "output"
                
                # Test conversion
                result_dir = model._run_docling_conversion(
                    Path(f.name),
                    output_dir,
                    on_progress=None
                )
                
                # Verify results
                assert result_dir == output_dir
                assert (output_dir / f"{Path(f.name).stem}.md").exists()
                assert (output_dir / f"{Path(f.name).stem}_metadata.json").exists()
                
                # Check markdown content
                markdown_content = (output_dir / f"{Path(f.name).stem}.md").read_text()
                assert "# Test Document" in markdown_content
            
            Path(f.name).unlink()
    
    def test_model_registry_docling_integration(self):
        """Test ModelRegistry includes Docling when available"""
        registry = ModelRegistry()
        models = registry.get_available_models()
        
        if DOCLING_AVAILABLE:
            assert "docling" in models
            assert models["docling"]["name"] == "Docling"
            assert models["docling"]["default"] == True
            assert registry.get_default_model() == "docling"
        else:
            assert registry.get_default_model() == "huridocs"
    
    def test_model_registry_set_default_docling(self):
        """Test setting Docling as default model"""
        if not DOCLING_AVAILABLE:
            pytest.skip("Docling is not available")
        
        registry = ModelRegistry()
        
        # Set Docling as default
        success = registry.set_default_model("docling")
        assert success == True
        
        models = registry.get_available_models()
        assert models["docling"]["default"] == True
        assert registry.get_default_model() == "docling"
        
        # Verify other models are not default
        for model_id, model_info in models.items():
            if model_id != "docling":
                assert model_info["default"] == False
    
    def test_model_registry_enable_disable_docling(self):
        """Test enabling/disabling Docling model"""
        if not DOCLING_AVAILABLE:
            pytest.skip("Docling is not available")
        
        registry = ModelRegistry()
        
        # Initially should be enabled
        models = registry.get_available_models()
        assert models["docling"]["enabled"] == True
        
        # Disable Docling
        success = registry.disable_model("docling")
        assert success == False  # Should fail because it's the default model
        
        # Try to disable a non-default model first
        if "huridocs" in models:
            success = registry.disable_model("huridocs")
            assert success == True
        
        # Re-enable
        success = registry.enable_model("huridocs")
        assert success == True


if __name__ == "__main__":
    pytest.main([__file__])
