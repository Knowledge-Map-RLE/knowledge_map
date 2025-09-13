"""
Модуль для обработки PDF документов.
"""

import io
import logging
from typing import List, Dict, Any, Optional, Tuple
import fitz  # PyMuPDF
import pdfplumber
from PIL import Image
import numpy as np
import cv2
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PDFPage:
    """Страница PDF документа."""
    page_number: int
    text: str
    images: List[np.ndarray]
    tables: List[Dict[str, Any]]
    bbox: Tuple[float, float, float, float]  # x, y, width, height


@dataclass
class PDFStructure:
    """Структура PDF документа."""
    total_pages: int
    pages: List[PDFPage]
    metadata: Dict[str, Any]


class PDFProcessor:
    """Процессор PDF документов."""
    
    def __init__(self, dpi: int = 300):
        self.dpi = dpi
        
    def process_pdf(self, pdf_content: bytes) -> PDFStructure:
        """
        Обрабатывает PDF документ и извлекает структурированную информацию.
        
        Args:
            pdf_content: Содержимое PDF файла в байтах
            
        Returns:
            PDFStructure: Структурированная информация о документе
        """
        try:
            # Открываем PDF с помощью PyMuPDF для извлечения изображений и текста
            pdf_doc = fitz.open(stream=pdf_content, filetype="pdf")
            
            # Открываем PDF с помощью pdfplumber для извлечения таблиц
            pdf_plumber = pdfplumber.open(io.BytesIO(pdf_content))
            
            pages = []
            total_pages = len(pdf_doc)
            
            for page_num in range(total_pages):
                logger.info(f"Обработка страницы {page_num + 1}/{total_pages}")
                
                # Извлекаем текст и изображения с помощью PyMuPDF
                page = pdf_doc[page_num]
                text = page.get_text()
                images = self._extract_images_from_page(page)
                
                # Извлекаем таблицы с помощью pdfplumber
                plumber_page = pdf_plumber.pages[page_num]
                tables = self._extract_tables_from_page(plumber_page)
                
                # Получаем размеры страницы
                rect = page.rect
                bbox = (0, 0, rect.width, rect.height)
                
                pdf_page = PDFPage(
                    page_number=page_num + 1,
                    text=text,
                    images=images,
                    tables=tables,
                    bbox=bbox
                )
                pages.append(pdf_page)
            
            pdf_doc.close()
            pdf_plumber.close()
            
            # Извлекаем метаданные
            metadata = self._extract_metadata(pdf_content)
            
            return PDFStructure(
                total_pages=total_pages,
                pages=pages,
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"Ошибка обработки PDF: {e}")
            raise
    
    def _extract_images_from_page(self, page) -> List[np.ndarray]:
        """Извлекает изображения со страницы."""
        images = []
        
        try:
            # Получаем список изображений на странице
            image_list = page.get_images()
            
            for img_index, img in enumerate(image_list):
                try:
                    # Получаем изображение
                    xref = img[0]
                    pix = fitz.Pixmap(page.parent, xref)
                    
                    if pix.n - pix.alpha < 4:  # GRAY или RGB
                        # Конвертируем в numpy array
                        img_data = pix.tobytes("png")
                        nparr = np.frombuffer(img_data, np.uint8)
                        cv_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        
                        if cv_img is not None:
                            images.append(cv_img)
                    
                    pix = None
                    
                except Exception as e:
                    logger.warning(f"Ошибка извлечения изображения {img_index}: {e}")
                    continue
                    
        except Exception as e:
            logger.warning(f"Ошибка извлечения изображений со страницы: {e}")
        
        return images
    
    def _extract_tables_from_page(self, page) -> List[Dict[str, Any]]:
        """Извлекает таблицы со страницы."""
        tables = []
        
        try:
            # Извлекаем таблицы
            page_tables = page.extract_tables()
            
            for table_index, table in enumerate(page_tables):
                if table:
                    table_data = {
                        'table_index': table_index,
                        'rows': len(table),
                        'columns': len(table[0]) if table else 0,
                        'data': table,
                        'bbox': None  # Можно добавить координаты таблицы
                    }
                    tables.append(table_data)
                    
        except Exception as e:
            logger.warning(f"Ошибка извлечения таблиц со страницы: {e}")
        
        return tables
    
    def _extract_metadata(self, pdf_content: bytes) -> Dict[str, Any]:
        """Извлекает метаданные из PDF."""
        metadata = {}
        
        try:
            pdf_doc = fitz.open(stream=pdf_content, filetype="pdf")
            pdf_metadata = pdf_doc.metadata
            
            if pdf_metadata:
                metadata.update({
                    'title': pdf_metadata.get('title', ''),
                    'author': pdf_metadata.get('author', ''),
                    'subject': pdf_metadata.get('subject', ''),
                    'creator': pdf_metadata.get('creator', ''),
                    'producer': pdf_metadata.get('producer', ''),
                    'creation_date': pdf_metadata.get('creationDate', ''),
                    'modification_date': pdf_metadata.get('modDate', '')
                })
            
            pdf_doc.close()
            
        except Exception as e:
            logger.warning(f"Ошибка извлечения метаданных: {e}")
        
        return metadata
    
    def detect_formulas(self, text: str) -> List[Dict[str, Any]]:
        """
        Обнаруживает математические формулы в тексте.
        
        Args:
            text: Текст для анализа
            
        Returns:
            List[Dict]: Список найденных формул с их позициями
        """
        formulas = []
        
        # Простые паттерны для обнаружения формул
        import re
        
        # Паттерны для математических выражений
        patterns = [
            r'\$[^$]+\$',  # LaTeX формулы в долларах
            r'\\[a-zA-Z]+\{[^}]+\}',  # LaTeX команды
            r'[a-zA-Z]\^[0-9]+',  # Степени
            r'[a-zA-Z]_[0-9]+',  # Индексы
            r'\\frac\{[^}]+\}\{[^}]+\}',  # Дроби
            r'\\sum|\\int|\\prod|\\lim',  # Математические операторы
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                formulas.append({
                    'content': match.group(),
                    'start': match.start(),
                    'end': match.end(),
                    'type': 'formula'
                })
        
        return formulas
    
    def detect_numbers_with_context(self, text: str) -> List[Dict[str, Any]]:
        """
        Обнаруживает числа с их контекстом.
        
        Args:
            text: Текст для анализа
            
        Returns:
            List[Dict]: Список найденных чисел с контекстом
        """
        numbers = []
        
        import re
        
        # Паттерны для различных типов чисел
        patterns = [
            r'\b\d+\.\d+\b',  # Десятичные числа
            r'\b\d+\b',  # Целые числа
            r'\b\d+[eE][+-]?\d+\b',  # Научная нотация
            r'\b\d+%',  # Проценты
            r'\$\d+(?:,\d{3})*(?:\.\d{2})?\b',  # Денежные суммы
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                # Извлекаем контекст вокруг числа
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end]
                
                numbers.append({
                    'number': match.group(),
                    'start': match.start(),
                    'end': match.end(),
                    'context': context,
                    'type': 'number'
                })
        
        return numbers
    
    def detect_dates(self, text: str) -> List[Dict[str, Any]]:
        """
        Обнаруживает даты в тексте.
        
        Args:
            text: Текст для анализа
            
        Returns:
            List[Dict]: Список найденных дат
        """
        dates = []
        
        import re
        from datetime import datetime
        
        # Паттерны для различных форматов дат
        patterns = [
            r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',  # DD/MM/YYYY или DD-MM-YYYY
            r'\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b',  # YYYY/MM/DD или YYYY-MM-DD
            r'\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4}\b',  # DD Mon YYYY
            r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{2,4}\b',  # Mon DD, YYYY
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                dates.append({
                    'date': match.group(),
                    'start': match.start(),
                    'end': match.end(),
                    'type': 'date'
                })
        
        return dates
