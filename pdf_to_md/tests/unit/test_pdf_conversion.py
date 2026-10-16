"""Проверки совместимого интерфейса преобразования."""

from unittest.mock import AsyncMock, Mock

import pytest

from src.core.types import ConversionResult as CoreConversionResult
from src.pdf_conversion.models import ConversionStatus
from src.pdf_conversion.service import ConversionService


@pytest.mark.unit
@pytest.mark.asyncio
async def test_legacy_interface_delegates_to_indra_and_returns_neutral_key():
    service = ConversionService()
    service._service.convert_pdf = AsyncMock(
        return_value=CoreConversionResult(
            success=True,
            doc_id="doc-1",
            markdown_content="# Текст",
            metadata={"engine": "indra-ocr", "mode": "ocr", "math": True},
            raw_markdown_s3_key="documents/doc-1/doc-1_raw.md",
            s3_images=[],
        )
    )

    result = await service.convert_pdf(
        pdf_content=b"%PDF-test", doc_id="doc-1", model_id="default"
    )

    service._service.convert_pdf.assert_awaited_once_with(
        pdf_content=b"%PDF-test",
        doc_id="doc-1",
        model_id="default",
        use_coordinate_extraction=True,
    )
    assert result.status is ConversionStatus.COMPLETED
    assert result.content == "# Текст"
    assert result.metadata["raw_markdown_s3_key"] == "documents/doc-1/doc-1_raw.md"
    assert service.get_conversion_result(result.task_id) is result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_legacy_interface_does_not_accept_non_markdown_output():
    service = ConversionService()

    with pytest.raises(ValueError, match="Поддерживается только формат Markdown"):
        await service.convert_pdf(b"%PDF-test", output_format="html")
