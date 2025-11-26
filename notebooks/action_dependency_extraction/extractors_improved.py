"""
Улучшенные экстракторы с поддержкой номинализаций и умной идентификации целей
"""

import re
from typing import List, Optional
from collections import defaultdict

from .models import Action, Dependency
from .markers import (
    TEMPORAL_MARKERS, CAUSAL_MARKERS, CONDITIONAL_MARKERS,
    PURPOSE_MARKERS, MECHANISM_MARKERS, CORRELATION_MARKERS,
    PRIORITY
)
from .nominalization_data import NOMINALIZATION_SET, NOMINALIZATION_TO_BASE, KEY_ENTITIES


class ImprovedActionExtractor:
    """Улучшенный экстрактор с поддержкой номинализаций"""

    def __init__(self, nlp_stanza):
        self.nlp = nlp_stanza

    def extract_actions_from_text(self, text: str) -> List[Action]:
        """Извлекает действия (глаголы + номинализации)"""
        print("Извлечение действий из текста (с номинализациями)...")

        doc_stanza = self.nlp(text)
        actions = []
        action_counter = 0
        current_char_pos = 0

        for sent_idx, sentence in enumerate(doc_stanza.sentences):
            sentence_text = sentence.text
            sentence_start = text.find(sentence_text, current_char_pos)
            if sentence_start == -1:
                sentence_start = current_char_pos

            # 1. Извлекаем глагольные действия
            verb_actions = self._extract_verb_actions(
                sentence, sent_idx, sentence_start, sentence_text, action_counter
            )
            actions.extend(verb_actions)
            action_counter += len(verb_actions)

            # 2. Извлекаем номинализации
            nominal_actions = self._extract_nominalizations(
                sentence, sent_idx, sentence_start, sentence_text, action_counter
            )
            actions.extend(nominal_actions)
            action_counter += len(nominal_actions)

            current_char_pos = sentence_start + len(sentence_text)

        print(f"[OK] Извлечено {len(actions)} действий")
        print(f"  - Глагольных: {sum(1 for a in actions if not getattr(a, 'is_nominalization', False))}")
        print(f"  - Номинализаций: {sum(1 for a in actions if getattr(a, 'is_nominalization', False))}")
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
        """Извлекает номинализации как псевдо-действия"""
        actions = []

        for token in sentence.words:
            # Проверяем, является ли существительное номинализацией
            if token.upos == 'NOUN' and token.lemma in NOMINALIZATION_SET:
                action = self._create_nominalization_action(
                    token, sentence, sent_idx, sentence_start,
                    sentence_text, f"N{start_id + len(actions)}"
                )
                if action:
                    actions.append(action)

        return actions

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

        # Позиция в тексте
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

        # Для номинализаций аргументы извлекаются по-другому
        # "mutations of α-synuclein" → subject = "α-synuclein"
        action.subject = self._extract_nominalization_subject(token, sentence)
        action.object = self._extract_nominalization_object(token, sentence)
        action.modifiers = self._extract_modifiers(token, sentence)

        return action

    def _extract_nominalization_subject(self, token, sentence) -> Optional[str]:
        """Извлекает субъект номинализации (обычно в 'of' фразе)"""
        # "mutations of α-synuclein" → "α-synuclein"
        # "loss of dopaminergic neurons" → "dopaminergic neurons"

        for child in sentence.words:
            # Ищем nmod (nominal modifier) с предлогом "of"
            if child.head == token.id and child.deprel.startswith('nmod'):
                # Проверяем предлог
                for case_word in sentence.words:
                    if case_word.head == child.id and case_word.deprel == 'case':
                        if case_word.text.lower() in ['of', 'in', 'by']:
                            return self._get_full_phrase(child, sentence)

        # Если не нашли, попробуем найти compound
        for child in sentence.words:
            if child.head == token.id and child.deprel == 'compound':
                return child.text

        return None

    def _extract_nominalization_object(self, token, sentence) -> Optional[str]:
        """Извлекает объект номинализации"""
        # Пока не реализовано, можно доработать
        return None

    def _extract_subject(self, token, sentence) -> Optional[str]:
        """Извлекает субъект глагола"""
        # 1. Обычные субъекты
        for word in sentence.words:
            if word.head == token.id and word.deprel in ['nsubj', 'nsubj:pass', 'csubj']:
                return self._get_full_phrase(word, sentence)

        # 2. Clausal complement (xcomp)
        parent_token = None
        for word in sentence.words:
            if word.id == token.head:
                parent_token = word
                break

        if parent_token and token.deprel == 'xcomp':
            parent_subj = self._extract_subject(parent_token, sentence)
            if parent_subj:
                return parent_subj

        # 3. Относительные придаточные (acl)
        if token.deprel in ['acl', 'acl:relcl']:
            if parent_token:
                return self._get_full_phrase(parent_token, sentence)

        # 4. Пассивный залог - агент
        for word in sentence.words:
            if word.head == token.id and word.deprel == 'obl:agent':
                return self._get_full_phrase(word, sentence)

        return None

    def _extract_object(self, token, sentence) -> Optional[str]:
        """Извлекает прямое дополнение"""
        for word in sentence.words:
            if word.head == token.id and word.deprel in ['obj', 'dobj', 'obl']:
                return self._get_full_phrase(word, sentence)
        return None

    def _extract_indirect_object(self, token, sentence) -> Optional[str]:
        """Извлекает косвенное дополнение"""
        for word in sentence.words:
            if word.head == token.id and word.deprel == 'iobj':
                return self._get_full_phrase(word, sentence)
        return None

    def _extract_modifiers(self, token, sentence) -> List[str]:
        """Извлекает модификаторы"""
        modifiers = []
        for word in sentence.words:
            if word.head == token.id and word.deprel in ['advmod', 'amod', 'npadvmod']:
                modifiers.append(word.text)
        return modifiers

    def _get_full_phrase(self, word, sentence) -> str:
        """Получает полную фразу с модификаторами (без дубликатов)"""
        words_in_phrase = [word]
        seen_ids = {word.id}

        # 1. Прямые модификаторы
        for w in sentence.words:
            if w.id not in seen_ids and w.head == word.id and w.deprel in ['amod', 'compound', 'det', 'nummod']:
                words_in_phrase.append(w)
                seen_ids.add(w.id)

        # 2. Prepositional phrases
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

        # 3. Координация
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


