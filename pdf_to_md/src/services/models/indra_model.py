"""Адаптер Indra OCR для преобразования страниц PDF в Markdown."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .base_model import BaseModel
from ...core.config import settings

logger = logging.getLogger(__name__)


class IndraModel(BaseModel):
    """Единственная модель сервиса с нейтральным внешним идентификатором."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "PDF OCR"
        self.description = "Преобразование PDF в структурированный Markdown"
        self.version = "0.3.2"
        self.capabilities = [
            "pdf_to_markdown",
            "document_structure",
            "ocr",
            "math_latex",
            "html_tables",
            "layout_blocks",
        ]
        self._converter: Any = None
        self._converter_lock = threading.Lock()
        self._conversion_lock = threading.Lock()

    def _get_converter(self) -> Any:
        """Загружает модель один раз; ошибка загрузки не скрывается."""
        if self._converter is not None:
            return self._converter

        with self._converter_lock:
            if self._converter is None:
                model_cache_dir = settings.model_cache_dir.expanduser().resolve()
                os.environ.setdefault("HF_HOME", str(model_cache_dir))
                # Indra ожидает по этой переменной плоскую папку с ONNX-файлами,
                # а наш кэш HF хранит снимок модели во вложенном каталоге.
                model_dir_override = os.environ.pop("INDRA_OCR_MODEL_DIR", None)
                if model_dir_override:
                    logger.warning(
                        "INDRA_OCR_MODEL_DIR отключён; модели будут загружены из HF_HOME=%s",
                        os.environ["HF_HOME"],
                    )
                try:
                    import indra_ocr
                except ImportError as exc:
                    raise RuntimeError(
                        "Зависимость indra-ocr не установлена в окружении сервиса"
                    ) from exc

                self._converter = indra_ocr.load(
                    path=None,
                    threads=settings.indra_threads,
                    dpi=settings.indra_dpi,
                    mode="ocr",
                    math=True,
                )
                logger.info(
                    "Indra OCR загружен: mode=ocr, math=True, threads=%s, dpi=%s",
                    settings.indra_threads,
                    settings.indra_dpi,
                )
        return self._converter

    @staticmethod
    def _serialize_block(block: Any) -> Dict[str, Any]:
        """Приводит блок Indra к JSON-совместимому виду."""
        if isinstance(block, dict):
            value = block
        elif hasattr(block, "model_dump"):
            value = block.model_dump()
        elif hasattr(block, "_asdict"):
            value = block._asdict()
        else:
            value = {
                "label": getattr(block, "label", ""),
                "bbox": getattr(block, "bbox", None),
                "text": getattr(block, "text", ""),
            }

        bbox = value.get("bbox")
        if bbox is not None and not isinstance(bbox, (dict, list, tuple)):
            bbox = getattr(bbox, "__dict__", str(bbox))
        if isinstance(bbox, tuple):
            bbox = list(bbox)
        return {
            "label": str(value.get("label", "")),
            "bbox": bbox,
            "text": str(value.get("text", "")),
        }

    def _convert_sync(self, input_path: Path, output_dir: Path) -> Path:
        """Выполняет OCR, проверяет полноту и сохраняет результаты страниц."""
        import fitz

        converter = self._get_converter()
        with fitz.open(str(input_path)) as pdf_document:
            expected_pages = len(pdf_document)

        pages: List[Dict[str, Any]] = []
        with self._conversion_lock:
            for page_index, (_, page) in enumerate(converter.convert(str(input_path))):
                source = str(getattr(page, "source", ""))
                if source == "error":
                    raise RuntimeError(
                        f"Indra OCR вернул ошибку для страницы {page_index + 1}"
                    )

                page_markdown = getattr(page, "markdown", None)
                if not isinstance(page_markdown, str):
                    raise RuntimeError(
                        f"Indra OCR не вернул Markdown для страницы {page_index + 1}"
                    )

                blocks = getattr(page, "blocks", []) or []
                timings = getattr(page, "timings", {}) or {}
                pages.append(
                    {
                        "page_number": page_index + 1,
                        "markdown": page_markdown,
                        "blocks": [self._serialize_block(block) for block in blocks],
                        "source": source,
                        "timings": dict(timings) if hasattr(timings, "items") else {},
                    }
                )

        if len(pages) != expected_pages:
            raise RuntimeError(
                f"Indra OCR обработал {len(pages)} из {expected_pages} страниц"
            )
        if not pages:
            raise RuntimeError("Indra OCR не обработал ни одной страницы")

        output_dir.mkdir(parents=True, exist_ok=True)
        markdown_path = output_dir / f"{input_path.stem}.md"
        markdown_path.write_text(
            "\n\n".join(page["markdown"].strip() for page in pages).strip() + "\n",
            encoding="utf-8",
        )
        (output_dir / "indra_pages.json").write_text(
            json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("Indra OCR обработал %s страниц", len(pages))
        return output_dir

    async def convert(
        self,
        input_path: Path,
        output_dir: Path,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Path:
        """Запускает синхронный движок вне event loop."""
        if on_progress:
            on_progress({"percent": 10, "phase": "indra_ocr", "message": "Распознавание PDF"})
        result = await asyncio.to_thread(self._convert_sync, input_path, output_dir)
        if on_progress:
            on_progress({"percent": 75, "phase": "indra_ocr", "message": "Страницы распознаны"})
        return result
