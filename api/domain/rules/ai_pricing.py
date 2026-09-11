"""
Layer: Domain (Rules)
Package: domain.rules.ai_pricing
Responsibility: Расчёт стоимости AI-запросов на основе тарифов Сбер Cloud.

Тарифы (₽ за 1 токен) — DeepSeek V4 Flash через Сбер Cloud
с наценкой 30%:
  - входные токены:            24,09 ₽ / 1M  (18,53 + 30%)
  - исходящие токены:          48,20 ₽ / 1M  (37,08 + 30%)
  - токены инструментов:       24,09 ₽ / 1M  (как входные)

Allowed imports: только стандартная библиотека Python
Forbidden imports: neomodel, pydantic, fastapi, grpc, aioboto3
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

# Цена за 1 токен, рубли (₽/1M токенов / 1_000_000).
# ``str`` (а не float) гарантирует точное десятичное представление.
INPUT_TOKENS_PRICE = Decimal("0.00002409")    # 24,09 ₽ / 1M
OUTPUT_TOKENS_PRICE = Decimal("0.00004820")   # 48,20 ₽ / 1M
TOOL_TOKENS_PRICE = Decimal("0.00002409")     # как входные

# Копеек в рубле — для конвертации стоимости в целые копейки.
_KOPECKS_PER_RUBLE = Decimal("100")


@dataclass(frozen=True)
class UsageCost:
    """Стоимость одного запроса по компонентам (рубли, Decimal)."""

    input_cost: Decimal
    output_cost: Decimal
    tool_cost: Decimal

    @property
    def total(self) -> Decimal:
        return self.input_cost + self.output_cost + self.tool_cost


def calculate_usage_cost(
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    tool_tokens: int = 0,
) -> UsageCost:
    """Считает стоимость запроса по фактическим/оценочным токенам."""
    input_cost = _cost(input_tokens, INPUT_TOKENS_PRICE)
    output_cost = _cost(output_tokens, OUTPUT_TOKENS_PRICE)
    tool_cost = _cost(tool_tokens, TOOL_TOKENS_PRICE)
    return UsageCost(
        input_cost=input_cost,
        output_cost=output_cost,
        tool_cost=tool_cost,
    )


def estimate_usage_cost(
    *,
    estimated_input_tokens: int = 0,
    estimated_output_tokens: int = 0,
    estimated_tool_tokens: int = 0,
) -> UsageCost:
    """Оценочная стоимость до отправки запроса."""
    return calculate_usage_cost(
        input_tokens=estimated_input_tokens,
        output_tokens=estimated_output_tokens,
        tool_tokens=estimated_tool_tokens,
    )


def tokens_to_kopecks(cost: Decimal) -> int:
    """Переводит стоимость из рублей в целые копейки (округление вверх).

    Округление вверх гарантирует, что списанная сумма покрывает фактическую
    стоимость — баланс никогда не уйдёт в минус из-за отбрасывания дробей.
    """
    kopecks = cost * _KOPECKS_PER_RUBLE
    return int(kopecks.to_integral_value(rounding="ROUND_CEILING"))


def total_tokens_cost(input_tokens: int, output_tokens: int, tool_tokens: int = 0) -> int:
    """Общее количество токенов для списания (вход + выход + инструменты).

    Возвращает целое число токенов — используется для списания с баланса.
    """
    return input_tokens + output_tokens + tool_tokens


def _cost(tokens: int, price_per_token: Decimal) -> Decimal:
    if tokens <= 0:
        return Decimal("0")
    return Decimal(tokens) * price_per_token
