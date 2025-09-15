"""
Клиент для работы с Nutrient SDK (бывший PSPDFKit)
"""
import asyncio
import httpx
from typing import Dict, Any, List
import json
from pathlib import Path

class NutrientPDFClient:
    """Клиент для работы с Nutrient SDK"""
    
    def __init__(self, api_key: str, base_url: str = "https://api.nutrient.io"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    async def convert_pdf_for_annotation(self, file_path: str) -> Dict[str, Any]:
        """Конвертация PDF для работы с Label Studio"""
        try:
            # Загружаем файл
            with open(file_path, "rb") as f:
                file_content = f.read()
            
            # Отправляем на конвертацию
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/v1/documents/convert",
                    headers=self.headers,
                    files={"file": (Path(file_path).name, file_content, "application/pdf")},
                    data={
                        "format": "json",
                        "include_text": True,
                        "include_images": True,
                        "extract_annotations": True
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return {
                        "success": True,
                        "document_id": result.get("document_id"),
                        "pages": result.get("pages", []),
                        "text_content": result.get("text_content", ""),
                        "annotations": result.get("annotations", []),
                        "metadata": result.get("metadata", {})
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Ошибка конвертации: {response.status_code}",
                        "details": response.text
                    }
                    
        except Exception as e:
            return {
                "success": False,
                "error": f"Ошибка обработки файла: {str(e)}"
            }
    
    async def extract_text_with_positions(self, file_path: str) -> Dict[str, Any]:
        """Извлечение текста с позициями для Label Studio"""
        try:
            with open(file_path, "rb") as f:
                file_content = f.read()
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/v1/documents/extract-text",
                    headers=self.headers,
                    files={"file": (Path(file_path).name, file_content, "application/pdf")},
                    data={
                        "include_positions": True,
                        "include_bbox": True,
                        "include_page_numbers": True
                    }
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    return {
                        "success": False,
                        "error": f"Ошибка извлечения текста: {response.status_code}"
                    }
                    
        except Exception as e:
            return {
                "success": False,
                "error": f"Ошибка извлечения текста: {str(e)}"
            }
    
    async def create_annotations(self, document_id: str, annotations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Создание аннотаций в документе"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/v1/documents/{document_id}/annotations",
                    headers=self.headers,
                    json={"annotations": annotations}
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    return {
                        "success": False,
                        "error": f"Ошибка создания аннотаций: {response.status_code}"
                    }
                    
        except Exception as e:
            return {
                "success": False,
                "error": f"Ошибка создания аннотаций: {str(e)}"
            }
    
    async def get_document_info(self, document_id: str) -> Dict[str, Any]:
        """Получение информации о документе"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/v1/documents/{document_id}",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    return {
                        "success": False,
                        "error": f"Ошибка получения информации: {response.status_code}"
                    }
                    
        except Exception as e:
            return {
                "success": False,
                "error": f"Ошибка получения информации: {str(e)}"
            }
