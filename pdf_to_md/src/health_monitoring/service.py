"""Health Monitoring Service"""

import psutil
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path

from .models import HealthStatus, ServiceMetrics, ComponentHealth, SystemHealth

try:
    from ..core.config import settings
    from ..core.logger import get_logger
    from ..model_registry.service import ModelRegistryService
    from ..file_management.service import FileManagementService
    from ..pdf_conversion.service import ConversionService
except ImportError:
    from core.config import settings
    from core.logger import get_logger
    from model_registry.service import ModelRegistryService
    from file_management.service import FileManagementService
    from pdf_conversion.service import ConversionService

logger = get_logger(__name__)

class HealthMonitoringService:
    """Service for health monitoring and metrics collection"""
    
    def __init__(self):
        self.start_time = time.time()
        self._request_count = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._response_times = []
        self._model_registry = ModelRegistryService()
        self._file_service = FileManagementService()
        self._conversion_service = ConversionService()
    
    def record_request(self, success: bool, response_time: float):
        """Record request metrics"""
        self._request_count += 1
        if success:
            self._successful_requests += 1
        else:
            self._failed_requests += 1
        
        self._response_times.append(response_time)
        
        # Keep only last 100 response times for average calculation
        if len(self._response_times) > 100:
            self._response_times = self._response_times[-100:]
    
    def get_uptime_seconds(self) -> float:
        """Get service uptime in seconds"""
        return time.time() - self.start_time
    
    def get_memory_usage_mb(self) -> float:
        """Get memory usage in MB"""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            return memory_info.rss / (1024 * 1024)  # Convert to MB
        except Exception as e:
            logger.warning(f"Failed to get memory usage: {e}")
            return 0.0
    
    def get_cpu_usage_percent(self) -> float:
        """Get CPU usage percentage"""
        try:
            return psutil.cpu_percent(interval=1)
        except Exception as e:
            logger.warning(f"Failed to get CPU usage: {e}")
            return 0.0
    
    def get_disk_usage_mb(self) -> float:
        """Get disk usage in MB"""
        try:
            disk_usage = psutil.disk_usage('/')
            return disk_usage.used / (1024 * 1024)  # Convert to MB
        except Exception as e:
            logger.warning(f"Failed to get disk usage: {e}")
            return 0.0
    
    def get_average_response_time(self) -> float:
        """Get average response time"""
        if not self._response_times:
            return 0.0
        return sum(self._response_times) / len(self._response_times)
    
    def get_service_metrics(self) -> ServiceMetrics:
        """Get comprehensive service metrics"""
        return ServiceMetrics(
            service_name=settings.service_name,
            version=settings.version,
            uptime_seconds=self.get_uptime_seconds(),
            total_requests=self._request_count,
            successful_requests=self._successful_requests,
            failed_requests=self._failed_requests,
            average_response_time=self.get_average_response_time(),
            active_conversions=len(self._conversion_service.get_active_conversions()),
            memory_usage_mb=self.get_memory_usage_mb(),
            cpu_usage_percent=self.get_cpu_usage_percent(),
            disk_usage_mb=self.get_disk_usage_mb()
        )
    
    def check_model_registry_health(self) -> ComponentHealth:
        """Check model registry health"""
        try:
            models_data = self._model_registry.get_available_models()
            available_count = models_data.get("available_count", 0)
            total_count = models_data.get("total_count", 0)
            
            if available_count == 0:
                return ComponentHealth(
                    component_name="model_registry",
                    status=HealthStatus.UNHEALTHY,
                    message="No models available",
                    details={"total_models": total_count, "available_models": available_count}
                )
            elif available_count < total_count:
                return ComponentHealth(
                    component_name="model_registry",
                    status=HealthStatus.DEGRADED,
                    message=f"Some models unavailable ({available_count}/{total_count})",
                    details={"total_models": total_count, "available_models": available_count}
                )
            else:
                return ComponentHealth(
                    component_name="model_registry",
                    status=HealthStatus.HEALTHY,
                    message=f"All models available ({available_count})",
                    details={"total_models": total_count, "available_models": available_count}
                )
        except Exception as e:
            logger.error(f"Model registry health check failed: {e}")
            return ComponentHealth(
                component_name="model_registry",
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {e}",
                details={"error": str(e)}
            )
    
    def check_file_service_health(self) -> ComponentHealth:
        """Check file service health"""
        try:
            stats = self._file_service.get_storage_stats()
            total_files = stats.get("total_files", 0)
            total_size_mb = stats.get("total_size_mb", 0)
            
            # Check if directories are accessible
            temp_dir = Path(settings.temp_dir)
            output_dir = Path(settings.output_dir)
            
            if not temp_dir.exists() or not output_dir.exists():
                return ComponentHealth(
                    component_name="file_service",
                    status=HealthStatus.UNHEALTHY,
                    message="Storage directories not accessible",
                    details={"temp_dir": str(temp_dir), "output_dir": str(output_dir)}
                )
            
            return ComponentHealth(
                component_name="file_service",
                status=HealthStatus.HEALTHY,
                message="File service operational",
                details={"total_files": total_files, "total_size_mb": total_size_mb}
            )
        except Exception as e:
            logger.error(f"File service health check failed: {e}")
            return ComponentHealth(
                component_name="file_service",
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {e}",
                details={"error": str(e)}
            )
    
    def check_conversion_service_health(self) -> ComponentHealth:
        """Check conversion service health"""
        try:
            active_conversions = self._conversion_service.get_active_conversions()
            active_count = len(active_conversions)
            
            # Check if there are too many active conversions
            max_concurrent = settings.max_concurrent_conversions
            if active_count >= max_concurrent:
                return ComponentHealth(
                    component_name="conversion_service",
                    status=HealthStatus.DEGRADED,
                    message=f"At capacity ({active_count}/{max_concurrent})",
                    details={"active_conversions": active_count, "max_concurrent": max_concurrent}
                )
            else:
                return ComponentHealth(
                    component_name="conversion_service",
                    status=HealthStatus.HEALTHY,
                    message=f"Service operational ({active_count}/{max_concurrent})",
                    details={"active_conversions": active_count, "max_concurrent": max_concurrent}
                )
        except Exception as e:
            logger.error(f"Conversion service health check failed: {e}")
            return ComponentHealth(
                component_name="conversion_service",
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {e}",
                details={"error": str(e)}
            )
    
    def get_system_health(self) -> SystemHealth:
        """Get overall system health"""
        components = [
            self.check_model_registry_health(),
            self.check_file_service_health(),
            self.check_conversion_service_health()
        ]
        
        # Determine overall status
        statuses = [comp.status for comp in components]
        if HealthStatus.UNHEALTHY in statuses:
            overall_status = HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            overall_status = HealthStatus.DEGRADED
        elif all(status == HealthStatus.HEALTHY for status in statuses):
            overall_status = HealthStatus.HEALTHY
        else:
            overall_status = HealthStatus.UNKNOWN
        
        return SystemHealth(
            overall_status=overall_status,
            service_metrics=self.get_service_metrics(),
            components=components
        )
    
    def get_health_status(self) -> HealthStatus:
        """Get simple health status"""
        system_health = self.get_system_health()
        return system_health.overall_status
