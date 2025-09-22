"""Pydantic schemas for model registry API"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

class ModelsResponse(BaseModel):
    models: List[Dict[str, Any]]
    default_model: Optional[str] = None
    total_count: int
    available_count: int

class ModelConfigRequest(BaseModel):
    config: Dict[str, Any] = Field(description="Model configuration parameters")

class ModelStatusResponse(BaseModel):
    model_id: str
    status: str
    is_enabled: bool
    is_default: bool
    last_used: Optional[datetime] = None
    usage_count: int

class ModelPerformanceResponse(BaseModel):
    model_id: str
    avg_processing_time: float
    success_rate: float
    total_conversions: int
    last_performance_check: datetime

class SetDefaultModelRequest(BaseModel):
    model_id: str = Field(description="Model ID to set as default")

class EnableModelRequest(BaseModel):
    model_id: str = Field(description="Model ID to enable/disable")
    enabled: bool = Field(default=True, description="Enable or disable the model")
