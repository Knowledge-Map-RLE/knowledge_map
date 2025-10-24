"""Custom exceptions"""


class PDFToTextError(Exception):
    """Base exception for PDF to text service"""
    pass


class PDFConversionError(PDFToTextError):
    """PDF conversion failed"""
    pass


class VectorizationError(PDFToTextError):
    """Text vectorization failed"""
    pass


class QdrantError(PDFToTextError):
    """Qdrant operation failed"""
    pass


class FileSizeExceededError(PDFToTextError):
    """File size exceeds maximum allowed"""
    pass


class UnsupportedFileTypeError(PDFToTextError):
    """Unsupported file type"""
    pass


