#!/usr/bin/env python3
"""
gRPC сервер для PDF to Markdown конвертации
"""
import asyncio
import logging
import sys
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

# Импортируем наш модуль конвертации
sys.path.append(str(Path(__file__).parent.parent))
from pdf_to_md_marker_demo import convert_pdf_to_markdown_marker_async

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

# Логируем запуск
logger.info("PDF to MD gRPC сервер инициализируется")
logger.info("PDF to MD gRPC сервер запускается...")


class PDFToMarkdownServicer(pdf_to_md_pb2_grpc.PDFToMarkdownServiceServicer):
    """gRPC сервис для конвертации PDF в Markdown"""
    
    def __init__(self):
        self.models = {
            "marker": {
                "name": "Marker PDF to Markdown",
                "description": "Конвертер PDF в Markdown с использованием Marker",
                "enabled": True,
                "default": True
            }
        }
        self.default_model = "marker"
    
    async def ConvertPDF(self, request, context):
        """Конвертация PDF в Markdown"""
        try:
            logger.info(f"[grpc] Начинаем конвертацию PDF: doc_id={request.doc_id}")
            logger.info(f"[grpc] Получен запрос с размером PDF: {len(request.pdf_content)} байт")
            
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
    
    # Настраиваем порт
    listen_addr = '0.0.0.0:50051'
    server.add_insecure_port(listen_addr)
    
    logger.info(f"[grpc] Запуск сервера на {listen_addr}")
    
    await server.start()
    logger.info("[grpc] Сервер запущен и готов к приему запросов")
    logger.info("[grpc] Ожидание запросов...")
    await server.wait_for_termination()


if __name__ == '__main__':
    asyncio.run(serve())