"""
Data models for actions and dependencies.
Перенесено из notebooks/action_dependency_extraction/models.py
"""

from typing import Optional, List


class Action:
    """Класс для представления действия (предиката)"""

    def __init__(self, action_id: str, verb: str, sentence_idx: int, token_idx):
        self.id = action_id
        self.verb = verb          # лемма глагола
        self.verb_text = verb     # оригинальная форма
        self.sentence_idx = sentence_idx
        self.token_idx = token_idx

        self.char_start = None
        self.char_end = None

        self.subject = None
        self.object = None
        self.indirect_object = None
        self.modifiers = []

        self.sentence_text = None

        self.is_nominalization = False
        self.is_entity = False
        self.entity_type = None

        self.ner_source = None
        self.ner_confidence = 0.95

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
            'ner_confidence': self.ner_confidence,
            'is_nominalization': self.is_nominalization,
            'is_entity': self.is_entity,
            'entity_type': self.entity_type,
        }


class Dependency:
    """Класс для представления зависимости между действиями"""

    def __init__(self, source_id: str, target_id: str, relation_type: str, confidence: float):
        self.source_id = source_id
        self.target_id = target_id
        self.relation_type = relation_type
        self.confidence = confidence
        self.evidence = []
        self.markers = []

    def __repr__(self):
        return f"Dependency({self.source_id} →[{self.relation_type}]→ {self.target_id}, conf={self.confidence:.2f})"

    def to_dict(self):
        return {
            'source': self.source_id,
            'target': self.target_id,
            'type': self.relation_type,
            'confidence': self.confidence,
            'markers': self.markers,
            'evidence': self.evidence,
        }
