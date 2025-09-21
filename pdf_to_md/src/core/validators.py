"""Data validation utilities for PDF to Markdown service"""

import hashlib
from pathlib import Path
from typing import Optional, Union
from pydantic import BaseModel, field_validator, Field

from .exceptions import (
    FileSizeExceededError,
    UnsupportedFileTypeError,
    InvalidPDFError
)
from .config import settings


class PDFFileValidator(BaseModel):
    """Validator for PDF files"""
    
    content: bytes = Field(..., description="PDF file content")
    filename: Optional[str] = Field(None, description="Original filename")
    size_mb: Optional[float] = Field(None, description="File size in MB")
    
    @field_validator('content')
    @classmethod
    def validate_content(cls, v):
        """Validate PDF content"""
        if not v:
            raise InvalidPDFError("PDF content is empty")
        
        # Check file size
        size_mb = len(v) / (1024 * 1024)
        if size_mb > settings.max_file_size_mb:
            raise FileSizeExceededError(
                f"File size {size_mb:.2f}MB exceeds maximum allowed size "
                f"{settings.max_file_size_mb}MB"
            )
        
        # Check PDF header
        if not v.startswith(b'%PDF-'):
            raise InvalidPDFError("File does not appear to be a valid PDF")
        
        return v
    
    @field_validator('filename')
    @classmethod
    def validate_filename(cls, v):
        """Validate filename"""
        if v is not None:
            if not v.lower().endswith('.pdf'):
                raise UnsupportedFileTypeError(
                    f"File '{v}' is not a PDF file"
                )
        return v
    
    def get_file_hash(self) -> str:
        """Get SHA-256 hash of file content"""
        return hashlib.sha256(self.content).hexdigest()
    
    def get_size_mb(self) -> float:
        """Get file size in MB"""
        return len(self.content) / (1024 * 1024)


class ConversionRequestValidator(BaseModel):
    """Validator for conversion requests"""
    
    pdf_content: bytes = Field(..., description="PDF file content")
    doc_id: Optional[str] = Field(None, description="Document ID")
    model_id: Optional[str] = Field(None, description="Model ID to use")
    filename: Optional[str] = Field(None, description="Original filename")
    
    @field_validator('doc_id')
    @classmethod
    def validate_doc_id(cls, v):
        """Validate document ID"""
        if v is not None:
            if len(v) > 255:
                raise ValueError("Document ID too long (max 255 characters)")
            if not v.replace('-', '').replace('_', '').isalnum():
                raise ValueError(
                    "Document ID can only contain alphanumeric characters, "
                    "hyphens, and underscores"
                )
        return v
    
    @field_validator('model_id')
    @classmethod
    def validate_model_id(cls, v):
        """Validate model ID"""
        if v is not None:
            if len(v) > 100:
                raise ValueError("Model ID too long (max 100 characters)")
            if not v.replace('-', '').replace('_', '').isalnum():
                raise ValueError(
                    "Model ID can only contain alphanumeric characters, "
                    "hyphens, and underscores"
                )
        return v
    
    def generate_doc_id(self) -> str:
        """Generate document ID from content hash if not provided"""
        if self.doc_id:
            return self.doc_id
        
        content_hash = hashlib.sha256(self.pdf_content).hexdigest()[:16]
        return f"doc_{content_hash}"


def validate_pdf_file(
    content: bytes,
    filename: Optional[str] = None
) -> PDFFileValidator:
    """
    Validate PDF file content and metadata
    
    Args:
        content: PDF file content
        filename: Original filename (optional)
        
    Returns:
        Validated PDF file data
        
    Raises:
        InvalidPDFError: If PDF is invalid
        FileSizeExceededError: If file is too large
        UnsupportedFileTypeError: If file type is not supported
    """
    return PDFFileValidator(content=content, filename=filename)


def validate_conversion_request(
    pdf_content: bytes,
    doc_id: Optional[str] = None,
    model_id: Optional[str] = None,
    filename: Optional[str] = None
) -> ConversionRequestValidator:
    """
    Validate conversion request
    
    Args:
        pdf_content: PDF file content
        doc_id: Document ID (optional)
        model_id: Model ID (optional)
        filename: Original filename (optional)
        
    Returns:
        Validated conversion request
        
    Raises:
        InvalidPDFError: If PDF is invalid
        FileSizeExceededError: If file is too large
        UnsupportedFileTypeError: If file type is not supported
        ValueError: If other validation fails
    """
    return ConversionRequestValidator(
        pdf_content=pdf_content,
        doc_id=doc_id,
        model_id=model_id,
        filename=filename
    )
