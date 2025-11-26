"""
Extractors for actions and dependencies from text
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
from .nominalization_data import NOMINALIZATION_SET, NOMINALIZATION_TO_BASE


class ActionExtractor:
    """Извлекает действия из текста с помощью Stanza"""

    def __init__(self, nlp_stanza):
        self.nlp = nlp_stanza

    def extract_actions_from_text(self, text: str) -> List[Action]:
        """
        Извлекает все действия (глаголы + номинализации) с правильным вычислением позиций.
        """
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

        verb_count = sum(1 for a in actions if not getattr(a, 'is_nominalization', False))
        nominal_count = sum(1 for a in actions if getattr(a, 'is_nominalization', False))
        print(f"[OK] Извлечено {len(actions)} действий")
        print(f"  - Глагольных: {verb_count}")
        print(f"  - Номинализаций: {nominal_count}")
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
        """Извлекает субъект с поддержкой xcomp, acl, obl:agent"""
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
                # Добавляем предлог
                for case_word in sentence.words:
                    if case_word.id not in seen_ids and case_word.head == w.id and case_word.deprel == 'case':
                        words_in_phrase.append(case_word)
                        seen_ids.add(case_word.id)
                        break
                words_in_phrase.append(w)
                seen_ids.add(w.id)

                # Модификаторы PP
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


class DependencyExtractor:
    """Извлекает зависимости между действиями"""

    def __init__(self, max_distance: int = 500):
        self.max_distance = max_distance

    def extract_all_dependencies(self, actions: List[Action], text: str) -> List[Dependency]:
        """Извлекает все типы зависимостей"""
        print("Извлечение зависимостей между действиями...")

        dependencies = []

        # 1. Временные
        temporal_deps = self._extract_temporal(actions, text)
        dependencies.extend(temporal_deps)
        print(f"  Временные: {len(temporal_deps)}")

        # 2. Причинные (ТОЛЬКО через маркеры!)
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

        # 7. Разрешение конфликтов
        dependencies = self._resolve_conflicts(dependencies)

        print(f"[OK] Извлечено {len(dependencies)} зависимостей (после разрешения конфликтов)")
        return dependencies

    def _extract_temporal(self, actions: List[Action], text: str) -> List[Dependency]:
        """Извлекает временные зависимости"""
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
                        else:  # DURING
                            dep = Dependency(action_before.id, action_after.id, 'TEMPORAL_DURING', 0.75)

                        dep.markers.append(match.group())
                        dependencies.append(dep)

        return dependencies

    def _extract_causal(self, actions: List[Action], text: str) -> List[Dependency]:
        """
        Извлекает причинные зависимости ТОЛЬКО через маркеры.
        Метод 2 (causal_verbs) УДАЛЁН!
        """
        dependencies = []

        for relation_type, patterns in CAUSAL_MARKERS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    marker_pos = match.start()
                    marker_text = match.group()

                    action_before = self._find_nearest_action_before(actions, marker_pos)
                    action_after = self._find_nearest_action_after(actions, marker_pos)

                    if action_before and action_after and action_before.id != action_after.id:
                        # Проверяем направление для "because of", "due to"
                        if re.search(r'\b(because of|due to|owing to)\b', marker_text, re.IGNORECASE):
                            dep = Dependency(action_after.id, action_before.id, relation_type, 0.90)
                        else:
                            dep = Dependency(action_before.id, action_after.id, relation_type, 0.90)

                        dep.markers.append(marker_text)
                        dependencies.append(dep)

        return dependencies

    def _extract_purpose(self, actions: List[Action], text: str) -> List[Dependency]:
        """Извлекает целевые зависимости с фильтрацией"""
        dependencies = []

        def is_valid_purpose(match_text, position_before, position_after):
            """Фильтрует ложные 'to'"""
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
        """Извлекает условные зависимости"""
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
        """Извлекает механистические связи"""
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
        """Извлекает корреляционные связи"""
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
        """Находит ближайшее действие перед позицией"""
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
        """Находит ближайшее действие после позиции"""
        nearest = None
        min_distance = float('inf')

        for action in actions:
            if action.char_start and action.char_start > position:
                distance = action.char_start - position
                if distance <= self.max_distance and distance < min_distance:
                    min_distance = distance
                    nearest = action

        return nearest

    def _resolve_conflicts(self, dependencies: List[Dependency]) -> List[Dependency]:
        """Разрешает конфликты с учётом приоритетов"""
        grouped = defaultdict(list)
        for dep in dependencies:
            key = (dep.source_id, dep.target_id)
            grouped[key].append(dep)

        resolved = []
        for key, deps in grouped.items():
            if len(deps) == 1:
                resolved.append(deps[0])
            else:
                # Выбираем по приоритету и confidence
                best = max(deps, key=lambda d: (
                    PRIORITY.get(d.relation_type, 0),
                    d.confidence
                ))
                best.markers = list(set([m for d in deps for m in d.markers]))
                resolved.append(best)

        return resolved
