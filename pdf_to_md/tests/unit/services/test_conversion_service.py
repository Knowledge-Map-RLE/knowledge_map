"""Проверки единого Indra-пути преобразования."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import fitz
import pytest

from src.core.config import settings
from src.services.indra_conversion_service import ConversionService


def _pdf_bytes():
    document = fitz.open()
    document.new_page()
    content = document.tobytes()
    document.close()
    return content


def _fake_model(markdown="# Исходный текст"):
    async def convert(input_path, output_dir, on_progress=None):
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{input_path.stem}.md").write_text(markdown, encoding="utf-8")
        pages = [{"page_number": 1, "markdown": markdown, "blocks": [], "timings": {}}]
        (output_dir / "indra_pages.json").write_text(
            json.dumps(pages, ensure_ascii=False), encoding="utf-8"
        )
        return output_dir

    return SimpleNamespace(is_enabled=True, convert=convert)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_conversion_uses_default_model_and_neutral_markdown_key(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "temp_dir", tmp_path / "tmp")
    service = ConversionService()
    service.model_service.get_model = Mock(return_value=_fake_model())
    service.model_service.get_default_model = Mock(return_value="default")
    service.figure_service.extract_images_with_s3 = AsyncMock(
        return_value={
            "markdown_content": "# Исходный текст",
            "images_extracted": 0,
            "extracted_images": [],
        }
    )
    import src.services.indra_conversion_service as conversion_module

    monkeypatch.setattr(
        conversion_module.s3_service,
        "upload_markdown",
        AsyncMock(
            return_value={
                "success": True,
                "object_key": "documents/doc-1/doc-1_raw.md",
            }
        ),
    )

    result = await service.convert_pdf(_pdf_bytes(), doc_id="doc-1")

    assert result.success is True
    assert result.raw_markdown_s3_key == "documents/doc-1/doc-1_raw.md"
    assert result.metadata["engine"] == "indra-ocr"
    assert result.metadata["mode"] == "ocr"
    assert result.metadata["math"] is True
    service.model_service.get_model.assert_called_once_with("default")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indra_failure_is_returned_without_alternate_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "temp_dir", tmp_path / "tmp")
    service = ConversionService()

    async def fail_conversion(*args, **kwargs):
        raise RuntimeError("Indra conversion failed")

    service.model_service.get_model = Mock(
        return_value=SimpleNamespace(is_enabled=True, convert=fail_conversion)
    )
    service.model_service.get_default_model = Mock(return_value="default")
    service.figure_service.extract_images_with_s3 = AsyncMock()
    import src.services.indra_conversion_service as conversion_module

    upload_markdown = AsyncMock()
    monkeypatch.setattr(conversion_module.s3_service, "upload_markdown", upload_markdown)

    result = await service.convert_pdf(_pdf_bytes(), doc_id="doc-2")

    assert result.success is False
    assert "Indra conversion failed" in result.error_message
    service.figure_service.extract_images_with_s3.assert_not_awaited()
    upload_markdown.assert_not_awaited()
    service.model_service.get_model.assert_called_once_with("default")
