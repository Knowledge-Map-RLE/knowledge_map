"""
Улучшенные экстракторы v3.0 с интеграцией spaCy NER и синтаксическим анализом
"""

import re
import spacy
from typing import List, Optional, Set, Tuple
from collections import defaultdict

from .models import Action, Dependency
from .markers import (
    TEMPORAL_MARKERS, CAUSAL_MARKERS, CONDITIONAL_MARKERS,
    PURPOSE_MARKERS, MECHANISM_MARKERS, CORRELATION_MARKERS,
    PART_OF_MARKERS, PRIORITY
)
from .nominalization_data import NOMINALIZATION_SET, NOMINALIZATION_TO_BASE


class MultiModelNERExtractor:
    """
    Мульти-модельный NER экстрактор для биомедицинских текстов.
    Использует каскадный подход: BC5CDR → BioNLP → JNLPBA → keywords.
    """

    def __init__(self, use_gpu=False):
        """
        Инициализация трёх scispaCy моделей + fallback keywords

        Args:
            use_gpu: Использовать ли GPU (по умолчанию False для CPU)
        """
        print("Zagruzka scispaCy modeley...")

        # Загрузка 3 scispaCy моделей
        try:
            self.nlp_bc5cdr = spacy.load("en_ner_bc5cdr_md")       # Priority 1
            print("  BC5CDR (chemicals/diseases): [OK]")
        except:
            print("  [WARNING] BC5CDR model not available")
            self.nlp_bc5cdr = None

        try:
            self.nlp_bionlp = spacy.load("en_ner_bionlp13cg_md")   # Priority 2
            print("  BioNLP (16 bio types): [OK]")
        except:
            print("  [WARNING] BioNLP model not available")
            self.nlp_bionlp = None

        try:
            self.nlp_jnlpba = spacy.load("en_ner_jnlpba_md")       # Priority 3
            print("  JNLPBA (proteins/DNA/RNA): [OK]")
        except:
            print("  [WARNING] JNLPBA model not available")
            self.nlp_jnlpba = None

        # Fallback keywords (из старого HybridActionExtractor)
        self.biomedical_keywords = {
            # Химические вещества
            'MPTP', 'rotenone', 'paraquat', 'trichloroethylene',
            'perchloroethylene', 'dopamine', 'iron', 'calcium',
            'superoxide', 'peroxide', 'hydroxyl', 'ROS',
            'glucocerebroside', 'neuromelanin',

            # Белки и гены
            'α-synuclein', 'a-synuclein', 'synuclein',
            'LRRK2', 'Parkin', 'PINK1', 'DJ-1', 'ATP13A2',
            'SNCA', 'GBA', 'glucocerebrosidase',
            'Nrf2', 'Keap1',

            # Клеточные структуры
            'mitochondria', 'mitochondrion', 'lysosome',
            'complex I', 'electron transport chain',
            'microglia', 'astrocyte', 'astrocytes',
            'neuron', 'neurons', 'dopaminergic',

            # Болезни
            'PD', 'IPD', 'parkinsonism', 'Gaucher',

            # Анатомия
            'substantia nigra', 'SN', 'striatum', 'CNS',
        }

        # Priority mapping (для разрешения конфликтов)
        self.model_priority = {
            'bc5cdr': 1,    # Highest
            'bionlp': 2,
            'jnlpba': 3,
            'keyword': 4    # Lowest
        }

    def extract_entities(self, sentence_text: str, sentence_start: int,
                        sent_idx: int, start_id: int) -> List[Action]:
        """
        Каскадная экстракция сущностей с дедупликацией.

        Args:
            sentence_text: Текст предложения
            sentence_start: Начальная позиция предложения в тексте
            sent_idx: Индекс предложения
            start_id: Начальный ID для сущностей

        Returns:
            List[Action]: Список извлечённых сущностей как Action objects
        """
        all_entities = []

        # 1. BC5CDR (chemicals, diseases) - Priority 1
        if self.nlp_bc5cdr:
            bc5cdr_entities = self._extract_from_model(
                self.nlp_bc5cdr, sentence_text, 'bc5cdr'
            )
            all_entities.extend(bc5cdr_entities)

        # 2. BioNLP (16 types) - Priority 2, skip overlaps
        if self.nlp_bionlp:
            bionlp_entities = self._extract_from_model(
                self.nlp_bionlp, sentence_text, 'bionlp'
            )
            bionlp_filtered = self._filter_overlaps(bionlp_entities, all_entities)
            all_entities.extend(bionlp_filtered)

        # 3. JNLPBA (proteins, DNA, RNA) - Priority 3, skip overlaps
        if self.nlp_jnlpba:
            jnlpba_entities = self._extract_from_model(
                self.nlp_jnlpba, sentence_text, 'jnlpba'
            )
            jnlpba_filtered = self._filter_overlaps(jnlpba_entities, all_entities)
            all_entities.extend(jnlpba_filtered)

        # 4. Keyword fallback - skip overlaps
        keyword_entities = self._extract_keywords(sentence_text, 'keyword')
        keyword_filtered = self._filter_overlaps(keyword_entities, all_entities)
        all_entities.extend(keyword_filtered)

        # Convert to Action objects
        actions = self._convert_to_actions(
            all_entities, sentence_text, sentence_start, sent_idx, start_id
        )

        return actions

    def _extract_from_model(self, nlp_model, sentence_text: str, source: str) -> List[dict]:
        """
        Извлекает сущности из одной scispaCy модели.

        Returns:
            List[dict]: [{'text': str, 'label': str, 'start': int, 'end': int, 'source': str, 'confidence': float}, ...]
        """
        entities = []
        doc = nlp_model(sentence_text)

        for ent in doc.ents:
            entities.append({
                'text': ent.text,
                'label': ent.label_,
                'start': ent.start_char,
                'end': ent.end_char,
                'source': source,
                'confidence': 0.90  # scispaCy не возвращает confidence, используем дефолтный
            })

        return entities

    def _extract_keywords(self, sentence_text: str, source: str) -> List[dict]:
        """
        Извлекает сущности через keyword matching (fallback).

        Returns:
            List[dict]: [{'text': str, 'label': str, 'start': int, 'end': int, 'source': str, 'confidence': float}, ...]
        """
        entities = []

        for keyword in self.biomedical_keywords:
            # Case-insensitive поиск
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            for match in pattern.finditer(sentence_text):
                entities.append({
                    'text': match.group(),
                    'label': 'KEYWORD',  # Generic type
                    'start': match.start(),
                    'end': match.end(),
                    'source': source,
                    'confidence': 0.70  # Низкая уверенность для keywords
                })

        return entities

    def _filter_overlaps(self, new_entities: List[dict], existing_entities: List[dict]) -> List[dict]:
        """
        Удаляет перекрывающиеся entity spans.
        Приоритет отдаётся existing_entities (уже добавленным).
        """
        filtered = []
        for new_ent in new_entities:
            has_overlap = False
            for existing_ent in existing_entities:
                if self._spans_overlap(new_ent, existing_ent):
                    has_overlap = True
                    break

            if not has_overlap:
                filtered.append(new_ent)

        return filtered

    def _spans_overlap(self, ent1: dict, ent2: dict) -> bool:
        """
        Проверяет перекрытие span'ов двух сущностей.

        Returns:
            True если spans перекрываются, False иначе
        """
        return not (ent1['end'] <= ent2['start'] or ent1['start'] >= ent2['end'])

    def _convert_to_actions(self, entities: List[dict], sentence_text: str,
                           sentence_start: int, sent_idx: int, start_id: int) -> List[Action]:
        """
        Конвертирует извлечённые сущности в Action objects.
        """
        actions = []

        for i, ent in enumerate(entities):
            action_id = f"E{start_id + i}"

            action = Action(
                action_id=action_id,
                verb=ent['text'],
                sentence_idx=sent_idx,
                token_idx=None  # NER spans не имеют token index
            )

            action.verb_text = ent['text']
            action.sentence_text = sentence_text
            action.is_entity = True
            action.is_nominalization = False
            action.entity_type = ent['label']

            # Позиция в тексте
            action.char_start = sentence_start + ent['start']
            action.char_end = sentence_start + ent['end']

            # Аргументы = None для сущностей
            action.subject = None
            action.object = None
            action.indirect_object = None
            action.modifiers = []

            # NEW: Метаданные NER
            action.ner_source = ent['source']
            action.ner_confidence = ent['confidence']

            actions.append(action)

        return actions

    def merge_abbreviations(self, actions: List[Action], text: str) -> List[Action]:
        """
        Объединяет аббревиатуры с их полными формами.

        Паттерны:
        - "Full Name (AB)" → объединяется в одну сущность "Full Name (AB)"
        - "AB" в тексте, если найдено "Full Name (AB)" ранее
        - Автоматическое определение по первым буквам слов

        Args:
            actions: Список действий
            text: Исходный текст

        Returns:
            Список действий с объединёнными аббревиатурами
        """
        import re

        # Паттерн 1: Явные определения в скобках "Text (ABBR)"
        abbr_pattern_explicit = re.compile(r'\b([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)+)\s+\(([A-Z]{2,})\)', re.IGNORECASE)

        # Паттерн 2: Аббревиатуры из заглавных букв (2+ символа)
        abbr_pattern = re.compile(r'\b([A-Z]{2,})\b')

        # Находим все пары full_form -> abbreviation
        abbr_map = {}  # {abbreviation_lower: (full_form, abbr_original)}
        full_form_map = {}  # {full_form_lower: (full_form, abbreviation)}

        # 1. Сначала находим явные определения
        for match in abbr_pattern_explicit.finditer(text):
            full_form = match.group(1).strip()
            abbr = match.group(2).upper()

            abbr_map[abbr.lower()] = (full_form, abbr)
            full_form_map[full_form.lower()] = (full_form, abbr)

        # 2. Для каждой найденной аббревиатуры пытаемся найти полную форму
        # если она не была явно определена в скобках
        all_abbrs = abbr_pattern.findall(text)
        entity_actions = [a for a in actions if getattr(a, 'is_entity', False)]

        for abbr in set(all_abbrs):
            if abbr.lower() in abbr_map:
                continue  # Уже найдена явная форма

            # Пытаемся найти полную форму по первым буквам слов
            # Ищем в окрестности (±200 символов от каждого упоминания)
            for match in re.finditer(r'\b' + re.escape(abbr) + r'\b', text):
                pos = match.start()
                window_start = max(0, pos - 200)
                window_end = min(len(text), pos + 200)
                window = text[window_start:window_end]

                # Ищем последовательности слов, где первые буквы совпадают с аббревиатурой
                full_form = self._find_full_form_by_initials(window, abbr)
                if full_form:
                    abbr_map[abbr.lower()] = (full_form, abbr)
                    full_form_map[full_form.lower()] = (full_form, abbr)
                    break

        # Создаём словарь действий по их тексту (нормализованному)
        entity_actions = [a for a in actions if getattr(a, 'is_entity', False)]

        # Группируем сущности, которые являются аббревиатурами или полными формами
        merged_entities = {}  # {canonical_text: [action_ids]}
        actions_to_merge = {}  # {action_id: canonical_text}

        for action in entity_actions:
            text_lower = action.verb_text.lower().strip()

            # Проверяем, является ли это аббревиатурой
            if text_lower in abbr_map:
                full_form = abbr_map[text_lower]
                canonical = f"{full_form} ({text_lower.upper()})"
                actions_to_merge[action.id] = canonical
                if canonical not in merged_entities:
                    merged_entities[canonical] = []
                merged_entities[canonical].append(action)

            # Проверяем, является ли это полной формой
            elif text_lower in full_form_map:
                full_form, abbr = full_form_map[text_lower]
                canonical = f"{full_form} ({abbr})"
                actions_to_merge[action.id] = canonical
                if canonical not in merged_entities:
                    merged_entities[canonical] = []
                merged_entities[canonical].append(action)

        # Объединяем сущности: оставляем только одну для каждой canonical формы
        merged_actions = []
        seen_canonical = set()

        for action in actions:
            if action.id in actions_to_merge:
                canonical = actions_to_merge[action.id]
                if canonical not in seen_canonical:
                    # Обновляем текст на canonical форму
                    action.verb = canonical
                    action.verb_text = canonical
                    merged_actions.append(action)
                    seen_canonical.add(canonical)
                # Иначе пропускаем (дубликат)
            else:
                # Не сущность или не нуждается в объединении
                merged_actions.append(action)

        return merged_actions

    def _find_full_form_by_initials(self, window: str, abbr: str) -> Optional[str]:
        """
        Находит полную форму аббревиатуры по первым буквам слов в окне текста.

        Например, для "PD" найдёт "Parkinson Disease" или "Parkinson's Disease"

        Args:
            window: Окно текста вокруг аббревиатуры
            abbr: Аббревиатура (например, "PD")

        Returns:
            Полная форма или None, если не найдена
        """
        import re

        # Убираем пунктуацию и разбиваем на слова
        words = re.findall(r'\b[A-Z][a-z]+\b', window)

        # Ищем последовательности слов, где первые буквы совпадают с аббревиатурой
        abbr_upper = abbr.upper()
        abbr_len = len(abbr_upper)

        for i in range(len(words) - abbr_len + 1):
            # Проверяем последовательность из abbr_len слов
            candidate_words = words[i:i + abbr_len]

            # Извлекаем первые буквы
            initials = ''.join([w[0].upper() for w in candidate_words])

            if initials == abbr_upper:
                # Нашли совпадение! Формируем полную форму
                full_form = ' '.join(candidate_words)

                # Проверяем, что это не часть более длинной фразы
                # (минимальная эвристика: слова должны быть не слишком короткими)
                if all(len(w) >= 2 for w in candidate_words):
                    return full_form

        return None


