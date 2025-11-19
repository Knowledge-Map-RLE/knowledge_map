"""Type definitions for PDF to Markdown service"""

from typing import Dict, Any, Optional, Callable, Union, List
from pathlib import Path
from enum import Enum
from dataclasses import dataclass


class ConversionStatus(str, Enum):
    """Conversion status enumeration"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelStatus(str, Enum):
    """Model status enumeration"""
    ENABLED = "enabled"
    DISABLED = "disabled"
    LOADING = "loading"
    ERROR = "error"


@dataclass
class ConversionProgress:
    """Conversion progress information"""
    doc_id: str
    status: ConversionStatus
    percent: int = 0
    phase: str = "initializing"
    message: str = ""
    pages_processed: Optional[int] = None
    total_pages: Optional[int] = None
    processing_time: Optional[float] = None
    throughput: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "doc_id": self.doc_id,
            "status": self.status.value,
            "percent": self.percent,
            "phase": self.phase,
            "message": self.message,
            "pages_processed": self.pages_processed,
            "total_pages": self.total_pages,
            "processing_time": self.processing_time,
            "throughput": self.throughput
        }


@dataclass
class ConversionResult:
    """Conversion result"""
    success: bool
    doc_id: str
    markdown_content: str = ""
    images: Dict[str, bytes] = None
    metadata: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    processing_time: Optional[float] = None
    s3_images: Optional[List[Dict[str, Any]]] = None
    extraction_method: Optional[str] = None
    docling_raw_s3_key: Optional[str] = None  # S3 key for raw Docling markdown
    formatted_s3_key: Optional[str] = None  # S3 key for AI-formatted markdown

    def __post_init__(self):
        if self.images is None:
            self.images = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = {
            "success": self.success,
            "doc_id": self.doc_id,
            "markdown_content": self.markdown_content,
            "images": {name: len(data) for name, data in self.images.items()},
            "metadata": self.metadata,
            "error_message": self.error_message,
            "processing_time": self.processing_time
        }

        # Add S3 fields if present
        if self.s3_images is not None:
            result["s3_images"] = self.s3_images
        if self.extraction_method is not None:
            result["extraction_method"] = self.extraction_method
        if self.docling_raw_s3_key is not None:
            result["docling_raw_s3_key"] = self.docling_raw_s3_key
        if self.formatted_s3_key is not None:
            result["formatted_s3_key"] = self.formatted_s3_key

        return result


@dataclass
class ModelInfo:
    """Model information"""
    id: str
    name: str
    description: str
    status: ModelStatus
    is_default: bool = False
    version: Optional[str] = None
    capabilities: List[str] = None
    
    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "is_default": self.is_default,
            "version": self.version,
            "capabilities": self.capabilities
        }


# Type aliases
ProgressCallback = Callable[[ConversionProgress], None]
ErrorCallback = Callable[[str, Exception], None]
PathLike = Union[str, Path]
