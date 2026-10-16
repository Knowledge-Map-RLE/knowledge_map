"""Единый реестр PDF OCR с нейтральным идентификатором модели."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..core.config import settings
from ..services.models.indra_model import IndraModel

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Совместимый интерфейс реестра для старых внутренних потребителей."""

    def __init__(self) -> None:
        if settings.environment.lower() == "production" and not settings.indra_license_reviewed:
            raise RuntimeError(
                "Для production необходимо проверить лицензию весов Indra "
                "и установить INDRA_LICENSE_REVIEWED=true"
            )
        self._model = IndraModel()
        self._default_model = "default"
        self._models: Dict[str, Dict[str, Any]] = {
            "default": {
                "name": "PDF OCR",
                "description": "Преобразование PDF в структурированный Markdown",
                "convert_func": self._indra_convert_wrapper,
                "enabled": True,
                "default": True,
            }
        }
        logger.info("Зарегистрирована модель PDF OCR с id=default")

    async def _indra_convert_wrapper(
        self,
        tmp_dir: Path,
        *,
        on_progress: Optional[Callable[[dict], None]] = None,
        doc_id: Optional[str] = None,
    ) -> Path:
        pdf_files = sorted(tmp_dir.glob("*.pdf"))
        if len(pdf_files) != 1:
            raise RuntimeError(
                f"Ожидался один PDF для обработки, найдено: {len(pdf_files)}"
            )
        output_dir = tmp_dir / "indra_output"
        return await self._model.convert(
            input_path=pdf_files[0], output_dir=output_dir, on_progress=on_progress
        )

    def get_available_models(self) -> Dict[str, Dict[str, Any]]:
        return {
            model_id: {
                "name": info["name"],
                "description": info["description"],
                "enabled": info["enabled"],
                "default": info["default"],
            }
            for model_id, info in self._models.items()
        }

    def get_default_model(self) -> str:
        return self._default_model

    def set_default_model(self, model_id: str) -> bool:
        if model_id not in self._models or not self._models[model_id]["enabled"]:
            return False
        for info in self._models.values():
            info["default"] = False
        self._models[model_id]["default"] = True
        self._default_model = model_id
        return True

    def enable_model(self, model_id: str) -> bool:
        if model_id not in self._models:
            return False
        self._models[model_id]["enabled"] = True
        return True

    def disable_model(self, model_id: str) -> bool:
        if model_id not in self._models or model_id == self._default_model:
            return False
        self._models[model_id]["enabled"] = False
        return True

    async def convert_pdf(
        self,
        tmp_dir: Path,
        *,
        on_progress: Optional[Callable[[dict], None]] = None,
        doc_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Path:
        selected_id = model_id or self._default_model
        info = self._models.get(selected_id)
        if info is None:
            raise ValueError(f"Модель {selected_id} не найдена")
        if not info["enabled"]:
            raise ValueError(f"Модель {selected_id} отключена")
        return await info["convert_func"](
            tmp_dir, on_progress=on_progress, doc_id=doc_id
        )

    def get_model_info(self, model_id: str) -> Optional[Dict[str, Any]]:
        return self._models.get(model_id)


model_registry = ModelRegistry()