"""Models for file management"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from pathlib import Path
from pydantic import BaseModel

class FileOperation(str, Enum):
    UPLOAD = "upload"
    DOWNLOAD = "download"
    DELETE = "delete"
    CLEANUP = "cleanup"

class FileInfo(BaseModel):
    file_id: str
    filename: str
    file_path: str
    file_size: int
    content_type: str
    created_at: datetime
    accessed_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

class FileOperationResult(BaseModel):
    operation: FileOperation
    file_id: str
    success: bool
    message: str
    timestamp: datetime = datetime.now()
    details: Optional[Dict[str, Any]] = None