class HybridActionExtractor:
    """
    Гибридный экстрактор, использующий Stanza для синтаксиса и spaCy для NER
    """

    def __init__(self, nlp_stanza, multi_ner_extractor=None):
        self.nlp_stanza = nlp_stanza

        # NEW: Multi-model NER extractor
        if multi_ner_extractor is None:
            self.multi_ner = MultiModelNERExtractor(use_gpu=False)  # CPU по умолчанию
        else:
            self.multi_ner = multi_ner_extractor

        # DEPRECATED: удаляем старый spaCy и keywords
        # self.nlp_spacy = ...
        # self.biomedical_keywords = ...

    def extract_actions_from_text(self, text: str) -> List[Action]:
        """
        Извлекает действия (глаголы + номинализации + сущности)
        """
        print("Извлечение действий (гибридный подход: Stanza + scispaCy multi-model NER)...")

        # Парсим текст Stanza
        doc_stanza = self.nlp_stanza(text)

        actions = []
        action_counter = 0
        current_char_pos = 0

        for sent_idx, sentence in enumerate(doc_stanza.sentences):
            sentence_text = sentence.text
            sentence_start = text.find(sentence_text, current_char_pos)
            if sentence_start == -1:
                sentence_start = current_char_pos

            # 1. Извлекаем глагольные действия (Stanza)
            verb_actions = self._extract_verb_actions(
                sentence, sent_idx, sentence_start, sentence_text, action_counter
            )
            actions.extend(verb_actions)
            action_counter += len(verb_actions)

            # 2. Извлекаем номинализации (Stanza)
            nominal_actions = self._extract_nominalizations(
                sentence, sent_idx, sentence_start, sentence_text, action_counter
            )
            actions.extend(nominal_actions)
            action_counter += len(nominal_actions)

            # 3. NEW: Извлекаем биомедицинские сущности (multi-model NER)
            entity_actions = self.multi_ner.extract_entities(
                sentence_text, sentence_start, sent_idx, action_counter
            )
            actions.extend(entity_actions)
            action_counter += len(entity_actions)

            current_char_pos = sentence_start + len(sentence_text)

        # NEW: Объединяем аббревиатуры с полными формами
        print("Объединение аббревиатур...")
        actions_before = len(actions)
        actions = self.multi_ner.merge_abbreviations(actions, text)
        if len(actions) < actions_before:
            print(f"  Объединено {actions_before - len(actions)} дубликатов аббревиатур")

        # Статистика
        verb_count = sum(1 for a in actions if not getattr(a, 'is_nominalization', False) and not getattr(a, 'is_entity', False))
        nominal_count = sum(1 for a in actions if getattr(a, 'is_nominalization', False))
        entity_count = sum(1 for a in actions if getattr(a, 'is_entity', False))

        print(f"[OK] Извлечено {len(actions)} действий")
        print(f"  - Глагольных: {verb_count}")
        print(f"  - Номинализаций: {nominal_count}")
        print(f"  - Сущностей: {entity_count}")

        return actions

    def _extract_verb_actions(self, sentence, sent_idx, sentence_start, sentence_text, start_id):
        """Извлекает глагольные действия"""
        actions = []

        for token in sentence.words:
            # Пропускаем AUX если есть главный глагол
            if token.upos == 'AUX':
                has_main_verb = any(
                    w.head == token.id and w.deprel in ['xcomp', 'ccomp', 'aux']
                    for w in sentence.words
                )
                if has_main_verb:
                    continue

            if token.upos in ['VERB', 'AUX']:
                action = self._create_action(
                    token, sentence, sent_idx, sentence_start,
                    sentence_text, f"A{start_id + len(actions)}"
                )
                actions.append(action)

        return actions

    def _extract_nominalizations(self, sentence, sent_idx, sentence_start, sentence_text, start_id):
        """Извлекает номинализации"""
        actions = []

        for token in sentence.words:
            if token.upos == 'NOUN' and token.lemma in NOMINALIZATION_SET:
                action = self._create_nominalization_action(
                    token, sentence, sent_idx, sentence_start,
                    sentence_text, f"N{start_id + len(actions)}"
                )
                if action:
                    actions.append(action)

        return actions

    # DEPRECATED: Метод удалён, используется MultiModelNERExtractor.extract_entities()
    # def _extract_biomedical_entities(...) - удалено

    def _create_action(self, token, sentence, sent_idx, sentence_start, sentence_text, action_id):
        """Создаёт действие из глагола"""
        action = Action(
            action_id=action_id,
            verb=token.lemma,
            sentence_idx=sent_idx,
            token_idx=token.id
        )
        action.verb_text = token.text
        action.sentence_text = sentence_text
        action.is_nominalization = False
        action.is_entity = False

        # Позиция
        words_before = [w.text for w in sentence.words if w.id < token.id]
        if words_before:
            total_chars = sum(len(w) for w in words_before)
            total_spaces = len(words_before)
            verb_pos_in_sent = total_chars + total_spaces
        else:
            verb_pos_in_sent = 0

        action.char_start = sentence_start + verb_pos_in_sent
        action.char_end = action.char_start + len(token.text)

        # Аргументы
        action.subject = self._extract_subject(token, sentence)
        action.object = self._extract_object(token, sentence)
        action.indirect_object = self._extract_indirect_object(token, sentence)
        action.modifiers = self._extract_modifiers(token, sentence)

        return action

    def _create_nominalization_action(self, token, sentence, sent_idx, sentence_start, sentence_text, action_id):
        """Создаёт псевдо-действие из номинализации"""
        action = Action(
            action_id=action_id,
            verb=NOMINALIZATION_TO_BASE.get(token.lemma, token.lemma),
            sentence_idx=sent_idx,
            token_idx=token.id
        )
        action.verb_text = token.text
        action.sentence_text = sentence_text
        action.is_nominalization = True
        action.is_entity = False

        # Позиция
        words_before = [w.text for w in sentence.words if w.id < token.id]
        if words_before:
            total_chars = sum(len(w) for w in words_before)
            total_spaces = len(words_before)
            nom_pos_in_sent = total_chars + total_spaces
        else:
            nom_pos_in_sent = 0

        action.char_start = sentence_start + nom_pos_in_sent
        action.char_end = action.char_start + len(token.text)

        # Аргументы
        action.subject = self._extract_nominalization_subject(token, sentence)
        action.object = self._extract_nominalization_object(token, sentence)
        action.modifiers = self._extract_modifiers(token, sentence)

        return action

    # DEPRECATED: Методы _create_entity_action и _create_keyword_entity_action удалены
    # Используется MultiModelNERExtractor._convert_to_actions() вместо них

    def _extract_nominalization_subject(self, token, sentence) -> Optional[str]:
        """Извлекает субъект номинализации"""
        for child in sentence.words:
            if child.head == token.id and child.deprel.startswith('nmod'):
                for case_word in sentence.words:
                    if case_word.head == child.id and case_word.deprel == 'case':
                        if case_word.text.lower() in ['of', 'in', 'by']:
                            return self._get_full_phrase(child, sentence)

        for child in sentence.words:
            if child.head == token.id and child.deprel == 'compound':
                return child.text

        return None

    def _extract_nominalization_object(self, token, sentence) -> Optional[str]:
        return None

    def _extract_subject(self, token, sentence) -> Optional[str]:
        """Извлекает субъект"""
        for word in sentence.words:
            if word.head == token.id and word.deprel in ['nsubj', 'nsubj:pass', 'csubj']:
                return self._get_full_phrase(word, sentence)

        parent_token = None
        for word in sentence.words:
            if word.id == token.head:
                parent_token = word
                break

        if parent_token and token.deprel == 'xcomp':
            parent_subj = self._extract_subject(parent_token, sentence)
            if parent_subj:
                return parent_subj

        if token.deprel in ['acl', 'acl:relcl']:
            if parent_token:
                return self._get_full_phrase(parent_token, sentence)

        for word in sentence.words:
            if word.head == token.id and word.deprel == 'obl:agent':
                return self._get_full_phrase(word, sentence)

        return None

    def _extract_object(self, token, sentence) -> Optional[str]:
        for word in sentence.words:
            if word.head == token.id and word.deprel in ['obj', 'dobj', 'obl']:
                return self._get_full_phrase(word, sentence)
        return None

    def _extract_indirect_object(self, token, sentence) -> Optional[str]:
        for word in sentence.words:
            if word.head == token.id and word.deprel == 'iobj':
                return self._get_full_phrase(word, sentence)
        return None

    def _extract_modifiers(self, token, sentence) -> List[str]:
        modifiers = []
        for word in sentence.words:
            if word.head == token.id and word.deprel in ['advmod', 'amod', 'npadvmod']:
                modifiers.append(word.text)
        return modifiers

    def _get_full_phrase(self, word, sentence) -> str:
        """Получает полную фразу с модификаторами"""
        words_in_phrase = [word]
        seen_ids = {word.id}

        for w in sentence.words:
            if w.id not in seen_ids and w.head == word.id and w.deprel in ['amod', 'compound', 'det', 'nummod']:
                words_in_phrase.append(w)
                seen_ids.add(w.id)

        for w in sentence.words:
            if w.id not in seen_ids and w.head == word.id and w.deprel.startswith('nmod'):
                for case_word in sentence.words:
                    if case_word.id not in seen_ids and case_word.head == w.id and case_word.deprel == 'case':
                        words_in_phrase.append(case_word)
                        seen_ids.add(case_word.id)
                        break
                words_in_phrase.append(w)
                seen_ids.add(w.id)

                for child in sentence.words:
                    if child.id not in seen_ids and child.head == w.id and child.deprel in ['amod', 'compound']:
                        words_in_phrase.append(child)
                        seen_ids.add(child.id)

        for w in sentence.words:
            if w.id not in seen_ids and w.head == word.id and w.deprel == 'conj':
                for cc in sentence.words:
                    if cc.id not in seen_ids and cc.head == w.id and cc.deprel == 'cc':
                        words_in_phrase.append(cc)
                        seen_ids.add(cc.id)
                words_in_phrase.append(w)
                seen_ids.add(w.id)

        words_in_phrase.sort(key=lambda x: x.id)
        return ' '.join([w.text for w in words_in_phrase])


