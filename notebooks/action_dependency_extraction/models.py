"""
Data models for actions and dependencies
"""

from typing import Optional, List


class Action:
    """Класс для представления действия (предиката)"""

    def __init__(self, action_id: str, verb: str, sentence_idx: int, token_idx: int):
        self.id = action_id
        self.verb = verb  # лемма глагола
        self.verb_text = verb  # оригинальная форма
        self.sentence_idx = sentence_idx
        self.token_idx = token_idx

        # Позиция в тексте для точного поиска
        self.char_start = None
        self.char_end = None

        # Аргументы предиката
        self.subject = None  # кто/что делает (ARG0, nsubj)
        self.object = None   # над чем делается (ARG1, obj, dobj)
        self.indirect_object = None  # косвенное дополнение (ARG2, iobj)
        self.modifiers = []  # модификаторы (advmod, amod, etc.)

        # Контекст
        self.sentence_text = None

        # Метаданные для NER (для сущностей)
        self.ner_source = None  # 'bc5cdr', 'bionlp', 'jnlpba', 'keyword', None для не-сущностей
        self.ner_confidence = 0.95  # Confidence score от модели

    def __repr__(self):
        subject_str = f"{self.subject}" if self.subject else "?"
        object_str = f"{self.object}" if self.object else "?"
        return f"Action({self.id}: {subject_str} → {self.verb} → {object_str})"

    def to_dict(self):
        return {
            'id': self.id,
            'verb': self.verb,
            'verb_text': self.verb_text,
            'subject': self.subject,
            'object': self.object,
            'indirect_object': self.indirect_object,
            'modifiers': self.modifiers,
            'sentence_idx': self.sentence_idx,
            'sentence': self.sentence_text,
            'char_start': self.char_start,
            'char_end': self.char_end,
            'ner_source': self.ner_source,
            'ner_confidence': self.ner_confidence
        }


class Dependency:
    """Класс для представления зависимости между действиями"""

    def __init__(self, source_id: str, target_id: str, relation_type: str, confidence: float):
        self.source_id = source_id  # ID действия-предка
        self.target_id = target_id  # ID действия-потомка
        self.relation_type = relation_type  # тип отношения
        self.confidence = confidence  # уверенность [0, 1]
        self.evidence = []  # текстовые свидетельства
        self.markers = []  # лингвистические маркеры

    def __repr__(self):
        return f"Dependency({self.source_id} →[{self.relation_type}]→ {self.target_id}, conf={self.confidence:.2f})"

    def to_dict(self):
        return {
            'source': self.source_id,
            'target': self.target_id,
            'type': self.relation_type,
            'confidence': self.confidence,
            'markers': self.markers
        }
