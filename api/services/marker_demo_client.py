"""Клиент для интеграции с pdf_to_md_marker_demo.py"""
import logging
import asyncio
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Callable
import sys
import os

# Импорт будет выполнен динамически в методе convert_pdf
convert_pdf_to_markdown_marker_async = None

logger = logging.getLogger(__name__)


class MarkerDemoClient:
    """Клиент для работы с pdf_to_md_marker_demo.py"""
    
    def __init__(self):
        self.is_available = convert_pdf_to_markdown_marker_async is not None
    
    async def convert_pdf(
        self, 
        pdf_content: bytes,
        doc_id: str,
        model_id: Optional[str] = None,
        timeout: int = 3600,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Конвертация PDF в Markdown с использованием marker_demo
        
        Args:
            pdf_content: Содержимое PDF файла
            doc_id: ID документа
            model_id: ID модели (игнорируется, используется Marker)
            timeout: Таймаут в секундах
            on_progress: Callback для отслеживания прогресса
            
        Returns:
            Результат конвертации
        """
        # Динамический импорт marker_demo
        global convert_pdf_to_markdown_marker_async
        
        if convert_pdf_to_markdown_marker_async is None:
            try:
                # Добавляем путь к pdf_to_md модулю
                pdf_to_md_path = Path("/app/pdf_to_md")
                logger.info(f"[marker_demo_client] Путь к pdf_to_md: {pdf_to_md_path}")
                logger.info(f"[marker_demo_client] Путь существует: {pdf_to_md_path.exists()}")
                
                if pdf_to_md_path.exists():
                    sys.path.insert(0, str(pdf_to_md_path))
                    logger.info(f"[marker_demo_client] Добавлен в sys.path: {str(pdf_to_md_path)}")
                    
                    from pdf_to_md_marker_demo import convert_pdf_to_markdown_marker_async
                    logger.info("[marker_demo_client] Успешно импортирован pdf_to_md_marker_demo")
                else:
                    logger.error(f"[marker_demo_client] Путь не существует: {pdf_to_md_path}")
                    return {
                        "success": False,
                        "doc_id": doc_id,
                        "markdown_content": "",
                        "images": {},
                        "metadata": None,
                        "message": f"Путь к pdf_to_md не найден: {pdf_to_md_path}"
                    }
            except ImportError as e:
                logger.error(f"Не удалось импортировать pdf_to_md_marker_demo: {e}")
                return {
                    "success": False,
                    "doc_id": doc_id,
                    "markdown_content": "",
                    "images": {},
                    "metadata": None,
                    "message": f"pdf_to_md_marker_demo не доступен: {e}"
                }
        
        if convert_pdf_to_markdown_marker_async is None:
            return {
                "success": False,
                "doc_id": doc_id,
                "markdown_content": "",
                "images": {},
                "metadata": None,
                "message": "pdf_to_md_marker_demo не доступен"
            }
        
        # Создаем временную директорию для работы
        temp_dir = Path(tempfile.mkdtemp(prefix=f"marker_demo_{doc_id}_"))
        result_data = None
        
        try:
            # Сохраняем PDF во временную директорию
            pdf_path = temp_dir / f"{doc_id}.pdf"
            pdf_path.write_bytes(pdf_content)
            
            logger.info(f"[marker_demo] Начинаем конвертацию: doc_id={doc_id}, pdf_size={len(pdf_content)} bytes")
            
            # Callback для прогресса
            def progress_callback(progress_data: Dict[str, Any]) -> None:
                """Преобразует прогресс marker_demo в формат системы"""
                try:
                    if on_progress:
                        # Преобразуем формат прогресса
                        converted_progress = {
                            "percent": progress_data.get("progress_percent", 0),
                            "phase": progress_data.get("stage", "processing"),
                            "message": f"Обработка: {progress_data.get('stage', 'processing')}",
                            "last_message": f"Страниц обработано: {progress_data.get('pages_processed', 0)}/{progress_data.get('total_pages', 0)}"
                        }
                        on_progress(converted_progress)
                except Exception as e:
                    logger.warning(f"[marker_demo] Ошибка в progress callback: {e}")
            
            # Callback для завершения
            def complete_callback(complete_data: Dict[str, Any]) -> None:
                """Обрабатывает результат конвертации"""
                nonlocal result_data
                result_data = complete_data
            
            # Запускаем асинхронную конвертацию
            await convert_pdf_to_markdown_marker_async(
                str(pdf_path),
                str(temp_dir),
                on_progress=progress_callback,
                on_complete=complete_callback
            )
            
            # Ждем результат
            if result_data and result_data.get("success"):
                logger.info(f"[marker_demo] Конвертация завершена успешно: doc_id={doc_id}")
                
                # Читаем markdown файл
                markdown_content = ""
                markdown_file = Path(result_data["markdown_file"])
                if markdown_file.exists():
                    markdown_content = markdown_file.read_text(encoding="utf-8", errors="ignore")
                
                # Собираем изображения
                images = {}
                output_dir = Path(result_data["output_dir"])
                image_extensions = ["*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp"]
                
                for ext in image_extensions:
                    for img_file in output_dir.glob(ext):
                        try:
                            img_data = img_file.read_bytes()
                            images[img_file.name] = img_data
                            logger.info(f"[marker_demo] Загружено изображение: {img_file.name}")
                        except Exception as e:
                            logger.warning(f"[marker_demo] Ошибка загрузки изображения {img_file.name}: {e}")
                
                # Создаем метаданные
                metadata = {
                    "pages_processed": result_data.get("pages_processed", 0),
                    "processing_time": result_data.get("processing_time", 0),
                    "throughput": result_data.get("throughput", 0),
                    "file_size_mb": result_data.get("file_size_mb", 0),
                    "images_count": result_data.get("images_count", 0),
                    "converter": "marker_demo"
                }
                
                return {
                    "success": True,
                    "doc_id": doc_id,
                    "markdown_content": markdown_content,
                    "images": images,
                    "metadata": metadata,
                    "message": "Конвертация завершена успешно"
                }
            else:
                error_msg = result_data.get("error", "Неизвестная ошибка") if result_data else "Конвертация не завершилась"
                logger.error(f"[marker_demo] Ошибка конвертации: {error_msg}")
                return {
                    "success": False,
                    "doc_id": doc_id,
                    "markdown_content": "",
                    "images": {},
                    "metadata": None,
                    "message": f"Ошибка конвертации: {error_msg}"
                }
                
        except Exception as e:
            logger.exception(f"[marker_demo] Исключение при конвертации: {e}")
            return {
                "success": False,
                "doc_id": doc_id,
                "markdown_content": "",
                "images": {},
                "metadata": None,
                "message": f"Исключение: {str(e)}"
            }
        finally:
            # Очищаем временную директорию
            try:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    logger.info(f"[marker_demo] Временная директория очищена: {temp_dir}")
            except Exception as e:
                logger.warning(f"[marker_demo] Ошибка очистки временной директории: {e}")
    
    async def get_models(self) -> Dict[str, Any]:
        """Получение информации о доступных моделях"""
        # Проверяем доступность marker_demo
        global convert_pdf_to_markdown_marker_async
        if convert_pdf_to_markdown_marker_async is None:
            try:
                pdf_to_md_path = Path("/app/pdf_to_md")
                if pdf_to_md_path.exists():
                    sys.path.insert(0, str(pdf_to_md_path))
                    from pdf_to_md_marker_demo import convert_pdf_to_markdown_marker_async
            except ImportError:
                pass
        
        is_available = convert_pdf_to_markdown_marker_async is not None
        
        return {
            "models": {
                "marker": {
                    "name": "Marker PDF to Markdown",
                    "description": "Конвертер PDF в Markdown с использованием Marker",
                    "enabled": is_available,
                    "default": True
                }
            },
            "default_model": "marker"
        }
    
    async def set_default_model(self, model_id: str) -> bool:
        """Установка модели по умолчанию (только marker поддерживается)"""
        global convert_pdf_to_markdown_marker_async
        is_available = convert_pdf_to_markdown_marker_async is not None
        return model_id == "marker" and is_available
    
    async def enable_model(self, model_id: str, enabled: bool = True) -> bool:
        """Включение/отключение модели (только marker поддерживается)"""
        global convert_pdf_to_markdown_marker_async
        is_available = convert_pdf_to_markdown_marker_async is not None
        return model_id == "marker" and is_available


# Глобальный экземпляр клиента
marker_demo_client = MarkerDemoClient()