class ImprovedGoalIdentifier:
    """Улучшенная идентификация целей"""

    # Ключевые слова, указывающие на цель исследования
    GOAL_KEYWORDS = {
        'treatment', 'therapy', 'cure', 'prevention',
        'diagnosis', 'understanding', 'research',
        'discovery', 'development', 'improvement',
        'targeting', 'intervention', 'approach'
    }

    GOAL_VERBS = {
        'treat', 'cure', 'prevent', 'diagnose',
        'understand', 'discover', 'develop', 'improve',
        'target', 'intervene', 'explore', 'investigate'
    }

    @classmethod
    def identify_goals(cls, dag, actions):
        """Идентифицирует РЕАЛЬНЫЕ цели, а не просто листовые узлы"""
        goals = set()
        action_map = {a.id: a for a in actions}

        for node in dag.nodes():
            action = action_map.get(node)
            if not action:
                continue

            # 1. Цель если глагол целевой
            if action.verb in cls.GOAL_VERBS:
                goals.add(node)
                continue

            # 2. Цель если объект содержит ключевое слово
            if action.object:
                if any(keyword in action.object.lower() for keyword in cls.GOAL_KEYWORDS):
                    goals.add(node)
                    continue

            # 3. Цель если это target PURPOSE зависимости
            for u, v, data in dag.in_edges(node, data=True):
                if data.get('relation') == 'PURPOSE':
                    goals.add(node)
                    break

            # 4. НЕ цель если это высокочастотный промежуточный узел
            if dag.in_degree(node) >= 3 and dag.out_degree(node) >= 2:
                # Это хаб, не цель
                if node in goals:
                    goals.remove(node)

        print(f"[OK] Идентифицировано {len(goals)} целей (вместо {sum(1 for n in dag.nodes() if dag.out_degree(n) == 0)} листьев)")
        return list(goals)
