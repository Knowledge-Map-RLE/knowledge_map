"""API routes for PDF to Markdown service"""

import asyncio
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Depends
from fastapi.responses import StreamingResponse

from .schemas import (
    ConvertRequest, ConvertResponse, ProgressUpdate, ModelsResponse,
    SetDefaultModelRequest, EnableModelRequest, StatusResponse,
    HealthResponse, ErrorResponse, ModelInfo
)
from .dependencies import get_conversion_service, get_current_user
from ..core.logger import get_logger
from ..core.config import settings
from ..core.exceptions import (
    PDFConversionError, ModelNotFoundError, ModelDisabledError,
    FileSizeExceededError, UnsupportedFileTypeError
)

logger = get_logger(__name__)

# Create router
router = APIRouter(prefix="/api/v1", tags=["PDF to Markdown"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        service=settings.service_name,
        version=settings.version,
        timestamp=datetime.now().isoformat()
    )


@router.get("/status", response_model=StatusResponse)
async def get_status(
    conversion_service = Depends(get_conversion_service),
    current_user = Depends(get_current_user)
):
    """Get service status"""
    try:
        models_data = conversion_service.model_service.get_available_models()
        active_conversions = len(conversion_service.get_active_conversions())
        
        return StatusResponse(
            status="running",
            service=settings.service_name,
            version=settings.version,
            models_count=len(models_data),
            default_model=conversion_service.model_service.get_default_model(),
            active_conversions=active_conversions
        )
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get service status"
        )


@router.post("/convert", response_model=ConvertResponse)
async def convert_pdf(
    file: UploadFile = File(..., description="PDF file to convert"),
    doc_id: str = Form(None, description="Document ID (optional)"),
    model_id: str = Form(None, description="Model ID (optional)"),
    conversion_service = Depends(get_conversion_service),
    current_user = Depends(get_current_user)
):
    """Convert PDF to Markdown"""
    try:
        # Validate file type
        if not file.content_type or not file.content_type.startswith('application/pdf'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be a PDF"
            )
        
        # Read file content
        pdf_content = await file.read()
        if not pdf_content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty file"
            )
        
        logger.info(f"Conversion request: doc_id={doc_id}, model_id={model_id}, size={len(pdf_content)} bytes")
        
        # Perform conversion
        result = await conversion_service.convert_pdf(
            pdf_content=pdf_content,
            doc_id=doc_id,
            model_id=model_id,
            filename=file.filename
        )
        
        # Convert to response format
        response = ConvertResponse(
            success=result.success,
            doc_id=result.doc_id,
            markdown_content=result.markdown_content,
            images={name: len(data) for name, data in result.images.items()},
            metadata=result.metadata,
            error_message=result.error_message,
            processing_time=result.processing_time
        )
        
        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.error_message or "Conversion failed"
            )
        
        return response
        
    except HTTPException:
        raise
    except (FileSizeExceededError, UnsupportedFileTypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except (ModelNotFoundError, ModelDisabledError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PDFConversionError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error in convert_pdf: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/models", response_model=ModelsResponse)
async def get_models(
    conversion_service = Depends(get_conversion_service),
    current_user = Depends(get_current_user)
):
    """Get available models"""
    try:
        models_data = conversion_service.model_service.get_available_models()
        default_model = conversion_service.model_service.get_default_model()
        
        # Convert dataclass ModelInfo to Pydantic ModelInfo
        pydantic_models = {}
        for model_id, model_info in models_data.items():
            pydantic_models[model_id] = ModelInfo(
                id=model_info.id,
                name=model_info.name,
                description=model_info.description,
                status=model_info.status.value,
                is_default=model_info.is_default,
                version=model_info.version,
                capabilities=model_info.capabilities
            )
        
        return ModelsResponse(
            models=pydantic_models,
            default_model=default_model
        )
    except Exception as e:
        logger.error(f"Error getting models: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get models"
        )


@router.post("/models/{model_id}/set-default")
async def set_default_model(
    model_id: str,
    conversion_service = Depends(get_conversion_service),
    current_user = Depends(get_current_user)
):
    """Set default model"""
    try:
        success = conversion_service.model_service.set_default_model(model_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to set model {model_id} as default"
            )
        
        return {"success": True, "message": f"Model {model_id} set as default"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting default model: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set default model"
        )


@router.post("/models/{model_id}/enable")
async def enable_model(
    model_id: str,
    enabled: bool = True,
    conversion_service = Depends(get_conversion_service),
    current_user = Depends(get_current_user)
):
    """Enable or disable model"""
    try:
        if enabled:
            success = conversion_service.model_service.enable_model(model_id)
            action = "enable"
        else:
            success = conversion_service.model_service.disable_model(model_id)
            action = "disable"
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to {action} model {model_id}"
            )
        
        return {"success": True, "message": f"Model {model_id} {action}d"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error changing model state: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to {action} model"
        )


@router.get("/conversions/{doc_id}/status")
async def get_conversion_status(
    doc_id: str,
    conversion_service = Depends(get_conversion_service),
    current_user = Depends(get_current_user)
):
    """Get conversion status"""
    try:
        conversion_status = await conversion_service.get_conversion_status(doc_id)
        if conversion_status is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversion {doc_id} not found"
            )
        
        return {"doc_id": doc_id, "status": conversion_status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversion status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get conversion status"
        )


@router.post("/conversions/{doc_id}/cancel")
async def cancel_conversion(
    doc_id: str,
    conversion_service = Depends(get_conversion_service),
    current_user = Depends(get_current_user)
):
    """Cancel active conversion"""
    try:
        success = await conversion_service.cancel_conversion(doc_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversion {doc_id} not found or not active"
            )
        
        return {"success": True, "message": f"Conversion {doc_id} cancelled"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling conversion: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel conversion"
        )


@router.get("/conversions/active")
async def get_active_conversions(
    conversion_service = Depends(get_conversion_service),
    current_user = Depends(get_current_user)
):
    """Get active conversions"""
    try:
        active_conversions = conversion_service.get_active_conversions()
        return {"active_conversions": active_conversions}
    except Exception as e:
        logger.error(f"Error getting active conversions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get active conversions"
        )
