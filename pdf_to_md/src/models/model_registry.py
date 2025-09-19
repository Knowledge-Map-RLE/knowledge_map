"""Реестр моделей для конвертации PDF в Markdown"""
import logging
from typing import Dict, Any, Optional, Callable
from pathlib import Path as SysPath

from .marker_utils import _run_marker_on_pdf as marker_legacy_convert
from .marker_proper_model import marker_proper_model
from .huridocs_model import huridocs_model

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Реестр доступных моделей конвертации"""
    
    def __init__(self):
        self._models: Dict[str, Any] = {}
        self._default_model: str = "huridocs"
        self._register_models()
    
    def _register_models(self):
        """Регистрирует доступные модели"""
        # HURIDOCS (модель по умолчанию)
        self._models["huridocs"] = {
            "name": "HURIDOCS",
            "description": "HURIDOCS PDF Document Layout Analysis - анализ структуры PDF и преобразование в Markdown",
            "convert_func": huridocs_model.convert_pdf_to_markdown,
            "enabled": True,
            "default": True
        }
        
        # Marker Proper (альтернативная модель)
        self._models["marker_proper"] = {
            "name": "Marker Proper",
            "description": "Улучшенная модель Marker с оптимизированной обработкой",
            "convert_func": marker_proper_model.convert_pdf_to_markdown,
            "enabled": True,
            "default": False
        }
        
        # Marker Legacy (старая модель)
        self._models["marker_legacy"] = {
            "name": "Marker Legacy", 
            "description": "Оригинальная модель Marker с subprocess",
            "convert_func": marker_legacy_convert,
            "enabled": True,
            "default": False
        }
        
        logger.info(f"[model_registry] Зарегистрировано моделей: {len(self._models)}")
    
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
