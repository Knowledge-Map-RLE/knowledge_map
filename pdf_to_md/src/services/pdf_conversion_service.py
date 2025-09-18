"""Сервис конвертации PDF в Markdown"""
import logging
import tempfile
import asyncio
from pathlib import Path as SysPath
from typing import Dict, Any, Optional, Callable

from ..models.model_registry import model_registry
from ..models.marker_utils import _collect_marker_outputs
from ..schemas.api import ConvertResponse, ProgressUpdate

logger = logging.getLogger(__name__)


class PDFConversionService:
    """Сервис для конвертации PDF в Markdown"""
    
    def __init__(self):
        self.model_registry = model_registry
    
    async def convert_pdf(
        self, 
        pdf_content: bytes,
        doc_id: str,
        model_id: Optional[str] = None,
        on_progress: Optional[Callable[[ProgressUpdate], None]] = None
    ) -> ConvertResponse:
        """
        Конвертирует PDF в Markdown
        
        Args:
            pdf_content: Содержимое PDF файла
            doc_id: ID документа
            model_id: ID модели (если None, используется по умолчанию)
            on_progress: Callback для отслеживания прогресса
            
        Returns:
            Результат конвертации
        """
        logger.info(f"[pdf_conversion] Начало конвертации doc_id={doc_id}, model_id={model_id}")
        
        # Создаем временную директорию
        tmp_dir = SysPath(tempfile.mkdtemp(prefix="pdf_to_md_"))
        
        try:
            # Сохраняем PDF во временную директорию
            pdf_path = tmp_dir / f"{doc_id}.pdf"
            with open(pdf_path, "wb") as f:
                f.write(pdf_content)
            
            logger.info(f"[pdf_conversion] PDF сохранен: {pdf_path}")
            
            # Создаем callback для прогресса
            def _on_progress(payload: dict) -> None:
                if on_progress:
                    progress_update = ProgressUpdate(
                        doc_id=doc_id,
                        percent=payload.get('percent', 0),
                        phase=payload.get('phase', 'processing'),
                        message=payload.get('message', payload.get('last_message', ''))
                    )
                    try:
                        # Запускаем callback в event loop
                        loop = asyncio.get_running_loop()
                        if asyncio.iscoroutinefunction(on_progress):
                            asyncio.run_coroutine_threadsafe(on_progress(progress_update), loop)
                        else:
                            loop.call_soon_threadsafe(on_progress, progress_update)
                    except Exception as e:
                        logger.warning(f"[pdf_conversion] Ошибка отправки прогресса: {e}")
            
            # Выполняем конвертацию
            result_dir = await self.model_registry.convert_pdf(
                tmp_dir,
                on_progress=_on_progress,
                doc_id=doc_id,
                model_id=model_id
            )
            
            # Собираем результаты
            outputs = await _collect_marker_outputs(result_dir, pdf_stem=doc_id)
            
            # Читаем markdown
            markdown_content = ""
            if "markdown" in outputs:
                markdown_path = outputs["markdown"]
                markdown_content = markdown_path.read_text(encoding="utf-8", errors="ignore")
                logger.info(f"[pdf_conversion] Markdown прочитан: {len(markdown_content)} символов")
            else:
                logger.warning(f"[pdf_conversion] Markdown файл не найден")
            
            # Собираем изображения
            images: Dict[str, bytes] = {}
            if "images_dir" in outputs:
                images_dir = outputs["images_dir"]
                image_extensions = ["*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp"]
                
                for ext in image_extensions:
                    for img_file in images_dir.glob(ext):
                        try:
                            image_data = img_file.read_bytes()
                            images[img_file.name] = image_data
                            logger.info(f"[pdf_conversion] Изображение добавлено: {img_file.name} ({len(image_data)} байт)")
                        except Exception as e:
                            logger.warning(f"[pdf_conversion] Ошибка чтения изображения {img_file.name}: {e}")
            
            # Читаем метаданные
            metadata = None
            if "meta" in outputs:
                meta_path = outputs["meta"]
                try:
                    import json
                    metadata = json.loads(meta_path.read_text(encoding="utf-8", errors="ignore"))
                    logger.info(f"[pdf_conversion] Метаданные прочитаны")
                except Exception as e:
                    logger.warning(f"[pdf_conversion] Ошибка чтения метаданных: {e}")
            
            logger.info(f"[pdf_conversion] Конвертация завершена успешно: doc_id={doc_id}")
            
            return ConvertResponse(
                success=True,
                doc_id=doc_id,
                markdown_content=markdown_content,
                images=images,
                metadata=metadata,
                message="Конвертация завершена успешно"
            )
            
        except Exception as e:
            logger.error(f"[pdf_conversion] Ошибка конвертации doc_id={doc_id}: {e}")
            return ConvertResponse(
                success=False,
                doc_id=doc_id,
                markdown_content="",
                images={},
                metadata=None,
                message=f"Ошибка конвертации: {str(e)}"
            )
        
        finally:
            # Удаляем временную директорию
            try:
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)
                logger.info(f"[pdf_conversion] Временная директория удалена: {tmp_dir}")
            except Exception as e:
                logger.warning(f"[pdf_conversion] Ошибка удаления временной директории: {e}")
    
    async def get_available_models(self) -> Dict[str, Any]:
        """Возвращает список доступных моделей"""
        return {
            "models": self.model_registry.get_available_models(),
            "default_model": self.model_registry.get_default_model()
        }
    
    async def set_default_model(self, model_id: str) -> bool:
        """Устанавливает модель по умолчанию"""
        return self.model_registry.set_default_model(model_id)
    
    async def enable_model(self, model_id: str) -> bool:
        """Включает модель"""
        return self.model_registry.enable_model(model_id)
    
    async def disable_model(self, model_id: str) -> bool:
        """Отключает модель"""
        return self.model_registry.disable_model(model_id)
