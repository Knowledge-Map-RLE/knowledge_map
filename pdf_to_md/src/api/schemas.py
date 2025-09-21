"""API schemas for PDF to Markdown service"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, field_validator


class ConvertRequest(BaseModel):
    """Request schema for PDF conversion"""
    doc_id: Optional[str] = Field(None, description="Document ID (auto-generated if not provided)")
    model_id: Optional[str] = Field(None, description="Model ID to use for conversion")
    filename: Optional[str] = Field(None, description="Original filename")
    
    @field_validator('doc_id')
    @classmethod
    def validate_doc_id(cls, v):
        if v is not None:
            if len(v) > 255:
                raise ValueError('Document ID too long (max 255 characters)')
            if not v.replace('-', '').replace('_', '').isalnum():
                raise ValueError(
                    'Document ID can only contain alphanumeric characters, '
                    'hyphens, and underscores'
                )
        return v
    
    @field_validator('model_id')
    @classmethod
    def validate_model_id(cls, v):
        if v is not None:
            if len(v) > 100:
                raise ValueError('Model ID too long (max 100 characters)')
            if not v.replace('-', '').replace('_', '').isalnum():
                raise ValueError(
                    'Model ID can only contain alphanumeric characters, '
                    'hyphens, and underscores'
                )
        return v


class ConvertResponse(BaseModel):
    """Response schema for PDF conversion"""
    success: bool = Field(..., description="Whether conversion was successful")
    doc_id: str = Field(..., description="Document ID")
    markdown_content: str = Field("", description="Converted markdown content")
    images: Dict[str, int] = Field(default_factory=dict, description="Image files (name -> size in bytes)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Conversion metadata")
    error_message: Optional[str] = Field(None, description="Error message if conversion failed")
    processing_time: Optional[float] = Field(None, description="Processing time in seconds")


class ProgressUpdate(BaseModel):
    """Progress update schema"""
    doc_id: str = Field(..., description="Document ID")
    status: str = Field(..., description="Conversion status")
    percent: int = Field(0, ge=0, le=100, description="Progress percentage")
    phase: str = Field("initializing", description="Current processing phase")
    message: str = Field("", description="Progress message")
    pages_processed: Optional[int] = Field(None, description="Number of pages processed")
    total_pages: Optional[int] = Field(None, description="Total number of pages")
    processing_time: Optional[float] = Field(None, description="Processing time so far")
    throughput: Optional[float] = Field(None, description="Processing throughput")


class ModelInfo(BaseModel):
    """Model information schema"""
    id: str = Field(..., description="Model ID")
    name: str = Field(..., description="Model name")
    description: str = Field(..., description="Model description")
    status: str = Field(..., description="Model status")
    is_default: bool = Field(False, description="Whether this is the default model")
    version: Optional[str] = Field(None, description="Model version")
    capabilities: List[str] = Field(default_factory=list, description="Model capabilities")


class ModelsResponse(BaseModel):
    """Response schema for models list"""
    models: Dict[str, ModelInfo] = Field(..., description="Available models")
    default_model: str = Field(..., description="Default model ID")


class SetDefaultModelRequest(BaseModel):
    """Request schema for setting default model"""
    model_id: str = Field(..., description="Model ID to set as default")


class EnableModelRequest(BaseModel):
    """Request schema for enabling/disabling model"""
    model_id: str = Field(..., description="Model ID")
    enabled: bool = Field(..., description="Whether to enable or disable the model")


class StatusResponse(BaseModel):
    """Service status response schema"""
    status: str = Field(..., description="Service status")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    models_count: int = Field(..., description="Number of available models")
    default_model: str = Field(..., description="Default model ID")
    active_conversions: int = Field(0, description="Number of active conversions")


class ErrorResponse(BaseModel):
    """Error response schema"""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Error details")
    code: Optional[str] = Field(None, description="Error code")


class HealthResponse(BaseModel):
    """Health check response schema"""
    status: str = Field(..., description="Health status")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    timestamp: str = Field(..., description="Response timestamp")
