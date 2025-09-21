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

# Отладочная информация при импорте модуля
logger.info("[grpc_client] Модуль pdf_to_md_grpc_client импортирован")


class PDFToMarkdownGRPCClient:
    """gRPC клиент для PDF to Markdown сервиса"""
    
    def __init__(self, host: str = None, port: int = None):
        import os
        # Для локального запуска используем жестко заданные значения
        # В Docker эти значения будут переопределены переменными окружения
        env_host = os.getenv("PDF_TO_MD_SERVICE_HOST", "127.0.0.1")
        env_port = os.getenv("PDF_TO_MD_SERVICE_PORT", "50053")
        
        # Если переменные окружения не установлены, используем значения для локального запуска
        if env_host == "127.0.0.1" and env_port == "50053":
            # Локальный запуск - PDF to MD сервис работает на порту 50053
            self.host = host or "127.0.0.1"
            self.port = port or 50053
        else:
            # Docker запуск - используем переменные окружения
            self.host = host or env_host
            self.port = port or int(env_port)
            
        self.channel = None
        self.stub = None
        self._connected = False
        logger.info(f"[grpc_client] Создан клиент с хостом: {self.host}, портом: {self.port}")
        logger.info(f"[grpc_client] Переменные окружения: PDF_TO_MD_SERVICE_HOST={env_host}, PDF_TO_MD_SERVICE_PORT={env_port}")
    
    async def connect(self):
        """Подключение к gRPC серверу"""
        try:
            if not self._connected:
                logger.info(f"[grpc_client] Пытаемся подключиться к {self.host}:{self.port}")
                self.channel = aio.insecure_channel(f"{self.host}:{self.port}")
                self.stub = pdf_to_md_pb2_grpc.PDFToMarkdownServiceStub(self.channel)
                self._connected = True
                logger.info(f"[grpc_client] Подключен к {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"[grpc_client] Ошибка подключения к {self.host}:{self.port}: {e}")
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
            
            logger.info(f"[grpc_client] Отправляем запрос на конвертацию: doc_id={doc_id}, host={self.host}, port={self.port}")
            
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
            
            # Создаем запрос
            request = pdf_to_md_pb2.ConvertPDFRequest(
                pdf_content=pdf_content,
                doc_id=doc_id,
                model_id=model_id or "marker"
            )
            
            # Выполняем gRPC вызов с отслеживанием прогресса
            response = await self.stub.ConvertPDFWithProgress(request, timeout=timeout)
            
            return {
                "success": response.success,
                "doc_id": response.doc_id,
                "markdown_content": response.markdown_content,
                "images": dict(response.images),
                "metadata_json": response.metadata_json or "",
                "message": response.message
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


# Глобальный экземпляр клиента (создается при первом использовании)
_pdf_to_md_grpc_client = None

def get_pdf_to_md_grpc_client() -> PDFToMarkdownGRPCClient:
    """Получение глобального экземпляра gRPC клиента"""
    global _pdf_to_md_grpc_client
    if _pdf_to_md_grpc_client is None:
        logger.info("[grpc_client] Создаем новый экземпляр gRPC клиента")
        _pdf_to_md_grpc_client = PDFToMarkdownGRPCClient()
        logger.info(f"[grpc_client] Создан глобальный клиент с портом: {_pdf_to_md_grpc_client.port}")
    else:
        logger.info(f"[grpc_client] Используем существующий глобальный клиент с портом: {_pdf_to_md_grpc_client.port}")
    return _pdf_to_md_grpc_client

# Для обратной совместимости - создаем глобальную переменную, но не инициализируем её
pdf_to_md_grpc_client = None

def get_pdf_to_md_grpc_client_instance():
    """Получение глобального экземпляра gRPC клиента с ленивой инициализацией"""
    global pdf_to_md_grpc_client
    if pdf_to_md_grpc_client is None:
        pdf_to_md_grpc_client = get_pdf_to_md_grpc_client()
    return pdf_to_md_grpc_client