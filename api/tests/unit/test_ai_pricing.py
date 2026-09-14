"""Юнит-тесты расчёта стоимости AI-запросов (Decimal-арифметика).

Тарифы берутся из окружения CLOUDRU_BASE_INPUT_PRICE / CLOUDRU_BASE_OUTPUT_PRICE
(дефолты — базовые тарифы cloud.ru без наценки).
"""
import os
from decimal import Decimal

import pytest

from domain.rules.ai_pricing import (
    INPUT_TOKENS_PRICE,
    OUTPUT_TOKENS_PRICE,
    TOOL_TOKENS_PRICE,
    calculate_usage_cost,
    load_token_prices,
    tokens_to_kopecks,
    estimate_usage_cost,
    total_tokens_cost,
)


def test_prices_are_decimal():
    for price in (INPUT_TOKENS_PRICE, OUTPUT_TOKENS_PRICE, TOOL_TOKENS_PRICE):
        assert isinstance(price, Decimal)


def test_default_tariffs_are_cloudru_baseline():
    assert INPUT_TOKENS_PRICE == Decimal("0.00001853")   # 18,53 ₽ / 1M
    assert OUTPUT_TOKENS_PRICE == Decimal("0.00003708")  # 37,08 ₽ / 1M
    assert TOOL_TOKENS_PRICE == INPUT_TOKENS_PRICE


def test_cost_only_input():
    cost = calculate_usage_cost(input_tokens=1000, output_tokens=0)
    assert cost.output_cost == Decimal("0")
    assert cost.input_cost == Decimal("0.01853")
    assert cost.total == Decimal("0.01853")


def test_cost_mixed_usage():
    cost = calculate_usage_cost(
        input_tokens=700, output_tokens=100, tool_tokens=50
    )
    # input 700*0.00001853=0.012971 + out 100*0.00003708=0.003708
    # + tool 50*0.00001853=0.0009265
    assert cost.total == Decimal("0.0176055")


def test_tokens_to_kopecks_rounds_up():
    assert tokens_to_kopecks(Decimal("0.28625")) == 29
    assert tokens_to_kopecks(Decimal("0.075")) == 8
    assert tokens_to_kopecks(Decimal("0.00")) == 0
    assert tokens_to_kopecks(Decimal("1.00")) == 100


def test_total_tokens_cost():
    assert total_tokens_cost(input_tokens=410, output_tokens=310) == 720
    assert total_tokens_cost(input_tokens=0, output_tokens=0) == 0
    assert total_tokens_cost(input_tokens=100, output_tokens=200, tool_tokens=50) == 350


def test_estimate_usage_cost():
    est = estimate_usage_cost(estimated_input_tokens=1000, estimated_output_tokens=1000)
    assert est.input_cost == Decimal("0.01853")
    assert est.output_cost == Decimal("0.03708")
    assert est.total == Decimal("0.05561")


def test_cost_no_cached_input():
    cost = calculate_usage_cost(input_tokens=1000, output_tokens=500)
    full = calculate_usage_cost(input_tokens=1000, output_tokens=500)
    assert cost.total == full.total


def test_prices_from_env_override(monkeypatch):
    monkeypatch.setenv("CLOUDRU_BASE_INPUT_PRICE", "0.00001")
    monkeypatch.setenv("CLOUDRU_BASE_OUTPUT_PRICE", "0.00002")
    prices = load_token_prices()
    assert prices.input_price == Decimal("0.00001")
    assert prices.output_price == Decimal("0.00002")
    assert prices.tool_price == Decimal("0.00001")

    cost = calculate_usage_cost(input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost.input_cost == Decimal("10")
    assert cost.output_cost == Decimal("20")


def test_invalid_env_value_raises(monkeypatch):
    monkeypatch.setenv("CLOUDRU_BASE_INPUT_PRICE", "not-a-number")
    with pytest.raises(Exception):
        load_token_prices()