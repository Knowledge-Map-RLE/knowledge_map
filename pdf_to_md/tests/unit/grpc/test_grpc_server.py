"""Проверки gRPC-контракта и фиксированного порта сервиса."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src import grpc_server
from src.core.types import ConversionResult
from src import pdf_to_md_pb2


@pytest.mark.grpc
@pytest.mark.asyncio
async def test_grpc_response_contains_neutral_raw_markdown_key():
    servicer = grpc_server.PDFToMarkdownServicer()
    result = ConversionResult(
        success=True,
        doc_id="doc-1",
        markdown_content="<table><tr><td>данные</td></tr></table>",
        metadata={"engine": "indra-ocr", "mode": "ocr", "math": True},
        s3_images=[],
        raw_markdown_s3_key="documents/doc-1/doc-1_raw.md",
    )
    servicer.conversion_service = SimpleNamespace(
        convert_pdf=AsyncMock(return_value=result)
    )
    context = Mock()
    request = pdf_to_md_pb2.ConvertPDFRequest(
        pdf_content=b"%PDF-test", doc_id="doc-1"
    )

    response = await servicer.ConvertPDF(request, context)

    servicer.conversion_service.convert_pdf.assert_awaited_once_with(
        pdf_content=b"%PDF-test",
        doc_id="doc-1",
        model_id="default",
        use_coordinate_extraction=True,
    )
    assert response.success is True
    assert response.raw_markdown_s3_key == "documents/doc-1/doc-1_raw.md"
    assert "<table>" in response.markdown_content


@pytest.mark.grpc
@pytest.mark.asyncio
async def test_grpc_server_binds_only_configured_port(monkeypatch):
    fake_server = SimpleNamespace(
        add_insecure_port=Mock(return_value=50053),
        start=AsyncMock(),
        wait_for_termination=AsyncMock(),
    )
    server_factory = Mock(return_value=fake_server)
    monkeypatch.setattr(grpc_server.grpc.aio, "server", server_factory)
    monkeypatch.setattr(
        grpc_server.pdf_to_md_pb2_grpc,
        "add_PDFToMarkdownServiceServicer_to_server",
        Mock(),
    )

    await grpc_server.serve()

    fake_server.add_insecure_port.assert_called_once_with("0.0.0.0:50053")
    fake_server.start.assert_awaited_once()
