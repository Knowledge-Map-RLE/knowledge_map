import re

from itertools import product

from spacy.tokens import Doc


# ====
def adding_end_dot_headings(text) -> str:
    """Ставит точки в конце markdwon-заголовков для корректной обработки NLP"""
    pattern = r'^(#|##|###|####|#####|######)\s(.*)$'
    
    return re.sub(pattern, repl, text, flags=re.MULTILINE)

def repl(match) -> str:
    # match.group(2) — это текст заголовка без знаков "#"
    return f"{match.group(1)} {match.group(2)}."


# ====
def split_sentences_by_and(doc: Doc) -> list:
    """
    Разделение предложения по союзу and и генерация
    всех сочетаний разделённых кусочков
    """
    # TODO: ❗ Не забыть что у существительного могут быть связные слова
    # не забывать их тоже переносить вместе с существительным
    groups = get_and_groups(doc)
    if not groups:
        return [doc.text]

    # Для каждой группы — список вариантов (индексы токенов)
    group_indices = [[t.i for t in group] for group in groups]
    # Декартово произведение индексов: все комбинации выбора по одному из каждой группы
    all_combinations = list(product(*group_indices))

    results = []
    for combo in all_combinations:
        # Оставляем только выбранные токены из conj-групп
        keep = set(combo)
        # Все токены, которые не входят в conj-группы, тоже оставляем
        for t in doc:
            if not any(t.i in group for group in group_indices):
                keep.add(t.i)
        
        # Удаляем cc токены (and), которые связывали conj-группы
        for group in groups:
            for token in group:
                for child in token.children:
                    if child.dep_ == "cc" and child.text.lower() == "and":
                        if child.i in keep:
                            keep.remove(child.i)
        
        # Собираем предложение
        tokens = [t.text_with_ws for t in doc if t.i in keep]
        results.append("".join(tokens).strip())
    return results

def get_and_groups(doc) -> list:
    """
    Находит все группы существительных, связанных через and/conj.
    Возвращает список списков токенов (предложений) всех сочетаний разбитых по and.
    """
    groups = []
    used = set()
    for token in doc:
        if token.pos_ == "NOUN" and token not in used:
            # Собираем conj-группу
            group = [token]
            for child in token.conjuncts:
                if child.pos_ == "NOUN":
                    group.append(child)
            # Проверяем, что группа больше одного и содержит and
            if len(group) > 1 and any(
                t for t in group for c in t.children if c.dep_ == "cc" and c.text.lower() == "and"
            ):
                groups.append(group)
                used.update(group)
    return groups