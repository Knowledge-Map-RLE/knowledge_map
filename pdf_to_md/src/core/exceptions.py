"""Custom exceptions for PDF to Markdown conversion"""


class PDFConversionError(Exception):
    """Base exception for PDF conversion errors"""
    pass


class ModelNotFoundError(PDFConversionError):
    """Raised when requested model is not found"""
    pass


class ModelDisabledError(PDFConversionError):
    """Raised when requested model is disabled"""
    pass


class InvalidPDFError(PDFConversionError):
    """Raised when PDF file is invalid or corrupted"""
    pass


class ConversionTimeoutError(PDFConversionError):
    """Raised when conversion process times out"""
    pass


class FileSizeExceededError(PDFConversionError):
    """Raised when file size exceeds maximum allowed size"""
    pass


class UnsupportedFileTypeError(PDFConversionError):
    """Raised when file type is not supported"""
    pass
