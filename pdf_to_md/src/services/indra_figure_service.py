"""Извлечение рисунков PDF по блокам Indra и сохранение в S3."""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote

import fitz

from .s3_service import s3_service

logger = logging.getLogger(__name__)


@dataclass
class _VisualCandidate:
    rect: fitz.Rect
    image_xrefs: set[int] = field(default_factory=set)
    has_vector: bool = False


class IndraFigureService:
    """Добавляет в Markdown изображения, связанные с подписями Indra."""

    _FIGURE_CAPTION_RE = re.compile(r"(?i)^\s*(?:fig(?:ure)?\.?)\s*(\d+)\s*[.:]")

    def __init__(self, s3_client: Any = None, dpi: int = 200) -> None:
        self.s3_service = s3_client or s3_service
        self.dpi = dpi

    def _indra_rect(self, bbox: Any) -> Optional[fitz.Rect]:
        """Переводит bbox Indra из пикселей рендера в координаты PDF."""
        if bbox is None:
            return None
        if isinstance(bbox, dict):
            values = [
                bbox.get("x0", bbox.get("left")),
                bbox.get("y0", bbox.get("top")),
                bbox.get("x1", bbox.get("right")),
                bbox.get("y1", bbox.get("bottom")),
            ]
        else:
            try:
                values = list(bbox)
            except TypeError:
                return None
        if len(values) != 4 or any(value is None for value in values):
            return None
        try:
            scale = 72.0 / self.dpi
            rect = fitz.Rect(*(float(value) * scale for value in values))
        except (TypeError, ValueError):
            return None
        if rect.is_empty or not all(
            value == value for value in (rect.x0, rect.y0, rect.x1, rect.y1)
        ):
            return None
        return rect

    @staticmethod
    def _union(left: fitz.Rect, right: fitz.Rect) -> fitz.Rect:
        return fitz.Rect(
            min(left.x0, right.x0),
            min(left.y0, right.y0),
            max(left.x1, right.x1),
            max(left.y1, right.y1),
        )

    @staticmethod
    def _near(left: fitz.Rect, right: fitz.Rect, gap: float) -> bool:
        expanded = fitz.Rect(left.x0 - gap, left.y0 - gap, left.x1 + gap, left.y1 + gap)
        return expanded.intersects(right)

    def _candidates(self, page: fitz.Page) -> List[_VisualCandidate]:
        """Объединяет близкие растровые и векторные части рисунков."""
        components: List[_VisualCandidate] = []
        for image in page.get_images(full=True):
            xref = int(image[0])
            for rect in page.get_image_rects(xref):
                rect = fitz.Rect(rect)
                if rect.get_area() >= 100 and rect.width >= 8 and rect.height >= 8:
                    components.append(_VisualCandidate(rect=rect, image_xrefs={xref}))

        for drawing in page.get_drawings():
            rect = fitz.Rect(drawing["rect"])
            if rect.get_area() >= 4 and rect.width >= 2 and rect.height >= 2:
                components.append(_VisualCandidate(rect=rect, has_vector=True))

        clusters: List[_VisualCandidate] = []
        for component in sorted(
            components, key=lambda item: (item.rect.y0, item.rect.x0)
        ):
            current = component
            changed = True
            while changed:
                changed = False
                for index, cluster in enumerate(clusters):
                    if self._near(current.rect, cluster.rect, gap=7):
                        current.rect = self._union(current.rect, cluster.rect)
                        current.image_xrefs.update(cluster.image_xrefs)
                        current.has_vector = current.has_vector or cluster.has_vector
                        clusters.pop(index)
                        changed = True
                        break
            clusters.append(current)

        page_area = max(page.rect.get_area(), 1)
        return [
            candidate
            for candidate in clusters
            if candidate.rect.width >= 24
            and candidate.rect.height >= 24
            and candidate.rect.get_area() >= 900
            and candidate.rect.get_area() < page_area * 0.95
        ]

    def _table_rects(self, blocks: Sequence[Dict[str, Any]]) -> List[fitz.Rect]:
        return [
            rect
            for block in blocks
            if str(block.get("label", "")).lower() == "table"
            if (rect := self._indra_rect(block.get("bbox"))) is not None
        ]

    @classmethod
    def _native_figure_captions(cls, page: fitz.Page) -> List[Dict[str, Any]]:
        """Находит подписи рисунков в текстовом слое исходного PDF."""
        captions: List[Dict[str, Any]] = []
        for block in page.get_text("blocks"):
            if len(block) < 5:
                continue
            text = re.sub(r"\s+", " ", str(block[4])).strip()
            if cls._FIGURE_CAPTION_RE.match(text):
                captions.append(
                    {
                        "label": "caption",
                        "bbox": fitz.Rect(block[:4]),
                        "text": text,
                        "source": "pdf_text",
                    }
                )
        return captions

    @classmethod
    def _figure_number(cls, caption: Dict[str, Any]) -> Optional[str]:
        match = cls._FIGURE_CAPTION_RE.match(str(caption.get("text", "")))
        return match.group(1) if match else None

    @staticmethod
    def _has_page_background_image(page: fitz.Page) -> bool:
        """Проверяет, что растровое изображение покрывает почти всю страницу."""
        page_area = max(page.rect.get_area(), 1)
        for image in page.get_images(full=True):
            for rect in page.get_image_rects(int(image[0])):
                clipped = fitz.Rect(rect) & page.rect
                if clipped.get_area() / page_area >= 0.95:
                    return True
        return False

    def _scan_figure_rect(
        self,
        page: fitz.Page,
        caption_rect: fitz.Rect,
        caption_rects: Sequence[fitz.Rect],
        table_rects: Sequence[fitz.Rect],
        layout_blocks: Sequence[Dict[str, Any]],
    ) -> Optional[fitz.Rect]:
        """Обрезает область рисунка в скане между текстом и его подписью."""
        preceding_paragraphs: List[Tuple[float, fitz.Rect]] = []
        text_blocks: List[Tuple[str, fitz.Rect]] = [
            (str(block[4]), fitz.Rect(block[:4]))
            for block in page.get_text("blocks")
            if len(block) >= 5
        ]
        text_blocks.extend(
            (str(block.get("text", "")), rect)
            for block in layout_blocks
            if (rect := self._indra_rect(block.get("bbox"))) is not None
        )
        for block_text, rect in text_blocks:
            text = re.sub(r"\s+", " ", block_text).strip()
            if (
                len(text.split()) < 8
                or sum(character.isalpha() for character in text) < 24
            ):
                continue
            if (
                rect.y1 >= caption_rect.y0
                or rect.y1 < caption_rect.y0 - page.rect.height * 0.4
            ):
                continue
            if self._overlap_ratio(rect, caption_rect) < 0.35:
                continue
            if any(
                not (rect & ignored).is_empty
                and (rect & ignored).get_area() / max(rect.get_area(), 1) > 0.2
                for ignored in [*caption_rects, *table_rects]
            ):
                continue
            preceding_paragraphs.append((rect.y1, rect))

        if not preceding_paragraphs:
            return None

        _, paragraph_rect = max(preceding_paragraphs, key=lambda item: item[0])
        # Подпись и предшествующий абзац задают ширину колонки; небольшие поля
        # захватывают края рисунка, не включая соседнюю колонку.
        column = fitz.Rect(
            min(caption_rect.x0, paragraph_rect.x0) - 3,
            paragraph_rect.y1 + 2,
            max(caption_rect.x1, paragraph_rect.x1) + 3,
            caption_rect.y0 - 2,
        )
        column &= page.rect
        if column.width < 24 or column.height < 24:
            return None
        if any(
            not (column & table_rect).is_empty
            and (column & table_rect).get_area() / max(column.get_area(), 1) > 0.5
            for table_rect in table_rects
        ):
            return None
        return column

    @staticmethod
    def _markdown_caption_segment(
        markdown: str, figure_number: str
    ) -> Optional[Tuple[int, int, str]]:
        """Находит в Markdown наиболее похожий на подпись абзац рисунка."""
        figure_pattern = re.compile(
            rf"(?i)\bfig(?:ure)?\.?\s*0*{re.escape(figure_number)}\s*[.:]"
        )
        paragraph_pattern = re.compile(r"(?s)\S.*?(?=\n[ \t]*\n|$)")
        candidates: List[Tuple[int, int, int, str]] = []
        for paragraph in paragraph_pattern.finditer(markdown):
            match = figure_pattern.search(paragraph.group())
            if match is None:
                continue
            caption = paragraph.group()[match.start() :].strip()
            if len(caption) < 30:
                continue
            prefix_length = len(paragraph.group()[: match.start()].strip())
            candidates.append(
                (prefix_length, -len(caption), paragraph.start(), paragraph.group())
            )
        if not candidates:
            return None
        _, _, start, paragraph_text = min(candidates)
        return start, start + len(paragraph_text), paragraph_text

    @staticmethod
    def _exclude_table_candidates(
        candidates: Sequence[_VisualCandidate], table_rects: Sequence[fitz.Rect]
    ) -> List[_VisualCandidate]:
        """Исключает графические области, состоящие преимущественно из таблиц."""
        filtered = []
        for candidate in candidates:
            if any(
                (intersection := candidate.rect & table_rect).get_area()
                / max(candidate.rect.get_area(), 1)
                > 0.5
                for table_rect in table_rects
            ):
                continue
            filtered.append(candidate)
        return filtered

    def _is_table_caption(
        self, caption: Dict[str, Any], table_rects: Sequence[fitz.Rect]
    ) -> bool:
        text = str(caption.get("text", "")).strip()
        if re.match(r"(?i)^table\b", text):
            return True
        caption_rect = self._indra_rect(caption.get("bbox"))
        if caption_rect is None:
            return False
        for table_rect in table_rects:
            intersection = caption_rect & table_rect
            if (
                not intersection.is_empty
                and intersection.get_area() / max(caption_rect.get_area(), 1) > 0.2
            ):
                return True
        return False

    @staticmethod
    def _overlap_ratio(left: fitz.Rect, right: fitz.Rect) -> float:
        horizontal = max(0.0, min(left.x1, right.x1) - max(left.x0, right.x0))
        return horizontal / max(min(left.width, right.width), 1.0)

    def _match_candidate(
        self,
        caption_rect: fitz.Rect,
        candidates: Sequence[_VisualCandidate],
        used: set[int],
        page_height: float,
    ) -> Optional[int]:
        scored: List[Tuple[float, int]] = []
        max_gap = max(120.0, page_height * 0.3)
        for index, candidate in enumerate(candidates):
            if index in used:
                continue
            rect = candidate.rect
            if rect.y1 <= caption_rect.y0:
                gap = caption_rect.y0 - rect.y1
                below_penalty = 0.0
            elif caption_rect.y1 <= rect.y0:
                gap = rect.y0 - caption_rect.y1
                below_penalty = 36.0
            else:
                gap = 0.0
                below_penalty = 0.0
            horizontal_overlap = self._overlap_ratio(caption_rect, rect)
            center_distance = abs(
                (caption_rect.x0 + caption_rect.x1) / 2 - (rect.x0 + rect.x1) / 2
            )
            if gap > max_gap or (horizontal_overlap < 0.12 and center_distance > 36):
                continue
            score = gap + below_penalty + center_distance * 0.15
            scored.append((score, index))
        return min(scored)[1] if scored else None

    def _extract_candidate(
        self, document: fitz.Document, page: fitz.Page, candidate: _VisualCandidate
    ) -> Tuple[bytes, Tuple[int, int], str]:
        """Берёт исходный одиночный растр или рендерит составную область."""
        if len(candidate.image_xrefs) == 1 and not candidate.has_vector:
            xref = next(iter(candidate.image_xrefs))
            image = document.extract_image(xref)
            if image and image.get("image"):
                extension = str(image.get("ext", "")).lower().lstrip(".")
                if extension in {
                    "jpg",
                    "jpeg",
                    "png",
                    "gif",
                    "bmp",
                    "webp",
                    "tif",
                    "tiff",
                }:
                    return (
                        image["image"],
                        (int(image["width"]), int(image["height"])),
                        extension,
                    )

        clip = fitz.Rect(candidate.rect)
        clip &= page.rect
        if clip.is_empty:
            raise ValueError("область рисунка вне страницы PDF")
        pixmap = page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=clip, alpha=False)
        if pixmap.width < 50 or pixmap.height < 50:
            raise ValueError(
                f"рендер рисунка слишком мал: {pixmap.width}x{pixmap.height}"
            )
        return pixmap.tobytes("png"), (pixmap.width, pixmap.height), "png"

    @staticmethod
    def _replace_caption(markdown: str, caption: str, figure_html: str) -> str:
        """Заменяет одно вхождение подписи цельным HTML-блоком figure."""
        words = [re.escape(word) for word in re.split(r"\s+", caption.strip()) if word]
        if not words:
            raise ValueError("Indra вернул пустую подпись рисунка")
        caption_pattern = r"\s+".join(words)
        standalone_caption = re.compile(
            r"(?im)(^|\n)[ \t]*(?:<p>\s*)?("
            + caption_pattern
            + r")(?:\s*</p>)?[ \t]*(?=\n|$)"
        )
        match = standalone_caption.search(markdown)
        standalone = match is not None
        if match is None:
            match = re.search(caption_pattern, markdown, flags=re.IGNORECASE)
        if not match:
            raise ValueError(f"Подпись Indra не найдена в Markdown: {caption[:100]!r}")

        if standalone:
            start = match.start() + len(match.group(1))
            end = match.end()
        else:
            start, end = match.span()
        return markdown[:start] + figure_html + markdown[end:]

    async def extract_images_with_s3(
        self,
        pdf_path: Any,
        document_id: str,
        pages: List[Dict[str, Any]],
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Связывает Caption-блоки Indra с рисунками PDF и добавляет их в Markdown."""
        with fitz.open(str(pdf_path)) as document:
            if len(document) != len(pages):
                raise RuntimeError(
                    f"Число страниц PDF ({len(document)}) не совпадает с результатом Indra ({len(pages)})"
                )

            markdown_pages: List[str] = []
            extracted_images: List[Dict[str, Any]] = []
            for page_index, page_data in enumerate(pages):
                page = document[page_index]
                blocks = page_data.get("blocks", [])
                table_rects = self._table_rects(blocks)
                candidates = self._exclude_table_candidates(
                    self._candidates(page), table_rects
                )
                used: set[int] = set()
                page_markdown = str(page_data.get("markdown", ""))

                captions = [
                    block
                    for block in blocks
                    if (
                        str(block.get("label", "")).lower() == "caption"
                        or self._figure_number(block) is not None
                    )
                    and str(block.get("text", "")).strip()
                    and not self._is_table_caption(block, table_rects)
                ]
                numbered_captions = {
                    figure_number
                    for caption in captions
                    if (figure_number := self._figure_number(caption)) is not None
                }
                for native_caption in self._native_figure_captions(page):
                    figure_number = self._figure_number(native_caption)
                    if figure_number not in numbered_captions:
                        captions.append(native_caption)
                        numbered_captions.add(figure_number)

                caption_rects = [
                    rect
                    for caption in captions
                    if (
                        rect := (
                            fitz.Rect(caption["bbox"])
                            if caption.get("source") == "pdf_text"
                            else self._indra_rect(caption.get("bbox"))
                        )
                    )
                    is not None
                ]
                has_page_background = self._has_page_background_image(page)
                processed_captions: set[str] = set()
                for figure_index, caption in enumerate(captions, start=1):
                    caption_text = str(caption["text"]).strip()
                    caption_key = re.sub(r"\s+", " ", caption_text).casefold()
                    if caption_key in processed_captions:
                        continue
                    caption_rect = (
                        fitz.Rect(caption["bbox"])
                        if caption.get("source") == "pdf_text"
                        else self._indra_rect(caption.get("bbox"))
                    )
                    figure_number = self._figure_number(caption)
                    is_numbered_figure = figure_number is not None
                    if caption_rect is None:
                        if is_numbered_figure:
                            raise RuntimeError(
                                f"Indra не вернул координаты подписи рисунка на странице {page_index + 1}"
                            )
                        continue

                    candidate_index = self._match_candidate(
                        caption_rect, candidates, used, page.rect.height
                    )
                    if candidate_index is not None:
                        candidate = candidates[candidate_index]
                    elif has_page_background and is_numbered_figure:
                        scan_rect = self._scan_figure_rect(
                            page, caption_rect, caption_rects, table_rects, blocks
                        )
                        if scan_rect is None:
                            raise RuntimeError(
                                f"Не удалось определить область рисунка на странице {page_index + 1}: {caption_text[:100]}"
                            )
                        candidate = _VisualCandidate(rect=scan_rect, has_vector=True)
                    elif is_numbered_figure:
                        raise RuntimeError(
                            f"Не найден рисунок для подписи на странице {page_index + 1}: {caption_text[:100]}"
                        )
                    else:
                        continue

                    image_bytes, image_size, image_extension = self._extract_candidate(
                        document, page, candidate
                    )
                    filename = (
                        f"page-{page_index + 1:04d}-figure-{figure_index:03d}."
                        f"{image_extension}"
                    )
                    upload = await self.s3_service.upload_image(
                        image_bytes,
                        filename=filename,
                        folder=f"documents/{document_id}/images",
                    )
                    if not upload.get("success"):
                        raise RuntimeError(
                            f"Не удалось сохранить рисунок {filename} в S3: {upload.get('error')}"
                        )

                    object_key = str(upload["object_key"])
                    image_url = f"/api/v1/s3/image/{quote(object_key, safe='/')}"
                    markdown_segment = (
                        self._markdown_caption_segment(page_markdown, figure_number)
                        if figure_number is not None
                        else None
                    )
                    rendered_caption = (
                        markdown_segment[2]
                        if markdown_segment is not None
                        else caption_text
                    )
                    escaped_caption = html.escape(rendered_caption, quote=True)
                    figure_html = (
                        f'<figure><img src="{html.escape(image_url, quote=True)}" '
                        'alt="" />'
                        f"<figcaption>{escaped_caption}</figcaption></figure>"
                    )
                    if markdown_segment is not None:
                        start, end, _ = markdown_segment
                        page_markdown = (
                            page_markdown[:start] + figure_html + page_markdown[end:]
                        )
                    elif caption.get("source") == "pdf_text":
                        raise RuntimeError(
                            f"Подпись рисунка Fig. {figure_number} не найдена в Markdown на странице {page_index + 1}"
                        )
                    else:
                        page_markdown = self._replace_caption(
                            page_markdown, caption_text, figure_html
                        )
                    if candidate_index is not None:
                        used.add(candidate_index)
                    processed_captions.add(caption_key)
                    extracted_images.append(
                        {
                            "filename": filename,
                            "s3_url": image_url,
                            "s3_object_key": object_key,
                            "page_no": page_index + 1,
                            "size_bytes": len(image_bytes),
                            "image_size": image_size,
                            "content_type": self._content_type(image_extension),
                        }
                    )
                    logger.info(
                        "Извлечён рисунок: doc_id=%s, page=%s, image=%s",
                        document_id,
                        page_index + 1,
                        object_key,
                    )

                    if on_progress:
                        on_progress(
                            {
                                "percent": 75
                                + int(15 * (page_index + 1) / max(len(pages), 1)),
                                "phase": "figure_extraction",
                                "message": f"Обработана страница {page_index + 1} из {len(pages)}",
                            }
                        )

                markdown_pages.append(page_markdown.strip())

        return {
            "success": True,
            "method": "indra_layout",
            "images_extracted": len(extracted_images),
            "extracted_images": extracted_images,
            "markdown_content": "\n\n".join(markdown_pages).strip() + "\n",
            "markdown_length": sum(len(page) for page in markdown_pages),
            "document_id": document_id,
        }

    @staticmethod
    def _content_type(extension: str) -> str:
        """Определяет MIME-тип, соответствующий фактическому формату изображения."""
        return {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "bmp": "image/bmp",
            "webp": "image/webp",
            "tif": "image/tiff",
            "tiff": "image/tiff",
        }.get(extension.lower(), "application/octet-stream")


indra_figure_service = IndraFigureService()
