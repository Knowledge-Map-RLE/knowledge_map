"""
Utility functions for text preprocessing
"""

import re


def preprocess_text(text: str) -> str:
    """
    Предобработка текста: удаляет метаданные и References.

    Args:
        text: исходный текст

    Returns:
        Очищенный текст
    """
    # Удаляем YAML метаданные в начале (между ---)
    if text.startswith('---'):
        end_pos = text.find('---', 3)
        if end_pos != -1:
            text = text[end_pos + 3:].strip()

    # Удаляем раздел References в конце
    references_patterns = [
        r'\n## References\n.*',
        r'\n## References$',
        r'\n## REFERENCES\n.*',
        r'\n# References\n.*'
    ]

    for pattern in references_patterns:
        text = re.sub(pattern, '', text, flags=re.DOTALL | re.IGNORECASE)

    return text.strip()
