"""
Layer: Domain (Rules)
Package: domain.rules.ai_pricing
Responsibility: Расчёт стоимости AI-запросов на основе тарифов cloud.ru
Foundation Models.

Тарифы (₽ за 1 токен) — DeepSeek-V4-Flash через cloud.ru:
  - входные токены:    18,53 ₽ / 1M
  - исходящие токены:  37,08 ₽ / 1M
  - токены инструментов:  тариф входных токенов

Значения задаются через переменные окружения:
  - CLOUDRU_BASE_INPUT_PRICE   — цена 1 входного токена в ₽
  - CLOUDRU_BASE_OUTPUT_PRICE  — цена 1 исходящего токена в ₽

Дефолты совпадают с базовыми тарифами cloud.ru.

Allowed imports: только стандартная библиотека Python
Forbidden imports: neomodel, pydantic, fastapi, grpc, aioboto3
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

# Дефолты совпадают с базовыми тарифами cloud.ru (без наценки).
_DEFAULT_INPUT_TOKENS_PRICE = Decimal("0.00001853")    # 18,53 ₽ / 1M
_DEFAULT_OUTPUT_TOKENS_PRICE = Decimal("0.00003708")   # 37,08 ₽ / 1M


def _env_decimal(var: str, default: Decimal) -> Decimal:
    raw = os.environ.get(var)
    if raw is None or not raw.strip():
        return default
    return Decimal(raw)


@dataclass(frozen=True)
class TokenPrices:
    """Итоговые цены за 1 токен (рубли, Decimal)."""

    input_price: Decimal
    output_price: Decimal
    tool_price: Decimal


def load_token_prices() -> TokenPrices:
    """Читает тарифы из окружения (с дефолтами cloud.ru) в runtime."""
    input_price = _env_decimal("CLOUDRU_BASE_INPUT_PRICE", _DEFAULT_INPUT_TOKENS_PRICE)
    output_price = _env_decimal("CLOUDRU_BASE_OUTPUT_PRICE", _DEFAULT_OUTPUT_TOKENS_PRICE)
    return TokenPrices(
        input_price=input_price,
        output_price=output_price,
        tool_price=input_price,
    )


# Копеек в рубле — для конвертации стоимости в целые копейки.
_KOPECKS_PER_RUBLE = Decimal("100")

# Рекламация для обратной совместимости: цены по умолчанию из окружения.
INPUT_TOKENS_PRICE = load_token_prices().input_price
OUTPUT_TOKENS_PRICE = load_token_prices().output_price
TOOL_TOKENS_PRICE = INPUT_TOKENS_PRICE


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
    prices: Optional[TokenPrices] = None,
) -> UsageCost:
    """Считает стоимость запроса по фактическим/оценочным токенам.

    ``prices`` — цены за токен; если не передан, читаются из окружения
    через ``load_token_prices``.
    """
    if prices is None:
        prices = load_token_prices()
    input_cost = _cost(input_tokens, prices.input_price)
    output_cost = _cost(output_tokens, prices.output_price)
    tool_cost = _cost(tool_tokens, prices.tool_price)
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
    prices: Optional[TokenPrices] = None,
) -> UsageCost:
    """Оценочная стоимость до отправки запроса."""
    return calculate_usage_cost(
        input_tokens=estimated_input_tokens,
        output_tokens=estimated_output_tokens,
        tool_tokens=estimated_tool_tokens,
        prices=prices,
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


# =============================================================================
# Price versions — для версионирования тарифов провайдеров
# =============================================================================


@dataclass(frozen=True)
class PriceVersionData:
    """Снимок цены на момент AI-запроса.

    Хранится в AIUsage для трассируемости: стоимость запроса рассчитывается
    по тарифу, действовавшему на момент выполнения, а не по текущему.
    """

    price_version_uid: str
    model: str
    input_price_per_token: Decimal
    output_price_per_token: Decimal
    cache_price_per_token: Optional[Decimal] = None

    @classmethod
    def from_million_prices(
        cls,
        uid: str,
        model: str,
        input_per_million: Decimal,
        output_per_million: Decimal,
        cache_per_million: Optional[Decimal] = None,
    ) -> "PriceVersionData":
        """Создаёт из цен за 1M токенов (₽)."""
        million = Decimal("1000000")
        return cls(
            price_version_uid=uid,
            model=model,
            input_price_per_token=input_per_million / million,
            output_price_per_token=output_per_million / million,
            cache_price_per_token=cache_per_million / million if cache_per_million else None,
        )


def calculate_provider_cost(
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_tokens: int = 0,
    price_version: PriceVersionData,
) -> UsageCost:
    """Расчёт себестоимости AI по версии тарифа провайдера.

    Использует цену из price_version — НЕ из окружения.
    Это гарантирует, что прошлые usage не пересчитываются.
    """
    input_cost = _cost(input_tokens, price_version.input_price_per_token)
    output_cost = _cost(output_tokens, price_version.output_price_per_token)
    cache_cost = (
        _cost(cached_tokens, price_version.cache_price_per_token)
        if price_version.cache_price_per_token is not None
        else Decimal("0")
    )
    return UsageCost(
        input_cost=input_cost,
        output_cost=output_cost,
        tool_cost=cache_cost,
    )