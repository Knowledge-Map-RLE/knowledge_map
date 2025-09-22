"""Pydantic schemas for file management API"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

class FileUploadResponse(BaseModel):
    file_id: str
    filename: str
    file_size: int
    upload_time: datetime
    message: str

class FileListResponse(BaseModel):
    files: List[Dict[str, Any]]
    total_count: int
    total_size: int

class FileDeleteRequest(BaseModel):
    file_ids: List[str] = Field(description="List of file IDs to delete")

class FileCleanupRequest(BaseModel):
    max_age_hours: int = Field(default=24, description="Maximum age of files to keep")
    dry_run: bool = Field(default=False, description="If true, only show what would be deleted")

class FileCleanupResponse(BaseModel):
    deleted_count: int
    freed_space: int
    deleted_files: List[str]
    dry_run: bool
