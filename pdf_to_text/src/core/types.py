"""Type definitions"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from datetime import datetime
from enum import Enum


class ConversionStatus(str, Enum):
    """Conversion status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ConversionResult(BaseModel):
    """Result of PDF to text conversion"""
    success: bool
    doc_id: str
    text: str
    text_length: int
    processing_time: Optional[float] = None
    error: Optional[str] = None
    created_at: datetime = datetime.now()


class VectorizationResult(BaseModel):
    """Result of text vectorization"""
    success: bool
    doc_id: str
    chunks_count: int
    vector_dimension: int
    error: Optional[str] = None


class QdrantUploadResult(BaseModel):
    """Result of Qdrant upload"""
    success: bool
    doc_id: str
    points_uploaded: int
    error: Optional[str] = None


class ProcessingResult(BaseModel):
    """Complete processing result"""
    success: bool
    doc_id: str
    conversion: ConversionResult
    vectorization: Optional[VectorizationResult] = None
    qdrant_upload: Optional[QdrantUploadResult] = None
    total_time: float
    status: ConversionStatus


class HealthStatus(BaseModel):
    """Health check status"""
    status: str
    service: str
    version: str
    qdrant_available: bool
    timestamp: datetime = datetime.now()



