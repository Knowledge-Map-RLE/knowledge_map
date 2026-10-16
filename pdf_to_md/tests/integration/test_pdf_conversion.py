"""Интеграционная проверка Indra-конвейера с подменёнными внешними ресурсами."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import fitz
import pytest

from src.core.config import settings
from src.services.indra_conversion_service import ConversionService


@pytest.mark.integration
@pytest.mark.asyncio
async def test_indra_pipeline_keeps_math_html_and_uploads_neutral_markdown(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "temp_dir", tmp_path / "temporary")
    service = ConversionService()
    markdown = "# Заголовок\\n\\n$x^2$\\n\\n<table><tr><td>ячейка</td></tr></table>"

    async def fake_convert(input_path, output_dir, on_progress=None):
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{input_path.stem}.md").write_text(markdown, encoding="utf-8")
        (output_dir / "indra_pages.json").write_text(
            json.dumps([{"markdown": markdown, "blocks": [], "timings": {}}]),
            encoding="utf-8",
        )
        return output_dir

    service.model_service.get_model = Mock(
        return_value=SimpleNamespace(is_enabled=True, convert=fake_convert)
    )
    service.model_service.get_default_model = Mock(return_value="default")
    service.figure_service.extract_images_with_s3 = AsyncMock(
        return_value={
            "markdown_content": markdown,
            "images_extracted": 0,
            "extracted_images": [],
        }
    )
    import src.services.indra_conversion_service as conversion_module

    upload = AsyncMock(
        return_value={
            "success": True,
            "object_key": "documents/doc-9/doc-9_raw.md",
        }
    )
    monkeypatch.setattr(conversion_module.s3_service, "upload_markdown", upload)

    document = fitz.open()
    document.new_page()
    pdf_content = document.tobytes()
    document.close()

    result = await service.convert_pdf(pdf_content, doc_id="doc-9")

    assert result.success is True
    assert "$x^2$" in result.markdown_content
    assert "<table>" in result.markdown_content
    assert result.raw_markdown_s3_key == "documents/doc-9/doc-9_raw.md"
    upload.assert_awaited_once()
