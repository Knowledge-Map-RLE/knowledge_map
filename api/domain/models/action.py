"""
Layer: Domain (Entities)
Package: domain.models.action
Responsibility: Чистое представление Action и его лингвистических сущностей.

Принадлежит слою Domain — только бизнес-атрибуты без зависимостей от фреймворков.
Action хранит полную лингвистическую структуру (токены, спаны), из которой
рендерится текст метки и восстанавливается исходное предложение.

Allowed imports: только стандартная библиотека Python
Forbidden imports: neomodel, pydantic, fastapi, grpc, aioboto3, spacy
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LinguisticToken:
    """Один токен (слово) с лингвистическими атрибутами из spaCy."""
    id: int                    # индекс в предложении (spaCy token.i)
    text: str                  # оригинальная форма ("inhibits")
    lemma: str                 # лемма ("inhibit")
    pos: str                   # coarse POS (VERB, NOUN, ADJ, ADV, ...)
    pos_fine: str = ""         # fine-grained POS (VBZ, NN, JJ, ...)
    dep: str = ""              # dependency label (nsubj, dobj, amod, ...)
    head_id: int = -1          # индекс головного токена
    is_stop: bool = False
    is_punct: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "lemma": self.lemma,
            "pos": self.pos,
            "pos_fine": self.pos_fine,
            "dep": self.dep,
            "head_id": self.head_id,
            "is_stop": self.is_stop,
            "is_punct": self.is_punct,
        }

    @classmethod
    def from_dict(cls, data: dict) -> LinguisticToken:
        return cls(
            id=data["id"],
            text=data["text"],
            lemma=data["lemma"],
            pos=data["pos"],
            pos_fine=data.get("pos_fine", ""),
            dep=data.get("dep", ""),
            head_id=data.get("head_id", -1),
            is_stop=data.get("is_stop", False),
            is_punct=data.get("is_punct", False),
        )


@dataclass
class DependencySpan:
    """Связная группа токенов, образующая синтаксическую роль (subject, verb, object и т.д.)."""
    span_type: str             # "SUBJECT" | "VERB" | "OBJECT" | "MODIFIER" | "PARTICLE"
    token_ids: list[int]       # индексы токенов в спане
    head_token_id: int         # индекс главного токена (ядро спана)
    text: str                  # полный текст спана ("Rapamycin")
    lemma_form: str = ""       # нормализованная форма ("rapamycin")

    @property
    def is_empty(self) -> bool:
        return len(self.token_ids) == 0

    def to_dict(self) -> dict:
        return {
            "span_type": self.span_type,
            "token_ids": self.token_ids,
            "head_token_id": self.head_token_id,
            "text": self.text,
            "lemma_form": self.lemma_form,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DependencySpan:
        return cls(
            span_type=data["span_type"],
            token_ids=data["token_ids"],
            head_token_id=data["head_token_id"],
            text=data["text"],
            lemma_form=data.get("lemma_form", ""),
        )


@dataclass
class Action:
    """
    Действие (глаголь / номинализация / биомедицинская сущность),
    извлечённое из текста научной статьи.

    Хранит полную лингвистическую структуру — коллекцию токенов и спанов,
    из которых рендерится текст метки и восстанавливается предложение.
    """
    uid: str

    # Ядро: лингвистические сущности
    tokens: list[LinguisticToken] = field(default_factory=list)
    spans: list[DependencySpan] = field(default_factory=list)

    # Указатели на ключевые спаны (индексы в spans[])
    verb_span_idx: int = -1
    subject_span_idx: int = -1
    object_span_idx: int = -1

    # Кэшированный текст метки (для быстрого доступа без десериализации)
    label_text: str = ""

    # Метаданные
    sentence_text: str = ""
    sentence_idx: int = 0
    char_start: int = 0
    char_end: int = 0
    doc_id: Optional[str] = None
    annotation_uid: Optional[str] = None
    action_class: str = "action"   # "action" | "result" | "mechanism"
    norm_key: str = ""

    # ─── Свойства для быстрого доступа ───────────────────────────────────

    @property
    def verb_span(self) -> Optional[DependencySpan]:
        if 0 <= self.verb_span_idx < len(self.spans):
            return self.spans[self.verb_span_idx]
        return None

    @property
    def subject_span(self) -> Optional[DependencySpan]:
        if 0 <= self.subject_span_idx < len(self.spans):
            return self.spans[self.subject_span_idx]
        return None

    @property
    def object_span(self) -> Optional[DependencySpan]:
        if 0 <= self.object_span_idx < len(self.spans):
            return self.spans[self.object_span_idx]
        return None

    @property
    def modifier_spans(self) -> list[DependencySpan]:
        return [s for i, s in enumerate(self.spans)
                if s.span_type == "MODIFIER"
                and i not in (self.verb_span_idx, self.subject_span_idx, self.object_span_idx)]

    # ─── Рендеринг текста из лингвистических сущностей ──────────────────

    def render_label(self, mode: str = "compact") -> str:
        """Рендерит текст метки для визуализации.

        Modes:
            compact:  "Rapamycin inhibits mTOR"        (subject + verb + object)
            full:     "Rapamycin inhibits mTOR signaling"  (все спаны + модификаторы)
            verb_only: "inhibits"                      (только глагол)
            sentence: полное предложение из tokens
        """
        if mode == "verb_only":
            return self._render_verb_only()
        if mode == "sentence":
            return self.render_sentence()
        if mode == "full":
            return self._render_full()
        return self._render_compact()

    def render_sentence(self) -> str:
        """Восстанавливает предложение из tokens с пробелами и пунктуацией."""
        if not self.tokens:
            return self.sentence_text

        # Сортируем токены по id и собираем текст
        sorted_tokens = sorted(self.tokens, key=lambda t: t.id)
        parts: list[str] = []
        for token in sorted_tokens:
            if token.is_punct:
                # Пунктуация приклеивается к предыдущему токену без пробела
                if parts:
                    parts[-1] = parts[-1] + token.text
                else:
                    parts.append(token.text)
            else:
                parts.append(token.text)

        return " ".join(parts)

    def _render_compact(self) -> str:
        """subject + verb_text + object — стандартная метка."""
        subject = self.subject_span.text if self.subject_span else ""
        verb = self.verb_span.text if self.verb_span else ""
        obj = self.object_span.text if self.object_span else ""

        parts = [p for p in [subject, verb, obj] if p]
        return " ".join(parts)

    def _render_full(self) -> str:
        """Все ключевые спаны + модификаторы."""
        parts: list[str] = []
        if self.subject_span:
            parts.append(self.subject_span.text)
        if self.verb_span:
            parts.append(self.verb_span.text)
        for mod in self.modifier_spans:
            parts.append(mod.text)
        if self.object_span:
            parts.append(self.object_span.text)
        return " ".join(parts) if parts else self.label_text

    def _render_verb_only(self) -> str:
        if self.verb_span:
            return self.verb_span.text
        # Fallback: ищем токен-глагол
        for token in self.tokens:
            if token.pos == "VERB":
                return token.text
        return ""

    # ─── Сериализация / десериализация ─────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "tokens": [t.to_dict() for t in self.tokens],
            "spans": [s.to_dict() for s in self.spans],
            "verb_span_idx": self.verb_span_idx,
            "subject_span_idx": self.subject_span_idx,
            "object_span_idx": self.object_span_idx,
            "label_text": self.label_text or self.render_label("compact"),
            "sentence_text": self.sentence_text,
            "sentence_idx": self.sentence_idx,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "doc_id": self.doc_id,
            "annotation_uid": self.annotation_uid,
            "action_class": self.action_class,
            "norm_key": self.norm_key,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Action:
        action = cls(
            uid=data["uid"],
            tokens=[LinguisticToken.from_dict(t) for t in data.get("tokens", [])],
            spans=[DependencySpan.from_dict(s) for s in data.get("spans", [])],
            verb_span_idx=data.get("verb_span_idx", -1),
            subject_span_idx=data.get("subject_span_idx", -1),
            object_span_idx=data.get("object_span_idx", -1),
            label_text=data.get("label_text", ""),
            sentence_text=data.get("sentence_text", ""),
            sentence_idx=data.get("sentence_idx", 0),
            char_start=data.get("char_start", 0),
            char_end=data.get("char_end", 0),
            doc_id=data.get("doc_id"),
            annotation_uid=data.get("annotation_uid"),
            action_class=data.get("action_class", "action"),
            norm_key=data.get("norm_key", ""),
        )
        return action

    # ─── Быстрые геттеры для совместимости со старым кодом ─────────────

    @property
    def verb_lemma(self) -> str:
        """Лемма глагола (для совместимости со старым кодом)."""
        if self.verb_span:
            # Берём лемму головного токена
            for token in self.tokens:
                if token.id == self.verb_span.head_token_id:
                    return token.lemma
            # Fallback: первый токен спана
            if self.verb_span.token_ids and self.tokens:
                token_map = {t.id: t for t in self.tokens}
                first_id = self.verb_span.token_ids[0]
                if first_id in token_map:
                    return token_map[first_id].lemma
        return ""

    @property
    def verb_text(self) -> str:
        """Оригинальная форма глагола."""
        if self.verb_span:
            return self.verb_span.text
        return ""

    @property
    def subject_text(self) -> str:
        """Текст подлежащего."""
        return self.subject_span.text if self.subject_span else ""

    @property
    def object_text(self) -> str:
        """Текст дополнения."""
        return self.object_span.text if self.object_span else ""


# =============================================================================
# LexicalUnit — лингвистическая единица для поиска по графу
# =============================================================================

@dataclass
class LexicalUnit:
    """
    Отдельная лексическая единица — узел в графе Neo4j.

    Хранит один токен (слово) с лингвистическими атрибутами.
    Связывается с Action через PART_OF, между собой — через DEPENDS_ON.
    Позволяет искать паттерны на уровне графа без JSON-парсинга.
    """
    uid: str                       # UUID единицы
    text: str                      # оригинальная форма ("inhibits")
    lemma: str                     # лемма ("inhibit")
    pos: str                       # coarse POS (VERB, NOUN, ADJ, ...)
    pos_fine: str = ""             # fine-grained POS (VBZ, NN, JJ, ...)
    dep: str = ""                  # dependency label (nsubj, dobj, amod, ...)
    is_stop: bool = False
    is_punct: bool = False
    doc_id: Optional[str] = None   # для индексации по документу

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "text": self.text,
            "lemma": self.lemma,
            "pos": self.pos,
            "pos_fine": self.pos_fine,
            "dep": self.dep,
            "is_stop": self.is_stop,
            "is_punct": self.is_punct,
            "doc_id": self.doc_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> LexicalUnit:
        return cls(
            uid=data["uid"],
            text=data["text"],
            lemma=data["lemma"],
            pos=data["pos"],
            pos_fine=data.get("pos_fine", ""),
            dep=data.get("dep", ""),
            is_stop=data.get("is_stop", False),
            is_punct=data.get("is_punct", False),
            doc_id=data.get("doc_id"),
        )

    @classmethod
    def from_token(cls, token: LinguisticToken, doc_id: Optional[str] = None) -> LexicalUnit:
        """Создаёт LexicalUnit из LinguisticToken."""
        return cls(
            uid=f"lu_{token.id}",  # будет перезаписан UUID при сохранении
            text=token.text,
            lemma=token.lemma,
            pos=token.pos,
            pos_fine=token.pos_fine,
            dep=token.dep,
            is_stop=token.is_stop,
            is_punct=token.is_punct,
            doc_id=doc_id,
        )


@dataclass
class DependencyLink:
    """
    Синтаксическая связь между двумя LexicalUnit.

    Хранит тип зависимости (dep_label) между головным и зависимым токеном.
    В графе: (head)-[:DEPENDS_ON {dep_label}]->(dependent)
    """
    source_uid: str                # uid головного токена
    target_uid: str                # uid зависимого токена
    dep_label: str                 # nsubj, dobj, amod, compound, ...
    doc_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "source_uid": self.source_uid,
            "target_uid": self.target_uid,
            "dep_label": self.dep_label,
            "doc_id": self.doc_id,
        }
