"""NLP сервис для анализа текста с использованием spaCy"""
import logging
from typing import List, Dict, Any, Optional
import spacy
from spacy.tokens import Doc, Token

logger = logging.getLogger(__name__)


# Маппинг частей речи spaCy на русские названия
POS_MAPPING = {
    "NOUN": "Существительное",
    "VERB": "Глагол",
    "ADJ": "Прилагательное",
    "ADV": "Наречие",
    "PRON": "Местоимение",
    "ADP": "Предлог",
    "CONJ": "Союз",
    "CCONJ": "Союз",  # Coordinating conjunction
    "SCONJ": "Союз",  # Subordinating conjunction
    "INTJ": "Междометие",
    "DET": "Определитель",
    "NUM": "Числительное",
    "PART": "Частица",
    "PROPN": "Имя собственное"
}

# Маппинг синтаксических ролей (dependency labels) на русские названия членов предложения
DEP_MAPPING = {
    "nsubj": "Подлежащее",
    "nsubjpass": "Подлежащее",
    "ROOT": "Сказуемое",
    "dobj": "Дополнение",
    "iobj": "Дополнение",
    "pobj": "Дополнение",
    "advmod": "Обстоятельство",
    "amod": "Определение",
    "det": "Определение",
    "compound": "Определение",
    "attr": "Именная часть сказуемого",
    "agent": "Дополнение"
}


class NLPService:
    """Сервис для NLP анализа текста"""

    def __init__(self, model_name: str = "en_core_web_sm"):
        """
        Инициализация NLP сервиса

        Args:
            model_name: Название spaCy модели для английского языка
        """
        try:
            self.nlp = spacy.load(model_name)
            logger.info(f"spaCy модель '{model_name}' успешно загружена")
        except OSError:
            logger.warning(f"Модель '{model_name}' не найдена. Попытка загрузки...")
            import subprocess
            subprocess.run(["python", "-m", "spacy", "download", model_name], check=True)
            self.nlp = spacy.load(model_name)
            logger.info(f"spaCy модель '{model_name}' загружена после установки")

    def analyze_text(self, text: str) -> Dict[str, Any]:
        """
        Анализ текста с помощью spaCy

        Args:
            text: Текст для анализа

        Returns:
            Словарь с результатами анализа: токены, части речи, члены предложения, сущности
        """
        try:
            doc = self.nlp(text)

            tokens = []
            for token in doc:
                token_info = {
                    "text": token.text,
                    "start": token.idx,
                    "end": token.idx + len(token.text),
                    "pos": token.pos_,  # Часть речи (английская)
                    "pos_ru": POS_MAPPING.get(token.pos_, token.pos_),  # Часть речи (русская)
                    "dep": token.dep_,  # Синтаксическая роль (английская)
                    "dep_ru": DEP_MAPPING.get(token.dep_, ""),  # Член предложения (русский)
                    "lemma": token.lemma_,  # Начальная форма
                    "is_alpha": token.is_alpha,
                    "is_stop": token.is_stop
                }
                tokens.append(token_info)

            # Извлечение именованных сущностей
            entities = []
            for ent in doc.ents:
                entity_type_ru = self._map_entity_type(ent.label_)
                entities.append({
                    "text": ent.text,
                    "start": ent.start_char,
                    "end": ent.end_char,
                    "label": ent.label_,  # Тип сущности (английский)
                    "label_ru": entity_type_ru  # Тип сущности (русский)
                })

            return {
                "success": True,
                "tokens": tokens,
                "entities": entities,
                "text_length": len(text)
            }

        except Exception as e:
            logger.error(f"Ошибка анализа текста: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def analyze_selection(self, text: str, start: int, end: int) -> Dict[str, Any]:
        """
        Анализ выделенного фрагмента текста

        Args:
            text: Полный текст
            start: Начальная позиция выделения
            end: Конечная позиция выделения

        Returns:
            Словарь с предложениями по типу аннотации для выделенного текста
        """
        try:
            selected_text = text[start:end].strip()
            doc = self.nlp(text)

            # Найти токены, которые находятся в выделенном диапазоне
            selected_tokens = [
                token for token in doc
                if token.idx >= start and (token.idx + len(token.text)) <= end
            ]

            if not selected_tokens:
                return {
                    "success": True,
                    "suggestions": [],
                    "selected_text": selected_text
                }

            suggestions = []

            # Если выделен один токен
            if len(selected_tokens) == 1:
                token = selected_tokens[0]

                # Часть речи
                pos_ru = POS_MAPPING.get(token.pos_, token.pos_)
                if pos_ru:
                    suggestions.append({
                        "type": pos_ru,
                        "category": "part_of_speech",
                        "confidence": 0.9
                    })

                # Член предложения
                dep_ru = DEP_MAPPING.get(token.dep_, "")
                if dep_ru:
                    suggestions.append({
                        "type": dep_ru,
                        "category": "sentence_member",
                        "confidence": 0.85
                    })

            # Проверка на именованную сущность
            for ent in doc.ents:
                if ent.start_char >= start and ent.end_char <= end:
                    entity_type_ru = self._map_entity_type(ent.label_)
                    suggestions.append({
                        "type": entity_type_ru,
                        "category": "entity",
                        "confidence": 0.95,
                        "spacy_label": ent.label_
                    })

            # Проверка на число
            if any(token.like_num for token in selected_tokens):
                suggestions.append({
                    "type": "Число",
                    "category": "number",
                    "confidence": 0.9
                })

            return {
                "success": True,
                "suggestions": suggestions,
                "selected_text": selected_text,
                "token_count": len(selected_tokens)
            }

        except Exception as e:
            logger.error(f"Ошибка анализа выделения: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _map_entity_type(self, spacy_label: str) -> str:
        """
        Маппинг типов сущностей spaCy на русские названия

        Args:
            spacy_label: Тип сущности из spaCy

        Returns:
            Русское название типа сущности
        """
        mapping = {
            "PERSON": "Персона",
            "GPE": "Место",  # Geopolitical entity
            "LOC": "Место",
            "ORG": "Организация",
            "DATE": "Число",
            "TIME": "Число",
            "PERCENT": "Число",
            "MONEY": "Число",
            "QUANTITY": "Число",
            "CARDINAL": "Число",
            "ORDINAL": "Число",
            "PRODUCT": "Модель животного",  # Может быть моделью или продуктом
            "NORP": "Организация",  # Nationalities or religious/political groups
        }
        return mapping.get(spacy_label, spacy_label)

    def extract_biomedical_entities(self, text: str) -> List[Dict[str, Any]]:
        """
        Попытка извлечения биомедицинских сущностей
        (требует специализированной модели, например en_core_sci_sm)

        Args:
            text: Текст для анализа

        Returns:
            Список найденных биомедицинских сущностей
        """
        # Базовая реализация с общей моделью
        # Для продакшена рекомендуется использовать scispacy или biobert
        doc = self.nlp(text)

        biomedical_entities = []

        # Простая эвристика: слова, начинающиеся с заглавной буквы в середине предложения
        # могут быть генами или белками
        for token in doc:
            if token.is_alpha and token.text[0].isupper() and not token.is_sent_start:
                # Проверка, не является ли это обычным именем собственным
                if token.pos_ == "PROPN" and token.ent_type_ not in ["PERSON", "GPE", "ORG"]:
                    biomedical_entities.append({
                        "text": token.text,
                        "start": token.idx,
                        "end": token.idx + len(token.text),
                        "type": "Ген/Белок",  # Требует уточнения
                        "confidence": 0.5  # Низкая уверенность без специализированной модели
                    })

        return biomedical_entities
