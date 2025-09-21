"""Реестр моделей для конвертации PDF в Markdown"""
import logging
from typing import Dict, Any, Optional, Callable
from pathlib import Path as SysPath

# Импорты с обработкой ошибок
try:
    from .marker_utils import _run_marker_on_pdf as marker_legacy_convert
    MARKER_LEGACY_AVAILABLE = True
except ImportError:
    MARKER_LEGACY_AVAILABLE = False

try:
    from .marker_proper_model import marker_proper_model
    MARKER_PROPER_AVAILABLE = True
except ImportError:
    MARKER_PROPER_AVAILABLE = False

try:
    from .huridocs_model import huridocs_model
    HURIDOCS_AVAILABLE = True
except ImportError:
    HURIDOCS_AVAILABLE = False

# Import Docling model
try:
    from ..services.models.docling_model import DoclingModel
    DOCLING_AVAILABLE = True
except ImportError as e:
    print(f"Docling not available: {e}")
    DOCLING_AVAILABLE = False

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Реестр доступных моделей конвертации"""
    
    def __init__(self):
        self._models: Dict[str, Any] = {}
        # Определяем модель по умолчанию
        if DOCLING_AVAILABLE:
            self._default_model = "docling"
        elif HURIDOCS_AVAILABLE:
            self._default_model = "huridocs"
        elif MARKER_PROPER_AVAILABLE:
            self._default_model = "marker_proper"
        elif MARKER_LEGACY_AVAILABLE:
            self._default_model = "marker_legacy"
        else:
            self._default_model = "docling"  # Fallback
        self._register_models()
    
    def _register_models(self):
        """Регистрирует доступные модели"""
        # Docling (модель по умолчанию, если доступна)
        if DOCLING_AVAILABLE:
            docling_model = DoclingModel()
            self._models["docling"] = {
                "name": "Docling",
                "description": "Docling PDF to Markdown conversion with advanced document understanding",
                "convert_func": self._docling_convert_wrapper,
                "enabled": True,
                "default": True
            }
        
        # HURIDOCS (резервная модель)
        if HURIDOCS_AVAILABLE:
            self._models["huridocs"] = {
                "name": "HURIDOCS",
                "description": "HURIDOCS PDF Document Layout Analysis - анализ структуры PDF и преобразование в Markdown",
                "convert_func": huridocs_model.convert_pdf_to_markdown,
                "enabled": True,
                "default": not DOCLING_AVAILABLE  # По умолчанию только если Docling недоступен
            }
        
        # Marker Proper (альтернативная модель)
        if MARKER_PROPER_AVAILABLE:
            self._models["marker_proper"] = {
                "name": "Marker Proper",
                "description": "Улучшенная модель Marker с оптимизированной обработкой",
                "convert_func": marker_proper_model.convert_pdf_to_markdown,
                "enabled": True,
                "default": False
            }
        
        # Marker Legacy (старая модель)
        if MARKER_LEGACY_AVAILABLE:
            self._models["marker_legacy"] = {
                "name": "Marker Legacy", 
                "description": "Оригинальная модель Marker с subprocess",
                "convert_func": marker_legacy_convert,
                "enabled": True,
                "default": False
            }
        
        # Store docling model instance for wrapper
        if DOCLING_AVAILABLE:
            self._docling_model = docling_model
        
        logger.info(f"[model_registry] Зарегистрировано моделей: {len(self._models)}")
        if DOCLING_AVAILABLE:
            logger.info("[model_registry] Docling модель зарегистрирована как модель по умолчанию")
    
    async def _docling_convert_wrapper(
        self, 
        tmp_dir: SysPath, 
        *, 
        on_progress: Optional[Callable[[dict], None]] = None, 
        doc_id: Optional[str] = None
    ) -> SysPath:
        """
        Wrapper для Docling модели, совместимый с интерфейсом других моделей
        
        Args:
            tmp_dir: Временная директория с PDF файлом
            on_progress: Callback для отслеживания прогресса
            doc_id: ID документа для логирования
            
        Returns:
            Путь к директории с результатами конвертации
        """
        if not DOCLING_AVAILABLE:
            raise RuntimeError("Docling model is not available")
        
        # Найти PDF файл в временной директории
        pdf_files = list(tmp_dir.glob("*.pdf"))
        if not pdf_files:
            raise FileNotFoundError("No PDF file found in temporary directory")
        
        pdf_path = pdf_files[0]
        
        # Создать выходную директорию
        output_dir = tmp_dir / "docling_output"
        
        # Выполнить конвертацию
        result_dir = await self._docling_model.convert(
            input_path=pdf_path,
            output_dir=output_dir,
            on_progress=on_progress
        )
        
        return result_dir
    
    def get_available_models(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает список доступных моделей"""
        return {
            model_id: {
                "name": info["name"],
                "description": info["description"],
                "enabled": info["enabled"],
                "default": info["default"]
            }
            for model_id, info in self._models.items()
        }
    
    def get_default_model(self) -> str:
        """Возвращает ID модели по умолчанию"""
        return self._default_model
    
    def set_default_model(self, model_id: str) -> bool:
        """Устанавливает модель по умолчанию"""
        if model_id not in self._models:
            logger.error(f"[model_registry] Модель {model_id} не найдена")
            return False
        
        if not self._models[model_id]["enabled"]:
            logger.error(f"[model_registry] Модель {model_id} отключена")
            return False
        
        # Сбрасываем флаг default для всех моделей
        for info in self._models.values():
            info["default"] = False
        
        # Устанавливаем новую модель по умолчанию
        self._models[model_id]["default"] = True
        self._default_model = model_id
        
        logger.info(f"[model_registry] Установлена модель по умолчанию: {model_id}")
        return True
    
    def enable_model(self, model_id: str) -> bool:
        """Включает модель"""
        if model_id not in self._models:
            logger.error(f"[model_registry] Модель {model_id} не найдена")
            return False
        
        self._models[model_id]["enabled"] = True
        logger.info(f"[model_registry] Модель {model_id} включена")
        return True
    
    def disable_model(self, model_id: str) -> bool:
        """Отключает модель"""
        if model_id not in self._models:
            logger.error(f"[model_registry] Модель {model_id} не найдена")
            return False
        
        # Нельзя отключить модель по умолчанию
        if self._models[model_id]["default"]:
            logger.error(f"[model_registry] Нельзя отключить модель по умолчанию: {model_id}")
            return False
        
        self._models[model_id]["enabled"] = False
        logger.info(f"[model_registry] Модель {model_id} отключена")
        return True
    
    async def convert_pdf(
        self, 
        tmp_dir: SysPath, 
        *, 
        on_progress: Optional[Callable[[dict], None]] = None, 
        doc_id: Optional[str] = None,
        model_id: Optional[str] = None
    ) -> SysPath:
        """
        Конвертирует PDF в Markdown с использованием указанной модели
        
        Args:
            tmp_dir: Временная директория с PDF файлом
            on_progress: Callback для отслеживания прогресса
            doc_id: ID документа для логирования
            model_id: ID модели (если None, используется модель по умолчанию)
            
        Returns:
            Путь к директории с результатами конвертации
        """
        # Выбираем модель
        if model_id is None:
            model_id = self._default_model
        
        if model_id not in self._models:
            raise ValueError(f"Модель {model_id} не найдена")
        
        model_info = self._models[model_id]
        if not model_info["enabled"]:
            raise ValueError(f"Модель {model_id} отключена")
        
        logger.info(f"[model_registry] Используем модель: {model_id} ({model_info['name']})")
        
        # Выполняем конвертацию
        convert_func = model_info["convert_func"]
        
        # Все модели возвращают путь к директории с результатами
        result_dir = await convert_func(tmp_dir, on_progress=on_progress, doc_id=doc_id)
        return result_dir
    
    def get_model_info(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Возвращает информацию о модели"""
        return self._models.get(model_id)


# Глобальный реестр моделей
model_registry = ModelRegistry()
