#!/usr/bin/env python3
"""Coordinate-based image extraction с интеграцией S3"""

import logging
import asyncio
import uuid
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, Callable
import fitz  # PyMuPDF for precise extraction
from PIL import Image
import io

from .s3_service import s3_service

logger = logging.getLogger(__name__)

class CoordinateExtractionService:
    """
    Сервис извлечения изображений по координатам с сохранением в S3
    """
    
    def __init__(self):
        self.s3_service = s3_service
    
    async def extract_images_with_s3(
        self,
        pdf_path: Path,
        document_id: Optional[str] = None,
        on_progress: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Извлечь изображения используя координаты и сохранить в S3
        
        Args:
            pdf_path: Путь к PDF файлу
            document_id: ID документа для организации в S3
            on_progress: Callback для отслеживания прогресса
            
        Returns:
            Результаты извлечения с URL изображений в S3
        """
        
        try:
            from docling.document_converter import DocumentConverter

            logger.info("=== Coordinate-Based Image Extraction with S3 ===")

            if on_progress:
                on_progress({"percent": 5, "message": "Инициализация S3..."})

            # Проверяем S3
            s3_health = await self.s3_service.health_check()
            if not s3_health['success']:
                raise Exception(f"S3 service unavailable: {s3_health.get('error')}")

            # Подсчитываем страницы через fitz до Docling
            total_pages = 0
            try:
                _pdf = fitz.open(str(pdf_path))
                total_pages = len(_pdf)
                _pdf.close()
            except Exception:
                pass

            if on_progress:
                on_progress({
                    "percent": 10,
                    "phase": "docling_ocr",
                    "message": f"Распознавание документа ({total_pages} стр.)..." if total_pages else "Распознавание документа..."
                })

            # Step 1: Получаем координаты от Docling
            logger.info("Step 1: Получение координат от Docling...")

            # Перехватываем DEBUG логи Docling о прогрессе страниц
            # docling.pipeline.base_pipeline логирует на DEBUG:
            # "Finished converting pages X\N time=..."
            class _DoclingPageProgressHandler(logging.Handler):
                def __init__(self, tp, cb):
                    super().__init__(logging.DEBUG)
                    self._total = tp
                    self._cb = cb

                def emit(self, record):
                    if not self._cb or not self._total:
                        return
                    msg = record.getMessage()
                    if "Finished converting pages" not in msg:
                        return
                    try:
                        # Формат: "Finished converting pages X\N time=..."
                        token = msg.split("Finished converting pages")[1].strip().split()[0]
                        # token может быть "3\13" или "3/13"
                        token = token.replace("\\", "/")
                        done_str, total_str = token.split("/")
                        done = int(done_str)
                        total = int(total_str) if total_str else self._total
                        pct = 10 + int(60 * done / total) if total else 10
                        self._cb({
                            "percent": pct,
                            "phase": "docling_ocr",
                            "message": f"Распознавание страниц: {done}/{total}"
                        })
                    except Exception:
                        pass

            _progress_handler = None
            _docling_logger = logging.getLogger("docling.pipeline.base_pipeline")
            _prev_level = _docling_logger.level
            if on_progress and total_pages:
                _progress_handler = _DoclingPageProgressHandler(total_pages, on_progress)
                _docling_logger.addHandler(_progress_handler)
                # Временно снижаем уровень логгера до DEBUG чтобы получать эти сообщения
                _docling_logger.setLevel(logging.DEBUG)

            try:
                converter = DocumentConverter()
                result = converter.convert(str(pdf_path))
            except Exception as e:
                error_msg = str(e)
                if 'SSL' in error_msg or 'huggingface' in error_msg.lower() or 'connection' in error_msg.lower():
                    logger.error(f"Failed to download Docling model from HuggingFace: {error_msg}")
                    logger.info("Falling back to standard conversion without coordinate extraction")
                    raise Exception(f"Docling model download failed (SSL/network error). Please check internet connection or download models manually.")
                else:
                    raise
            finally:
                if _progress_handler:
                    _docling_logger.removeHandler(_progress_handler)
                    _docling_logger.setLevel(_prev_level if _prev_level != logging.NOTSET else logging.WARNING)
            
            coordinates = self._extract_coordinates_from_docling(result)
            logger.info(f"Найдено {len(coordinates)} координат изображений")
            
            if on_progress:
                on_progress({
                    "percent": 30,
                    "phase": "extracting_images",
                    "message": f"Распознано {total_pages} стр., найдено {len(coordinates)} изображений"
                })
            
            # Step 2: Извлечение изображений с PyMuPDF и сохранение в S3
            logger.info("Step 2: Извлечение изображений и сохранение в S3...")
            extracted_images = await self._extract_and_upload_images(
                pdf_path, coordinates, document_id, on_progress
            )
            
            if on_progress:
                on_progress({"percent": 80, "message": f"Извлечено {len(extracted_images)} изображений"})
            
            # Step 3: Экспорт markdown с S3 URL
            logger.info("Step 3: Экспорт markdown с S3 URL...")
            markdown_content = ""
            if hasattr(result, 'document') and result.document:
                markdown_content = result.document.export_to_markdown()

                # Конвертируем markdown таблицы в HTML
                markdown_content = self._convert_tables_to_html(markdown_content)

                # Обновляем ссылки на изображения на S3 URL (HTML figure теги)
                markdown_content = self._update_markdown_with_s3_urls(
                    markdown_content, extracted_images
                )
            
            if on_progress:
                on_progress({"percent": 100, "message": "Координатное извлечение завершено"})
            
            return {
                "success": True,
                "method": "coordinate_based_s3",
                "coordinates_found": len(coordinates),
                "images_extracted": len(extracted_images),
                "extracted_images": extracted_images,
                "markdown_content": markdown_content,
                "markdown_length": len(markdown_content),
                "coordinate_details": coordinates,
                "document_id": document_id
            }
            
        except Exception as e:
            logger.error(f"Coordinate-based extraction with S3 failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "method": "coordinate_based_s3"
            }
    
    def _extract_coordinates_from_docling(self, result) -> List[Dict[str, Any]]:
        """Извлечь информацию о координатах из результата Docling"""
        
        coordinates: List[Dict[str, Any]] = []
        
        try:
            if not hasattr(result, 'document') or not result.document:
                logger.warning("Нет документа в результате")
                return coordinates
            
            document = result.document
            
            if hasattr(document, 'pictures') and document.pictures:
                logger.info(f"Обработка {len(document.pictures)} изображений для координат")
                
                for i, picture in enumerate(document.pictures):
                    try:
                        # Извлекаем информацию о происхождении
                        if hasattr(picture, 'prov') and picture.prov:
                            for prov_item in picture.prov:
                                if hasattr(prov_item, 'bbox') and hasattr(prov_item, 'page_no'):
                                    bbox = prov_item.bbox
                                    page_no = prov_item.page_no
                                    
                                    # Конвертируем координаты
                                    coord_info = {
                                        "picture_index": i,
                                        "page_no": page_no,  # 1-based
                                        "page_index": page_no - 1,  # 0-based для PyMuPDF
                                        "bbox": {
                                            "left": bbox.l,
                                            "top": bbox.t,
                                            "right": bbox.r,
                                            "bottom": bbox.b,
                                            "coord_origin": str(bbox.coord_origin)
                                        },
                                        "width": bbox.r - bbox.l,
                                        "height": bbox.t - bbox.b,  # Note: BOTTOMLEFT origin
                                        "self_ref": picture.self_ref if hasattr(picture, 'self_ref') else f"#/pictures/{i}"
                                    }
                                    
                                    coordinates.append(coord_info)
                                    
                                    logger.info(f"Изображение {i}: Страница {page_no}, "
                                               f"BBox=({bbox.l:.1f}, {bbox.t:.1f}, {bbox.r:.1f}, {bbox.b:.1f}), "
                                               f"Размер=({coord_info['width']:.1f}x{coord_info['height']:.1f})")
                    
                    except Exception as e:
                        logger.warning(f"Не удалось извлечь координаты для изображения {i}: {e}")
                        continue
            
            logger.info(f"Извлечено {len(coordinates)} наборов координат")
            return coordinates
            
        except Exception as e:
            logger.error(f"Извлечение координат из Docling не удалось: {e}")
            return coordinates
    
    async def _extract_and_upload_images(
        self,
        pdf_path: Path,
        coordinates: List[Dict],
        document_id: Optional[str],
        on_progress: Optional[Callable] = None
    ) -> List[Dict[str, Any]]:
        """Извлечь изображения с PyMuPDF и загрузить в S3"""
        
        extracted_images = []
        
        try:
            # Открываем PDF с PyMuPDF
            doc = fitz.open(str(pdf_path))
            logger.info(f"Открыт PDF с {len(doc)} страницами для координатного извлечения")
            
            # Подготавливаем папку в S3
            s3_folder = f"documents/{document_id}/images" if document_id else "images"
            
            total_coords = len(coordinates)
            total_pages = len(doc)

            for idx, coord_info in enumerate(coordinates):
                try:
                    # Прогресс: 30-80% распределяем по изображениям
                    if on_progress and total_coords > 0:
                        pct = 30 + int(50 * idx / total_coords)
                        page_no = coord_info.get("page_no", idx + 1)
                        on_progress({
                            "percent": pct,
                            "phase": "extracting_images",
                            "message": f"Извлечение изображения {idx + 1}/{total_coords} (стр. {page_no}/{total_pages})"
                        })

                    page_index = coord_info["page_index"]
                    page = doc.load_page(page_index)
                    
                    # Получаем размеры страницы
                    page_rect = page.rect
                    page_height = page_rect.height
                    
                    logger.info(f"\n--- Извлечение изображения {coord_info['picture_index']} ---")
                    logger.info(f"Страница {coord_info['page_no']} (индекс {page_index})")
                    logger.info(f"Размеры страницы: {page_rect.width} x {page_rect.height}")
                    
                    # Конвертируем координаты Docling (BOTTOMLEFT) в PyMuPDF (TOPLEFT)
                    bbox = coord_info["bbox"]
                    
                    # Docling использует BOTTOMLEFT, PyMuPDF использует TOPLEFT
                    # Конвертируем координаты
                    left = bbox["left"]
                    right = bbox["right"]
                    # Для конвертации BOTTOMLEFT в TOPLEFT:
                    top = page_height - bbox["top"]
                    bottom = page_height - bbox["bottom"]
                    
                    # Создаем прямоугольник PyMuPDF
                    extract_rect = fitz.Rect(left, top, right, bottom)
                    
                    logger.info(f"Исходный bbox (BOTTOMLEFT): ({bbox['left']:.1f}, {bbox['top']:.1f}, {bbox['right']:.1f}, {bbox['bottom']:.1f})")
                    logger.info(f"Конвертированный rect (TOPLEFT): ({left:.1f}, {top:.1f}, {right:.1f}, {bottom:.1f})")
                    
                    # Извлекаем изображение из конкретной области
                    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=extract_rect)  # 2x масштаб для лучшего качества
                    
                    if pix.width > 0 and pix.height > 0:
                        # Конвертируем в PIL Image
                        img_data = pix.tobytes("png")
                        pil_image = Image.open(io.BytesIO(img_data))
                        
                        logger.info(f"Размер извлеченного изображения: {pil_image.size}")
                        logger.info(f"Режим извлеченного изображения: {pil_image.mode}")

                        # Генерируем имя файла (без случайной части для предсказуемости)
                        filename = f"page_{coord_info['page_no']}_pic_{coord_info['picture_index']}.png"
                        
                        # Загружаем в S3
                        upload_result = await self.s3_service.upload_image(
                            image_data=pil_image,
                            filename=filename,
                            folder=s3_folder
                        )
                        
                        # URL уже установлен как постоянная API ссылка в upload_image
                        if upload_result['success']:
                            upload_result['url_type'] = 'api_proxy'  # Постоянная API ссылка
                        
                        if upload_result['success']:
                            logger.info(f"✅ ЗАГРУЖЕНО В S3: {filename}")
                            
                            extracted_images.append({
                                "filename": filename,
                                "s3_object_key": upload_result['object_key'],
                                "s3_url": upload_result['url'],
                                "picture_index": coord_info["picture_index"],
                                "page_no": coord_info["page_no"],
                                "page_index": page_index,
                                "size_bytes": upload_result.get('size_bytes'),
                                "image_size": pil_image.size,
                                "extraction_method": "coordinate_based_s3",
                                "coordinates": coord_info,
                                "self_ref": coord_info["self_ref"],
                                "document_id": document_id
                            })
                            
                            if on_progress:
                                progress_percent = 30 + (idx + 1) / total_coords * 45  # 30-75%
                                on_progress({
                                    "percent": int(progress_percent),
                                    "type": "image_extracted",
                                    "filename": filename,
                                    "method": "coordinate_based_s3"
                                })
                        else:
                            logger.error(f"Не удалось загрузить изображение в S3: {upload_result.get('error')}")
                    else:
                        logger.warning(f"Пустой pixmap для изображения {coord_info['picture_index']}")
                    
                    pix = None  # Освобождаем память
                    
                except Exception as e:
                    logger.error(f"Не удалось извлечь изображение для координат {coord_info}: {e}")
                    continue
            
            doc.close()
            
            logger.info(f"✅ Координатное извлечение с S3: {len(extracted_images)} изображений")
            return extracted_images
            
        except Exception as e:
            logger.error(f"Координатное извлечение PyMuPDF не удалось: {e}")
            return extracted_images
    
    def _convert_tables_to_html(self, markdown_content: str) -> str:
        """Конвертирует markdown таблицы в HTML теги."""
        import re
        lines = markdown_content.split('\n')
        result = []
        i = 0
        while i < len(lines):
            line = lines[i]
            # Проверяем начало таблицы (строка с |)
            if '|' in line and line.strip().startswith('|'):
                table_lines = []
                while i < len(lines) and '|' in lines[i] and lines[i].strip().startswith('|'):
                    table_lines.append(lines[i])
                    i += 1
                # Пропускаем разделительные строки (|---|---|)
                header = None
                body_rows = []
                for tl in table_lines:
                    cells = [c.strip() for c in tl.strip().strip('|').split('|')]
                    if all(re.match(r'^[-:]+$', c) for c in cells if c):
                        continue  # разделитель
                    if header is None:
                        header = cells
                    else:
                        body_rows.append(cells)

                if header:
                    html = ['<table>']
                    html.append('<thead><tr>')
                    for h in header:
                        html.append(f'<th>{h}</th>')
                    html.append('</tr></thead>')
                    if body_rows:
                        html.append('<tbody>')
                        for row in body_rows:
                            html.append('<tr>')
                            for cell in row:
                                html.append(f'<td>{cell}</td>')
                            html.append('</tr>')
                        html.append('</tbody>')
                    html.append('</table>')
                    result.append(''.join(html))
                continue
            result.append(line)
            i += 1
        return '\n'.join(result)

    def _update_markdown_with_s3_urls(self, markdown_content: str, extracted_images: List[Dict]) -> str:
        """Обновить ссылки на изображения в markdown с относительными путями"""

        if not extracted_images:
            return markdown_content

        # Сортируем изображения по picture_index для сохранения порядка
        sorted_images = sorted(extracted_images, key=lambda x: x["picture_index"])

        # Заменяем плейсхолдеры <!-- image --> на реальные ссылки на изображения
        lines = markdown_content.split('\n')
        image_count = 0

        for i, line in enumerate(lines):
            if '<!-- image -->' in line and image_count < len(sorted_images):
                image_info = sorted_images[image_count]
                filename = image_info['filename']
                s3_key = image_info.get('s3_object_key', '')
                # Строим API proxy URL через s3_object_key
                image_url = f"/api/v1/s3/image/{s3_key}" if s3_key else image_info.get('s3_url', filename)

                # HTML разметка для изображений
                lines[i] = f'<figure><img src="{image_url}" alt="Изображение {image_count + 1}" style="max-width:100%"/><figcaption>Рисунок {image_count + 1}</figcaption></figure>'
                image_count += 1

                logger.info(f"Обновлена ссылка на изображение {image_count}: {image_url}")

        return '\n'.join(lines)
    
    async def get_document_images(self, document_id: str) -> Dict[str, Any]:
        """Получить все изображения документа из S3"""
        
        try:
            s3_folder = f"documents/{document_id}/images"
            result = await self.s3_service.list_images(folder=s3_folder)
            
            if result['success']:
                return {
                    "success": True,
                    "document_id": document_id,
                    "images": result['images'],
                    "count": result['count']
                }
            else:
                return {
                    "success": False,
                    "error": result['error'],
                    "document_id": document_id
                }
                
        except Exception as e:
            logger.error(f"Не удалось получить изображения документа {document_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "document_id": document_id
            }
    
    async def delete_document_images(self, document_id: str) -> Dict[str, Any]:
        """Удалить все изображения документа из S3"""
        
        try:
            # Получаем список изображений
            images_result = await self.get_document_images(document_id)
            
            if not images_result['success']:
                return images_result
            
            deleted_count = 0
            errors = []
            
            # Удаляем каждое изображение
            for image in images_result['images']:
                delete_result = await self.s3_service.delete_image(image['object_key'])
                if delete_result['success']:
                    deleted_count += 1
                else:
                    errors.append(f"{image['filename']}: {delete_result['error']}")
            
            return {
                "success": len(errors) == 0,
                "document_id": document_id,
                "deleted_count": deleted_count,
                "total_count": len(images_result['images']),
                "errors": errors
            }
            
        except Exception as e:
            logger.error(f"Не удалось удалить изображения документа {document_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "document_id": document_id
            }


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
        on_progress=progress_callback
    )
    
    logger.info(f"\n=== Результаты координатного извлечения с S3 ===")
    logger.info(f"Успех: {results['success']}")
    if results['success']:
        logger.info(f"Метод: {results['method']}")
        logger.info(f"Найдено координат: {results['coordinates_found']}")
        logger.info(f"Извлечено изображений: {results['images_extracted']}")
        logger.info(f"Длина markdown: {results['markdown_length']} символов")
        logger.info(f"ID документа: {results['document_id']}")
        
        if results['extracted_images']:
            logger.info(f"\nИзвлеченные изображения:")
            for img in results['extracted_images']:
                logger.info(f"  - {img['filename']} (Страница {img['page_no']}, {img['size_bytes']} байт, {img['image_size']})")
                logger.info(f"    S3 URL: {img['s3_url']}")
    else:
        logger.error(f"Ошибка: {results['error']}")


if __name__ == "__main__":
    asyncio.run(test_coordinate_extraction_with_s3())
