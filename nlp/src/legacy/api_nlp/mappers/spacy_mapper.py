"""
Mapper for converting spaCy types to annotation system types.

Maps all 94 spaCy linguistic entity types to the annotation system format.
"""

from typing import Dict, Tuple
from ..base import AnnotationCategory


class SpacyMapper:
    """Maps spaCy annotation types to system annotation types with colors."""

    # Universal POS tags (18 types)
    POS_MAPPING: Dict[str, Tuple[str, str, AnnotationCategory]] = {
        # (spaCy code, русское название, цвет, категория)
        "ADJ": ("Прилагательное", "#4CAF50", AnnotationCategory.PART_OF_SPEECH),
        "ADP": ("Предлог", "#2196F3", AnnotationCategory.PART_OF_SPEECH),
        "ADV": ("Наречие", "#FF9800", AnnotationCategory.PART_OF_SPEECH),
        "AUX": ("Вспомогательный глагол", "#9C27B0", AnnotationCategory.PART_OF_SPEECH),
        "CCONJ": ("Сочинительный союз", "#00BCD4", AnnotationCategory.PART_OF_SPEECH),
        "DET": ("Определитель", "#3F51B5", AnnotationCategory.PART_OF_SPEECH),
        "INTJ": ("Междометие", "#E91E63", AnnotationCategory.PART_OF_SPEECH),
        "NOUN": ("Существительное", "#FFEB3B", AnnotationCategory.PART_OF_SPEECH),
        "NUM": ("Числительное", "#00E676", AnnotationCategory.PART_OF_SPEECH),
        "PART": ("Частица", "#FF5722", AnnotationCategory.PART_OF_SPEECH),
        "PRON": ("Местоимение", "#FFC107", AnnotationCategory.PART_OF_SPEECH),
        "PROPN": ("Имя собственное", "#CDDC39", AnnotationCategory.PART_OF_SPEECH),
        "PUNCT": ("Пунктуация", "#9E9E9E", AnnotationCategory.PART_OF_SPEECH),
        "SCONJ": ("Подчинительный союз", "#03A9F4", AnnotationCategory.PART_OF_SPEECH),
        "SYM": ("Символ", "#607D8B", AnnotationCategory.PART_OF_SPEECH),
        "VERB": ("Глагол", "#8BC34A", AnnotationCategory.PART_OF_SPEECH),
        "X": ("Прочее", "#795548", AnnotationCategory.PART_OF_SPEECH),
        "SPACE": ("Пробел", "#FFFFFF", AnnotationCategory.PART_OF_SPEECH),
    }

    # Dependency relations (44 types)
    DEP_MAPPING: Dict[str, Tuple[str, str, AnnotationCategory]] = {
        "acl": ("Придаточное определение", "#E1BEE7", AnnotationCategory.SYNTAX),
        "acomp": ("Адъективное дополнение", "#C5CAE9", AnnotationCategory.SYNTAX),
        "advcl": ("Обстоятельственное придаточное", "#B2DFDB", AnnotationCategory.SYNTAX),
        "advmod": ("Обстоятельство", "#C8E6C9", AnnotationCategory.SYNTAX),
        "agent": ("Агенс", "#DCEDC8", AnnotationCategory.SYNTAX),
        "amod": ("Определение (прилагательное)", "#F0F4C3", AnnotationCategory.SYNTAX),
        "appos": ("Приложение", "#FFECB3", AnnotationCategory.SYNTAX),
        "attr": ("Именная часть сказуемого", "#FFE0B2", AnnotationCategory.SYNTAX),
        "aux": ("Вспомогательный глагол", "#FFCCBC", AnnotationCategory.SYNTAX),
        "auxpass": ("Вспомогательный глагол (страд.)", "#D7CCC8", AnnotationCategory.SYNTAX),
        "case": ("Падежный показатель", "#CFD8DC", AnnotationCategory.SYNTAX),
        "cc": ("Сочинительный союз", "#F8BBD0", AnnotationCategory.SYNTAX),
        "ccomp": ("Придаточное дополнение", "#E1BEE7", AnnotationCategory.SYNTAX),
        "compound": ("Сложное слово", "#D1C4E9", AnnotationCategory.SYNTAX),
        "conj": ("Однородный член", "#C5CAE9", AnnotationCategory.SYNTAX),
        "csubj": ("Придаточное подлежащее", "#BBDEFB", AnnotationCategory.SYNTAX),
        "csubjpass": ("Придаточное подлежащее (страд.)", "#B3E5FC", AnnotationCategory.SYNTAX),
        "dative": ("Дательный падеж", "#B2EBF2", AnnotationCategory.SYNTAX),
        "dep": ("Неопределённая зависимость", "#B2DFDB", AnnotationCategory.SYNTAX),
        "det": ("Определитель", "#C8E6C9", AnnotationCategory.SYNTAX),
        "dobj": ("Прямое дополнение", "#DCEDC8", AnnotationCategory.SYNTAX),
        "expl": ("Формальное подлежащее", "#F0F4C3", AnnotationCategory.SYNTAX),
        "intj": ("Междометие", "#FFECB3", AnnotationCategory.SYNTAX),
        "mark": ("Маркер (союз)", "#FFE0B2", AnnotationCategory.SYNTAX),
        "meta": ("Мета-модификатор", "#FFCCBC", AnnotationCategory.SYNTAX),
        "neg": ("Отрицание", "#D7CCC8", AnnotationCategory.SYNTAX),
        "nmod": ("Именной модификатор", "#CFD8DC", AnnotationCategory.SYNTAX),
        "npadvmod": ("Именная группа (обстоятельство)", "#F8BBD0", AnnotationCategory.SYNTAX),
        "nsubj": ("Подлежащее", "#FFCDD2", AnnotationCategory.SENTENCE_MEMBER),
        "nsubjpass": ("Подлежащее (страд.)", "#FFCCBC", AnnotationCategory.SENTENCE_MEMBER),
        "nummod": ("Числовой модификатор", "#D7CCC8", AnnotationCategory.SYNTAX),
        "oprd": ("Объектный предикат", "#CFD8DC", AnnotationCategory.SYNTAX),
        "parataxis": ("Паратаксис", "#F8BBD0", AnnotationCategory.SYNTAX),
        "pcomp": ("Дополнение предлога", "#E1BEE7", AnnotationCategory.SYNTAX),
        "pobj": ("Объект предлога", "#D1C4E9", AnnotationCategory.SYNTAX),
        "poss": ("Притяжательный модификатор", "#C5CAE9", AnnotationCategory.SYNTAX),
        "preconj": ("Предсоюз", "#BBDEFB", AnnotationCategory.SYNTAX),
        "predet": ("Предопределитель", "#B3E5FC", AnnotationCategory.SYNTAX),
        "prep": ("Предложное дополнение", "#B2EBF2", AnnotationCategory.SYNTAX),
        "prt": ("Частица", "#B2DFDB", AnnotationCategory.SYNTAX),
        "punct": ("Пунктуация", "#9E9E9E", AnnotationCategory.SYNTAX),
        "quantmod": ("Модификатор квантора", "#C8E6C9", AnnotationCategory.SYNTAX),
        "relcl": ("Относительное придаточное", "#DCEDC8", AnnotationCategory.SYNTAX),
        "ROOT": ("Корень предложения", "#F44336", AnnotationCategory.SYNTAX),
        "xcomp": ("Инфинитивное дополнение", "#E91E63", AnnotationCategory.SYNTAX),
    }

    # Named Entity types (18 types)
    NER_MAPPING: Dict[str, Tuple[str, str, AnnotationCategory]] = {
        "PERSON": ("Персона", "#FF6B6B", AnnotationCategory.NAMED_ENTITY),
        "NORP": ("Национальность/Религия/Политика", "#FFA07A", AnnotationCategory.NAMED_ENTITY),
        "FAC": ("Здание/Сооружение", "#FFD93D", AnnotationCategory.NAMED_ENTITY),
        "ORG": ("Организация", "#6BCF7F", AnnotationCategory.NAMED_ENTITY),
        "GPE": ("Страна/Город/Штат", "#4ECDC4", AnnotationCategory.NAMED_ENTITY),
        "LOC": ("Локация", "#45B7D1", AnnotationCategory.NAMED_ENTITY),
        "PRODUCT": ("Продукт", "#96CEB4", AnnotationCategory.NAMED_ENTITY),
        "EVENT": ("Событие", "#FFEAA7", AnnotationCategory.NAMED_ENTITY),
        "WORK_OF_ART": ("Произведение искусства", "#DFE6E9", AnnotationCategory.NAMED_ENTITY),
        "LAW": ("Закон", "#74B9FF", AnnotationCategory.NAMED_ENTITY),
        "LANGUAGE": ("Язык", "#A29BFE", AnnotationCategory.NAMED_ENTITY),
        "DATE": ("Дата", "#FD79A8", AnnotationCategory.NAMED_ENTITY),
        "TIME": ("Время", "#FDCB6E", AnnotationCategory.NAMED_ENTITY),
        "PERCENT": ("Процент", "#55EFC4", AnnotationCategory.NAMED_ENTITY),
        "MONEY": ("Деньги", "#81ECEC", AnnotationCategory.NAMED_ENTITY),
        "QUANTITY": ("Количество", "#74B9FF", AnnotationCategory.NAMED_ENTITY),
        "ORDINAL": ("Порядковое числительное", "#A29BFE", AnnotationCategory.NAMED_ENTITY),
        "CARDINAL": ("Количественное числительное", "#FD79A8", AnnotationCategory.NAMED_ENTITY),
    }

    # Morphological features (14 categories)
    MORPH_MAPPING: Dict[str, Tuple[str, str, AnnotationCategory]] = {
        "Tense": ("Время", "#E8F5E9", AnnotationCategory.MORPHOLOGY),
        "Aspect": ("Вид", "#F1F8E9", AnnotationCategory.MORPHOLOGY),
        "Mood": ("Наклонение", "#F9FBE7", AnnotationCategory.MORPHOLOGY),
        "Voice": ("Залог", "#FFFDE7", AnnotationCategory.MORPHOLOGY),
        "Number": ("Число", "#FFF8E1", AnnotationCategory.MORPHOLOGY),
        "Person": ("Лицо", "#FFF3E0", AnnotationCategory.MORPHOLOGY),
        "Gender": ("Род", "#FBE9E7", AnnotationCategory.MORPHOLOGY),
        "Case": ("Падеж", "#EFEBE9", AnnotationCategory.MORPHOLOGY),
        "Degree": ("Степень", "#ECEFF1", AnnotationCategory.MORPHOLOGY),
        "VerbForm": ("Форма глагола", "#F3E5F5", AnnotationCategory.MORPHOLOGY),
        "PronType": ("Тип местоимения", "#EDE7F6", AnnotationCategory.MORPHOLOGY),
        "Poss": ("Притяжательное", "#E8EAF6", AnnotationCategory.MORPHOLOGY),
        "Reflex": ("Возвратное", "#E3F2FD", AnnotationCategory.MORPHOLOGY),
        "NumType": ("Тип числительного", "#E1F5FE", AnnotationCategory.MORPHOLOGY),
    }

    @classmethod
    def map_pos_tag(cls, pos_tag: str) -> Tuple[str, str, AnnotationCategory]:
        """
        Map spaCy POS tag to annotation type.

        Args:
            pos_tag: spaCy POS tag (e.g., "NOUN", "VERB")

        Returns:
            Tuple of (русское название, цвет, категория)
        """
        return cls.POS_MAPPING.get(
            pos_tag,
            ("Неизвестная часть речи", "#9E9E9E", AnnotationCategory.PART_OF_SPEECH)
        )

    @classmethod
    def map_dependency(cls, dep: str) -> Tuple[str, str, AnnotationCategory]:
        """
        Map spaCy dependency relation to annotation type.

        Args:
            dep: spaCy dependency relation (e.g., "nsubj", "dobj")

        Returns:
            Tuple of (русское название, цвет, категория)
        """
        return cls.DEP_MAPPING.get(
            dep,
            ("Неизвестная зависимость", "#9E9E9E", AnnotationCategory.SYNTAX)
        )

    @classmethod
    def map_entity_type(cls, ent_type: str) -> Tuple[str, str, AnnotationCategory]:
        """
        Map spaCy entity type to annotation type.

        Args:
            ent_type: spaCy entity type (e.g., "PERSON", "ORG")

        Returns:
            Tuple of (русское название, цвет, категория)
        """
        return cls.NER_MAPPING.get(
            ent_type,
            ("Неизвестная сущность", "#9E9E9E", AnnotationCategory.NAMED_ENTITY)
        )

    @classmethod
    def map_morph_feature(cls, feature: str) -> Tuple[str, str, AnnotationCategory]:
        """
        Map spaCy morphological feature to annotation type.

        Args:
            feature: spaCy morph feature (e.g., "Tense", "Number")

        Returns:
            Tuple of (русское название, цвет, категория)
        """
        return cls.MORPH_MAPPING.get(
            feature,
            ("Неизвестный признак", "#9E9E9E", AnnotationCategory.MORPHOLOGY)
        )

    @classmethod
    def get_all_types(cls) -> Dict[AnnotationCategory, Dict[str, Tuple[str, str]]]:
        """
        Get all supported annotation types grouped by category.

        Returns:
            Dict mapping category to dict of {spacy_code: (русское название, цвет)}
        """
        return {
            AnnotationCategory.PART_OF_SPEECH: {
                code: (name, color)
                for code, (name, color, _) in cls.POS_MAPPING.items()
            },
            AnnotationCategory.SYNTAX: {
                code: (name, color)
                for code, (name, color, _) in cls.DEP_MAPPING.items()
            },
            AnnotationCategory.NAMED_ENTITY: {
                code: (name, color)
                for code, (name, color, _) in cls.NER_MAPPING.items()
            },
            AnnotationCategory.MORPHOLOGY: {
                code: (name, color)
                for code, (name, color, _) in cls.MORPH_MAPPING.items()
            },
        }

    @classmethod
    def get_russian_names(cls) -> Dict[str, str]:
        """
        Get mapping of all spaCy codes to Russian names.

        Returns:
            Dict mapping spaCy code to Russian name
        """
        result = {}

        for code, (name, _, _) in cls.POS_MAPPING.items():
            result[code] = name

        for code, (name, _, _) in cls.DEP_MAPPING.items():
            result[code] = name

        for code, (name, _, _) in cls.NER_MAPPING.items():
            result[code] = name

        for code, (name, _, _) in cls.MORPH_MAPPING.items():
            result[code] = name

        return result

    @classmethod
    def get_colors(cls) -> Dict[str, str]:
        """
        Get mapping of all annotation types to their default colors.

        Returns:
            Dict mapping annotation type (Russian name) to color
        """
        result = {}

        for code, (name, color, _) in cls.POS_MAPPING.items():
            result[name] = color

        for code, (name, color, _) in cls.DEP_MAPPING.items():
            result[name] = color

        for code, (name, color, _) in cls.NER_MAPPING.items():
            result[name] = color

        for code, (name, color, _) in cls.MORPH_MAPPING.items():
            result[name] = color

        return result
