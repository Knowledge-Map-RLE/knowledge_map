"""
Layer: Domain (Rules)
Package: domain.rules.ai_pricing
Responsibility: Расчёт стоимости AI-запросов на основе официальных тарифов.

Принадлежит слою Domain, потому что содержит бизнес-правило формирования
стоимости без зависимостей от фреймворков. Деньги представлены Decimal —
никаких float (погрешность бинарной арифметики недопустима для финансов).

Тарифы (₽ за 1000 токенов) — DeepSeek V4 Flash через Yandex AI Studio
(https://aistudio.yandex.ru/docs/ru/ai-studio/pricing.html,
подтверждено https://yandex.cloud/ru/blog/yandex-ai-studio-deepseek-v4-flash):
  - входные токены (cache miss):   0,30 ₽ / 1000
  - кэшированные входные токены:   0,075 ₽ / 1000
  - исходящие токены:              0,50 ₽ / 1000
  - токены инструментов:           0,075 ₽ / 1000

Allowed imports: только стандартная библиотека Python
Forbidden imports: neomodel, pydantic, fastapi, grpc, aioboto3
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

# Цена за 1000 токенов, рубли.
# ``str`` (а не float) гарантирует точное десятичное представление.
INPUT_TOKENS_PRICE_PER_1K = Decimal("0.30")
CACHED_INPUT_TOKENS_PRICE_PER_1K = Decimal("0.075")
OUTPUT_TOKENS_PRICE_PER_1K = Decimal("0.50")
TOOL_TOKENS_PRICE_PER_1K = Decimal("0.075")

# Копеек в рубле — для конвертации стоимости в целые копейки.
_KOPECKS_PER_RUBLE = Decimal("100")


@dataclass(frozen=True)
class UsageCost:
    """Стоимость одного запроса по компонентам (рубли, Decimal)."""

    input_cost: Decimal
    cached_input_cost: Decimal
    output_cost: Decimal
    tool_cost: Decimal

    @property
    def total(self) -> Decimal:
        return (
            self.input_cost
            + self.cached_input_cost
            + self.output_cost
            + self.tool_cost
        )


def calculate_usage_cost(
    *,
    input_tokens: int = 0,
    cached_input_tokens: int = 0,
    output_tokens: int = 0,
    tool_tokens: int = 0,
) -> UsageCost:
    """Считает стоимость запроса по фактическим/оценочным токенам.

    Кэшированные токены никогда не дублируются в ``input_tokens``: стоимость
    входа = (input_tokens - cached) по обычной ставке + cached по льготной.
    Если ``cached_input_tokens`` передан отдельным полем (как у провайдеров,
    возвращающих ``prompt_cache_hit_tokens``), обычные входные — это разность.
    При неизвестном кэше (0) весь вход оплачивается по обычной ставке.
    """
    if cached_input_tokens > input_tokens:
        raise ValueError(
            "cached_input_tokens не может превышать input_tokens "
            f"({cached_input_tokens} > {input_tokens})"
        )

    uncached_input = input_tokens - cached_input_tokens
    input_cost = _cost(uncached_input, INPUT_TOKENS_PRICE_PER_1K)
    cached_input_cost = _cost(cached_input_tokens, CACHED_INPUT_TOKENS_PRICE_PER_1K)
    output_cost = _cost(output_tokens, OUTPUT_TOKENS_PRICE_PER_1K)
    tool_cost = _cost(tool_tokens, TOOL_TOKENS_PRICE_PER_1K)
    return UsageCost(
        input_cost=input_cost,
        cached_input_cost=cached_input_cost,
        output_cost=output_cost,
        tool_cost=tool_cost,
    )


def estimate_usage_cost(
    *,
    estimated_input_tokens: int = 0,
    estimated_output_tokens: int = 0,
    estimated_tool_tokens: int = 0,
    cached_input_tokens: Optional[int] = None,
) -> UsageCost:
    """Оценочная стоимость до отправки запроса.

    Кэш на этапе оценки неизвестен (``cached_input_tokens=None``) — весь
    вход считается по обычной ставке (консервативно). Если кэш передан —
    применяется льготная ставка к его части.
    """
    cached = cached_input_tokens or 0
    return calculate_usage_cost(
        input_tokens=estimated_input_tokens,
        cached_input_tokens=cached,
        output_tokens=estimated_output_tokens,
        tool_tokens=estimated_tool_tokens,
    )


def cost_to_kopecks(cost: Decimal) -> int:
    """Переводит стоимость из рублей в целые копейки (округление вверх).

    Округление вверх гарантирует, что списанная сумма покрывает фактическую
    стоимость — баланс никогда не уйдёт в минус из-за отбрасывания дробей.
    """
    kopecks = cost * _KOPECKS_PER_RUBLE
    return int(kopecks.to_integral_value(rounding="ROUND_CEILING"))


def _cost(tokens: int, price_per_1k: Decimal) -> Decimal:
    if tokens <= 0:
        return Decimal("0")
    return (Decimal(tokens) * price_per_1k) / Decimal("1000")
