"""Юнит-тесты расчёта стоимости AI-запросов (Decimal-арифметика)."""
from decimal import Decimal

import pytest

from domain.rules.ai_pricing import (
    CACHED_INPUT_TOKENS_PRICE_PER_1K,
    INPUT_TOKENS_PRICE_PER_1K,
    OUTPUT_TOKENS_PRICE_PER_1K,
    TOOL_TOKENS_PRICE_PER_1K,
    calculate_usage_cost,
    cost_to_kopecks,
    estimate_usage_cost,
)


def test_prices_are_decimal():
    for price in (
        INPUT_TOKENS_PRICE_PER_1K,
        CACHED_INPUT_TOKENS_PRICE_PER_1K,
        OUTPUT_TOKENS_PRICE_PER_1K,
        TOOL_TOKENS_PRICE_PER_1K,
    ):
        assert isinstance(price, Decimal)


def test_cost_only_cached_input():
    cost = calculate_usage_cost(input_tokens=1000, cached_input_tokens=1000, output_tokens=0)
    # Кэш 0.075 ₽/1k — не считается как обычный вход.
    assert cost.input_cost == Decimal("0")
    assert cost.cached_input_cost == Decimal("0.075")
    assert cost.total == Decimal("0.075")


def test_cost_mixed_usage():
    cost = calculate_usage_cost(
        input_tokens=700, cached_input_tokens=300, output_tokens=100, tool_tokens=50
    )
    # uncached 400*0.30/1k=0.12 + cached 300*0.075/1k=0.0225
    # + out 100*0.50/1k=0.05 + tool 50*0.075/1k=0.00375
    assert cost.total == Decimal("0.19625")


def test_cost_no_double_count_cached():
    full = calculate_usage_cost(input_tokens=1000, cached_input_tokens=1000, output_tokens=500)
    no_cache = calculate_usage_cost(input_tokens=1000, cached_input_tokens=0, output_tokens=500)
    # 1000 из 1000 закэшированы — дешевле, чем 1000 обычных входных.
    assert full.total < no_cache.total


def test_cost_to_kopecks_rounds_up():
    assert cost_to_kopecks(Decimal("0.28625")) == 29
    assert cost_to_kopecks(Decimal("0.075")) == 8
    assert cost_to_kopecks(Decimal("0.00")) == 0
    assert cost_to_kopecks(Decimal("1.00")) == 100


def test_estimate_usage_cost_conservative():
    # Без данных о кэше оценка консервативна: всё как обычный вход.
    est = estimate_usage_cost(estimated_input_tokens=1000, estimated_output_tokens=1000)
    assert est.cached_input_cost == Decimal("0")
    assert est.input_cost == Decimal("0.30")
    assert est.total == Decimal("0.80")


def test_estimate_with_cached():
    est = estimate_usage_cost(
        estimated_input_tokens=700,
        estimated_output_tokens=1000,
        cached_input_tokens=300,
    )
    # uncached 400*0.30=0.12 + cached 300*0.075=0.0225 + out 1000*0.50=0.50
    assert est.total == Decimal("0.6425")
