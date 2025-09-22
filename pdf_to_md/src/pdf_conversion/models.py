"""Models for PDF conversion"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel

class ConversionStatus(str, Enum):
    STARTED = "started"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ConversionProgress(BaseModel):
    task_id: str
    status: ConversionStatus
    progress: int  # 0-100
    message: str
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()

class ConversionResult(BaseModel):
    task_id: str
    status: ConversionStatus
    output_path: Optional[str] = None
    filename: str
    content: str
    created_at: datetime
    metadata: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
