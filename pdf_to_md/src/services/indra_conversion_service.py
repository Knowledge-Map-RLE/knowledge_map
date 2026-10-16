"""Оркестрация PDF → Indra OCR → Markdown и S3."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from ..core.config import settings
from ..core.exceptions import (
    ConversionTimeoutError,
    ModelDisabledError,
    ModelNotFoundError,
    PDFConversionError,
)
from ..core.types import ConversionProgress, ConversionResult, ConversionStatus
from ..core.validators import validate_conversion_request
from .file_service import FileService
from .indra_figure_service import IndraFigureService
from .model_service import ModelService
from .s3_service import s3_service

logger = logging.getLogger(__name__)


class ConversionService:
    """Единый конвертер без переключения на альтернативные OCR-движки."""

    def __init__(self) -> None:
        self.model_service = ModelService()
        self.file_service = FileService()
        self.figure_service = IndraFigureService(dpi=settings.indra_dpi)
        self._active_conversions: Dict[str, asyncio.Task] = {}
        self._conversion_semaphore = asyncio.Semaphore(
            settings.max_concurrent_conversions
        )

    async def convert_pdf(
        self,
        pdf_content: bytes,
        doc_id: Optional[str] = None,
        model_id: Optional[str] = None,
        filename: Optional[str] = None,
        use_coordinate_extraction: bool = True,
        on_progress: Optional[Any] = None,
    ) -> ConversionResult:
        """Преобразует PDF и сохраняет сырой Markdown и рисунки в S3."""
        started_at = datetime.now()
        request_id = doc_id or "unknown"
        temp_dir: Optional[Path] = None
        task = asyncio.current_task()
        registered = False
        try:
            request = validate_conversion_request(
                pdf_content=pdf_content,
                doc_id=doc_id,
                model_id=model_id,
                filename=filename,
            )
            request_id = request.doc_id or request.generate_doc_id()
            if not use_coordinate_extraction:
                raise PDFConversionError(
                    "Извлечение рисунков обязательно и не может быть отключено"
                )
            if request_id in self._active_conversions:
                raise PDFConversionError(
                    f"Конвертация документа {request_id} уже выполняется"
                )

            selected_model_id = request.model_id or self.model_service.get_default_model()
            model = self.model_service.get_model(selected_model_id)
            if model is None:
                raise ModelNotFoundError(f"Модель {selected_model_id} не найдена")
            if not model.is_enabled:
                raise ModelDisabledError(f"Модель {selected_model_id} отключена")

            temp_dir = self.file_service.create_temp_directory(
                prefix=f"pdf_to_md_{request_id}_"
            )
            pdf_path = temp_dir / f"{request_id}.pdf"
            pdf_path.write_bytes(request.pdf_content)
            self._active_conversions[request_id] = task or asyncio.current_task()
            registered = True

            async with self._conversion_semaphore:
                result = await asyncio.wait_for(
                    self._perform_conversion(
                        model=model,
                        pdf_path=pdf_path,
                        output_dir=temp_dir / "output",
                        document_id=request_id,
                        on_progress=on_progress,
                    ),
                    timeout=settings.conversion_timeout_seconds,
                )
            result.processing_time = (datetime.now() - started_at).total_seconds()
            return result
        except asyncio.TimeoutError as exc:
            raise ConversionTimeoutError(
                f"Превышено время конвертации {settings.conversion_timeout_seconds} секунд"
            ) from exc
        except Exception as exc:
            elapsed = (datetime.now() - started_at).total_seconds()
            logger.error(
                "Конвертация Indra завершилась ошибкой: doc_id=%s, elapsed=%.2fs, error=%s",
                request_id,
                elapsed,
                exc,
                exc_info=True,
            )
            return ConversionResult(
                success=False,
                doc_id=request_id,
                error_message=str(exc),
                processing_time=elapsed,
            )
        finally:
            if registered and self._active_conversions.get(request_id) is task:
                self._active_conversions.pop(request_id, None)
            if temp_dir is not None:
                self.file_service.cleanup_temp_directory(temp_dir)

    async def _perform_conversion(
        self,
        model: Any,
        pdf_path: Path,
        output_dir: Path,
        document_id: str,
        on_progress: Optional[Any] = None,
    ) -> ConversionResult:
        """Выполняет единственный путь обработки и сохраняет результаты."""
        output_dir.mkdir(parents=True, exist_ok=True)

        def report(payload: Dict[str, Any]) -> None:
            if on_progress is None:
                return
            if isinstance(payload, ConversionProgress):
                on_progress(payload)
                return
            on_progress(
                ConversionProgress(
                    doc_id=document_id,
                    status=ConversionStatus.PROCESSING,
                    percent=int(payload.get("percent", 0)),
                    phase=str(payload.get("phase", "indra_ocr")),
                    message=str(payload.get("message", "")),
                    pages_processed=payload.get("pages_processed"),
                    total_pages=payload.get("total_pages"),
                )
            )

        result_dir = await model.convert(
            input_path=pdf_path,
            output_dir=output_dir,
            on_progress=report,
        )
        markdown_path = result_dir / f"{pdf_path.stem}.md"
        pages_path = result_dir / "indra_pages.json"
        if not markdown_path.is_file() or not pages_path.is_file():
            raise PDFConversionError("Indra не создал Markdown и данные страниц")

        pages = json.loads(pages_path.read_text(encoding="utf-8"))
        figure_result = await self.figure_service.extract_images_with_s3(
            pdf_path=pdf_path,
            document_id=document_id,
            pages=pages,
            on_progress=lambda payload: report(payload),
        )
        markdown_content = figure_result["markdown_content"]

        report(
            {
                "percent": 92,
                "phase": "save_raw_markdown",
                "message": "Сохранение исходного Markdown в S3",
            }
        )
        upload = await s3_service.upload_markdown(
            markdown_content=markdown_content,
            filename=f"{document_id}_raw.md",
            folder=f"documents/{document_id}",
        )
        if not upload.get("success"):
            raise PDFConversionError(
                f"Не удалось сохранить Markdown в S3: {upload.get('error')}"
            )

        metadata = {
            "engine": "indra-ocr",
            "mode": "ocr",
            "math": True,
            "page_count": len(pages),
            "page_timings": [page.get("timings", {}) for page in pages],
            "figure_count": figure_result["images_extracted"],
        }
        report(
            {
                "percent": 100,
                "phase": "complete",
                "message": "Конвертация завершена",
            }
        )
        return ConversionResult(
            success=True,
            doc_id=document_id,
            markdown_content=markdown_content,
            metadata=metadata,
            s3_images=figure_result["extracted_images"],
            extraction_method="indra_ocr",
            raw_markdown_s3_key=upload["object_key"],
        )

    async def cancel_conversion(self, doc_id: str) -> bool:
        task = self._active_conversions.get(doc_id)
        if task is None or task.done():
            return False
        task.cancel()
        logger.info("Запрошена отмена конвертации doc_id=%s", doc_id)
        return True

    def get_active_conversions(self) -> Dict[str, str]:
        return {doc_id: "processing" for doc_id in self._active_conversions}

    async def get_conversion_status(self, doc_id: str) -> Optional[str]:
        task = self._active_conversions.get(doc_id)
        if task is None:
            return None
        return "processing" if not task.done() else "completed"
