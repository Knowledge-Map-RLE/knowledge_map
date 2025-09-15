"""
Микросервис для управления Label Studio и интеграции с Nutrient SDK
"""
import os
import json
import asyncio
from typing import List, Dict, Any, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from label_studio_sdk import Client

from models import ProjectCreate, ProjectResponse, AnnotationTask, AnnotationResponse
from config import settings
from nutrient_client import NutrientPDFClient

app = FastAPI(
    title="Label Studio Service",
    description="Микросервис для управления Label Studio и работы с PDF",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализация клиентов
label_studio_client = None
nutrient_client = None

@app.on_event("startup")
async def startup_event():
    """Инициализация клиентов при запуске"""
    global label_studio_client, nutrient_client
    
    try:
        # Инициализация Label Studio клиента
        label_studio_client = Client(
            url=settings.LABEL_STUDIO_URL,
            api_key=settings.LABEL_STUDIO_API_KEY
        )
        
        # Инициализация Nutrient SDK клиента
        nutrient_client = NutrientPDFClient(
            api_key=settings.NUTRIENT_API_KEY,
            base_url=settings.NUTRIENT_BASE_URL
        )
        
        print("✅ Label Studio и Nutrient SDK клиенты инициализированы")
        
    except Exception as e:
        print(f"❌ Ошибка инициализации клиентов: {e}")

class ProjectManager:
    """Менеджер проектов Label Studio"""
    
    def __init__(self, client: Client):
        self.client = client
        self.pdf_config = self._get_pdf_annotation_config()
    
    def _get_pdf_annotation_config(self) -> str:
        """Конфигурация для разметки PDF с поддержкой связей"""
        return """
        <View>
            <Document name="document" value="$document" zoom="true" height="600"/>
            <Relations>
                <Relation value="causes" background="red"/>
                <Relation value="treats" background="green"/>
                <Relation value="affects" background="blue"/>
                <Relation value="prevents" background="orange"/>
                <Relation value="indicates" background="purple"/>
                <Relation value="contraindicates" background="brown"/>
            </Relations>
            <Labels name="label" toName="document">
                <Label value="disease" background="red" showInline="true"/>
                <Label value="symptom" background="lightblue" showInline="true"/>
                <Label value="treatment" background="green" showInline="true"/>
                <Label value="drug" background="lightgreen" showInline="true"/>
                <Label value="anatomy" background="yellow" showInline="true"/>
                <Label value="procedure" background="pink" showInline="true"/>
            </Labels>
        </View>
        """
    
    async def create_pdf_project(self, name: str, description: str = "") -> Dict[str, Any]:
        """Создание проекта для разметки PDF"""
        try:
            project = self.client.create_project(
                title=name,
                description=description,
                label_config=self.pdf_config,
                expert_instruction="Разметьте медицинские сущности в PDF документе и создайте связи между ними."
            )
            
            return {
                "id": project.id,
                "name": project.title,
                "description": project.description,
                "url": f"{settings.LABEL_STUDIO_URL}/projects/{project.id}/data"
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ошибка создания проекта: {str(e)}")
    
    async def add_pdf_to_project(self, project_id: int, pdf_url: str, filename: str) -> Dict[str, Any]:
        """Добавление PDF файла в проект"""
        try:
            # Создаем задачу для разметки
            task_data = {
                "data": {
                    "document": pdf_url,
                    "filename": filename
                }
            }
            
            # Импортируем задачу в проект
            result = self.client.import_tasks(project_id, [task_data])
            
            return {
                "task_id": result[0]["id"] if result else None,
                "status": "imported",
                "url": f"{settings.LABEL_STUDIO_URL}/projects/{project_id}/data"
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ошибка добавления PDF: {str(e)}")
    
    async def get_project_annotations(self, project_id: int) -> List[Dict[str, Any]]:
        """Получение аннотаций из проекта"""
        try:
            # Экспортируем аннотации
            annotations = self.client.export_annotations(project_id)
            
            return annotations
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ошибка получения аннотаций: {str(e)}")

# Инициализация менеджера проектов
project_manager = None

@app.on_event("startup")
async def init_project_manager():
    """Инициализация менеджера проектов"""
    global project_manager
    if label_studio_client:
        project_manager = ProjectManager(label_studio_client)

# API Endpoints

@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {
        "status": "healthy",
        "label_studio": "connected" if label_studio_client else "disconnected",
        "nutrient_sdk": "connected" if nutrient_client else "disconnected"
    }

@app.post("/projects", response_model=ProjectResponse)
async def create_project(project_data: ProjectCreate):
    """Создание нового проекта для разметки PDF"""
    if not project_manager:
        raise HTTPException(status_code=503, detail="Label Studio не подключен")
    
    result = await project_manager.create_pdf_project(
        name=project_data.name,
        description=project_data.description
    )
    
    return ProjectResponse(**result)

@app.post("/projects/{project_id}/pdf")
async def add_pdf_to_project(
    project_id: int,
    pdf_url: str,
    filename: str
):
    """Добавление PDF файла в проект"""
    if not project_manager:
        raise HTTPException(status_code=503, detail="Label Studio не подключен")
    
    result = await project_manager.add_pdf_to_project(project_id, pdf_url, filename)
    return result

@app.get("/projects/{project_id}/annotations")
async def get_annotations(project_id: int):
    """Получение аннотаций из проекта"""
    if not project_manager:
        raise HTTPException(status_code=503, detail="Label Studio не подключен")
    
    annotations = await project_manager.get_project_annotations(project_id)
    return {"annotations": annotations}

@app.post("/projects/{project_id}/embed")
async def embed_label_studio(project_id: int):
    """Получение URL для встраивания Label Studio"""
    if not project_manager:
        raise HTTPException(status_code=503, detail="Label Studio не подключен")
    
    embed_url = f"{settings.LABEL_STUDIO_URL}/projects/{project_id}/data"
    
    return {
        "embed_url": embed_url,
        "iframe_url": f"{embed_url}?embed=true",
        "project_id": project_id
    }

@app.post("/pdf/convert")
async def convert_pdf_for_annotation(
    file: UploadFile = File(...)
):
    """Конвертация PDF для работы с Label Studio"""
    if not nutrient_client:
        raise HTTPException(status_code=503, detail="Nutrient SDK не подключен")
    
    try:
        # Сохраняем загруженный файл
        file_path = f"/tmp/{file.filename}"
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Конвертируем PDF с помощью Nutrient SDK
        result = await nutrient_client.convert_pdf_for_annotation(file_path)
        
        # Удаляем временный файл
        os.remove(file_path)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка конвертации PDF: {str(e)}")

@app.get("/projects")
async def list_projects():
    """Получение списка всех проектов"""
    if not label_studio_client:
        raise HTTPException(status_code=503, detail="Label Studio не подключен")
    
    try:
        projects = label_studio_client.get_projects()
        return {"projects": [{"id": p.id, "title": p.title, "description": p.description} for p in projects]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения проектов: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
