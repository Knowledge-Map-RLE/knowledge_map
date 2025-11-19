#!/usr/bin/env python3
"""
gRPC сервер для PDF to Markdown конвертации
"""
import asyncio
import logging
import socket
import sys
import subprocess
import platform
import json
from pathlib import Path
from typing import Dict, Any

import grpc
from concurrent import futures

# Добавляем путь к proto файлам
sys.path.append(str(Path(__file__).parent))

# Импортируем сгенерированные proto файлы
try:
    import pdf_to_md_pb2
    import pdf_to_md_pb2_grpc
except ImportError:
    # Если proto файлы не сгенерированы, генерируем их
    import subprocess
    import os
    
    proto_path = Path(__file__).parent.parent / "proto"
    src_path = Path(__file__).parent
    
    subprocess.run([
        sys.executable, "-m", "grpc_tools.protoc",
        f"--proto_path={proto_path}",
        f"--python_out={src_path}",
        f"--grpc_python_out={src_path}",
        str(proto_path / "pdf_to_md.proto")
    ], check=True)
    
    import pdf_to_md_pb2
    import pdf_to_md_pb2_grpc

# Импортируем наши модули конвертации
sys.path.append(str(Path(__file__).parent))

# Настройка логирования
import os
os.makedirs('logs', exist_ok=True)

# Настройка UTF-8 для консольного вывода на Windows
stream_handler = logging.StreamHandler()
if hasattr(stream_handler.stream, 'reconfigure'):
    stream_handler.stream.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/pdf_to_md.log', encoding='utf-8'),
        stream_handler
    ]
)
logger = logging.getLogger(__name__)

# Импортируем сервис конвертации
from services.conversion_service import ConversionService
logger.info("[grpc] Архитектура с Docling загружена")


