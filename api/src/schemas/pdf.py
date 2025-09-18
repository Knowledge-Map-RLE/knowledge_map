"""Схемы для работы с PDF документами"""
from typing import List, Dict, Optional, Any
from pydantic import BaseModel
from datetime import datetime


class PDFUploadResponse(BaseModel):
    success: bool
    message: str
    document_id: Optional[str] = None
    md5_hash: Optional[str] = None
    already_exists: bool = False


class PDFDocumentResponse(BaseModel):
    uid: str
    original_filename: str
    md5_hash: str
    file_size: Optional[int]
    upload_date: datetime
    title: Optional[str]
    authors: Optional[List[str]]
    abstract: Optional[str]
    keywords: Optional[List[str]]
    processing_status: str
    is_processed: bool


class PDFAnnotationResponse(BaseModel):
    uid: str
    annotation_type: str
    content: str
    confidence: Optional[float]
    page_number: Optional[int]
    bbox: Optional[Dict[str, float]]
    metadata: Optional[Dict[str, Any]]
