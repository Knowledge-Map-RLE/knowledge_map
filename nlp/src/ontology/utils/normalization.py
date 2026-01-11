"""
Утилиты для нормализации и обработки текста
"""

def normalize_concept_name(text: str) -> str:
    """Нормализует имя концепта для URI"""
    return text.replace(" ", "_").replace("'", "").replace("(", "").replace(")", "").replace("-", "_")


def should_preserve_form(token, preserve_dict: dict) -> bool:
    """Проверяет нужно ли сохранить оригинальную форму токена"""
    text_lower = token.text.lower()
    return text_lower in preserve_dict


def is_content_word(token) -> bool:
    """Проверяет является ли токен content word"""
    if token.pos_ not in {"NOUN", "PROPN", "VERB", "ADJ", "NUM"}:
        return False
    if token.pos_ == "VERB" and token.dep_ in ["aux", "auxpass", "cop"]:
        return False
    return True