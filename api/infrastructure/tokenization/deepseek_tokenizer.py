"""
Layer: Frameworks & Drivers — Infrastructure
Package: infrastructure.tokenization.deepseek_tokenizer
Responsibility: Официальный токенизатор DeepSeek V4 (HuggingFace BPE) для
оценки количества токенов до отправки запроса.

Принадлежит слою Infrastructure, потому что использует внешнюю библиотеку
``tokenizers`` (деталь). Оценка токенов — НЕ финансовый источник: фактический
usage приходит от провайдера в ответе и является единственной истиной для
списания (см. domain.rules.ai_pricing и поток обработки сообщения).

Файл ``tokenizer.json`` — официальный релиз deepseek-ai/DeepSeek-V4-Flash,
хранится локально рядом с модулем, чтобы не зависеть от сети при запуске.
"""
from __future__ import annotations

import json
import logging
import os
from typing import List, Optional

from tokenizers import Tokenizer

logger = logging.getLogger(__name__)

_TOKENIZER_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "src", "tokenizers", "deepseek_v4", "tokenizer.json")

_tokenizer: Optional[Tokenizer] = None


def _load_tokenizer() -> Tokenizer:
    global _tokenizer
    if _tokenizer is None:
        tokenizer = Tokenizer.from_file(_TOKENIZER_PATH)
        _tokenizer = tokenizer
    return _tokenizer


def count_tokens(text: str) -> int:
    """Точное число токенов текста по официальному BPE DeepSeek V4."""
    if not text:
        return 0
    encoding = _load_tokenizer().encode(text)
    return len(encoding.ids)


def count_messages_tokens(messages: List[dict]) -> int:
    """Токены полного диалога (system + user + assistant + tools).

    Каждое сообщение кодируется как ``<сообщение>\\n\\n`` — так же, как
    собирается промпт при отправке в API. Приближение для оценки.
    """
    total = 0
    for message in messages:
        content = message.get("content") or ""
        if isinstance(content, list):
            # OpenAI-совместимый мультимодальный контент: берём текстовые части.
            text_parts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            content = "\n".join(text_parts)
        total += count_tokens(str(content))
        total += 4  # разделители ролей (приблизительно)
    return total


def estimate_messages_usage(messages: List[dict], max_output_tokens: Optional[int] = None) -> dict:
    """Оценка usage диалога: input-токены (полный контекст) и output.

    Output на этапе оценки неизвестен: при переданном ``max_output_tokens``
    берём его как верхнюю границу (консервативно), иначе — умеренную оценку.
    """
    input_tokens = count_messages_tokens(messages)
    if max_output_tokens and max_output_tokens > 0:
        output_tokens = max_output_tokens
    else:
        # Эвристика: ответ примерно сопоставим с вопросом, но не меньше 32 токенов.
        output_tokens = max(32, min(1024, input_tokens // 4))
    return {
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
        "estimated_cached_tokens": None,
    }
