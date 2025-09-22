"""API endpoints for file management"""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends, Query
from fastapi.responses import StreamingResponse

from .schemas import (
    FileUploadResponse, 
    FileListResponse, 
    FileDeleteRequest, 
    FileCleanupRequest,
    FileCleanupResponse
)
from .service import FileManagementService
from shared.dependencies import get_current_user
from core.logger import get_logger
from core.exceptions import PDFConversionError

logger = get_logger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/files", tags=["File Management"])

# Dependency injection
def get_file_service() -> FileManagementService:
    return FileManagementService()

@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    file_service: FileManagementService = Depends(get_file_service),
    current_user = Depends(get_current_user)
):
    """Upload a file"""
    try:
        # Read file content
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file")
        
        # Save file
        file_id = file_service.save_to_output(
            content=content.decode('utf-8', errors='ignore'),
            filename=file.filename or "uploaded_file.txt"
        )
        
        return FileUploadResponse(
            file_id=file_id,
            filename=file.filename or "uploaded_file.txt",
            file_size=len(content),
            upload_time=datetime.now(),
            message="File uploaded successfully"
        )
        
    except Exception as e:
        logger.error(f"File upload error: {e}")
        raise HTTPException(status_code=500, detail="File upload failed")

@router.get("/list", response_model=FileListResponse)
async def list_files(
    subdir: Optional[str] = Query(None, description="Filter by subdirectory"),
    file_service: FileManagementService = Depends(get_file_service),
    current_user = Depends(get_current_user)
):
    """List all files"""
    try:
        files = file_service.list_files(subdir=subdir)
        
        file_list = []
        total_size = 0
        
        for file_info in files:
            file_data = {
                "file_id": file_info.file_id,
                "filename": file_info.filename,
                "file_size": file_info.file_size,
                "content_type": file_info.content_type,
                "created_at": file_info.created_at.isoformat(),
                "metadata": file_info.metadata
            }
            file_list.append(file_data)
            total_size += file_info.file_size
        
        return FileListResponse(
            files=file_list,
            total_count=len(file_list),
            total_size=total_size
        )
        
    except Exception as e:
        logger.error(f"File list error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list files")

@router.get("/info/{file_id}")
async def get_file_info(
    file_id: str,
    file_service: FileManagementService = Depends(get_file_service),
    current_user = Depends(get_current_user)
):
    """Get file information"""
    file_info = file_service.get_file_info(file_id)
    if not file_info:
        raise HTTPException(status_code=404, detail="File not found")
    
    return {
        "file_id": file_info.file_id,
        "filename": file_info.filename,
        "file_path": file_info.file_path,
        "file_size": file_info.file_size,
        "content_type": file_info.content_type,
        "created_at": file_info.created_at.isoformat(),
        "accessed_at": file_info.accessed_at.isoformat() if file_info.accessed_at else None,
        "metadata": file_info.metadata
    }

@router.get("/download/{file_id}")
async def download_file(
    file_id: str,
    file_service: FileManagementService = Depends(get_file_service),
    current_user = Depends(get_current_user)
):
    """Download file"""
    file_info = file_service.get_file_info(file_id)
    if not file_info:
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        from pathlib import Path
        file_path = Path(file_info.file_path)
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found on disk")
        
        def iter_file():
            with open(file_path, "rb") as f:
                while chunk := f.read(8192):
                    yield chunk
        
        return StreamingResponse(
            iter_file(),
            media_type=file_info.content_type,
            headers={"Content-Disposition": f"attachment; filename={file_info.filename}"}
        )
        
    except Exception as e:
        logger.error(f"File download error: {e}")
        raise HTTPException(status_code=500, detail="File download failed")

@router.delete("/delete/{file_id}")
async def delete_file(
    file_id: str,
    file_service: FileManagementService = Depends(get_file_service),
    current_user = Depends(get_current_user)
):
    """Delete file"""
    result = file_service.delete_file(file_id)
    
    if not result.success:
        raise HTTPException(status_code=404, detail=result.message)
    
    return {
        "success": True,
        "message": result.message,
        "details": result.details
    }

@router.post("/delete-multiple")
async def delete_multiple_files(
    request: FileDeleteRequest,
    file_service: FileManagementService = Depends(get_file_service),
    current_user = Depends(get_current_user)
):
    """Delete multiple files"""
    results = []
    
    for file_id in request.file_ids:
        result = file_service.delete_file(file_id)
        results.append({
            "file_id": file_id,
            "success": result.success,
            "message": result.message
        })
    
    return {
        "results": results,
        "total_requested": len(request.file_ids),
        "successful_deletions": sum(1 for r in results if r["success"])
    }

@router.post("/cleanup", response_model=FileCleanupResponse)
async def cleanup_files(
    request: FileCleanupRequest,
    file_service: FileManagementService = Depends(get_file_service),
    current_user = Depends(get_current_user)
):
    """Cleanup old files"""
    result = file_service.cleanup_old_files(
        max_age_hours=request.max_age_hours,
        dry_run=request.dry_run
    )
    
    details = result.details or {}
    return FileCleanupResponse(
        deleted_count=details.get("deleted_count", 0),
        freed_space=details.get("freed_space", 0),
        deleted_files=details.get("deleted_files", []),
        dry_run=details.get("dry_run", False)
    )

@router.get("/stats")
async def get_storage_stats(
    file_service: FileManagementService = Depends(get_file_service),
    current_user = Depends(get_current_user)
):
    """Get storage statistics"""
    stats = file_service.get_storage_stats()
    return stats
