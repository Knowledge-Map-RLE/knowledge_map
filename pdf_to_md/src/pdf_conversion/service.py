"""Совместимый API-адаптер над единым сервисом Indra OCR."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.config import settings
from ..services.indra_conversion_service import ConversionService as IndraConversionService
from .models import ConversionProgress, ConversionResult, ConversionStatus


class ConversionService:
    """Сохраняет старую форму ответа, используя общий production-конвертер."""

    def __init__(self) -> None:
        self._service = IndraConversionService()
        self._results: Dict[str, ConversionResult] = {}
        self._progress: Dict[str, ConversionProgress] = {}

    async def convert_pdf(
        self,
        pdf_content: bytes,
        doc_id: Optional[str] = None,
        model_id: Optional[str] = None,
        output_format: str = "markdown",
        use_coordinate_extraction: bool = True,
        options: Optional[Dict[str, Any]] = None,
    ) -> ConversionResult:
        if output_format != "markdown":
            raise ValueError("Поддерживается только формат Markdown")
        result = await self._service.convert_pdf(
            pdf_content=pdf_content,
            doc_id=doc_id,
            model_id=model_id,
            use_coordinate_extraction=use_coordinate_extraction,
        )
        task_id = f"conv_{result.doc_id}"
        now = datetime.now()
        status = ConversionStatus.COMPLETED if result.success else ConversionStatus.FAILED
        wrapped = ConversionResult(
            task_id=task_id,
            status=status,
            output_path=None,
            filename=f"{result.doc_id}_raw.md",
            content=result.markdown_content,
            created_at=now,
            metadata={
                **(result.metadata or {}),
                "doc_id": result.doc_id,
                "raw_markdown_s3_key": result.raw_markdown_s3_key,
                "s3_images": result.s3_images or [],
            },
            error_message=result.error_message,
        )
        self._results[task_id] = wrapped
        self._progress[task_id] = ConversionProgress(
            task_id=task_id,
            status=status,
            progress=100 if result.success else 0,
            message="Конвертация завершена" if result.success else result.error_message or "Ошибка",
            created_at=now,
            updated_at=now,
        )
        return wrapped

    def get_conversion_progress(self, task_id: str) -> Optional[ConversionProgress]:
        return self._progress.get(task_id)

    def get_conversion_result(self, task_id: str) -> Optional[ConversionResult]:
        return self._results.get(task_id)

    def get_active_conversions(self) -> List[str]:
        return list(self._service.get_active_conversions())

    async def cancel_conversion(self, task_id: str) -> bool:
        doc_id = task_id.removeprefix("conv_")
        return await self._service.cancel_conversion(doc_id)

    def cleanup_old_results(self, max_age_hours: int = 24) -> int:
        cutoff = datetime.now().timestamp() - max_age_hours * 3600
        old = [
            task_id
            for task_id, result in self._results.items()
            if result.created_at.timestamp() < cutoff
        ]
        for task_id in old:
            self._results.pop(task_id, None)
            self._progress.pop(task_id, None)
        return len(old)

    async def get_available_models(self) -> Dict[str, Any]:
        return {
            "models": {
                key: value.to_dict()
                for key, value in self._service.model_service.get_available_models().items()
            },
            "default_model": self._service.model_service.get_default_model(),
        }

    async def set_default_model(self, model_id: str) -> bool:
        return self._service.model_service.set_default_model(model_id)

    async def enable_model(self, model_id: str) -> bool:
        return self._service.model_service.enable_model(model_id)

    async def disable_model(self, model_id: str) -> bool:
        return self._service.model_service.disable_model(model_id)