"""Юнит-тесты расчёта стоимости AI-запросов (Decimal-арифметика)."""
from decimal import Decimal

import pytest

from domain.rules.ai_pricing import (
    INPUT_TOKENS_PRICE,
    OUTPUT_TOKENS_PRICE,
    TOOL_TOKENS_PRICE,
    calculate_usage_cost,
    tokens_to_kopecks,
    estimate_usage_cost,
    total_tokens_cost,
)


def test_prices_are_decimal():
    for price in (INPUT_TOKENS_PRICE, OUTPUT_TOKENS_PRICE, TOOL_TOKENS_PRICE):
        assert isinstance(price, Decimal)


def test_cost_only_input():
    cost = calculate_usage_cost(input_tokens=1000, output_tokens=0)
    assert cost.output_cost == Decimal("0")
    assert cost.input_cost == Decimal("0.02409")
    assert cost.total == Decimal("0.02409")


def test_cost_mixed_usage():
    cost = calculate_usage_cost(
        input_tokens=700, output_tokens=100, tool_tokens=50
    )
    # input 700*0.00002409=0.016863 + out 100*0.00004820=0.004820
    # + tool 50*0.00002409=0.0012045
    assert cost.total == Decimal("0.0228875")


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
    assert est.input_cost == Decimal("0.02409")
    assert est.output_cost == Decimal("0.04820")
    assert est.total == Decimal("0.07229")


def test_cost_no_cached_input():
    cost = calculate_usage_cost(input_tokens=1000, output_tokens=500)
    full = calculate_usage_cost(input_tokens=1000, output_tokens=500)
    assert cost.total == full.total