def is_port_available(port: int) -> bool:
    """Проверяет, доступен ли порт для использования"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('localhost', port))
            return result != 0  # Порт свободен, если соединение не удалось
    except Exception:
        return False


def get_process_using_port(port: int) -> int:
    """Возвращает PID процесса, использующего указанный порт"""
    try:
        if platform.system() == "Windows":
            # Для Windows используем netstat
            result = subprocess.run(
                ['netstat', '-ano'], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if f':{port}' in line and 'LISTENING' in line:
                        parts = line.split()
                        if len(parts) >= 5:
                            return int(parts[-1])
        else:
            # Для Linux/Mac используем lsof
            result = subprocess.run(
                ['lsof', '-ti', f':{port}'], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip())
    except Exception as e:
        logger.warning(f"[grpc] Ошибка при поиске процесса на порту {port}: {e}")
    return None


def kill_process_on_port(port: int) -> bool:
    """Завершает процесс, использующий указанный порт"""
    pid = get_process_using_port(port)
    if pid is None:
        logger.info(f"[grpc] Порт {port} свободен")
        return True
    
    try:
        logger.warning(f"[grpc] Порт {port} занят процессом PID {pid}, принудительно завершаем процесс...")
        
        if platform.system() == "Windows":
            # Сразу используем принудительное завершение
            result = subprocess.run(
                ['taskkill', '/PID', str(pid), '/F'], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            
            # Если taskkill не сработал, пробуем PowerShell с правами администратора
            if result.returncode != 0:
                logger.warning(f"[grpc] taskkill не сработал, пробуем PowerShell с правами администратора...")
                ps_command = f"Stop-Process -Id {pid} -Force -ErrorAction Stop"
                result = subprocess.run(
                    ['powershell', '-Command', ps_command], 
                    capture_output=True, 
                    text=True, 
                    timeout=15
                )
            
            # Если и PowerShell не сработал, пробуем PowerShell с правами администратора
            if result.returncode != 0:
                logger.warning(f"[grpc] PowerShell не сработал, пробуем PowerShell с правами администратора...")
                ps_command = f"Start-Process powershell -ArgumentList '-Command Stop-Process -Id {pid} -Force' -Verb RunAs -WindowStyle Hidden"
                result = subprocess.run(
                    ['powershell', '-Command', ps_command], 
                    capture_output=True, 
                    text=True, 
                    timeout=15
                )
            
            # Если и это не сработало, пробуем wmic
            if result.returncode != 0:
                logger.warning(f"[grpc] PowerShell с правами администратора не сработал, пробуем wmic...")
                result = subprocess.run(
                    ['wmic', 'process', 'where', f'ProcessId={pid}', 'delete'], 
                    capture_output=True, 
                    text=True, 
                    timeout=10
                )
        else:
            # Для Linux/Mac сразу используем SIGKILL
            result = subprocess.run(
                ['kill', '-9', str(pid)], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
        
        # Ждем завершения процесса
        import time
        time.sleep(3)
        
        # Проверяем, освободился ли порт
        if is_port_available(port):
            logger.info(f"[grpc] Процесс PID {pid} успешно завершен, порт {port} освобожден")
            return True
        else:
            logger.error(f"[grpc] Процесс PID {pid} не был завершен, порт {port} все еще занят")
            return False
            
    except Exception as e:
        logger.error(f"[grpc] Ошибка при завершении процесса PID {pid}: {e}")
        return False


def ensure_port_available(port: int) -> bool:
    """Обеспечивает доступность порта, завершая процессы при необходимости"""
    if is_port_available(port):
        logger.info(f"[grpc] Порт {port} доступен")
        return True
    
    logger.warning(f"[grpc] Порт {port} занят, принудительно освобождаем...")
    
    # Принудительно завершаем процесс
    if kill_process_on_port(port):
        return True
    
    # Если не удалось завершить, пробуем еще раз с большей задержкой
    logger.warning(f"[grpc] Повторная попытка завершения процесса на порту {port}...")
    import time
    time.sleep(2)
    
    if kill_process_on_port(port):
        return True
    
    logger.error(f"[grpc] Не удалось освободить порт {port} после всех попыток")
    return False


# Логируем запуск
logger.info("PDF to MD gRPC сервер инициализируется")
logger.info("PDF to MD gRPC сервер запускается...")


class PDFToMarkdownServicer(pdf_to_md_pb2_grpc.PDFToMarkdownServiceServicer):
    """gRPC сервис для конвертации PDF в Markdown"""

    def __init__(self):
        # Используем архитектуру с поддержкой Docling
        self.conversion_service = ConversionService()
        logger.info("[grpc] Инициализирована архитектура с поддержкой Docling")
    
    async def ConvertPDF(self, request, context):
        """Конвертация PDF в Markdown"""
        try:
            logger.info(f"[grpc] Начинаем конвертацию PDF: doc_id={request.doc_id}")
            logger.info(f"[grpc] Получен запрос с размером PDF: {len(request.pdf_content)} байт")
            logger.info(f"[grpc] Запрошенная модель: {request.model_id or 'None (будет использована по умолчанию)'}")

            # Используем сервис конвертации с поддержкой Docling
            result = await self.conversion_service.convert_pdf(
                pdf_content=request.pdf_content,
                doc_id=request.doc_id or None,
                model_id=request.model_id or None,
                use_coordinate_extraction=True  # По умолчанию включено
            )

            if result.success:
                logger.info(f"[grpc] Конвертация завершена успешно: doc_id={request.doc_id}")

                # Handle S3 images vs traditional images
                response_images = {}
                message = "Конвертация завершена успешно"

                # Check if we have S3 images
                if hasattr(result, 's3_images') and result.s3_images:
                    logger.info(f"[grpc] S3 изображений: {len(result.s3_images)}")
                    message = f"Конвертация завершена успешно (извлечено {len(result.s3_images)} изображений в S3)"
                    # For gRPC compatibility, keep images empty (they're in S3)
                    response_images = {}
                else:
                    # Traditional embedded images - ensure they are bytes
                    if result.images:
                        for filename, img_data in result.images.items():
                            if isinstance(img_data, bytes):
                                response_images[filename] = img_data
                            else:
                                logger.warning(f"[grpc] Skipping non-bytes image: {filename} (type: {type(img_data)})")

                # Prepare S3 keys for response
                docling_raw_s3_key = getattr(result, 'docling_raw_s3_key', None) or ""
                formatted_s3_key = getattr(result, 'formatted_s3_key', None) or ""

                return pdf_to_md_pb2.ConvertPDFResponse(
                    success=True,
                    doc_id=result.doc_id,
                    markdown_content=result.markdown_content,
                    images=response_images,
                    metadata_json=json.dumps(result.metadata) if result.metadata else "",
                    message=message,
                    docling_raw_s3_key=docling_raw_s3_key,
                    formatted_s3_key=formatted_s3_key
                )
            else:
                logger.error(f"[grpc] Ошибка конвертации: {result.error_message}")
                return pdf_to_md_pb2.ConvertPDFResponse(
                    success=False,
                    doc_id=result.doc_id,
                    markdown_content="",
                    images={},
                    message=f"Ошибка конвертации: {result.error_message}"
                )

        except Exception as e:
            logger.error(f"[grpc] Исключение при конвертации: {e}")
            return pdf_to_md_pb2.ConvertPDFResponse(
                success=False,
                doc_id=request.doc_id or "unknown",
                markdown_content="",
                images={},
                message=f"Исключение: {str(e)}"
            )
    
    async def GetModels(self, request, context):
        """Получение списка доступных моделей"""
        try:
            # Получаем доступные модели из сервиса
            models_data = self.conversion_service.model_service.get_available_models()
            default_model = self.conversion_service.model_service.get_default_model()

            models = {}
            for model_id, model_info in models_data.items():
                models[model_id] = pdf_to_md_pb2.ModelInfo(
                    name=model_info.name,
                    description=model_info.description,
                    enabled=(model_info.status.value == "enabled"),
                    default=model_info.is_default
                )

            return pdf_to_md_pb2.GetModelsResponse(
                models=models,
                default_model=default_model
            )
        except Exception as e:
            logger.error(f"[grpc] Ошибка получения моделей: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pdf_to_md_pb2.GetModelsResponse()
    
    async def SetDefaultModel(self, request, context):
        """Установка модели по умолчанию"""
        try:
            # Устанавливаем модель по умолчанию через сервис
            success = self.conversion_service.model_service.set_default_model(request.model_id)

            return pdf_to_md_pb2.SetDefaultModelResponse(
                success=success,
                message=f"Модель {request.model_id} установлена по умолчанию" if success else f"Модель {request.model_id} не найдена"
            )
        except Exception as e:
            logger.error(f"[grpc] Ошибка установки модели по умолчанию: {e}")
            return pdf_to_md_pb2.SetDefaultModelResponse(
                success=False,
                message=f"Ошибка: {str(e)}"
            )
    
    async def EnableModel(self, request, context):
        """Включение/отключение модели"""
        try:
            # Включаем/отключаем модель через сервис
            if request.enabled:
                success = self.conversion_service.model_service.enable_model(request.model_id)
                action = "включена"
            else:
                success = self.conversion_service.model_service.disable_model(request.model_id)
                action = "отключена"

            return pdf_to_md_pb2.EnableModelResponse(
                success=success,
                message=f"Модель {request.model_id} {action}" if success else f"Модель {request.model_id} не найдена"
            )
        except Exception as e:
            logger.error(f"[grpc] Ошибка изменения состояния модели: {e}")
            return pdf_to_md_pb2.EnableModelResponse(
                success=False,
                message=f"Ошибка: {str(e)}"
            )
    
    async def ConvertPDFWithProgress(self, request, context):
        """Конвертация с отслеживанием прогресса (streaming)"""
        try:
            logger.info(f"[grpc] Начинаем конвертацию с прогрессом: doc_id={request.doc_id}")

            # TODO: Реализовать streaming прогресса для Docling
            # Пока используем обычную конвертацию
            result = await self.conversion_service.convert_pdf(
                pdf_content=request.pdf_content,
                doc_id=request.doc_id or None,
                model_id=request.model_id or None,
                use_coordinate_extraction=True
            )

            if result.success:
                # Отправляем финальное обновление
                final_update = pdf_to_md_pb2.ProgressUpdate(
                    doc_id=request.doc_id or "unknown",
                    percent=100,
                    phase="completed",
                    message="Конвертация завершена успешно"
                )
                yield final_update
            else:
                error_update = pdf_to_md_pb2.ProgressUpdate(
                    doc_id=request.doc_id or "unknown",
                    percent=0,
                    phase="failed",
                    message=f"Ошибка: {result.error_message}"
                )
                yield error_update

        except Exception as e:
            logger.error(f"[grpc] Исключение при конвертации с прогрессом: {e}")
            error_update = pdf_to_md_pb2.ProgressUpdate(
                doc_id=request.doc_id or "unknown",
                percent=0,
                phase="failed",
                message=f"Исключение: {str(e)}"
            )
            yield error_update


async def serve():
    """Запуск gRPC сервера"""
    logger.info("[grpc] Инициализация gRPC сервера")

    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    
    # Добавляем сервис
    pdf_to_md_pb2_grpc.add_PDFToMarkdownServiceServicer_to_server(
        PDFToMarkdownServicer(), server
    )
    
    # Настраиваем порт - всегда используем 50053
    port = 50053
    listen_addr = f'0.0.0.0:{port}'
    
    try:
        # Обеспечиваем доступность порта 50053
        if not ensure_port_available(port):
            raise RuntimeError(f"Не удалось освободить порт {port}. Сервер не может быть запущен.")
        
        server.add_insecure_port(listen_addr)
        logger.info(f"[grpc] Запуск сервера на {listen_addr}")
        
        await server.start()
        logger.info("[grpc] Сервер запущен и готов к приему запросов")
        logger.info("[grpc] Ожидание запросов...")
        await server.wait_for_termination()
        
    except RuntimeError as e:
        logger.error(f"[grpc] Ошибка привязки к порту: {e}")
        logger.error("[grpc] Сервер не может быть запущен")
        raise
    except Exception as e:
        logger.error(f"[grpc] Неожиданная ошибка при запуске сервера: {e}")
        raise


if __name__ == '__main__':
    asyncio.run(serve())