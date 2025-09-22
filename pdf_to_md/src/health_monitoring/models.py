"""Models for health monitoring"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

class ServiceMetrics(BaseModel):
    service_name: str
    version: str
    uptime_seconds: float
    total_requests: int
    successful_requests: int
    failed_requests: int
    average_response_time: float
    active_conversions: int
    memory_usage_mb: float
    cpu_usage_percent: float
    disk_usage_mb: float
    last_updated: datetime = datetime.now()

class ComponentHealth(BaseModel):
    component_name: str
    status: HealthStatus
    message: str
    last_check: datetime = datetime.now()
    details: Optional[Dict[str, Any]] = None

class SystemHealth(BaseModel):
    overall_status: HealthStatus
    service_metrics: ServiceMetrics
    components: List[ComponentHealth]
    last_updated: datetime = datetime.now()
