"""API endpoints for PDF conversion"""

import asyncio
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Depends
from fastapi.responses import StreamingResponse

from .schemas import ConvertRequest, ConvertResponse, ProgressUpdate, ConversionStatusResponse
from .service import ConversionService

try:
    from ..shared.dependencies import get_current_user
    from ..core.logger import get_logger
    from ..core.exceptions import (
        PDFConversionError, 
        ModelNotFoundError, 
        ModelDisabledError,
        FileSizeExceededError,
        UnsupportedFileTypeError
    )
except ImportError:
    from shared.dependencies import get_current_user
    from core.logger import get_logger
    from core.exceptions import (
        PDFConversionError, 
        ModelNotFoundError, 
        ModelDisabledError,
        FileSizeExceededError,
        UnsupportedFileTypeError
    )

logger = get_logger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/conversion", tags=["PDF Conversion"])

# Dependency injection
def get_conversion_service() -> ConversionService:
    return ConversionService()

@router.post("/convert", response_model=ConvertResponse)
async def convert_pdf(
    file: UploadFile = File(...),
    model_id: str = Form(default="docling"),
    output_format: str = Form(default="markdown"),
    conversion_service: ConversionService = Depends(get_conversion_service),
    current_user = Depends(get_current_user)
):
    """Convert PDF to Markdown"""
    try:
        # Validate file type
        if not file.content_type or not file.content_type.startswith('application/pdf'):
            raise UnsupportedFileTypeError("File must be a PDF")
        
        # Read file content
        pdf_content = await file.read()
        if not pdf_content:
            raise HTTPException(status_code=400, detail="Empty file")
        
        # Check file size
        max_size = 100 * 1024 * 1024  # 100MB
        if len(pdf_content) > max_size:
            raise FileSizeExceededError(f"File size exceeds maximum allowed size of {max_size} bytes")
        
        logger.info(f"Converting PDF: filename={file.filename}, size={len(pdf_content)} bytes, model_id={model_id}")
        
        # Perform conversion
        result = await conversion_service.convert_pdf(
            pdf_content=pdf_content,
            model_id=model_id,
            output_format=output_format
        )
        
        return ConvertResponse(
            task_id=result.task_id,
            status=result.status.value,
            message=result.metadata.get("message", "Conversion completed") if result.metadata else "Conversion completed",
            progress=100 if result.status.value == "completed" else 0,
            created_at=result.created_at,
            doc_id=result.metadata.get("doc_id") if result.metadata else None
        )
        
    except (PDFConversionError, ModelNotFoundError, ModelDisabledError, 
            FileSizeExceededError, UnsupportedFileTypeError) as e:
        logger.error(f"Conversion error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected conversion error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/progress/{task_id}", response_model=ConversionStatusResponse)
async def get_conversion_progress(
    task_id: str,
    conversion_service: ConversionService = Depends(get_conversion_service)
):
    """Get conversion progress"""
    progress = conversion_service.get_conversion_progress(task_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return ConversionStatusResponse(
        task_id=progress.task_id,
        status=progress.status.value,
        progress=progress.progress,
        message=progress.message,
        created_at=progress.created_at,
        updated_at=progress.updated_at
    )

@router.get("/result/{task_id}")
async def get_conversion_result(
    task_id: str,
    conversion_service: ConversionService = Depends(get_conversion_service)
):
    """Get conversion result"""
    result = conversion_service.get_conversion_result(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    
    if result.status.value != "completed":
        raise HTTPException(status_code=400, detail="Conversion not completed")
    
    return {
        "task_id": result.task_id,
        "status": result.status.value,
        "filename": result.filename,
        "content": result.content,
        "created_at": result.created_at,
        "metadata": result.metadata
    }

@router.get("/download/{task_id}")
async def download_result(
    task_id: str,
    conversion_service: ConversionService = Depends(get_conversion_service)
):
    """Download conversion result"""
    result = conversion_service.get_conversion_result(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    
    if result.status.value != "completed":
        raise HTTPException(status_code=400, detail="Conversion not completed")
    
    from io import BytesIO
    content_bytes = result.content.encode('utf-8')
    
    return StreamingResponse(
        BytesIO(content_bytes),
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={result.filename}"}
    )

@router.post("/cancel/{task_id}")
async def cancel_conversion(
    task_id: str,
    conversion_service: ConversionService = Depends(get_conversion_service)
):
    """Cancel active conversion"""
    success = await conversion_service.cancel_conversion(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found or cannot be cancelled")
    
    return {"success": True, "message": f"Task {task_id} cancelled"}

@router.get("/active")
async def get_active_conversions(
    conversion_service: ConversionService = Depends(get_conversion_service)
):
    """Get list of active conversions"""
    active_tasks = conversion_service.get_active_conversions()
    return {"active_tasks": active_tasks, "count": len(active_tasks)}
