"""
Модели данных для Label Studio сервиса
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = ""

class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str
    url: str

class AnnotationTask(BaseModel):
    document_url: str
    filename: str
    metadata: Optional[Dict[str, Any]] = {}

class AnnotationResponse(BaseModel):
    task_id: int
    annotations: List[Dict[str, Any]]
    status: str

class PDFConversionRequest(BaseModel):
    file_url: str
    filename: str

class PDFConversionResponse(BaseModel):
    converted_url: str
    pages: List[str]
    text_content: str
    metadata: Dict[str, Any]

class LabelStudioEmbedRequest(BaseModel):
    project_id: int
    width: Optional[str] = "100%"
    height: Optional[str] = "600px"
    theme: Optional[str] = "light"

class LabelStudioEmbedResponse(BaseModel):
    embed_url: str
    iframe_url: str
    project_id: int
    config: Dict[str, Any]
