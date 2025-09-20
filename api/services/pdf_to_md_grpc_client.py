#!/usr/bin/env python3
"""
gRPC клиент для взаимодействия с PDF to Markdown сервисом
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Callable

import grpc
from grpc import aio

# Импортируем сгенерированные proto файлы
sys.path.append(str(Path(__file__).parent.parent / "utils" / "generated"))
import pdf_to_md_pb2
import pdf_to_md_pb2_grpc

logger = logging.getLogger(__name__)


class PDFToMarkdownGRPCClient:
    """gRPC клиент для PDF to Markdown сервиса"""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 50051):
        self.host = host
        self.port = port
        self.channel = None
        self.stub = None
        self._connected = False
    
    async def connect(self):
        """Подключение к gRPC серверу"""
        try:
            if not self._connected:
                self.channel = aio.insecure_channel(f"{self.host}:{self.port}")
                self.stub = pdf_to_md_pb2_grpc.PDFToMarkdownServiceStub(self.channel)
                self._connected = True
                logger.info(f"[grpc_client] Подключен к {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"[grpc_client] Ошибка подключения: {e}")
            raise
    
    async def disconnect(self):
        """Отключение от gRPC сервера"""
        if self.channel:
            await self.channel.close()
            self._connected = False
            logger.info("[grpc_client] Отключен от сервера")
    
    async def convert_pdf(
        self, 
        pdf_content: bytes,
        doc_id: str,
        model_id: Optional[str] = None,
        timeout: int = 3600,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Конвертация PDF в Markdown через gRPC
        
        Args:
            pdf_content: Содержимое PDF файла
            doc_id: ID документа
            model_id: ID модели (опционально)
            timeout: Таймаут в секундах
            on_progress: Callback для отслеживания прогресса
            
        Returns:
            Результат конвертации
        """
        try:
            await self.connect()
            
            logger.info(f"[grpc_client] Отправляем запрос на конвертацию: doc_id={doc_id}")
            
            # Создаем запрос
            request = pdf_to_md_pb2.ConvertPDFRequest(
                pdf_content=pdf_content,
                doc_id=doc_id,
                model_id=model_id or "marker"
            )
            
            # Выполняем gRPC вызов
            response = await self.stub.ConvertPDF(request, timeout=timeout)
            
            return {
                "success": response.success,
                "doc_id": response.doc_id,
                "markdown_content": response.markdown_content,
                "images": dict(response.images),
                "metadata_json": response.metadata_json or "",
                "message": response.message
            }
            
        except Exception as e:
            logger.error(f"[grpc_client] Ошибка конвертации: {e}")
            return {
                "success": False,
                "doc_id": doc_id,
                "markdown_content": "",
                "images": {},
                "metadata_json": "",
                "message": f"Ошибка: {str(e)}"
            }
    
    async def convert_pdf_with_progress(
        self, 
        pdf_content: bytes,
        doc_id: str,
        model_id: Optional[str] = None,
        timeout: int = 3600,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Конвертация PDF в Markdown с отслеживанием прогресса через gRPC
        
        Args:
            pdf_content: Содержимое PDF файла
            doc_id: ID документа
            model_id: ID модели (опционально)
            timeout: Таймаут в секундах
            on_progress: Callback для отслеживания прогресса
            
        Returns:
            Результат конвертации
        """
        try:
            await self.connect()
            
            logger.info(f"[grpc_client] Отправляем запрос на конвертацию с прогрессом: doc_id={doc_id}")
            
            # Пока возвращаем заглушку
            logger.warning("[grpc_client] gRPC сервис пока недоступен, возвращаем заглушку")
            
            return {
                "success": False,
                "doc_id": doc_id,
                "message": "gRPC сервис пока недоступен. Используйте прямую интеграцию."
            }
            
        except Exception as e:
            logger.error(f"[grpc_client] Ошибка конвертации с прогрессом: {e}")
            return {
                "success": False,
                "doc_id": doc_id,
                "message": f"Ошибка: {str(e)}"
            }
    
    async def get_models(self) -> Dict[str, Any]:
        """Получение информации о доступных моделях"""
        try:
            await self.connect()
            
            # Создаем запрос
            request = pdf_to_md_pb2.GetModelsRequest()
            
            # Выполняем gRPC вызов
            response = await self.stub.GetModels(request)
            
            # Преобразуем ответ
            models = {}
            for model_id, model_info in response.models.items():
                models[model_id] = {
                    "name": model_info.name,
                    "description": model_info.description,
                    "enabled": model_info.enabled,
                    "default": model_info.default
                }
            
            return {
                "models": models,
                "default_model": response.default_model
            }
            
        except Exception as e:
            logger.error(f"[grpc_client] Ошибка получения моделей: {e}")
            return {
                "models": {},
                "default_model": ""
            }
    
    async def set_default_model(self, model_id: str) -> bool:
        """Установка модели по умолчанию"""
        try:
            await self.connect()
            
            # Создаем запрос
            request = pdf_to_md_pb2.SetDefaultModelRequest(model_id=model_id)
            
            # Выполняем gRPC вызов
            response = await self.stub.SetDefaultModel(request)
            
            return response.success
            
        except Exception as e:
            logger.error(f"[grpc_client] Ошибка установки модели по умолчанию: {e}")
            return False
    
    async def enable_model(self, model_id: str, enabled: bool = True) -> bool:
        """Включение/отключение модели"""
        try:
            await self.connect()
            
            # Создаем запрос
            request = pdf_to_md_pb2.EnableModelRequest(model_id=model_id, enabled=enabled)
            
            # Выполняем gRPC вызов
            response = await self.stub.EnableModel(request)
            
            return response.success
            
        except Exception as e:
            logger.error(f"[grpc_client] Ошибка изменения состояния модели: {e}")
            return False


# Глобальный экземпляр клиента
pdf_to_md_grpc_client = PDFToMarkdownGRPCClient()