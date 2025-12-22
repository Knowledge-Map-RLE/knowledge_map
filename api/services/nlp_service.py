"""Сервис для работы с NLP процессорами"""
import logging
from typing import Dict, Any, List, Optional

from services.nlp_grpc_client import get_nlp_grpc_client

logger = logging.getLogger(__name__)


class NLPService:
    """Сервис для NLP анализа текста и автоматической аннотации"""

    def __init__(self):
        """Инициализация gRPC клиента для NLP сервиса"""
        self.grpc_client = get_nlp_grpc_client()
        logger.info("NLPService инициализирован с gRPC клиентом")

    async def analyze_text(self, text: str, processors: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Полный NLP анализ текста всеми зарегистрированными процессорами

        Args:
            text: Текст для анализа
            processors: Список процессоров для использования (None = все)

        Returns:
            Словарь с результатами анализа от каждого процессора
        """
        try:
            # Вызываем асинхронный gRPC метод
            await self.grpc_client.connect()
            grpc_result = await self.grpc_client.process_text(
                text=text,
                processor_names=processors,
                merge_results=False
            )

            if not grpc_result.get("success", False):
                error_msg = grpc_result.get("message", "Unknown error")
                logger.error(f"gRPC ошибка анализа текста: {error_msg}")
                raise Exception(f"NLP service error: {error_msg}")

            # Форматируем результаты для API ответа (совместимый формат)
            formatted_results = {}
            for result in grpc_result.get("results", []):
                proc_name = result.get("processor_name", "unknown")
                formatted_results[proc_name] = {
                    "annotations": [
                        {
                            "text": ann.get("text", ""),
                            "type": ann.get("annotation_type", ""),
                            "category": ann.get("category", "").lower(),
                            "start": ann.get("start_offset", 0),
                            "end": ann.get("end_offset", 0),
                            "confidence": ann.get("confidence", 0.0),
                            "color": ann.get("color", "#000000"),
                            "metadata": ann.get("metadata", {})
                        }
                        for ann in result.get("annotations", [])
                    ],
                    "relations": [
                        {
                            "source_text": rel.get("source_text", ""),
                            "target_text": rel.get("target_text", ""),
                            "relation_type": rel.get("relation_type", ""),
                            "confidence": rel.get("confidence", 0.0),
                            "metadata": rel.get("metadata", {})
                        }
                        for rel in result.get("relations", [])
                    ],
                    "metadata": result.get("metadata", {})
                }

            return formatted_results

        except Exception as e:
            logger.error(f"Ошибка анализа текста: {e}", exc_info=True)
            raise

    async def analyze_selection(self, text: str, start: int, end: int) -> Dict[str, Any]:
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

            # Вызываем асинхронный gRPC метод
            await self.grpc_client.connect()
            grpc_result = await self.grpc_client.process_selection(
                text=text,
                selection=selected_text,
                start_offset=start,
                end_offset=end,
                processor_names=["spacy"],
                merge_results=False
            )

            if not grpc_result.get("success", False):
                error_msg = grpc_result.get("message", "Unknown error")
                logger.error(f"gRPC ошибка анализа выделения: {error_msg}")
                return {
                    "success": False,
                    "message": error_msg
                }

            # Ищем аннотации, которые попадают в выделенный диапазон
            suggestions = []
            for result in grpc_result.get("results", []):
                for ann in result.get("annotations", []):
                    ann_start = ann.get("start_offset", 0)
                    ann_end = ann.get("end_offset", 0)
                    # Проверяем пересечение с выделенным фрагментом
                    if (ann_start >= start and ann_start < end) or \
                       (ann_end > start and ann_end <= end) or \
                       (ann_start <= start and ann_end >= end):
                        suggestions.append({
                            "type": ann.get("annotation_type", ""),
                            "category": ann.get("category", "").lower(),
                            "confidence": ann.get("confidence", 0.0),
                            "color": ann.get("color", "#000000")
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
            logger.error(f"Ошибка анализа выделения: {e}", exc_info=True)
            return {
                "success": False,
                "message": str(e)
            }

    async def get_all_supported_types(self) -> Dict[str, Any]:
        """
        Получить все поддерживаемые типы аннотаций от всех процессоров

        Returns:
            Словарь с категориями и типами аннотаций
        """
        try:
            # Вызываем асинхронный gRPC метод
            await self.grpc_client.connect()
            grpc_result = await self.grpc_client.get_supported_types()

            # Форматируем для API (совместимый формат)
            result = {}
            processors_info = grpc_result.get("processors", [])
            
            # Группируем типы по категориям из всех процессоров
            category_map = {}
            for proc in processors_info:
                proc_name = proc.get("name", "unknown")
                supported_categories = proc.get("supported_categories", [])
                
                for category_name in supported_categories:
                    if category_name not in category_map:
                        category_map[category_name] = {
                            "name": category_name,
                            "display_name": self._get_category_display_name(category_name),
                            "types": []
                        }
            
            # Добавляем типы аннотаций из списка
            annotation_types = grpc_result.get("annotation_types", [])
            for ann_type in annotation_types:
                # Пытаемся определить категорию (упрощенная логика)
                category = self._infer_category(ann_type)
                if category not in category_map:
                    category_map[category] = {
                        "name": category,
                        "display_name": self._get_category_display_name(category),
                        "types": []
                    }
                
                category_map[category]["types"].append({
                    "code": ann_type,
                    "name": ann_type,
                    "color": self._get_default_color_for_type(ann_type),
                    "source": "nlp_service"
                })

            return {
                "success": True,
                "categories": category_map,
                "total_types": sum(len(cat["types"]) for cat in category_map.values())
            }

        except Exception as e:
            logger.error(f"Ошибка получения поддерживаемых типов: {e}", exc_info=True)
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
        return names.get(category.lower(), category)

    def _infer_category(self, annotation_type: str) -> str:
        """Определить категорию по типу аннотации (упрощенная логика)"""
        type_lower = annotation_type.lower()
        if any(pos in type_lower for pos in ["noun", "verb", "adj", "adv", "pron", "det", "prep", "conj"]):
            return "part_of_speech"
        elif any(syn in type_lower for syn in ["subject", "object", "predicate", "modifier"]):
            return "sentence_member"
        elif any(ent in type_lower for ent in ["person", "org", "location", "date", "time"]):
            return "named_entity"
        else:
            return "general_entity"

    def _get_default_color_for_type(self, annotation_type: str) -> str:
        """Получить цвет по умолчанию для типа аннотации"""
        # Базовые цвета для разных категорий
        type_lower = annotation_type.lower()
        if "noun" in type_lower:
            return "#4CAF50"  # Green
        elif "verb" in type_lower:
            return "#2196F3"  # Blue
        elif "adj" in type_lower:
            return "#FF9800"  # Orange
        else:
            return "#9E9E9E"  # Grey default
