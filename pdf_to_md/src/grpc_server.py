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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/pdf_to_md.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Импортируем новую архитектуру сервисов
try:
    from services.conversion_service import ConversionService
    NEW_ARCHITECTURE = True
    logger.info("[grpc] Новая архитектура с Docling доступна")
except ImportError as e:
    # Fallback к старой архитектуре
    logger.warning(f"[grpc] Новая архитектура недоступна: {e}")
    sys.path.append(str(Path(__file__).parent.parent))
    from pdf_to_md_marker_demo import convert_pdf_to_markdown_marker_async
    NEW_ARCHITECTURE = False


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
        if NEW_ARCHITECTURE:
            # Используем новую архитектуру с поддержкой множественных моделей
            self.conversion_service = ConversionService()
            logger.info("[grpc] Инициализирована новая архитектура с поддержкой Docling")
        else:
            # Fallback к старой архитектуре
            self.models = {
                "marker": {
                    "name": "Marker PDF to Markdown",
                    "description": "Конвертер PDF в Markdown с использованием Marker",
                    "enabled": True,
                    "default": True
                }
            }
            self.default_model = "marker"
            logger.info("[grpc] Используется старая архитектура с Marker")
    
    async def ConvertPDF(self, request, context):
        """Конвертация PDF в Markdown"""
        try:
            logger.info(f"[grpc] Начинаем конвертацию PDF: doc_id={request.doc_id}")
            logger.info(f"[grpc] Получен запрос с размером PDF: {len(request.pdf_content)} байт")
            logger.info(f"[grpc] Запрошенная модель: {request.model_id or 'None (будет использована по умолчанию)'}")
            
            if NEW_ARCHITECTURE:
                # Используем новую архитектуру с поддержкой множественных моделей
                result = await self.conversion_service.convert_pdf(
                    pdf_content=request.pdf_content,
                    doc_id=request.doc_id or None,
                    model_id=request.model_id or None
                )
                
                if result.success:
                    logger.info(f"[grpc] Конвертация завершена успешно: doc_id={request.doc_id}")
                    return pdf_to_md_pb2.ConvertPDFResponse(
                        success=True,
                        doc_id=result.doc_id,
                        markdown_content=result.markdown_content,
                        images=result.images,
                        metadata_json=json.dumps(result.metadata) if result.metadata else "",
                        message="Конвертация завершена успешно"
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
            else:
                # Fallback к старой архитектуре
                return await self._convert_pdf_legacy(request, context)
                    
        except Exception as e:
            logger.error(f"[grpc] Исключение при конвертации: {e}")
            return pdf_to_md_pb2.ConvertPDFResponse(
                success=False,
                doc_id=request.doc_id or "unknown",
                markdown_content="",
                images={},
                message=f"Исключение: {str(e)}"
            )
    
    async def _convert_pdf_legacy(self, request, context):
        """Legacy конвертация PDF в Markdown (старая архитектура)"""
        # Создаем временный файл
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_file.write(request.pdf_content)
            temp_pdf_path = temp_file.name
        
        try:
            # Создаем временную папку для результатов
            temp_dir = tempfile.mkdtemp()
            try:
                # Выполняем конвертацию
                logger.info(f"[grpc] Вызываем convert_pdf_to_markdown_marker_async для {temp_pdf_path}")
                try:
                    result = await convert_pdf_to_markdown_marker_async(
                        pdf_path=temp_pdf_path,
                        output_dir=temp_dir
                    )
                except Exception as e:
                    logger.error(f"[grpc] Ошибка при вызове convert_pdf_to_markdown_marker_async: {e}")
                    import traceback
                    logger.error(f"[grpc] Traceback: {traceback.format_exc()}")
                    result = None
                
                logger.info(f"[grpc] Результат конвертации: {result}")
                
                if result and result.get('success'):
                    # Читаем markdown файл
                    markdown_path = Path(result['markdown_file'])
                    markdown_content = markdown_path.read_text(encoding='utf-8')
                    
                    # Собираем изображения
                    images = {}
                    output_dir = Path(result['output_dir'])
                    for img_file in output_dir.glob('*.{jpg,jpeg,png,gif,bmp}'):
                        images[img_file.name] = img_file.read_bytes()
                    
                    # Создаем метаданные
                    metadata = {
                        "pages_processed": result.get('pages_processed', 0),
                        "processing_time": result.get('processing_time', 0),
                        "throughput": result.get('throughput', 0),
                        "file_size_mb": result.get('file_size_mb', 0),
                        "images_count": result.get('images_count', 0)
                    }
                    
                    import json
                    metadata_json = json.dumps(metadata)
                    
                    logger.info(f"[grpc] Конвертация завершена успешно: doc_id={request.doc_id}")
                    
                    return pdf_to_md_pb2.ConvertPDFResponse(
                        success=True,
                        doc_id=request.doc_id or "unknown",
                        markdown_content=markdown_content,
                        images=images,
                        metadata_json=metadata_json,
                        message="Конвертация завершена успешно"
                    )
                else:
                    error_msg = result.get('error', 'Неизвестная ошибка') if result else 'Ошибка конвертации'
                    logger.error(f"[grpc] Ошибка конвертации: {error_msg}")
                    
                    return pdf_to_md_pb2.ConvertPDFResponse(
                        success=False,
                        doc_id=request.doc_id or "unknown",
                        markdown_content="",
                        images={},
                        message=f"Ошибка конвертации: {error_msg}"
                    )
            finally:
                # Удаляем временную папку
                import shutil
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass
        
        finally:
            # Удаляем временный файл
            try:
                os.unlink(temp_pdf_path)
            except:
                pass
    
    async def GetModels(self, request, context):
        """Получение списка доступных моделей"""
        try:
            if NEW_ARCHITECTURE:
                # Используем новую архитектуру
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
            else:
                # Fallback к старой архитектуре
                models = {}
                for model_id, model_info in self.models.items():
                    models[model_id] = pdf_to_md_pb2.ModelInfo(
                        name=model_info["name"],
                        description=model_info["description"],
                        enabled=model_info["enabled"],
                        default=model_info["default"]
                    )
                
                return pdf_to_md_pb2.GetModelsResponse(
                    models=models,
                    default_model=self.default_model
                )
        except Exception as e:
            logger.error(f"[grpc] Ошибка получения моделей: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pdf_to_md_pb2.GetModelsResponse()
    
    async def SetDefaultModel(self, request, context):
        """Установка модели по умолчанию"""
        try:
            if NEW_ARCHITECTURE:
                # Используем новую архитектуру
                success = self.conversion_service.model_service.set_default_model(request.model_id)
                
                return pdf_to_md_pb2.SetDefaultModelResponse(
                    success=success,
                    message=f"Модель {request.model_id} установлена по умолчанию" if success else f"Модель {request.model_id} не найдена"
                )
            else:
                # Fallback к старой архитектуре
                if request.model_id in self.models:
                    # Сбрасываем флаг default для всех моделей
                    for model_info in self.models.values():
                        model_info["default"] = False
                    
                    # Устанавливаем новую модель по умолчанию
                    self.models[request.model_id]["default"] = True
                    self.default_model = request.model_id
                    
                    return pdf_to_md_pb2.SetDefaultModelResponse(
                        success=True,
                        message=f"Модель {request.model_id} установлена по умолчанию"
                    )
                else:
                    return pdf_to_md_pb2.SetDefaultModelResponse(
                        success=False,
                        message=f"Модель {request.model_id} не найдена"
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
            if NEW_ARCHITECTURE:
                # Используем новую архитектуру
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
            else:
                # Fallback к старой архитектуре
                if request.model_id in self.models:
                    self.models[request.model_id]["enabled"] = request.enabled
                    action = "включена" if request.enabled else "отключена"
                    
                    return pdf_to_md_pb2.EnableModelResponse(
                        success=True,
                        message=f"Модель {request.model_id} {action}"
                    )
                else:
                    return pdf_to_md_pb2.EnableModelResponse(
                        success=False,
                        message=f"Модель {request.model_id} не найдена"
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
            
            # Создаем временный файл
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                temp_file.write(request.pdf_content)
                temp_pdf_path = temp_file.name
            
            try:
                # Создаем временную папку для результатов
                with tempfile.TemporaryDirectory() as temp_dir:
                    # Callback для прогресса
                    def on_progress(progress_data):
                        try:
                            update = pdf_to_md_pb2.ProgressUpdate(
                                doc_id=request.doc_id or "unknown",
                                percent=progress_data.get('progress_percent', 0),
                                phase=progress_data.get('stage', 'processing'),
                                message=f"Прогресс: {progress_data.get('progress_percent', 0)}%"
                            )
                            context.write(update)
                        except Exception as e:
                            logger.error(f"[grpc] Ошибка отправки прогресса: {e}")
                    
                    # Выполняем конвертацию
                    result = await convert_pdf_to_markdown_marker_async(
                        pdf_path=temp_pdf_path,
                        output_dir=temp_dir,
                        on_progress=on_progress
                    )
                    
                    if result and result.get('success'):
                        # Отправляем финальное обновление
                        final_update = pdf_to_md_pb2.ProgressUpdate(
                            doc_id=request.doc_id or "unknown",
                            percent=100,
                            phase="completed",
                            message="Конвертация завершена успешно"
                        )
                        context.write(final_update)
                    else:
                        error_msg = result.get('error', 'Неизвестная ошибка') if result else 'Ошибка конвертации'
                        error_update = pdf_to_md_pb2.ProgressUpdate(
                            doc_id=request.doc_id or "unknown",
                            percent=0,
                            phase="failed",
                            message=f"Ошибка: {error_msg}"
                        )
                        context.write(error_update)
            
            finally:
                # Удаляем временный файл
                try:
                    os.unlink(temp_pdf_path)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"[grpc] Исключение при конвертации с прогрессом: {e}")
            error_update = pdf_to_md_pb2.ProgressUpdate(
                doc_id=request.doc_id or "unknown",
                percent=0,
                phase="failed",
                message=f"Исключение: {str(e)}"
            )
            context.write(error_update)


async def serve():
    """Запуск gRPC сервера"""
    logger.info("[grpc] Инициализация gRPC сервера")
    
    # Проверяем, что Marker доступен
    try:
        import marker
        logger.info("[grpc] Marker успешно импортирован")
    except ImportError as e:
        logger.error(f"[grpc] Ошибка импорта Marker: {e}")
    
    # Проверяем, что функция конвертации доступна
    try:
        from pdf_to_md_marker_demo import convert_pdf_to_markdown_marker_async
        logger.info("[grpc] Функция convert_pdf_to_markdown_marker_async успешно импортирована")
    except ImportError as e:
        logger.error(f"[grpc] Ошибка импорта функции конвертации: {e}")
    
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