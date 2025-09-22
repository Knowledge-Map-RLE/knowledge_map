"""API endpoints for health monitoring"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException

from .schemas import HealthResponse, StatusResponse, MetricsResponse, ComponentStatusResponse
from .service import HealthMonitoringService
from shared.dependencies import get_current_user
from core.logger import get_logger
from core.config import settings

logger = get_logger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/health", tags=["Health Monitoring"])

# Dependency injection
def get_health_service() -> HealthMonitoringService:
    return HealthMonitoringService()

@router.get("/", response_model=HealthResponse)
async def health_check(
    health_service: HealthMonitoringService = Depends(get_health_service)
):
    """Basic health check endpoint"""
    try:
        uptime = health_service.get_uptime_seconds()
        return HealthResponse(
            status="healthy",
            service=settings.service_name,
            version=settings.version,
            timestamp=datetime.now().isoformat(),
            uptime_seconds=uptime
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            service=settings.service_name,
            version=settings.version,
            timestamp=datetime.now().isoformat()
        )

@router.get("/status", response_model=StatusResponse)
async def get_status(
    health_service: HealthMonitoringService = Depends(get_health_service),
    current_user = Depends(get_current_user)
):
    """Get detailed service status"""
    try:
        system_health = health_service.get_system_health()
        service_metrics = system_health.service_metrics
        
        # Get model registry info
        from ..model_registry.service import ModelRegistryService
        model_registry = ModelRegistryService()
        models_data = model_registry.get_available_models()
        
        return StatusResponse(
            status=system_health.overall_status.value,
            service=settings.service_name,
            models_count=models_data.get("total_count", 0),
            default_model=models_data.get("default_model"),
            active_conversions=service_metrics.active_conversions,
            uptime_seconds=service_metrics.uptime_seconds,
            memory_usage_mb=service_metrics.memory_usage_mb,
            last_updated=datetime.now()
        )
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail="Status check failed")

@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    health_service: HealthMonitoringService = Depends(get_health_service),
    current_user = Depends(get_current_user)
):
    """Get detailed service metrics"""
    try:
        system_health = health_service.get_system_health()
        
        # Convert service metrics to dict
        metrics_dict = {
            "service_name": system_health.service_metrics.service_name,
            "version": system_health.service_metrics.version,
            "uptime_seconds": system_health.service_metrics.uptime_seconds,
            "total_requests": system_health.service_metrics.total_requests,
            "successful_requests": system_health.service_metrics.successful_requests,
            "failed_requests": system_health.service_metrics.failed_requests,
            "average_response_time": system_health.service_metrics.average_response_time,
            "active_conversions": system_health.service_metrics.active_conversions,
            "memory_usage_mb": system_health.service_metrics.memory_usage_mb,
            "cpu_usage_percent": system_health.service_metrics.cpu_usage_percent,
            "disk_usage_mb": system_health.service_metrics.disk_usage_mb
        }
        
        # Convert component health to dict
        component_health = []
        for component in system_health.components:
            component_health.append({
                "component_name": component.component_name,
                "status": component.status.value,
                "message": component.message,
                "last_check": component.last_check.isoformat(),
                "details": component.details
            })
        
        return MetricsResponse(
            service_metrics=metrics_dict,
            component_health=component_health,
            overall_status=system_health.overall_status.value,
            last_updated=datetime.now()
        )
    except Exception as e:
        logger.error(f"Metrics check failed: {e}")
        raise HTTPException(status_code=500, detail="Metrics check failed")

@router.get("/components")
async def get_component_health(
    health_service: HealthMonitoringService = Depends(get_health_service),
    current_user = Depends(get_current_user)
):
    """Get health status of individual components"""
    try:
        system_health = health_service.get_system_health()
        
        components = []
        for component in system_health.components:
            components.append(ComponentStatusResponse(
                component_name=component.component_name,
                status=component.status.value,
                message=component.message,
                last_check=component.last_check,
                details=component.details
            ))
        
        return {
            "components": components,
            "overall_status": system_health.overall_status.value,
            "last_updated": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Component health check failed: {e}")
        raise HTTPException(status_code=500, detail="Component health check failed")

@router.get("/ready")
async def readiness_check(
    health_service: HealthMonitoringService = Depends(get_health_service)
):
    """Kubernetes readiness probe"""
    try:
        system_health = health_service.get_system_health()
        
        # Service is ready if it's healthy or degraded (but not unhealthy)
        from .models import HealthStatus
        if system_health.overall_status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]:
            return {"status": "ready", "timestamp": datetime.now().isoformat()}
        else:
            return {"status": "not_ready", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {"status": "not_ready", "error": str(e), "timestamp": datetime.now().isoformat()}

@router.get("/live")
async def liveness_check(
    health_service: HealthMonitoringService = Depends(get_health_service)
):
    """Kubernetes liveness probe"""
    try:
        # Basic liveness check - service is alive if it can respond
        uptime = health_service.get_uptime_seconds()
        return {"status": "alive", "uptime_seconds": uptime, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Liveness check failed: {e}")
        return {"status": "dead", "error": str(e), "timestamp": datetime.now().isoformat()}
