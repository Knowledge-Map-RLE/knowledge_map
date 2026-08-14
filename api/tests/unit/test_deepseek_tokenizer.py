"""Юнит-тесты токенизатора DeepSeek V4 (официальный BPE, библиотека tokenizers)."""
from infrastructure.tokenization.deepseek_tokenizer import (
    count_messages_tokens,
    count_tokens,
    estimate_messages_usage,
)


def test_count_tokens_english():
    assert count_tokens("Hello, world!") == 4


def test_count_tokens_russian():
    # Русский текст кодируется полноценно (не посимвольно).
    assert count_tokens("Привет, мир! Это проверка работы токенизатора.") == 14


def test_count_messages_tokens():
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is 2+2?"},
        {"role": "assistant", "content": "4"},
    ]
    assert count_messages_tokens(messages) == 26


def test_estimate_messages_usage_returns_tokens():
    messages = [{"role": "user", "content": "Hello, world!"}]
    est = estimate_messages_usage(messages)
    assert est["estimated_input_tokens"] == count_messages_tokens(messages)
    # output = max(32, min(1024, input//4)); для 8 входных → 32
    assert est["estimated_output_tokens"] == 32


def test_estimate_messages_usage_respects_max_output():
    messages = [{"role": "user", "content": "Hello, world!"}]
    est = estimate_messages_usage(messages, max_output_tokens=100)
    assert est["estimated_output_tokens"] == 100
