"""Проверки адаптера Indra OCR без загрузки внешних весов."""

import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import fitz
import pytest

from src.core.config import settings
from src.services.models.indra_model import IndraModel


def _create_pdf(path, page_count=2):
    document = fitz.open()
    for _ in range(page_count):
        document.new_page()
    document.save(path)
    document.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indra_uses_ocr_math_and_preserves_page_markdown(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HOME", str(tmp_path / "models"))
    monkeypatch.delenv("INDRA_OCR_MODEL_DIR", raising=False)
    pdf_path = tmp_path / "sample.pdf"
    _create_pdf(pdf_path)
    output_dir = tmp_path / "output"
    pages = [
        SimpleNamespace(
            source="ocr",
            markdown=f"# Страница {index}\n\n$x_{index}^2$\n\n<table><tr><td>{index}</td></tr></table>",
            blocks=[{"label": "Caption", "bbox": [1, 2, 3, 4], "text": f"Figure {index}"}],
            timings={"total": 0.1},
        )
        for index in (1, 2)
    ]
    converter = Mock()
    converter.convert.return_value = iter(enumerate(pages))
    loader = Mock(return_value=converter)
    monkeypatch.setitem(sys.modules, "indra_ocr", SimpleNamespace(load=loader))

    model = IndraModel()
    result_dir = await model.convert(pdf_path, output_dir)

    loader.assert_called_once_with(
        path=None,
        threads=settings.indra_threads,
        dpi=settings.indra_dpi,
        mode="ocr",
        math=True,
    )
    converter.convert.assert_called_once_with(str(pdf_path))
    markdown = (result_dir / "sample.md").read_text(encoding="utf-8")
    assert markdown.index("Страница 1") < markdown.index("Страница 2")
    assert "$x_1^2$" in markdown and "$x_2^2$" in markdown
    assert "<table>" in markdown
    saved_pages = json.loads(
        (result_dir / "indra_pages.json").read_text(encoding="utf-8")
    )
    assert [page["page_number"] for page in saved_pages] == [1, 2]
    assert saved_pages[0]["blocks"][0]["label"] == "Caption"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indra_fails_when_it_does_not_process_every_page(tmp_path, monkeypatch):
    pdf_path = tmp_path / "sample.pdf"
    _create_pdf(pdf_path, page_count=2)
    converter = Mock()
    converter.convert.return_value = iter(
        [(0, SimpleNamespace(source="ocr", markdown="page", blocks=[], timings={}))]
    )
    monkeypatch.setitem(
        sys.modules,
        "indra_ocr",
        SimpleNamespace(load=Mock(return_value=converter)),
    )

    with pytest.raises(RuntimeError, match="обработал 1 из 2 страниц"):
        await IndraModel().convert(pdf_path, tmp_path / "output")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indra_page_error_is_propagated_without_fallback(tmp_path, monkeypatch):
    pdf_path = tmp_path / "sample.pdf"
    _create_pdf(pdf_path, page_count=1)
    converter = Mock()
    converter.convert.return_value = iter(
        [(0, SimpleNamespace(source="error", markdown="", blocks=[], timings={}))]
    )
    monkeypatch.setitem(
        sys.modules,
        "indra_ocr",
        SimpleNamespace(load=Mock(return_value=converter)),
    )

    with pytest.raises(RuntimeError, match="ошибку для страницы 1"):
        await IndraModel().convert(pdf_path, tmp_path / "output")
