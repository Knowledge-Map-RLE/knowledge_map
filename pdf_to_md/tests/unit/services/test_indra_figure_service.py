"""Проверки сопоставления подписей Indra с рисунками PDF."""

from unittest.mock import AsyncMock
import io

import fitz
import pytest
from PIL import Image

from src.services.indra_figure_service import IndraFigureService


def _pixels(rect, dpi=200):
    scale = dpi / 72
    return [coordinate * scale for coordinate in rect]


def test_figure_insertion_prefers_standalone_caption_over_text_reference():
    caption = "Figure 1. Test diagram"
    reference = f"Discussion refers to {caption}."
    markdown = f"{reference}\n\n<p>{caption}</p>"

    result = IndraFigureService._replace_caption(
        markdown,
        caption,
        f"<figure><figcaption>{caption}</figcaption></figure>",
    )

    assert result.startswith(f"{reference}\n\n<figure>")
    assert result.count("<figure>") == 1
    assert result.count(caption) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vector_figure_is_embedded_once_and_html_table_is_preserved(tmp_path):
    pdf_path = tmp_path / "figure.pdf"
    document = fitz.open()
    page = document.new_page(width=600, height=800)
    page.draw_rect(fitz.Rect(100, 100, 300, 300), color=(0, 0, 0), fill=(0.8, 0.8, 0.8))
    document.save(pdf_path)
    document.close()

    caption = "Figure 1. Test diagram"
    markdown = (
        f"<p>{caption}</p>\n\n"
        "<table><tr><td>Kept as HTML</td></tr></table>"
    )
    pages = [
        {
            "markdown": markdown,
            "blocks": [
                {
                    "label": "Caption",
                    "bbox": _pixels((100, 305, 300, 330)),
                    "text": caption,
                },
                {
                    "label": "Table",
                    "bbox": _pixels((350, 400, 550, 500)),
                    "text": "",
                },
            ],
        }
    ]
    s3 = type("S3", (), {})()
    s3.upload_image = AsyncMock(
        return_value={"success": True, "object_key": "documents/doc/images/figure.png"}
    )

    result = await IndraFigureService(s3_client=s3).extract_images_with_s3(
        pdf_path, "doc", pages
    )

    output = result["markdown_content"]
    assert output.count("<figure>") == 1
    assert output.count("<figcaption>Figure 1. Test diagram</figcaption>") == 1
    assert output.count(caption) == 1
    assert '<img src="/api/v1/s3/image/documents/doc/images/figure.png"' in output
    assert "<table><tr><td>Kept as HTML</td></tr></table>" in output
    assert result["images_extracted"] == 1
    s3.upload_image.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_table_caption_is_not_converted_to_figure(tmp_path):
    pdf_path = tmp_path / "table.pdf"
    document = fitz.open()
    document.new_page(width=600, height=800)
    document.save(pdf_path)
    document.close()

    caption = "Table 1. Results"
    markdown = f"<table><tr><td>Data</td></tr></table>\n\n<p>{caption}</p>"
    s3 = type("S3", (), {"upload_image": AsyncMock()})()
    result = await IndraFigureService(s3_client=s3).extract_images_with_s3(
        pdf_path,
        "doc",
        [
            {
                "markdown": markdown,
                "blocks": [
                    {"label": "Caption", "bbox": _pixels((10, 20, 200, 30)), "text": caption},
                    {"label": "Table", "bbox": _pixels((10, 35, 200, 100)), "text": ""},
                ],
            }
        ],
    )

    assert result["markdown_content"].strip() == markdown
    assert result["images_extracted"] == 0
    s3.upload_image.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_raster_figure_keeps_its_real_file_format(tmp_path):
    pdf_path = tmp_path / "raster.pdf"
    image_buffer = io.BytesIO()
    Image.new("RGB", (200, 200), color="red").save(image_buffer, format="JPEG")
    document = fitz.open()
    page = document.new_page(width=600, height=800)
    page.insert_image(fitz.Rect(100, 100, 300, 300), stream=image_buffer.getvalue())
    document.save(pdf_path)
    document.close()

    caption = "Figure 3. Raster diagram"
    s3 = type("S3", (), {})()
    s3.upload_image = AsyncMock(
        return_value={"success": True, "object_key": "documents/doc/images/figure.jpg"}
    )
    result = await IndraFigureService(s3_client=s3).extract_images_with_s3(
        pdf_path,
        "doc",
        [
            {
                "markdown": caption,
                "blocks": [
                    {
                        "label": "Caption",
                        "bbox": _pixels((100, 305, 300, 330)),
                        "text": caption,
                    }
                ],
            }
        ],
    )

    uploaded_filename = s3.upload_image.await_args.kwargs["filename"]
    assert uploaded_filename.endswith((".jpg", ".jpeg"))
    assert result["extracted_images"][0]["content_type"] == "image/jpeg"
    assert "<figure>" in result["markdown_content"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_numbered_figure_without_pdf_visual_fails_explicitly(tmp_path):
    pdf_path = tmp_path / "no-figure.pdf"
    document = fitz.open()
    document.new_page(width=600, height=800)
    document.save(pdf_path)
    document.close()
    caption = "Figure 2. Missing diagram"

    with pytest.raises(RuntimeError, match="Не найден рисунок"):
        await IndraFigureService(s3_client=object()).extract_images_with_s3(
            pdf_path,
            "doc",
            [
                {
                    "markdown": caption,
                    "blocks": [
                        {
                            "label": "Caption",
                            "bbox": _pixels((100, 300, 400, 330)),
                            "text": caption,
                        }
                    ],
                }
            ],
        )
