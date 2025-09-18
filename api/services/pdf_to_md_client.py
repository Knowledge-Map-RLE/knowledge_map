"""gRPC клиент для PDF to Markdown сервиса"""
import logging
import asyncio
from typing import Dict, Any, Optional, Callable

import grpc
from grpc import aio

# Импорты proto файлов (будут сгенерированы)
try:
    from proto import pdf_to_md_pb2_grpc, pdf_to_md_pb2
except ImportError:
    # Fallback для разработки
    try:
        import pdf_to_md_pb2_grpc
        import pdf_to_md_pb2
    except ImportError:
        pdf_to_md_pb2_grpc = None
        pdf_to_md_pb2 = None

from .config import settings

logger = logging.getLogger(__name__)


class PDFToMarkdownClient:
    """gRPC клиент для взаимодействия с PDF to Markdown сервисом"""
    
    def __init__(self, host: str = "pdf_to_md", port: int = 50051):
        self.host = host
        self.port = port
        self.channel = None
        self.stub = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()
    
    async def connect(self):
        """Подключение к gRPC серверу"""
        try:
            self.channel = aio.insecure_channel(f"{self.host}:{self.port}")
            self.stub = pdf_to_md_pb2_grpc.PDFToMarkdownServiceStub(self.channel)
            logger.info(f"[pdf_to_md_client] Подключен к {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"[pdf_to_md_client] Ошибка подключения: {e}")
            raise
    
    async def disconnect(self):
        """Отключение от gRPC сервера"""
        if self.channel:
            await self.channel.close()
            logger.info("[pdf_to_md_client] Отключен от сервера")
    
    async def convert_pdf(
        self, 
        pdf_content: bytes,
        doc_id: str,
        model_id: Optional[str] = None,
        timeout: int = 3600
    ) -> Dict[str, Any]:
        """
        Конвертация PDF в Markdown
        
        Args:
            pdf_content: Содержимое PDF файла
            doc_id: ID документа
            model_id: ID модели (если None, используется по умолчанию)
            timeout: Таймаут в секундах
            
        Returns:
            Результат конвертации
        """
        try:
            if not self.stub:
                await self.connect()
            
            # Создаем запрос
            request = pdf_to_md_pb2.ConvertPDFRequest(
                pdf_content=pdf_content,
                doc_id=doc_id,
                model_id=model_id
            )
            
            logger.info(f"[pdf_to_md_client] Отправка запроса на конвертацию: doc_id={doc_id}")
            
            # Выполняем вызов с таймаутом
            response = await self.stub.ConvertPDF(
                request, 
                timeout=timeout
            )
            
            logger.info(f"[pdf_to_md_client] Получен ответ: success={response.success}")
            
            # Преобразуем ответ в словарь
            result = {
                "success": response.success,
                "doc_id": response.doc_id,
                "markdown_content": response.markdown_content,
                "images": dict(response.images),
                "metadata": None,
                "message": response.message
            }
            
            # Парсим метаданные если есть
            if response.metadata_json:
                try:
                    import json
                    result["metadata"] = json.loads(response.metadata_json)
                except Exception as e:
                    logger.warning(f"[pdf_to_md_client] Ошибка парсинга метаданных: {e}")
            
            return result
            
        except grpc.RpcError as e:
            logger.error(f"[pdf_to_md_client] gRPC ошибка: {e}")
            return {
                "success": False,
                "doc_id": doc_id,
                "markdown_content": "",
                "images": {},
                "metadata": None,
                "message": f"gRPC ошибка: {str(e)}"
            }
        except Exception as e:
            logger.error(f"[pdf_to_md_client] Ошибка конвертации: {e}")
            return {
                "success": False,
                "doc_id": doc_id,
                "markdown_content": "",
                "images": {},
                "metadata": None,
                "message": f"Ошибка: {str(e)}"
            }
    
    async def get_models(self) -> Dict[str, Any]:
        """Получение списка доступных моделей"""
        try:
            if not self.stub:
                await self.connect()
            
            request = pdf_to_md_pb2.GetModelsRequest()
            response = await self.stub.GetModels(request, timeout=30)
            
            # Преобразуем модели в словарь
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
            logger.error(f"[pdf_to_md_client] Ошибка получения моделей: {e}")
            return {
                "models": {},
                "default_model": ""
            }
    
    async def set_default_model(self, model_id: str) -> bool:
        """Установка модели по умолчанию"""
        try:
            if not self.stub:
                await self.connect()
            
            request = pdf_to_md_pb2.SetDefaultModelRequest(model_id=model_id)
            response = await self.stub.SetDefaultModel(request, timeout=30)
            
            logger.info(f"[pdf_to_md_client] Установка модели по умолчанию: {response.message}")
            return response.success
            
        except Exception as e:
            logger.error(f"[pdf_to_md_client] Ошибка установки модели по умолчанию: {e}")
            return False
    
    async def enable_model(self, model_id: str, enabled: bool = True) -> bool:
        """Включение/отключение модели"""
        try:
            if not self.stub:
                await self.connect()
            
            request = pdf_to_md_pb2.EnableModelRequest(
                model_id=model_id,
                enabled=enabled
            )
            response = await self.stub.EnableModel(request, timeout=30)
            
            logger.info(f"[pdf_to_md_client] Изменение состояния модели: {response.message}")
            return response.success
            
        except Exception as e:
            logger.error(f"[pdf_to_md_client] Ошибка изменения состояния модели: {e}")
            return False


# Глобальный экземпляр клиента
pdf_to_md_client = PDFToMarkdownClient()
