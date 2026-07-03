#!/usr/bin/env python3
"""Image extraction via OpenDataLoader + S3 upload"""

import asyncio
import functools
import logging
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .s3_service import s3_service

logger = logging.getLogger(__name__)


class CoordinateExtractionService:
    """
    Сервис конвертации PDF через OpenDataLoader с сохранением изображений в S3.

    OpenDataLoader сам извлекает изображения и кладёт их в папку {stem}_images/.
    Мы загружаем эти изображения в S3 и обновляем пути в markdown.
    """

    def __init__(self):
        self.s3_service = s3_service

    async def extract_images_with_s3(
        self,
        pdf_path: Path,
        document_id: Optional[str] = None,
        on_progress: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Конвертировать PDF через OpenDataLoader (hybrid mode), загрузить
        изображения в S3 и вернуть markdown с обновлёнными ссылками.

        Args:
            pdf_path: Путь к PDF файлу
            document_id: ID документа для организации в S3
            on_progress: Callback для отслеживания прогресса

        Returns:
            Результаты с markdown и URL изображений в S3
        """
        try:
            import opendataloader_pdf

            logger.info("=== OpenDataLoader PDF Extraction with S3 ===")

            if on_progress:
                on_progress({"percent": 5, "message": "Инициализация S3..."})

            # Проверяем S3
            s3_health = await self.s3_service.health_check()
            if not s3_health["success"]:
                raise Exception(f"S3 service unavailable: {s3_health.get('error')}")

            import fitz
            total_pages = 0
            try:
                _pdf = fitz.open(str(pdf_path))
                total_pages = len(_pdf)
                _pdf.close()
            except Exception:
                pass

            if on_progress:
                on_progress(
                    {
                        "percent": 10,
                        "phase": "odl_ocr",
                        "message": (
                            f"Запуск OpenDataLoader (hybrid mode, {total_pages} стр.)..."
                            if total_pages
                            else "Запуск OpenDataLoader (hybrid mode)..."
                        ),
                    }
                )

            # Step 1: Запускаем OpenDataLoader — он сам вырезает изображения
            logger.info("Step 1: Запуск OpenDataLoader (hybrid=docling-fast)...")

            odl_output_dir = Path(tempfile.mkdtemp(prefix="odl_out_"))
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    functools.partial(
                        opendataloader_pdf.convert,
                        input_path=str(pdf_path),
                        output_dir=str(odl_output_dir),
                        # markdown-with-html: таблицы как HTML; json: координаты для прямого извлечения из PDF
                        format="markdown-with-html,json",
                        hybrid="docling-fast",
                        hybrid_fallback=True,
                        hybrid_timeout="180000",  # 3 мин — Docling нужно время для сложных таблиц
                        table_method="cluster",  # лучше для таблиц без явных границ
                        image_output="external",  # изображения в отдельных файлах
                    ),
                )

                stem = pdf_path.stem

                # Step 2: Читаем markdown
                md_path = odl_output_dir / f"{stem}.md"
                markdown_content = (
                    md_path.read_text(encoding="utf-8") if md_path.exists() else ""
                )
                logger.info(f"Markdown: {len(markdown_content)} символов")

                # Step 3: Загружаем изображения из папки {stem}_images/ в S3
                # ODL JSON используется для сопоставления изображений с координатами в PDF
                images_dir = odl_output_dir / f"{stem}_images"
                json_path = odl_output_dir / f"{stem}.json"
                extracted_images = await self._upload_odl_images(
                    images_dir=images_dir,
                    document_id=document_id,
                    pdf_path=pdf_path,
                    odl_json_path=json_path,
                    on_progress=on_progress,
                )

                # Step 4: Заменяем относительные пути в markdown на S3 пути
                if markdown_content and extracted_images:
                    markdown_content = self._replace_image_paths(
                        markdown_content=markdown_content,
                        stem=stem,
                        extracted_images=extracted_images,
                    )

            finally:
                shutil.rmtree(odl_output_dir, ignore_errors=True)

            if on_progress:
                on_progress({"percent": 100, "message": "Конвертация завершена"})

            return {
                "success": True,
                "method": "coordinate_based_s3",
                "coordinates_found": len(extracted_images),
                "images_extracted": len(extracted_images),
                "extracted_images": extracted_images,
                "markdown_content": markdown_content,
                "markdown_length": len(markdown_content),
                "coordinate_details": [],
                "document_id": document_id,
            }

        except Exception as e:
            logger.error(f"OpenDataLoader extraction failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "method": "coordinate_based_s3",
            }

    async def _upload_odl_images(
        self,
        images_dir: Path,
        document_id: Optional[str],
        pdf_path: Optional[Path] = None,
        odl_json_path: Optional[Path] = None,
        on_progress: Optional[Callable] = None,
    ) -> List[Dict[str, Any]]:
        """
        Загрузить изображения в S3 с максимальным качеством.

        Стратегия:
        1. Читаем ODL JSON — получаем bbox изображений на страницах PDF.
        2. Для каждого изображения ищем embedded растр в PDF (PyMuPDF get_images).
           Если найден — извлекаем исходник без потерь (extract_image).
        3. Если embedded растр не найден (векторная фигура, составная область) —
           рендерим crop страницы через PyMuPDF с DPI=216 (Matrix 2.25×).
        4. Если PDF недоступен или координаты не известны — берём файл из ODL как есть.
        """
        import io
        import json
        from PIL import Image

        extracted_images: List[Dict[str, Any]] = []

        if not images_dir.exists():
            logger.info(f"Папка изображений не найдена: {images_dir} — изображений нет")
            return extracted_images

        image_files = sorted(
            [f for f in images_dir.iterdir() if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".bmp")],
            key=lambda f: f.name,
        )

        if not image_files:
            logger.info("Изображений в папке ODL не найдено")
            return extracted_images

        logger.info(f"Step 3: Загрузка {len(image_files)} изображений в S3...")
        s3_folder = f"documents/{document_id}" if document_id else "images"
        total = len(image_files)

        # Строим индекс: имя файла ODL → {page_index, bbox} из ODL JSON
        odl_image_meta: Dict[str, Dict] = {}
        if odl_json_path and odl_json_path.exists():
            try:
                odl_data = json.loads(odl_json_path.read_text(encoding="utf-8"))
                kids = odl_data.get("kids", []) if isinstance(odl_data, dict) else []
                for el in kids:
                    if el.get("type") == "image" and el.get("source"):
                        filename = Path(el["source"]).name
                        bb = el.get("bounding box") or el.get("bounding_box")
                        odl_image_meta[filename] = {
                            "page_index": int(el.get("page number", 1)) - 1,  # 0-based
                            "bbox_bottomleft": bb,  # [x1, y1, x2, y2] origin=BOTTOMLEFT
                        }
            except Exception as e:
                logger.warning(f"Не удалось разобрать ODL JSON: {e}")

        # Открываем PDF для прямого извлечения изображений
        fitz_doc = None
        if pdf_path and pdf_path.exists():
            try:
                import fitz
                fitz_doc = fitz.open(str(pdf_path))
            except Exception as e:
                logger.warning(f"Не удалось открыть PDF через PyMuPDF: {e}")

        try:
            for idx, img_path in enumerate(image_files):
                try:
                    if on_progress and total > 0:
                        pct = 70 + int(25 * idx / total)
                        on_progress(
                            {
                                "percent": pct,
                                "phase": "extracting_images",
                                "message": f"Загрузка изображения {idx + 1}/{total}: {img_path.name}",
                            }
                        )

                    img_bytes, extraction_method, image_size = await self._get_best_image_bytes(
                        img_path=img_path,
                        odl_meta=odl_image_meta.get(img_path.name),
                        fitz_doc=fitz_doc,
                    )

                    upload_result = await self.s3_service.upload_image(
                        image_data=img_bytes,
                        filename=img_path.name,
                        folder=s3_folder,
                    )

                    if upload_result["success"]:
                        s3_key = upload_result["object_key"]
                        image_url = f"/api/v1/s3/image/{s3_key}"
                        logger.info(f"✅ Загружено: {img_path.name} → {s3_key} [{extraction_method}]")
                        extracted_images.append(
                            {
                                "filename": img_path.name,
                                "s3_object_key": s3_key,
                                "s3_url": image_url,
                                "picture_index": idx,
                                "page_no": (odl_image_meta[img_path.name]["page_index"] + 1)
                                if img_path.name in odl_image_meta
                                else None,
                                "size_bytes": len(img_bytes),
                                "image_size": image_size,
                                "extraction_method": extraction_method,
                                "document_id": document_id,
                            }
                        )
                    else:
                        logger.error(f"Ошибка загрузки {img_path.name}: {upload_result.get('error')}")

                except Exception as e:
                    logger.error(f"Ошибка обработки изображения {img_path.name}: {e}")
        finally:
            if fitz_doc:
                fitz_doc.close()

        logger.info(f"✅ Загружено {len(extracted_images)}/{total} изображений")
        return extracted_images

    async def _get_best_image_bytes(
        self,
        img_path: Path,
        odl_meta: Optional[Dict],
        fitz_doc: Any,
    ):
        """
        Вернуть (bytes, method_name, (width, height)) для изображения.

        Приоритеты:
        1. Embedded растр в PDF — extract_image() без перекодировки
        2. Рендер crop-региона с DPI=216 — для векторных фигур
        3. Файл из ODL как есть — фолбэк
        """
        import io
        import fitz as _fitz
        from PIL import Image

        RENDER_SCALE = 2.25  # ~216 DPI (72 * 2.25)

        if fitz_doc and odl_meta:
            page_index = odl_meta["page_index"]
            bb = odl_meta.get("bbox_bottomleft")

            if 0 <= page_index < len(fitz_doc) and bb and len(bb) == 4:
                page = fitz_doc[page_index]
                page_height = page.rect.height

                # ODL координаты: BOTTOMLEFT origin → конвертируем в PyMuPDF TOPLEFT
                x1, y_bot1, x2, y_bot2 = bb
                top = page_height - y_bot2
                bottom = page_height - y_bot1
                fitz_rect = _fitz.Rect(x1, top, x2, bottom)

                rect_w_pts = fitz_rect.x1 - fitz_rect.x0  # width in points
                rect_h_pts = fitz_rect.y1 - fitz_rect.y0  # height in points
                MIN_RECT_DIM = 2.0  # points — degenerate if smaller

                if rect_w_pts < MIN_RECT_DIM or rect_h_pts < MIN_RECT_DIM:
                    logger.warning(f"  {img_path.name}: degenerate rect {rect_w_pts:.1f}x{rect_h_pts:.1f}pt — skipping PDF extraction")
                    raise ValueError("degenerate rect")

                # Ищем embedded растр, bbox которого близко совпадает с fitz_rect
                try:
                    best_xref = None
                    best_overlap = 0.0
                    for img_info in page.get_images(full=True):
                        xref = img_info[0]
                        for img_rect in page.get_image_rects(xref):
                            intersection = fitz_rect & img_rect
                            if intersection.is_empty:
                                continue
                            overlap = intersection.get_area() / fitz_rect.get_area()
                            if overlap > best_overlap:
                                best_overlap = overlap
                                best_xref = xref

                    if best_xref is not None and best_overlap > 0.5:
                        # Проверяем: есть ли векторные пути поверх растра?
                        # Если да — нельзя брать только embedded растр, нужен рендер всего региона
                        vector_paths_in_region = sum(
                            1 for d in page.get_drawings()
                            if not (fitz_rect & d["rect"]).is_empty
                        )
                        if vector_paths_in_region > 3:
                            # Составная фигура: растр + векторный слой — рендерим целиком
                            logger.info(
                                f"  {img_path.name}: composite figure (embedded + {vector_paths_in_region} "
                                f"vector paths) — rendering at {int(72 * RENDER_SCALE)} DPI"
                            )
                            # Переходим к блоку рендера ниже
                        else:
                            # Чисто растровое изображение — берём исходник без потерь
                            base_image = fitz_doc.extract_image(best_xref)
                            img_bytes = base_image["image"]
                            pil = Image.open(io.BytesIO(img_bytes))
                            image_size = pil.size
                            pil.close()
                            # Если embedded слишком мал — не используем его
                            if image_size[0] < 50 or image_size[1] < 50:
                                raise ValueError(f"embedded image too small: {image_size}")
                            logger.info(
                                f"  {img_path.name}: embedded xref={best_xref} overlap={best_overlap:.2f} "
                                f"size={image_size}"
                            )
                            return img_bytes, "pdf_embedded", image_size
                except Exception as e:
                    logger.warning(f"  Не удалось извлечь embedded растр для {img_path.name}: {e}")

                # Фолбэк: рендер clip-региона с высоким DPI
                try:
                    matrix = _fitz.Matrix(RENDER_SCALE, RENDER_SCALE)
                    pixmap = page.get_pixmap(matrix=matrix, clip=fitz_rect, alpha=False)
                    # Проверяем размер — если слишком мал, падаем на ODL fallback
                    if pixmap.width < 50 or pixmap.height < 50:
                        raise ValueError(f"rendered image too small: {pixmap.width}x{pixmap.height}")
                    img_bytes = pixmap.tobytes("png")
                    image_size = (pixmap.width, pixmap.height)
                    logger.info(
                        f"  {img_path.name}: rendered DPI={72 * RENDER_SCALE:.0f} size={image_size}"
                    )
                    return img_bytes, f"pdf_render_{int(72 * RENDER_SCALE)}dpi", image_size
                except Exception as e:
                    logger.warning(f"  Не удалось отрендерить {img_path.name}: {e}")

        # Финальный фолбэк: исходный файл из ODL
        img_bytes = img_path.read_bytes()
        pil = Image.open(io.BytesIO(img_bytes))
        image_size = pil.size
        pil.close()
        return img_bytes, "opendataloader", image_size

    def _replace_image_paths(
        self,
        markdown_content: str,
        stem: str,
        extracted_images: List[Dict[str, Any]],
    ) -> str:
        """
        Заменить относительные пути изображений ODL на /api/v1/s3/image/{s3_key}.

        ODL генерирует: ![image 1]({stem}_images/imageFile1.png)
        Нужно заменить на: ![image 1](/api/v1/s3/image/documents/{doc_id}/images/imageFile1.png)
        """
        # Строим маппинг filename → s3_url
        filename_to_url: Dict[str, str] = {
            img["filename"]: img["s3_url"] for img in extracted_images
        }

        def replace_match(match: re.Match) -> str:
            alt = match.group(1)
            path = match.group(2)
            # Убираем префикс {stem}_images/ если есть
            filename = Path(path).name
            if filename in filename_to_url:
                return f"![{alt}]({filename_to_url[filename]})"
            # Путь уже абсолютный или не найден — оставляем как есть
            return match.group(0)

        return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace_match, markdown_content)

    async def get_document_images(self, document_id: str) -> Dict[str, Any]:
        """Получить все изображения документа из S3"""
        try:
            s3_folder = f"documents/{document_id}"
            result = await self.s3_service.list_images(folder=s3_folder)
            if result["success"]:
                return {
                    "success": True,
                    "document_id": document_id,
                    "images": result["images"],
                    "count": result["count"],
                }
            else:
                return {"success": False, "error": result["error"], "document_id": document_id}
        except Exception as e:
            logger.error(f"Не удалось получить изображения документа {document_id}: {e}")
            return {"success": False, "error": str(e), "document_id": document_id}

    async def delete_document_images(self, document_id: str) -> Dict[str, Any]:
        """Удалить все изображения документа из S3"""
        try:
            images_result = await self.get_document_images(document_id)
            if not images_result["success"]:
                return images_result
            deleted_count = 0
            errors = []
            for image in images_result["images"]:
                delete_result = await self.s3_service.delete_image(image["object_key"])
                if delete_result["success"]:
                    deleted_count += 1
                else:
                    errors.append(f"{image['filename']}: {delete_result['error']}")
            return {
                "success": len(errors) == 0,
                "document_id": document_id,
                "deleted_count": deleted_count,
                "total_count": len(images_result["images"]),
                "errors": errors,
            }
        except Exception as e:
            logger.error(f"Не удалось удалить изображения документа {document_id}: {e}")
            return {"success": False, "error": str(e), "document_id": document_id}


# Глобальный экземпляр сервиса
coordinate_extraction_service = CoordinateExtractionService()


async def test_coordinate_extraction_with_s3():
    """Тест координатного извлечения с S3"""
    pdf_path = Path("test_input/parkinson_paper.pdf").resolve()
    if not pdf_path.exists():
        logger.error(f"PDF не найден: {pdf_path}")
        return

    def progress_callback(data):
        logger.info(f"Прогресс: {data.get('percent', 0)}% - {data.get('message', 'Обработка')}")

    document_id = f"test_doc_{uuid.uuid4().hex[:8]}"
    logger.info("Тестирование координатного извлечения с S3...")
    results = await coordinate_extraction_service.extract_images_with_s3(
        pdf_path=pdf_path,
        document_id=document_id,
        on_progress=progress_callback,
    )

    logger.info(f"Успех: {results['success']}")
    if results["success"]:
        logger.info(f"Извлечено изображений: {results['images_extracted']}")
        logger.info(f"Длина markdown: {results['markdown_length']} символов")
    else:
        logger.error(f"Ошибка: {results['error']}")


if __name__ == "__main__":
    asyncio.run(test_coordinate_extraction_with_s3())
