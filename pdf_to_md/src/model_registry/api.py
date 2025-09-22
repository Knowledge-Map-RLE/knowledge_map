"""API endpoints for model registry"""

from typing import Dict, Any
from fastapi import APIRouter, HTTPException, status, Depends, Path as PathParam

from .schemas import (
    ModelsResponse, 
    ModelConfigRequest, 
    ModelStatusResponse,
    ModelPerformanceResponse,
    SetDefaultModelRequest,
    EnableModelRequest
)
from .service import ModelRegistryService
from shared.dependencies import get_current_user
from core.logger import get_logger
from core.exceptions import ModelNotFoundError, ModelDisabledError

logger = get_logger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/models", tags=["Model Registry"])

# Dependency injection
def get_model_registry() -> ModelRegistryService:
    return ModelRegistryService()

@router.get("/", response_model=ModelsResponse)
async def get_models(
    model_registry: ModelRegistryService = Depends(get_model_registry),
    current_user = Depends(get_current_user)
):
    """Get list of available models"""
    try:
        models_data = model_registry.get_available_models()
        return ModelsResponse(**models_data)
    except Exception as e:
        logger.error(f"Error getting models: {e}")
        raise HTTPException(status_code=500, detail="Failed to get models")

@router.get("/{model_id}", response_model=ModelStatusResponse)
async def get_model_info(
    model_id: str = PathParam(..., description="Model ID"),
    model_registry: ModelRegistryService = Depends(get_model_registry),
    current_user = Depends(get_current_user)
):
    """Get model information"""
    try:
        model_info = model_registry.get_model_info(model_id)
        if not model_info:
            raise HTTPException(status_code=404, detail="Model not found")
        
        return ModelStatusResponse(
            model_id=model_info.model_id,
            status=model_info.status.value,
            is_enabled=model_info.is_enabled,
            is_default=model_info.is_default,
            last_used=model_info.last_used,
            usage_count=model_info.usage_count
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting model info: {e}")
        raise HTTPException(status_code=500, detail="Failed to get model info")

@router.get("/{model_id}/performance", response_model=ModelPerformanceResponse)
async def get_model_performance(
    model_id: str = PathParam(..., description="Model ID"),
    model_registry: ModelRegistryService = Depends(get_model_registry),
    current_user = Depends(get_current_user)
):
    """Get model performance statistics"""
    try:
        performance = model_registry.get_model_performance(model_id)
        if not performance:
            raise HTTPException(status_code=404, detail="Performance data not found for model")
        
        return ModelPerformanceResponse(
            model_id=performance.model_id,
            avg_processing_time=performance.avg_processing_time,
            success_rate=performance.success_rate,
            total_conversions=performance.total_conversions,
            last_performance_check=performance.last_performance_check
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting model performance: {e}")
        raise HTTPException(status_code=500, detail="Failed to get model performance")

@router.get("/performance/all")
async def get_all_model_performance(
    model_registry: ModelRegistryService = Depends(get_model_registry),
    current_user = Depends(get_current_user)
):
    """Get performance statistics for all models"""
    try:
        performance_data = model_registry.get_all_model_performance()
        
        result = {}
        for model_id, performance in performance_data.items():
            result[model_id] = {
                "model_id": performance.model_id,
                "avg_processing_time": performance.avg_processing_time,
                "success_rate": performance.success_rate,
                "total_conversions": performance.total_conversions,
                "last_performance_check": performance.last_performance_check.isoformat()
            }
        
        return result
    except Exception as e:
        logger.error(f"Error getting all model performance: {e}")
        raise HTTPException(status_code=500, detail="Failed to get model performance")

@router.post("/{model_id}/set-default")
async def set_default_model(
    model_id: str = PathParam(..., description="Model ID"),
    model_registry: ModelRegistryService = Depends(get_model_registry),
    current_user = Depends(get_current_user)
):
    """Set default model"""
    try:
        success = model_registry.set_default_model(model_id)
        if not success:
            raise HTTPException(status_code=400, detail=f"Failed to set model {model_id} as default")
        
        return {"success": True, "message": f"Model {model_id} set as default"}
    except (ModelNotFoundError, ModelDisabledError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error setting default model: {e}")
        raise HTTPException(status_code=500, detail="Failed to set default model")

@router.post("/{model_id}/enable")
async def enable_model(
    model_id: str = PathParam(..., description="Model ID"),
    enabled: bool = True,
    model_registry: ModelRegistryService = Depends(get_model_registry),
    current_user = Depends(get_current_user)
):
    """Enable or disable model"""
    try:
        if enabled:
            success = model_registry.enable_model(model_id)
            action = "enable"
        else:
            success = model_registry.disable_model(model_id)
            action = "disable"
        
        if not success:
            raise HTTPException(status_code=400, detail=f"Failed to {action} model {model_id}")
        
        return {"success": True, "message": f"Model {model_id} {action}d successfully"}
    except ModelNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error changing model state: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to {action} model")

@router.put("/{model_id}/config")
async def update_model_config(
    request: ModelConfigRequest,
    model_id: str = PathParam(..., description="Model ID"),
    model_registry: ModelRegistryService = Depends(get_model_registry),
    current_user = Depends(get_current_user)
):
    """Update model configuration"""
    try:
        success = model_registry.update_model_config(model_id, request.config)
        if not success:
            raise HTTPException(status_code=400, detail=f"Failed to update config for model {model_id}")
        
        return {"success": True, "message": f"Configuration updated for model {model_id}"}
    except ModelNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating model config: {e}")
        raise HTTPException(status_code=500, detail="Failed to update model configuration")

@router.get("/default/current")
async def get_default_model(
    model_registry: ModelRegistryService = Depends(get_model_registry),
    current_user = Depends(get_current_user)
):
    """Get current default model"""
    try:
        default_model_id = model_registry.get_default_model_id()
        if not default_model_id:
            raise HTTPException(status_code=404, detail="No default model set")
        
        model_info = model_registry.get_model_info(default_model_id)
        if not model_info:
            raise HTTPException(status_code=404, detail="Default model not found")
        
        return {
            "model_id": default_model_id,
            "name": model_info.name,
            "type": model_info.model_type.value,
            "status": model_info.status.value,
            "is_enabled": model_info.is_enabled
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting default model: {e}")
        raise HTTPException(status_code=500, detail="Failed to get default model")