class ImprovedDependencyExtractor:
    """
    Улучшенный экстрактор зависимостей с обработкой пассива и увеличенной дистанцией
    """

    def __init__(self, max_distance: int = 1000):
        """max_distance увеличен до 1000 для биомедицинских текстов"""
        self.max_distance = max_distance

    def extract_all_dependencies(self, actions: List[Action], text: str) -> List[Dependency]:
        """Извлекает все типы зависимостей"""
        print("Извлечение зависимостей (улучшенный алгоритм)...")

        dependencies = []

        # 1. Временные
        temporal_deps = self._extract_temporal(actions, text)
        dependencies.extend(temporal_deps)
        print(f"  Временные: {len(temporal_deps)}")

        # 2. Причинные
        causal_deps = self._extract_causal(actions, text)
        dependencies.extend(causal_deps)
        print(f"  Причинные: {len(causal_deps)}")

        # 3. Целевые
        purpose_deps = self._extract_purpose(actions, text)
        dependencies.extend(purpose_deps)
        print(f"  Целевые: {len(purpose_deps)}")

        # 4. Условные
        conditional_deps = self._extract_conditional(actions, text)
        dependencies.extend(conditional_deps)
        print(f"  Условные: {len(conditional_deps)}")

        # 5. Механистические
        mechanism_deps = self._extract_mechanism(actions, text)
        dependencies.extend(mechanism_deps)
        print(f"  Механистические: {len(mechanism_deps)}")

        # 6. Корреляционные
        correlation_deps = self._extract_correlation(actions, text)
        dependencies.extend(correlation_deps)
        print(f"  Корреляционные: {len(correlation_deps)}")

        # 7. НОВОЕ: Синтаксические связи (номинализация → глагол)
        syntax_deps = self._extract_syntactic_dependencies(actions)
        dependencies.extend(syntax_deps)
        print(f"  Синтаксические: {len(syntax_deps)}")

        # 8. НОВОЕ: Пассивный залог
        passive_deps = self._extract_passive_voice_dependencies(actions)
        dependencies.extend(passive_deps)
        print(f"  Пассивный залог: {len(passive_deps)}")

        # 9. НОВОЕ: Координация (списки)
        coordination_deps = self._extract_coordination_dependencies(actions)
        dependencies.extend(coordination_deps)
        print(f"  Координация: {len(coordination_deps)}")

        # 10. НОВОЕ: Отношения "часть-целое"
        part_of_deps = self._extract_part_of_dependencies(actions, text)
        dependencies.extend(part_of_deps)
        print(f"  Часть-целое: {len(part_of_deps)}")

        # 11. Разрешение конфликтов
        dependencies = self._resolve_conflicts(dependencies)

        print(f"[OK] Извлечено {len(dependencies)} зависимостей")
        return dependencies

    def _extract_syntactic_dependencies(self, actions: List[Action]) -> List[Dependency]:
        """
        Извлекает связи между номинализациями/сущностями и глаголами в том же предложении
        """
        dependencies = []

        # Группируем действия по предложениям
        by_sentence = defaultdict(list)
        for action in actions:
            by_sentence[action.sentence_idx].append(action)

        # Для каждого предложения ищем связи
        for sent_idx, sent_actions in by_sentence.items():
            # Находим номинализации и сущности
            nominals_entities = [a for a in sent_actions if getattr(a, 'is_nominalization', False) or getattr(a, 'is_entity', False)]
            verbs = [a for a in sent_actions if not getattr(a, 'is_nominalization', False) and not getattr(a, 'is_entity', False)]

            # Связываем если номинализация/сущность является субъектом или объектом глагола
            for verb in verbs:
                for ne in nominals_entities:
                    # Проверяем, упоминается ли номинализация/сущность в аргументах глагола
                    if verb.subject and ne.verb_text.lower() in verb.subject.lower():
                        dep = Dependency(ne.id, verb.id, 'LINKED_AS_SUBJECT', 0.80)
                        dep.markers.append('syntax')
                        dependencies.append(dep)
                    elif verb.object and ne.verb_text.lower() in verb.object.lower():
                        dep = Dependency(verb.id, ne.id, 'LINKED_AS_OBJECT', 0.80)
                        dep.markers.append('syntax')
                        dependencies.append(dep)

        return dependencies

    def _extract_temporal(self, actions: List[Action], text: str) -> List[Dependency]:
        dependencies = []
        for relation_type, patterns in TEMPORAL_MARKERS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    marker_pos = match.start()
                    action_before = self._find_nearest_action_before(actions, marker_pos)
                    action_after = self._find_nearest_action_after(actions, marker_pos)

                    if action_before and action_after and action_before.id != action_after.id:
                        if relation_type == 'BEFORE':
                            dep = Dependency(action_before.id, action_after.id, 'TEMPORAL_BEFORE', 0.85)
                        elif relation_type == 'AFTER':
                            dep = Dependency(action_after.id, action_before.id, 'TEMPORAL_AFTER', 0.85)
                        else:
                            dep = Dependency(action_before.id, action_after.id, 'TEMPORAL_DURING', 0.75)
                        dep.markers.append(match.group())
                        dependencies.append(dep)
        return dependencies

    def _extract_causal(self, actions: List[Action], text: str) -> List[Dependency]:
        dependencies = []
        for relation_type, patterns in CAUSAL_MARKERS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    marker_pos = match.start()
                    marker_text = match.group()
                    action_before = self._find_nearest_action_before(actions, marker_pos)
                    action_after = self._find_nearest_action_after(actions, marker_pos)

                    if action_before and action_after and action_before.id != action_after.id:
                        if re.search(r'\b(because of|due to|owing to)\b', marker_text, re.IGNORECASE):
                            dep = Dependency(action_after.id, action_before.id, relation_type, 0.90)
                        else:
                            dep = Dependency(action_before.id, action_after.id, relation_type, 0.90)
                        dep.markers.append(marker_text)
                        dependencies.append(dep)
        return dependencies

    def _extract_purpose(self, actions: List[Action], text: str) -> List[Dependency]:
        dependencies = []

        def is_valid_purpose(match_text, position_before, position_after):
            before_words = text[max(0, position_before-20):position_before].lower().split()
            if before_words and before_words[-1] in ['is', 'be', 'was', 'were', 'been']:
                return False
            after_words = text[position_after:position_after+30].lower().split()
            if after_words and after_words[0] in ['be', 'have', 'seem', 'appear']:
                return False
            return True

        for patterns in PURPOSE_MARKERS.values():
            for pattern in patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    marker_pos = match.start()
                    if not is_valid_purpose(match.group(), marker_pos, match.end()):
                        continue
                    action_before = self._find_nearest_action_before(actions, marker_pos)
                    action_after = self._find_nearest_action_after(actions, marker_pos)
                    if action_before and action_after and action_before.id != action_after.id:
                        dep = Dependency(action_before.id, action_after.id, 'PURPOSE', 0.85)
                        dep.markers.append(match.group())
                        dependencies.append(dep)
        return dependencies

    def _extract_conditional(self, actions: List[Action], text: str) -> List[Dependency]:
        dependencies = []
        for patterns in CONDITIONAL_MARKERS.values():
            for pattern in patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    marker_pos = match.start()
                    action_before = self._find_nearest_action_before(actions, marker_pos)
                    action_after = self._find_nearest_action_after(actions, marker_pos)
                    if action_before and action_after and action_before.id != action_after.id:
                        dep = Dependency(action_after.id, action_before.id, 'REQUIRES', 0.88)
                        dep.markers.append(match.group())
                        dependencies.append(dep)
        return dependencies

    def _extract_mechanism(self, actions: List[Action], text: str) -> List[Dependency]:
        dependencies = []
        for patterns in MECHANISM_MARKERS.values():
            for pattern in patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    marker_pos = match.start()
                    action_before = self._find_nearest_action_before(actions, marker_pos)
                    action_after = self._find_nearest_action_after(actions, marker_pos)
                    if action_before and action_after and action_before.id != action_after.id:
                        dep = Dependency(action_before.id, action_after.id, 'VIA_MECHANISM', 0.90)
                        dep.markers.append(match.group())
                        dependencies.append(dep)
        return dependencies

    def _extract_correlation(self, actions: List[Action], text: str) -> List[Dependency]:
        dependencies = []
        for patterns in CORRELATION_MARKERS.values():
            for pattern in patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    marker_pos = match.start()
                    action_before = self._find_nearest_action_before(actions, marker_pos)
                    action_after = self._find_nearest_action_after(actions, marker_pos)
                    if action_before and action_after and action_before.id != action_after.id:
                        dep = Dependency(action_before.id, action_after.id, 'CORRELATES', 0.75)
                        dep.markers.append(match.group())
                        dependencies.append(dep)
        return dependencies

    def _find_nearest_action_before(self, actions: List[Action], position: int) -> Optional[Action]:
        nearest = None
        min_distance = float('inf')
        for action in actions:
            if action.char_start and action.char_start < position:
                distance = position - action.char_start
                if distance <= self.max_distance and distance < min_distance:
                    min_distance = distance
                    nearest = action
        return nearest

    def _find_nearest_action_after(self, actions: List[Action], position: int) -> Optional[Action]:
        nearest = None
        min_distance = float('inf')
        for action in actions:
            if action.char_start and action.char_start > position:
                distance = action.char_start - position
                if distance <= self.max_distance and distance < min_distance:
                    min_distance = distance
                    nearest = action
        return nearest

    def _extract_passive_voice_dependencies(self, actions: List[Action]) -> List[Dependency]:
        """
        Извлекает зависимости из пассивных конструкций типа "X is caused by Y"
        """
        dependencies = []

        # Группируем действия по предложениям
        by_sentence = defaultdict(list)
        for action in actions:
            by_sentence[action.sentence_idx].append(action)

        for sent_idx, sent_actions in by_sentence.items():
            # Ищем глаголы "be" с причастием прошедшего времени
            for action in sent_actions:
                if action.verb in ['be', 'is', 'are', 'was', 'were', 'been'] and not getattr(action, 'is_nominalization', False):
                    # Проверяем, есть ли причастие или каузальный маркер рядом
                    sentence_text = action.sentence_text.lower()

                    # Паттерны пассива: "is caused by", "is triggered by", "are induced by"
                    passive_patterns = [
                        r'(?:is|are|was|were|been)\s+(caused|triggered|induced|generated|produced|inhibited|activated|prevented|blocked)',
                        r'(?:is|are|was|were|been)\s+(?:an?|the)?\s+inhibitor',
                        r'(?:is|are|was|were|been)\s+(?:an?|the)?\s+activator',
                    ]

                    for pattern in passive_patterns:
                        if re.search(pattern, sentence_text):
                            # Ищем агента (обычно после "by")
                            by_match = re.search(r'\bby\s+([\w\s-]+?)(?:\s+and\s+|\s+or\s+|,|\.|$)', sentence_text)

                            if by_match:
                                agent_text = by_match.group(1).strip()

                                # Ищем соответствующие действия/сущности
                                agent_action = None
                                patient_action = None

                                # Агент - это то, что после "by"
                                for a in sent_actions:
                                    if getattr(a, 'is_entity', False) or getattr(a, 'is_nominalization', False):
                                        if a.verb_text.lower() in agent_text:
                                            agent_action = a
                                            break

                                # Пациент - это субъект глагола "be"
                                if action.subject:
                                    for a in sent_actions:
                                        if getattr(a, 'is_entity', False) or getattr(a, 'is_nominalization', False):
                                            if a.verb_text.lower() in action.subject.lower():
                                                patient_action = a
                                                break

                                # Создаём зависимость: agent → CAUSES/PREVENTS → patient
                                if agent_action and patient_action and agent_action.id != patient_action.id:
                                    if 'prevent' in sentence_text or 'inhibit' in sentence_text or 'block' in sentence_text:
                                        dep = Dependency(agent_action.id, patient_action.id, 'PREVENTS', 0.85)
                                    elif 'activ' in sentence_text:
                                        dep = Dependency(agent_action.id, patient_action.id, 'ENABLES', 0.85)
                                    else:
                                        dep = Dependency(agent_action.id, patient_action.id, 'CAUSES', 0.85)
                                    dep.markers.append('passive_voice')
                                    dependencies.append(dep)

        return dependencies

    def _extract_coordination_dependencies(self, actions: List[Action]) -> List[Dependency]:
        """
        Извлекает зависимости для списков координированных сущностей
        Например: "MPTP, rotenone, and paraquat cause dysfunction"
        → MPTP→dysfunction, rotenone→dysfunction, paraquat→dysfunction
        """
        dependencies = []

        # Группируем по предложениям
        by_sentence = defaultdict(list)
        for action in actions:
            by_sentence[action.sentence_idx].append(action)

        for sent_idx, sent_actions in by_sentence.items():
            # Находим последовательности сущностей/номинализаций
            entities = [a for a in sent_actions if (getattr(a, 'is_entity', False) or getattr(a, 'is_nominalization', False))]
            verbs = [a for a in sent_actions if not getattr(a, 'is_entity', False) and not getattr(a, 'is_nominalization', False)]

            if len(entities) >= 2 and len(verbs) >= 1:
                # Ищем координацию через позиции и запятые/and в тексте
                sentence_text = sent_actions[0].sentence_text if sent_actions else ""

                # Проверяем, идут ли сущности подряд с запятыми/and
                entities_sorted = sorted(entities, key=lambda x: x.char_start if x.char_start else 0)

                # Группируем близко расположенные сущности
                coordinated_groups = []
                current_group = [entities_sorted[0]]

                for i in range(1, len(entities_sorted)):
                    prev = entities_sorted[i-1]
                    curr = entities_sorted[i]

                    if prev.char_end and curr.char_start:
                        distance = curr.char_start - prev.char_end
                        between_text = sentence_text[prev.char_end - sent_actions[0].char_start : curr.char_start - sent_actions[0].char_start] if sent_actions[0].char_start else ""

                        # Если между ними запятая, "and" или "or" и расстояние < 20 символов
                        if distance < 20 and (',' in between_text or 'and' in between_text.lower() or 'or' in between_text.lower()):
                            current_group.append(curr)
                        else:
                            if len(current_group) >= 2:
                                coordinated_groups.append(current_group)
                            current_group = [curr]

                if len(current_group) >= 2:
                    coordinated_groups.append(current_group)

                # Для каждой группы копируем связи последнего элемента на остальные
                for group in coordinated_groups:
                    # Последний элемент группы (обычно связан с глаголом)
                    last_entity = group[-1]

                    # Ищем существующие зависимости для последнего элемента
                    # (они будут добавлены через другие методы)
                    # Здесь создаём связь между элементами группы
                    for i in range(len(group) - 1):
                        dep = Dependency(group[i].id, last_entity.id, 'COORDINATED_WITH', 0.70)
                        dep.markers.append('coordination')
                        dependencies.append(dep)

        return dependencies

    def _extract_part_of_dependencies(self, actions: List[Action], text: str) -> List[Dependency]:
        """
        Извлекает отношения "часть-целое" (PART_OF).

        Примеры:
        - "substantia nigra is a part of the brain" → substantia nigra PART_OF brain
        - "neurons located in the striatum" → neurons PART_OF striatum
        - "dopaminergic neurons of the substantia nigra" → neurons PART_OF substantia nigra

        Args:
            actions: Список действий
            text: Исходный текст

        Returns:
            Список зависимостей типа PART_OF
        """
        import re
        dependencies = []

        # Группируем действия по предложениям
        by_sentence = defaultdict(list)
        for action in actions:
            by_sentence[action.sentence_idx].append(action)

        for sent_idx, sent_actions in by_sentence.items():
            if not sent_actions:
                continue

            sentence_text = sent_actions[0].sentence_text
            if not sentence_text:
                continue

            # Находим все сущности и номинализации в предложении
            entities_nominals = [a for a in sent_actions if (
                getattr(a, 'is_entity', False) or getattr(a, 'is_nominalization', False)
            )]

            if len(entities_nominals) < 2:
                continue

            # Проверяем каждую пару сущностей на наличие маркеров "часть-целое" между ними
            for i, part_action in enumerate(entities_nominals):
                for j, whole_action in enumerate(entities_nominals):
                    if i == j:
                        continue

                    # Проверяем порядок в тексте
                    if not (part_action.char_start and whole_action.char_start):
                        continue

                    # Часть должна быть перед целым или наоборот
                    if part_action.char_start < whole_action.char_start:
                        start = part_action.char_end
                        end = whole_action.char_start
                        source = part_action
                        target = whole_action
                    else:
                        start = whole_action.char_end
                        end = part_action.char_start
                        source = part_action
                        target = whole_action

                    # Проверяем расстояние
                    distance = abs(end - start)
                    if distance > 100:  # Слишком далеко
                        continue

                    # Извлекаем текст между сущностями
                    between_text = text[start:end].lower().strip()

                    # Проверяем наличие маркеров "часть-целое"
                    for rel_type, patterns in PART_OF_MARKERS.items():
                        for pattern in patterns:
                            if re.search(pattern, between_text):
                                # Определяем направление связи
                                # "part of whole" → part PART_OF whole
                                # "whole contains part" → part PART_OF whole

                                # Маркеры типа "of the" указывают на то, что первая сущность - часть второй
                                if 'of the' in between_text or 'of' in between_text:
                                    # "neurons of the substantia nigra"
                                    dep = Dependency(source.id, target.id, 'PART_OF', 0.80)
                                elif 'in the' in between_text or 'within' in between_text or 'located in' in between_text:
                                    # "neurons located in the striatum"
                                    dep = Dependency(source.id, target.id, 'PART_OF', 0.80)
                                else:
                                    # Общий случай
                                    dep = Dependency(source.id, target.id, 'PART_OF', 0.75)

                                dep.markers.append(pattern)
                                dependencies.append(dep)
                                break  # Один маркер достаточно для одной пары

        return dependencies

    def _resolve_conflicts(self, dependencies: List[Dependency]) -> List[Dependency]:
        grouped = defaultdict(list)
        for dep in dependencies:
            key = (dep.source_id, dep.target_id)
            grouped[key].append(dep)

        resolved = []
        for key, deps in grouped.items():
            if len(deps) == 1:
                resolved.append(deps[0])
            else:
                best = max(deps, key=lambda d: (
                    PRIORITY.get(d.relation_type, 0),
                    d.confidence
                ))
                best.markers = list(set([m for d in deps for m in d.markers]))
                resolved.append(best)

        return resolved
