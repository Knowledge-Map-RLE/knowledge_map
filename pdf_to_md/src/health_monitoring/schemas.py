"""Pydantic schemas for health monitoring API"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str
    uptime_seconds: Optional[float] = None

class StatusResponse(BaseModel):
    status: str
    service: str
    models_count: int
    default_model: Optional[str] = None
    active_conversions: int
    uptime_seconds: float
    memory_usage_mb: float
    last_updated: datetime

class MetricsResponse(BaseModel):
    service_metrics: Dict[str, Any]
    component_health: List[Dict[str, Any]]
    overall_status: str
    last_updated: datetime

class ComponentStatusResponse(BaseModel):
    component_name: str
    status: str
    message: str
    last_check: datetime
    details: Optional[Dict[str, Any]] = None
