"""gRPC сервер для PDF to Markdown сервиса"""
import asyncio
import logging
import json
from concurrent import futures
from typing import Dict, Any

import grpc
from grpc import aio

from proto import pdf_to_md_pb2_grpc, pdf_to_md_pb2
from .services.pdf_conversion_service import PDFConversionService
from .schemas.api import ProgressUpdate

logger = logging.getLogger(__name__)


class PDFToMarkdownServicer(pdf_to_md_pb2_grpc.PDFToMarkdownServiceServicer):
    """gRPC сервис для конвертации PDF в Markdown"""
    
    def __init__(self):
        self.conversion_service = PDFConversionService()
    
    async def ConvertPDF(self, request: pdf_to_md_pb2.ConvertPDFRequest, context) -> pdf_to_md_pb2.ConvertPDFResponse:
        """Конвертация PDF в Markdown"""
        try:
            logger.info(f"[grpc] Получен запрос на конвертацию: doc_id={request.doc_id}")
            
            # Выполняем конвертацию
            result = await self.conversion_service.convert_pdf(
                pdf_content=request.pdf_content,
                doc_id=request.doc_id or "unknown",
                model_id=request.model_id if request.model_id else None
            )
            
            # Преобразуем результат в gRPC ответ
            metadata_json = None
            if result.metadata:
                metadata_json = json.dumps(result.metadata, ensure_ascii=False)
            
            return pdf_to_md_pb2.ConvertPDFResponse(
                success=result.success,
                doc_id=result.doc_id,
                markdown_content=result.markdown_content,
                images=result.images,
                metadata_json=metadata_json,
                message=result.message
            )
            
        except Exception as e:
            logger.error(f"[grpc] Ошибка конвертации: {e}")
            return pdf_to_md_pb2.ConvertPDFResponse(
                success=False,
                doc_id=request.doc_id or "unknown",
                markdown_content="",
                images={},
                metadata_json=None,
                message=f"Ошибка конвертации: {str(e)}"
            )
    
    async def GetModels(self, request: pdf_to_md_pb2.GetModelsRequest, context) -> pdf_to_md_pb2.GetModelsResponse:
        """Получение списка доступных моделей"""
        try:
            logger.info("[grpc] Получен запрос на список моделей")
            
            models_data = await self.conversion_service.get_available_models()
            
            # Преобразуем модели в gRPC формат
            models = {}
            for model_id, model_info in models_data["models"].items():
                models[model_id] = pdf_to_md_pb2.ModelInfo(
                    name=model_info["name"],
                    description=model_info["description"],
                    enabled=model_info["enabled"],
                    default=model_info["default"]
                )
            
            return pdf_to_md_pb2.GetModelsResponse(
                models=models,
                default_model=models_data["default_model"]
            )
            
        except Exception as e:
            logger.error(f"[grpc] Ошибка получения моделей: {e}")
            return pdf_to_md_pb2.GetModelsResponse(
                models={},
                default_model=""
            )
    
    async def SetDefaultModel(self, request: pdf_to_md_pb2.SetDefaultModelRequest, context) -> pdf_to_md_pb2.SetDefaultModelResponse:
        """Установка модели по умолчанию"""
        try:
            logger.info(f"[grpc] Установка модели по умолчанию: {request.model_id}")
            
            success = await self.conversion_service.set_default_model(request.model_id)
            
            if success:
                return pdf_to_md_pb2.SetDefaultModelResponse(
                    success=True,
                    message=f"Модель {request.model_id} установлена по умолчанию"
                )
            else:
                return pdf_to_md_pb2.SetDefaultModelResponse(
                    success=False,
                    message=f"Не удалось установить модель {request.model_id} по умолчанию"
                )
                
        except Exception as e:
            logger.error(f"[grpc] Ошибка установки модели по умолчанию: {e}")
            return pdf_to_md_pb2.SetDefaultModelResponse(
                success=False,
                message=f"Ошибка: {str(e)}"
            )
    
    async def EnableModel(self, request: pdf_to_md_pb2.EnableModelRequest, context) -> pdf_to_md_pb2.EnableModelResponse:
        """Включение/отключение модели"""
        try:
            logger.info(f"[grpc] {'Включение' if request.enabled else 'Отключение'} модели: {request.model_id}")
            
            if request.enabled:
                success = await self.conversion_service.enable_model(request.model_id)
                action = "включить"
            else:
                success = await self.conversion_service.disable_model(request.model_id)
                action = "отключить"
            
            if success:
                return pdf_to_md_pb2.EnableModelResponse(
                    success=True,
                    message=f"Модель {request.model_id} успешно {action}ена"
                )
            else:
                return pdf_to_md_pb2.EnableModelResponse(
                    success=False,
                    message=f"Не удалось {action} модель {request.model_id}"
                )
                
        except Exception as e:
            logger.error(f"[grpc] Ошибка изменения состояния модели: {e}")
            return pdf_to_md_pb2.EnableModelResponse(
                success=False,
                message=f"Ошибка: {str(e)}"
            )
    
    async def ConvertPDFWithProgress(self, request: pdf_to_md_pb2.ConvertPDFRequest, context) -> pdf_to_md_pb2.ProgressUpdate:
        """Конвертация с отслеживанием прогресса (streaming)"""
        try:
            logger.info(f"[grpc] Получен запрос на конвертацию с прогрессом: doc_id={request.doc_id}")
            
            # Функция для отправки обновлений прогресса
            def progress_callback(progress: ProgressUpdate):
                try:
                    # Создаем gRPC сообщение прогресса
                    grpc_progress = pdf_to_md_pb2.ProgressUpdate(
                        doc_id=progress.doc_id,
                        percent=progress.percent,
                        phase=progress.phase,
                        message=progress.message
                    )
                    
                    # Отправляем обновление (это нужно будет реализовать через queue или другой механизм)
                    # Пока просто логируем
                    logger.info(f"[grpc] Прогресс: {progress.percent}% - {progress.message}")
                    
                except Exception as e:
                    logger.warning(f"[grpc] Ошибка отправки прогресса: {e}")
            
            # Выполняем конвертацию с отслеживанием прогресса
            result = await self.conversion_service.convert_pdf(
                pdf_content=request.pdf_content,
                doc_id=request.doc_id or "unknown",
                model_id=request.model_id if request.model_id else None,
                on_progress=progress_callback
            )
            
            # Отправляем финальный результат как последнее обновление прогресса
            yield pdf_to_md_pb2.ProgressUpdate(
                doc_id=result.doc_id,
                percent=100,
                phase="completed",
                message=f"Конвертация завершена: {result.message}"
            )
            
        except Exception as e:
            logger.error(f"[grpc] Ошибка конвертации с прогрессом: {e}")
            yield pdf_to_md_pb2.ProgressUpdate(
                doc_id=request.doc_id or "unknown",
                percent=0,
                phase="error",
                message=f"Ошибка конвертации: {str(e)}"
            )


async def serve(port: int = 50051):
    """Запуск gRPC сервера"""
    server = aio.server(futures.ThreadPoolExecutor(max_workers=10))
    
    # Добавляем сервис
    pdf_to_md_pb2_grpc.add_PDFToMarkdownServiceServicer_to_server(
        PDFToMarkdownServicer(), server
    )
    
    # Настраиваем порт
    listen_addr = f'[::]:{port}'
    server.add_insecure_port(listen_addr)
    
    logger.info(f"[grpc] Запуск сервера на {listen_addr}")
    
    # Запускаем сервер
    await server.start()
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("[grpc] Получен сигнал остановки")
        await server.stop(grace=5.0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())
