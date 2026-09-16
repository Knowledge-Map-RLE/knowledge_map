"""
Layer: Domain (Rules)
Package: domain.rules.plan_vs_fact
Responsibility: Правила сравнения плановых и фактических показателей.

Allowed imports: decimal, typing, domain.models.admin
Forbidden imports: neomodel, pydantic, fastapi, float
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from domain.models.admin import PlanVsFactItem

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")


def _deviation_pct(plan: Decimal, fact: Decimal) -> Decimal:
    """Процент отклонения: (fact - plan) / |plan| * 100."""
    if plan == _ZERO:
        return _ZERO
    return ((fact - plan) / abs(plan) * _HUNDRED).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _deviation_abs(plan: Decimal, fact: Decimal) -> Decimal:
    """Абсолютное отклонение: fact - plan."""
    return (fact - plan).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compare_plan_vs_fact(
    plan: dict[str, Decimal],
    fact: dict[str, Decimal],
) -> list[PlanVsFactItem]:
    """Сравнение плановых и фактических метрик.

    plan и fact — словари {metric_name: value}.
    Возвращает список PlanVsFactItem с расчётами отклонений.

    Метрики:
    - users: пользователи
    - paying_users: платящие пользователи
    - conversion_rate: конверсия (%)
    - avg_tokens_per_user: среднее потребление токенов
    - input_share: доля input токенов (%)
    - output_share: доля output токенов (%)
    - cache_share: доля cache токенов (%)
    - avg_check: средний чек (₽)
    - infrastructure_cost: инфраструктурные расходы (₽)
    - tax: налоги (₽)
    - acquiring: эквайринг (₽)
    - cac: стоимость привлечения (₽)
    - ai_cost: AI-себестоимость (₽)
    - revenue: выручка (₽)
    - profit: прибыль (₽)
    - margin: маржинальность (%)
    """
    metric_definitions: list[tuple[str, str, str, str]] = [
        ("users", "Пользователи", "Целевое кол-во", "шт"),
        ("paying_users", "Платящие", "Целевое кол-во платящих", "шт"),
        ("conversion_rate", "Конверсия", "paying_users / users", "%"),
        (
            "avg_tokens_per_user",
            "Ср. токены/пользователь",
            "среднее потребление",
            "токенов",
        ),
        ("input_share", "Доля input", "input / total", "%"),
        ("output_share", "Доля output", "output / total", "%"),
        ("cache_share", "Доля cache", "cache / total", "%"),
        ("avg_check", "Средний чек", "revenue / paying_users", "₽"),
        (
            "infrastructure_cost",
            "Инфраструктура",
            "фиксированные расходы",
            "₽",
        ),
        ("tax", "Налоги", "revenue * tax_rate", "₽"),
        ("acquiring", "Эквайринг", "revenue * acquiring_rate", "₽"),
        ("cac", "CAC", "advertising / new_users", "₽"),
        ("ai_cost", "AI-себестоимость", "sum(actual_cost)", "₽"),
        ("revenue", "Выручка", "sum(payments)", "₽"),
        ("profit", "Прибыль", "revenue - all_costs", "₽"),
        ("margin", "Маржинальность", "profit / revenue", "%"),
    ]

    items: list[PlanVsFactItem] = []
    for metric_name, label, formula, unit in metric_definitions:
        plan_val = plan.get(metric_name, _ZERO)
        fact_val = fact.get(metric_name, _ZERO)
        deviation_abs = _deviation_abs(plan_val, fact_val)
        deviation_pct = _deviation_pct(plan_val, fact_val)
        items.append(
            PlanVsFactItem(
                metric_name=metric_name,
                metric_label=label,
                plan_value=plan_val,
                fact_value=fact_val,
                deviation_abs=deviation_abs,
                deviation_pct=deviation_pct,
                formula=formula,
                unit=unit,
            )
        )

    return items


def detect_anomaly_deviations(
    items: list[PlanVsFactItem],
    threshold_pct: Decimal = Decimal("20"),
) -> list[PlanVsFactItem]:
    """Выявление аномальных отклонений (> threshold_pct по модулю)."""
    return [
        item
        for item in items
        if abs(item.deviation_pct) > threshold_pct
    ]


def summarize_plan_vs_fact(items: list[PlanVsFactItem]) -> dict:
    """Итоговая сводка план/факт."""
    positive = [i for i in items if i.deviation_abs > _ZERO]
    negative = [i for i in items if i.deviation_abs < _ZERO]
    on_plan = [i for i in items if i.deviation_abs == _ZERO]
    anomalies = detect_anomaly_deviations(items)

    return {
        "total_metrics": len(items),
        "better_than_plan": len(positive),
        "worse_than_plan": len(negative),
        "on_plan": len(on_plan),
        "anomalies_count": len(anomalies),
        "anomalies": anomalies,
    }
