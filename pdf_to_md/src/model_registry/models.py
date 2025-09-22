"""Models for model registry"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

class ModelStatus(str, Enum):
    AVAILABLE = "available"
    LOADING = "loading"
    ERROR = "error"
    DISABLED = "disabled"

class ModelType(str, Enum):
    DOCLING = "docling"
    MARKER = "marker"
    HURIDOCS = "huridocs"

class ModelInfo(BaseModel):
    model_id: str
    name: str
    model_type: ModelType
    status: ModelStatus
    version: Optional[str] = None
    description: Optional[str] = None
    is_default: bool = False
    is_enabled: bool = True
    config: Optional[Dict[str, Any]] = None
    created_at: datetime = datetime.now()
    last_used: Optional[datetime] = None
    usage_count: int = 0

class ModelPerformance(BaseModel):
    model_id: str
    avg_processing_time: float
    success_rate: float
    total_conversions: int
    last_performance_check: datetime = datetime.now()

class ModelConfig(BaseModel):
    model_id: str
    config: Dict[str, Any]
    updated_at: datetime = datetime.now()
