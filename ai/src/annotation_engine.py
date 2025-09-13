"""
Движок для автоматической аннотации PDF документов.
"""

import logging
import time
from typing import List, Dict, Any, Optional
import torch
from transformers import (
    AutoTokenizer, AutoModelForTokenClassification, 
    AutoModelForSequenceClassification, pipeline
)
import numpy as np
from dataclasses import dataclass

from .pdf_processor import PDFProcessor, PDFStructure
from .models import AnnotationItem

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Конфигурация модели."""
    name: str
    max_length: int
    device: str
    batch_size: int = 1


class AnnotationEngine:
    """Движок для автоматической аннотации."""
    
    def __init__(self, model_config: ModelConfig):
        self.config = model_config
        self.device = self._get_device()
        self.models = {}
        self.tokenizer = None
        self._load_models()
        
    def _get_device(self) -> str:
        """Определяет устройство для выполнения."""
        if self.config.device == "auto":
            if torch.cuda.is_available():
                return "cuda"
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                return "mps"
            else:
                return "cpu"
        return self.config.device
    
    def _load_models(self):
        """Загружает необходимые модели."""
        try:
            logger.info(f"Загрузка моделей на устройство: {self.device}")
            
            # Загружаем токенизатор
            self.tokenizer = AutoTokenizer.from_pretrained(self.config.name)
            
            # Загружаем модель для NER (Named Entity Recognition)
            self.models['ner'] = pipeline(
                "ner",
                model="dbmdz/bert-large-cased-finetuned-conll03-english",
                tokenizer="dbmdz/bert-large-cased-finetuned-conll03-english",
                device=0 if self.device == "cuda" else -1,
                aggregation_strategy="simple"
            )
            
            # Загружаем модель для классификации текста
            self.models['text_classification'] = pipeline(
                "text-classification",
                model="microsoft/DialoGPT-medium",
                device=0 if self.device == "cuda" else -1
            )
            
            # Загружаем модель для извлечения ключевых слов
            self.models['keyword_extraction'] = pipeline(
                "feature-extraction",
                model="sentence-transformers/all-MiniLM-L6-v2",
                device=0 if self.device == "cuda" else -1
            )
            
            logger.info("Модели успешно загружены")
            
        except Exception as e:
            logger.error(f"Ошибка загрузки моделей: {e}")
            raise
    
    def annotate_pdf(self, pdf_structure: PDFStructure) -> List[AnnotationItem]:
        """
        Аннотирует PDF документ.
        
        Args:
            pdf_structure: Структура PDF документа
            
        Returns:
            List[AnnotationItem]: Список аннотаций
        """
        start_time = time.time()
        annotations = []
        
        try:
            logger.info(f"Начало аннотации документа с {pdf_structure.total_pages} страницами")
            
            # Обрабатываем каждую страницу
            for page in pdf_structure.pages:
                page_annotations = self._annotate_page(page)
                annotations.extend(page_annotations)
            
            # Обрабатываем метаданные документа
            metadata_annotations = self._annotate_metadata(pdf_structure.metadata)
            annotations.extend(metadata_annotations)
            
            processing_time = time.time() - start_time
            logger.info(f"Аннотация завершена за {processing_time:.2f} секунд. Найдено {len(annotations)} аннотаций")
            
            return annotations
            
        except Exception as e:
            logger.error(f"Ошибка аннотации PDF: {e}")
            raise
    
    def _annotate_page(self, page) -> List[AnnotationItem]:
        """Аннотирует отдельную страницу."""
        annotations = []
        
        try:
            # Аннотируем текст страницы
            text_annotations = self._annotate_text(page.text, page.page_number)
            annotations.extend(text_annotations)
            
            # Аннотируем изображения
            for img_index, image in enumerate(page.images):
                image_annotations = self._annotate_image(image, page.page_number, img_index)
                annotations.extend(image_annotations)
            
            # Аннотируем таблицы
            for table_index, table in enumerate(page.tables):
                table_annotations = self._annotate_table(table, page.page_number, table_index)
                annotations.extend(table_annotations)
            
        except Exception as e:
            logger.warning(f"Ошибка аннотации страницы {page.page_number}: {e}")
        
        return annotations
    
    def _annotate_text(self, text: str, page_number: int) -> List[AnnotationItem]:
        """Аннотирует текстовое содержимое."""
        annotations = []
        
        if not text.strip():
            return annotations
        
        try:
            # NER аннотации
            ner_results = self.models['ner'](text)
            for entity in ner_results:
                annotation = AnnotationItem(
                    annotation_type="entity",
                    content=entity['word'],
                    confidence=entity['score'],
                    page_number=page_number,
                    metadata={
                        'entity_type': entity['entity_group'],
                        'start': entity['start'],
                        'end': entity['end']
                    }
                )
                annotations.append(annotation)
            
            # Извлечение ключевых слов
            keywords = self._extract_keywords(text)
            for keyword in keywords:
                annotation = AnnotationItem(
                    annotation_type="keyword",
                    content=keyword['text'],
                    confidence=keyword['score'],
                    page_number=page_number,
                    metadata=keyword.get('metadata', {})
                )
                annotations.append(annotation)
            
            # Обнаружение чисел
            numbers = self._detect_numbers(text)
            for number in numbers:
                annotation = AnnotationItem(
                    annotation_type="number",
                    content=number['text'],
                    confidence=number['confidence'],
                    page_number=page_number,
                    metadata=number.get('metadata', {})
                )
                annotations.append(annotation)
            
            # Обнаружение дат
            dates = self._detect_dates(text)
            for date in dates:
                annotation = AnnotationItem(
                    annotation_type="date",
                    content=date['text'],
                    confidence=date['confidence'],
                    page_number=page_number,
                    metadata=date.get('metadata', {})
                )
                annotations.append(annotation)
            
            # Обнаружение формул
            formulas = self._detect_formulas(text)
            for formula in formulas:
                annotation = AnnotationItem(
                    annotation_type="formula",
                    content=formula['text'],
                    confidence=formula['confidence'],
                    page_number=page_number,
                    metadata=formula.get('metadata', {})
                )
                annotations.append(annotation)
            
        except Exception as e:
            logger.warning(f"Ошибка аннотации текста на странице {page_number}: {e}")
        
        return annotations
    
    def _annotate_image(self, image: np.ndarray, page_number: int, image_index: int) -> List[AnnotationItem]:
        """Аннотирует изображение."""
        annotations = []
        
        try:
            # Простая аннотация изображения
            annotation = AnnotationItem(
                annotation_type="image",
                content=f"Изображение {image_index + 1}",
                confidence=0.9,
                page_number=page_number,
                metadata={
                    'image_index': image_index,
                    'width': image.shape[1],
                    'height': image.shape[0],
                    'channels': image.shape[2] if len(image.shape) > 2 else 1
                }
            )
            annotations.append(annotation)
            
        except Exception as e:
            logger.warning(f"Ошибка аннотации изображения {image_index} на странице {page_number}: {e}")
        
        return annotations
    
    def _annotate_table(self, table: Dict[str, Any], page_number: int, table_index: int) -> List[AnnotationItem]:
        """Аннотирует таблицу."""
        annotations = []
        
        try:
            # Аннотация таблицы
            annotation = AnnotationItem(
                annotation_type="table",
                content=f"Таблица {table_index + 1}",
                confidence=0.9,
                page_number=page_number,
                metadata={
                    'table_index': table_index,
                    'rows': table.get('rows', 0),
                    'columns': table.get('columns', 0),
                    'data': table.get('data', [])
                }
            )
            annotations.append(annotation)
            
        except Exception as e:
            logger.warning(f"Ошибка аннотации таблицы {table_index} на странице {page_number}: {e}")
        
        return annotations
    
    def _annotate_metadata(self, metadata: Dict[str, Any]) -> List[AnnotationItem]:
        """Аннотирует метаданные документа."""
        annotations = []
        
        try:
            # Заголовок
            if metadata.get('title'):
                annotation = AnnotationItem(
                    annotation_type="title",
                    content=metadata['title'],
                    confidence=0.95,
                    metadata={'source': 'metadata'}
                )
                annotations.append(annotation)
            
            # Автор
            if metadata.get('author'):
                annotation = AnnotationItem(
                    annotation_type="author",
                    content=metadata['author'],
                    confidence=0.95,
                    metadata={'source': 'metadata'}
                )
                annotations.append(annotation)
            
        except Exception as e:
            logger.warning(f"Ошибка аннотации метаданных: {e}")
        
        return annotations
    
    def _extract_keywords(self, text: str) -> List[Dict[str, Any]]:
        """Извлекает ключевые слова из текста."""
        keywords = []
        
        try:
            # Простое извлечение ключевых слов на основе частоты
            words = text.lower().split()
            word_freq = {}
            
            for word in words:
                # Очищаем слово от знаков препинания
                clean_word = ''.join(c for c in word if c.isalnum())
                if len(clean_word) > 3:  # Игнорируем короткие слова
                    word_freq[clean_word] = word_freq.get(clean_word, 0) + 1
            
            # Сортируем по частоте и берем топ-10
            sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
            
            for word, freq in sorted_words:
                keywords.append({
                    'text': word,
                    'score': min(freq / len(words), 1.0),
                    'metadata': {'frequency': freq}
                })
            
        except Exception as e:
            logger.warning(f"Ошибка извлечения ключевых слов: {e}")
        
        return keywords
    
    def _detect_numbers(self, text: str) -> List[Dict[str, Any]]:
        """Обнаруживает числа в тексте."""
        numbers = []
        
        try:
            import re
            
            # Паттерны для различных типов чисел
            patterns = [
                (r'\b\d+\.\d+\b', 'decimal'),
                (r'\b\d+\b', 'integer'),
                (r'\b\d+[eE][+-]?\d+\b', 'scientific'),
                (r'\b\d+%', 'percentage'),
            ]
            
            for pattern, num_type in patterns:
                matches = re.finditer(pattern, text)
                for match in matches:
                    numbers.append({
                        'text': match.group(),
                        'confidence': 0.9,
                        'metadata': {
                            'type': num_type,
                            'start': match.start(),
                            'end': match.end()
                        }
                    })
            
        except Exception as e:
            logger.warning(f"Ошибка обнаружения чисел: {e}")
        
        return numbers
    
    def _detect_dates(self, text: str) -> List[Dict[str, Any]]:
        """Обнаруживает даты в тексте."""
        dates = []
        
        try:
            import re
            
            # Паттерны для дат
            patterns = [
                r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',
                r'\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b',
            ]
            
            for pattern in patterns:
                matches = re.finditer(pattern, text)
                for match in matches:
                    dates.append({
                        'text': match.group(),
                        'confidence': 0.8,
                        'metadata': {
                            'start': match.start(),
                            'end': match.end()
                        }
                    })
            
        except Exception as e:
            logger.warning(f"Ошибка обнаружения дат: {e}")
        
        return dates
    
    def _detect_formulas(self, text: str) -> List[Dict[str, Any]]:
        """Обнаруживает математические формулы в тексте."""
        formulas = []
        
        try:
            import re
            
            # Паттерны для формул
            patterns = [
                r'\$[^$]+\$',  # LaTeX формулы
                r'\\[a-zA-Z]+\{[^}]+\}',  # LaTeX команды
                r'[a-zA-Z]\^[0-9]+',  # Степени
                r'[a-zA-Z]_[0-9]+',  # Индексы
            ]
            
            for pattern in patterns:
                matches = re.finditer(pattern, text)
                for match in matches:
                    formulas.append({
                        'text': match.group(),
                        'confidence': 0.85,
                        'metadata': {
                            'start': match.start(),
                            'end': match.end()
                        }
                    })
            
        except Exception as e:
            logger.warning(f"Ошибка обнаружения формул: {e}")
        
        return formulas
