"""Сервис для работы с NLP процессорами"""
import logging
from typing import Dict, Any, List, Optional

from nlp.nlp_manager import NLPManager
from nlp.processors import SpacyProcessor
from nlp.mappers import SpacyMapper

logger = logging.getLogger(__name__)


class NLPService:
    """Сервис для NLP анализа текста и автоматической аннотации"""

    def __init__(self):
        """Инициализация NLP менеджера и регистрация процессоров"""
        self.nlp_manager = NLPManager()

        # Регистрируем spaCy процессор
        try:
            spacy_processor = SpacyProcessor()
            self.nlp_manager.register_processor(spacy_processor)
            logger.info("SpacyProcessor успешно зарегистрирован")
        except Exception as e:
            logger.error(f"Ошибка инициализации SpacyProcessor: {e}")
            # Не падаем, просто логируем - возможно модели не загружены

    def analyze_text(self, text: str, processors: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Полный NLP анализ текста всеми зарегистрированными процессорами

        Args:
            text: Текст для анализа
            processors: Список процессоров для использования (None = все)

        Returns:
            Словарь с результатами анализа от каждого процессора
        """
        try:
            results = self.nlp_manager.process_text(
                text=text,
                processor_names=processors,
                parallel=True
            )

            # Форматируем результаты для API ответа
            formatted_results = {}
            for proc_name, result in results.items():
                formatted_results[proc_name] = {
                    "annotations": [
                        {
                            "text": ann.text,
                            "type": ann.annotation_type,
                            "category": ann.category.value,
                            "start": ann.start_offset,
                            "end": ann.end_offset,
                            "confidence": ann.confidence,
                            "color": ann.color,
                            "metadata": ann.metadata
                        }
                        for ann in result.annotations
                    ],
                    "relations": [
                        {
                            "source_text": rel.source_text,
                            "target_text": rel.target_text,
                            "relation_type": rel.relation_type,
                            "confidence": rel.confidence,
                            "metadata": rel.metadata
                        }
                        for rel in result.relations
                    ],
                    "metadata": result.metadata
                }

            return formatted_results

        except Exception as e:
            logger.error(f"Ошибка анализа текста: {e}")
            raise

    def analyze_selection(self, text: str, start: int, end: int) -> Dict[str, Any]:
        """
        Анализ выделенного фрагмента текста для подсказок при аннотации

        Args:
            text: Полный текст
            start: Начальная позиция выделения
            end: Конечная позиция выделения

        Returns:
            Словарь с предложениями типов аннотации для выделенного текста
        """
        try:
            # Извлекаем выделенный фрагмент
            selected_text = text[start:end]

            # Анализируем с помощью spaCy
            results = self.nlp_manager.process_text(
                text=text,
                processor_names=["spacy"],
                parallel=False
            )

            if "spacy" not in results:
                return {
                    "success": False,
                    "message": "spaCy процессор недоступен"
                }

            spacy_result = results["spacy"]

            # Ищем аннотации, которые попадают в выделенный диапазон
            suggestions = []
            for ann in spacy_result.annotations:
                # Проверяем пересечение с выделенным фрагментом
                if (ann.start_offset >= start and ann.start_offset < end) or \
                   (ann.end_offset > start and ann.end_offset <= end) or \
                   (ann.start_offset <= start and ann.end_offset >= end):
                    suggestions.append({
                        "type": ann.annotation_type,
                        "category": ann.category.value,
                        "confidence": ann.confidence,
                        "color": ann.color
                    })

            # Убираем дубликаты и сортируем по уверенности
            unique_suggestions = {}
            for s in suggestions:
                key = s["type"]
                if key not in unique_suggestions or s["confidence"] > unique_suggestions[key]["confidence"]:
                    unique_suggestions[key] = s

            sorted_suggestions = sorted(
                unique_suggestions.values(),
                key=lambda x: x["confidence"],
                reverse=True
            )

            return {
                "success": True,
                "selected_text": selected_text,
                "suggestions": sorted_suggestions[:10]  # Топ 10 предложений
            }

        except Exception as e:
            logger.error(f"Ошибка анализа выделения: {e}")
            return {
                "success": False,
                "message": str(e)
            }

    def get_all_supported_types(self) -> Dict[str, Any]:
        """
        Получить все поддерживаемые типы аннотаций от всех процессоров

        Returns:
            Словарь с категориями и типами аннотаций
        """
        try:
            # Пока только spaCy, но в будущем можем добавить другие процессоры
            spacy_types = SpacyMapper.get_all_types()

            # Форматируем для API
            result = {}
            for category, types_dict in spacy_types.items():
                result[category.value] = {
                    "name": category.value,
                    "display_name": self._get_category_display_name(category.value),
                    "types": [
                        {
                            "code": code,
                            "name": name,
                            "color": color,
                            "source": "spacy"
                        }
                        for code, (name, color) in types_dict.items()
                    ]
                }

            return {
                "success": True,
                "categories": result,
                "total_types": sum(len(cat["types"]) for cat in result.values())
            }

        except Exception as e:
            logger.error(f"Ошибка получения поддерживаемых типов: {e}")
            raise

    def _get_category_display_name(self, category: str) -> str:
        """Получить отображаемое имя категории"""
        names = {
            "part_of_speech": "Части речи",
            "syntax": "Синтаксис",
            "sentence_member": "Члены предложения",
            "named_entity": "Именованные сущности",
            "morphology": "Морфология"
        }
        return names.get(category, category)
