"""Tests for validators module"""

import pytest
from src.core.validators import (
    validate_pdf_file, validate_conversion_request,
    PDFFileValidator, ConversionRequestValidator
)
from src.core.exceptions import (
    InvalidPDFError, FileSizeExceededError, UnsupportedFileTypeError
)


class TestPDFFileValidator:
    """Test PDF file validator"""
    
    def test_valid_pdf(self):
        """Test valid PDF content"""
        content = b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\n%%EOF'
        validator = PDFFileValidator(content=content)
        
        assert validator.content == content
        assert validator.get_size_mb() > 0
        assert len(validator.get_file_hash()) == 64  # SHA-256 hash length
    
    def test_empty_content(self):
        """Test empty content"""
        with pytest.raises(InvalidPDFError, match="PDF content is empty"):
            PDFFileValidator(content=b"")
    
    def test_invalid_pdf_header(self):
        """Test invalid PDF header"""
        with pytest.raises(InvalidPDFError, match="File does not appear to be a valid PDF"):
            PDFFileValidator(content=b"Not a PDF file")
    
    def test_large_file(self):
        """Test file size limit"""
        # Create content larger than default limit (100MB)
        large_content = b'%PDF-1.4\n' + b'x' * (101 * 1024 * 1024)
        
        with pytest.raises(FileSizeExceededError):
            PDFFileValidator(content=large_content)
    
    def test_invalid_filename(self):
        """Test invalid filename"""
        content = b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\n%%EOF'
        
        with pytest.raises(UnsupportedFileTypeError):
            PDFFileValidator(content=content, filename="document.txt")


class TestConversionRequestValidator:
    """Test conversion request validator"""
    
    def test_valid_request(self):
        """Test valid conversion request"""
        content = b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\n%%EOF'
        request = ConversionRequestValidator(
            pdf_content=content,
            doc_id="test_doc_123",
            model_id="test_model",
            filename="test.pdf"
        )
        
        assert request.pdf_content == content
        assert request.doc_id == "test_doc_123"
        assert request.model_id == "test_model"
        assert request.filename == "test.pdf"
    
    def test_generate_doc_id(self):
        """Test document ID generation"""
        content = b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\n%%EOF'
        request = ConversionRequestValidator(pdf_content=content)
        
        doc_id = request.generate_doc_id()
        assert doc_id.startswith("doc_")
        assert len(doc_id) == 20  # "doc_" + 16 char hash
    
    def test_invalid_doc_id(self):
        """Test invalid document ID"""
        content = b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\n%%EOF'
        
        with pytest.raises(ValueError, match="Document ID too long"):
            ConversionRequestValidator(
                pdf_content=content,
                doc_id="x" * 256
            )
        
        with pytest.raises(ValueError, match="Document ID can only contain"):
            ConversionRequestValidator(
                pdf_content=content,
                doc_id="invalid@doc#id"
            )
    
    def test_invalid_model_id(self):
        """Test invalid model ID"""
        content = b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\n%%EOF'
        
        with pytest.raises(ValueError, match="Model ID too long"):
            ConversionRequestValidator(
                pdf_content=content,
                model_id="x" * 101
            )
        
        with pytest.raises(ValueError, match="Model ID can only contain"):
            ConversionRequestValidator(
                pdf_content=content,
                model_id="invalid@model#id"
            )


class TestValidationFunctions:
    """Test validation functions"""
    
    def test_validate_pdf_file(self):
        """Test validate_pdf_file function"""
        content = b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\n%%EOF'
        
        validator = validate_pdf_file(content, "test.pdf")
        assert isinstance(validator, PDFFileValidator)
        assert validator.content == content
        assert validator.filename == "test.pdf"
    
    def test_validate_conversion_request(self):
        """Test validate_conversion_request function"""
        content = b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\n%%EOF'
        
        request = validate_conversion_request(
            pdf_content=content,
            doc_id="test_doc",
            model_id="test_model",
            filename="test.pdf"
        )
        
        assert isinstance(request, ConversionRequestValidator)
        assert request.pdf_content == content
        assert request.doc_id == "test_doc"
        assert request.model_id == "test_model"
        assert request.filename == "test.pdf"
