"""
=============================================================================
ФАЙЛ 2: src/ontology/utils/term_utils.py
=============================================================================
"""
from typing import Optional, List
import spacy


def safe_lemma_check(token: spacy.tokens.Token, target_word: str) -> bool:
    """Проверяет и text и lemma для надёжности"""
    return (
        token.text.lower() == target_word.lower() or
        token.lemma_.lower() == target_word.lower()
    )


def normalize_term(token: spacy.tokens.Token, preserve_forms: List[str] = None) -> str:
    """Нормализует термин с учётом POS и специальных форм"""
    preserve_forms = preserve_forms or []
    
    if token.text.lower() in preserve_forms:
        return token.text.lower()
    
    if token.pos_ in ["PROPN", "NUM"]:
        return token.text
    elif token.pos_ == "VERB" and token.dep_ in ["amod", "acl"]:
        return token.text.lower()
    else:
        return token.lemma_.lower()


def normalize_name(text: str) -> str:
    """Нормализует имя концепта для RDF"""
    return text.replace(" ", "_").replace("'", "").replace("(", "").replace(")", "").replace("-", "_")