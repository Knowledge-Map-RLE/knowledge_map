"""Pydantic schemas for PDF conversion API"""

from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

class ConvertRequest(BaseModel):
    model_id: str = Field(default="docling", description="Model to use for conversion")
    output_format: str = Field(default="markdown", description="Output format")
    options: Optional[Dict[str, Any]] = Field(default=None, description="Conversion options")

class ConvertResponse(BaseModel):
    task_id: str
    status: str
    message: str
    progress: int
    created_at: datetime
    doc_id: Optional[str] = None

class ProgressUpdate(BaseModel):
    task_id: str
    status: str
    progress: int
    message: str
    updated_at: datetime

class ConversionStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: int
    message: str
    created_at: datetime
    updated_at: datetime
