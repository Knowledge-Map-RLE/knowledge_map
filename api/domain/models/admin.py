"""
Layer: Domain (Entities)
Package: domain.models.admin
Responsibility: Доменные модели admin-панели экономики.

Чистые dataclass-ы без зависимостей от инфраструктуры.
Все денежные значения — Decimal (рубли), копейки — только на уровне персистентности.

Allowed imports: dataclasses, datetime, decimal, typing
Forbidden imports: neomodel, pydantic, fastapi, grpc
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional


# =============================================================================
# Dashboard
# =============================================================================


@dataclass(frozen=True)
class DashboardSummary:
    """KPI-карточки главной страницы admin-панели."""

    revenue_rubles: Decimal
    expenses_rubles: Decimal
    ai_cost_rubles: Decimal
    infrastructure_cost_rubles: Decimal
    tax_rubles: Decimal
    acquiring_rubles: Decimal
    advertising_rubles: Decimal
    other_costs_rubles: Decimal
    profit_rubles: Decimal
    margin_pct: Decimal
    total_users: int
    paying_users: int
    active_users: int
    average_check_rubles: Decimal
    ai_cost_per_paying_user: Decimal
    cac_rubles: Decimal
    ltv_rubles: Optional[Decimal] = None


@dataclass(frozen=True)
class TimeSeriesPoint:
    """Точка временного ряда для графиков."""

    date: str
    value: Decimal


@dataclass(frozen=True)
class DashboardCharts:
    """Данные для графиков на dashboard."""

    revenue_by_period: list[TimeSeriesPoint]
    expenses_by_period: list[TimeSeriesPoint]
    ai_cost_by_period: list[TimeSeriesPoint]
    profit_by_period: list[TimeSeriesPoint]
    paying_users_by_period: list[TimeSeriesPoint]
    token_consumption_by_period: list[TimeSeriesPoint]
    input_output_cache_by_period: list[dict]
    avg_cost_per_user_by_period: list[TimeSeriesPoint]


# =============================================================================
# Users
# =============================================================================


@dataclass(frozen=True)
class AdminUserSummary:
    """Сводка по пользователю для таблицы."""

    uid: str
    login: str
    nickname: str
    is_active: bool
    created_at: str
    plan_code: str
    total_payments_kopecks: int
    total_payments_rubles: Decimal
    actual_input_tokens: int
    actual_output_tokens: int
    actual_cached_tokens: int
    total_tokens: int
    ai_cost_rubles: Decimal
    revenue_rubles: Decimal
    tax_rubles: Decimal
    acquiring_rubles: Decimal
    profit_rubles: Decimal
    last_ai_request: Optional[str] = None
    last_payment: Optional[str] = None


@dataclass(frozen=True)
class UserDetail:
    """Подробная карточка пользователя."""

    uid: str
    login: str
    nickname: str
    is_active: bool
    created_at: str
    last_login: Optional[str]
    plan_code: str
    plan_name: str
    total_payments_count: int
    total_payments_rubles: Decimal
    actual_input_tokens: int
    actual_output_tokens: int
    actual_cached_tokens: int
    total_tokens: int
    ai_cost_rubles: Decimal
    revenue_rubles: Decimal
    profit_rubles: Decimal
    last_ai_request: Optional[str]
    last_payment: Optional[str]


# =============================================================================
# Tokens
# =============================================================================


@dataclass(frozen=True)
class TokenOverview:
    """Обзор потребления токенов."""

    total_input_tokens: int
    total_output_tokens: int
    total_cached_tokens: int
    total_tokens: int
    input_share_pct: Decimal
    output_share_pct: Decimal
    cache_share_pct: Decimal
    avg_per_user: Decimal
    median_per_user: Decimal
    p90: Decimal
    p95: Decimal
    p99: Decimal
    total_input_cost_rubles: Decimal
    total_output_cost_rubles: Decimal
    total_cache_cost_rubles: Decimal
    total_ai_cost_rubles: Decimal


@dataclass(frozen=True)
class AnomalyUser:
    """Пользователь с аномально высоким потреблением."""

    uid: str
    login: str
    nickname: str
    total_tokens: int
    ai_cost_rubles: Decimal
    z_score: Decimal


# =============================================================================
# Sales
# =============================================================================


@dataclass(frozen=True)
class SalesOverview:
    """Обзор продаж."""

    total_sales_count: int
    total_revenue_rubles: Decimal
    average_check_rubles: Decimal
    refunds_count: int
    refunds_amount_rubles: Decimal
    net_revenue_rubles: Decimal


@dataclass(frozen=True)
class PackageSales:
    """Продажи по пакету."""

    plan_code: str
    plan_name: str
    tokens_granted: int
    price_rubles: Decimal
    sales_count: int
    revenue_rubles: Decimal
    ai_cost_rubles: Decimal
    gross_profit_rubles: Decimal
    markup_pct: Decimal
    margin_pct: Decimal


# =============================================================================
# Expenses
# =============================================================================


@dataclass
class Expense:
    """Расход проекта."""

    uid: str
    category: str
    subcategory: str
    description: str
    amount_kopecks: int
    currency: str
    period_start: str
    period_end: str
    is_recurring: bool
    is_fixed: bool
    source: str
    created_by_uid: str
    created_at: str
    updated_at: str

    @property
    def amount_rubles(self) -> Decimal:
        return Decimal(self.amount_kopecks) / Decimal("100")


@dataclass(frozen=True)
class ExpenseSummary:
    """Агрегация расходов по категориям."""

    total_rubles: Decimal
    infrastructure_rubles: Decimal
    ai_tokens_rubles: Decimal
    acquiring_rubles: Decimal
    advertising_rubles: Decimal
    tax_rubles: Decimal
    other_rubles: Decimal
    fixed_rubles: Decimal
    variable_rubles: Decimal


# =============================================================================
# AI Providers
# =============================================================================


@dataclass(frozen=True)
class AIProvider:
    """AI-провайдер."""

    uid: str
    name: str
    display_name: str
    base_url: Optional[str]
    is_active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class PriceVersion:
    """Версия тарифа AI-провайдера."""

    uid: str
    provider_uid: str
    model: str
    input_price_per_million: Decimal
    output_price_per_million: Decimal
    cache_input_price_per_million: Optional[Decimal]
    currency: str
    valid_from: str
    valid_to: Optional[str]
    is_active: bool
    created_at: str


# =============================================================================
# Financial Plan
# =============================================================================


@dataclass
class FinancialPlan:
    """Финансовый план проекта."""

    uid: str
    version: int
    name: str
    data: dict
    is_active: bool
    created_by_uid: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class PlanVsFactItem:
    """Элемент сравнения план/факт."""

    metric_name: str
    metric_label: str
    plan_value: Decimal
    fact_value: Decimal
    deviation_abs: Decimal
    deviation_pct: Decimal
    formula: str
    unit: str  # "₽" | "%" | "шт" | "токенов"


# =============================================================================
# Strategy / Stages
# =============================================================================


@dataclass(frozen=True)
class StageEconomics:
    """Экономика стадии развития."""

    uid: str
    user_count: int
    stage_name: str
    revenue_rubles: Decimal
    ai_cost_rubles: Decimal
    fixed_costs_rubles: Decimal
    variable_costs_rubles: Decimal
    profit_rubles: Decimal
    cumulative_cashflow: Decimal
    required_capital: Decimal
    is_breakeven: bool


# =============================================================================
# Unit Economics
# =============================================================================


@dataclass(frozen=True)
class UnitEconomics:
    """Unit economics для пакета токенов."""

    plan_code: str
    plan_name: str
    tokens_granted: int
    price_rubles: Decimal
    ai_cost_rubles: Decimal
    tax_rubles: Decimal
    acquiring_rubles: Decimal
    cac_rubles: Decimal
    contribution_profit_rubles: Decimal
    contribution_margin_pct: Decimal


# =============================================================================
# Launch Scenarios
# =============================================================================


@dataclass(frozen=True)
class LaunchScenarioResult:
    """Результат расчёта сценария запуска."""

    audience_size: int
    conversion_rate: Decimal
    visitors: int
    registrations: int
    buyers: int
    revenue_rubles: Decimal
    ai_cost_rubles: Decimal
    expenses_rubles: Decimal
    profit_rubles: Decimal
    required_capital_rubles: Decimal


# =============================================================================
# Capital
# =============================================================================


@dataclass(frozen=True)
class CapitalCalculation:
    """Расчёт стартового капитала."""

    min_capital_rubles: Decimal
    base_capital_rubles: Decimal
    conservative_capital_rubles: Decimal
    monthly_fixed_costs_rubles: Decimal
    months_to_breakeven: int
    max_negative_cashflow_rubles: Decimal


# =============================================================================
# Audit Log
# =============================================================================


@dataclass(frozen=True)
class AuditLogEntry:
    """Запись журнала действий администратора."""

    uid: str
    admin_uid: str
    action: str
    entity_type: str
    entity_uid: Optional[str]
    old_value: Optional[str]
    new_value: Optional[str]
    created_at: str
