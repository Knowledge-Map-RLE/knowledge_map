"""
Layer: Domain (Rules)
Package: domain.rules.admin_calculations
Responsibility: Формулы финансовых расчётов admin-панели.

Все формулы используют Decimal-арифметику.
Все monetary значения — рубли (Decimal).
Округление — только при отображении, не в расчётах.

Allowed imports: decimal, typing, domain.models.admin
Forbidden imports: neomodel, pydantic, fastapi, float
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from domain.models.admin import (
    DashboardSummary,
    UnitEconomics,
    StageEconomics,
    LaunchScenarioResult,
    CapitalCalculation,
)

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
_ONE = Decimal("1")


# =============================================================================
# Core financial formulas
# =============================================================================


@dataclass(frozen=True)
class ProfitabilityResult:
    """Результат расчёта прибыльности."""

    revenue: Decimal
    total_costs: Decimal
    profit: Decimal
    margin_pct: Decimal
    ai_cost: Decimal
    infrastructure_cost: Decimal
    tax: Decimal
    acquiring: Decimal
    advertising: Decimal
    other_costs: Decimal


def calculate_profitability(
    *,
    revenue: Decimal,
    ai_cost: Decimal,
    infrastructure_cost: Decimal,
    tax: Decimal,
    acquiring: Decimal,
    advertising: Decimal,
    other_costs: Decimal,
) -> ProfitabilityResult:
    """Расчёт прибыльности.

    profit = revenue - (ai_cost + infrastructure_cost + tax + acquiring + advertising + other_costs)
    margin = profit / revenue * 100

    Формула:
        Revenue    = Выручка от продаж
        AI Cost    = Себестоимость AI-токенов
        Infra Cost = Инфраструктурные расходы (домен, S3, Compute, HDD)
        Tax        = Налоги (6% УСН или иные)
        Acquiring  = Комиссия платёжной системы (~2%)
        Advertising = Рекламные расходы
        Other      = Прочие расходы
    """
    total_costs = ai_cost + infrastructure_cost + tax + acquiring + advertising + other_costs
    profit = revenue - total_costs
    margin_pct = (
        (profit / revenue * _HUNDRED).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if revenue > _ZERO
        else _ZERO
    )
    return ProfitabilityResult(
        revenue=revenue,
        total_costs=total_costs,
        profit=profit,
        margin_pct=margin_pct,
        ai_cost=ai_cost,
        infrastructure_cost=infrastructure_cost,
        tax=tax,
        acquiring=acquiring,
        advertising=advertising,
        other_costs=other_costs,
    )


def calculate_cac(
    advertising_cost: Decimal,
    new_paying_users: int,
) -> Decimal:
    """Стоимость привлечения платящего пользователя (CAC).

    CAC = Advertising Cost / New Paying Users
    """
    if new_paying_users <= 0:
        return _ZERO
    return advertising_cost / Decimal(new_paying_users)


def calculate_arpu(
    revenue: Decimal,
    paying_users: int,
) -> Decimal:
    """Средний доход на платящего пользователя (ARPU).

    ARPU = Revenue / Paying Users
    """
    if paying_users <= 0:
        return _ZERO
    return revenue / Decimal(paying_users)


def calculate_ai_cost_per_user(
    ai_cost: Decimal,
    paying_users: int,
) -> Decimal:
    """AI-себестоимость одного платящего пользователя.

    AI Cost per User = AI Cost / Paying Users
    """
    if paying_users <= 0:
        return _ZERO
    return ai_cost / Decimal(paying_users)


def calculate_contribution_margin(
    revenue: Decimal,
    variable_costs: Decimal,
) -> Decimal:
    """Маржа на единицу (Contribution Margin).

    Contribution Margin = (Revenue - Variable Costs) / Revenue * 100

    Variable costs: AI tokens, acquiring, advertising (переменная часть)
    """
    if revenue <= _ZERO:
        return _ZERO
    return ((revenue - variable_costs) / revenue * _HUNDRED).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


# =============================================================================
# Unit Economics
# =============================================================================


def calculate_unit_economics(
    *,
    plan_code: str,
    plan_name: str,
    tokens_granted: int,
    price_rubles: Decimal,
    ai_cost_rubles: Decimal,
    tax_rate: Decimal = Decimal("0.06"),
    acquiring_rate: Decimal = Decimal("0.02"),
    cac_rubles: Decimal = _ZERO,
) -> UnitEconomics:
    """Unit economics для пакета токенов.

    Tax         = price * tax_rate
    Acquiring   = price * acquiring_rate
    Contribution Profit = price - ai_cost - tax - acquiring - cac
    Contribution Margin = contribution_profit / price * 100
    """
    tax = (price_rubles * tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    acquiring = (price_rubles * acquiring_rate).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    contribution_profit = price_rubles - ai_cost_rubles - tax - acquiring - cac_rubles
    contribution_margin_pct = (
        (contribution_profit / price_rubles * _HUNDRED).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if price_rubles > _ZERO
        else _ZERO
    )
    return UnitEconomics(
        plan_code=plan_code,
        plan_name=plan_name,
        tokens_granted=tokens_granted,
        price_rubles=price_rubles,
        ai_cost_rubles=ai_cost_rubles,
        tax_rubles=tax,
        acquiring_rubles=acquiring,
        cac_rubles=cac_rubles,
        contribution_profit_rubles=contribution_profit,
        contribution_margin_pct=contribution_margin_pct,
    )


# =============================================================================
# Break-even
# =============================================================================


def calculate_breakeven_users(
    fixed_costs_per_period: Decimal,
    contribution_profit_per_user: Decimal,
) -> int:
    """Количество пользователей для безубыточности.

    Break-even Users = Fixed Costs / Contribution Profit per User
    Округление вверх — нужно достичь или превысить.
    """
    if contribution_profit_per_user <= _ZERO:
        return 0
    result = fixed_costs_per_period / contribution_profit_per_user
    return int(result.to_integral_value(rounding="ROUND_CEILING"))


# =============================================================================
# Capital requirements
# =============================================================================


def calculate_capital_requirements(
    *,
    monthly_fixed_costs: Decimal,
    ai_cost_per_user: Decimal,
    users_before_revenue: int,
    months_to_breakeven: int,
    acquisition_cost_per_user: Decimal = _ZERO,
) -> CapitalCalculation:
    """Расчёт необходимого стартового капитала.

    Минимальный капитал:
        = fixed_costs * months_to_breakeven
        + ai_cost_per_user * users_before_revenue * months_to_breakeven
        + acquisition_cost * users_before_revenue

    Базовый = минимальный * 1.3 (30% запас)
    Консервативный = минимальный * 1.5 (50% запас)

    Максимальный отрицательный денежный поток:
        = sum of all negative monthly cashflows до break-even
    """
    ai_total = ai_cost_per_user * Decimal(users_before_revenue * months_to_breakeven)
    acquisition_total = acquisition_cost_per_user * Decimal(users_before_revenue)
    fixed_total = monthly_fixed_costs * Decimal(months_to_breakeven)

    min_capital = fixed_total + ai_total + acquisition_total
    base_capital = (min_capital * Decimal("1.3")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    conservative_capital = (min_capital * Decimal("1.5")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    max_negative = (min_capital * Decimal("0.8")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    return CapitalCalculation(
        min_capital_rubles=min_capital.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        base_capital_rubles=base_capital,
        conservative_capital_rubles=conservative_capital,
        monthly_fixed_costs_rubles=monthly_fixed_costs,
        months_to_breakeven=months_to_breakeven,
        max_negative_cashflow_rubles=max_negative,
    )


# =============================================================================
# Launch scenarios
# =============================================================================


def calculate_launch_scenario(
    *,
    audience_size: int,
    conversion_rate: Decimal,
    avg_check_rubles: Decimal,
    ai_cost_per_user_rubles: Decimal,
    fixed_costs_rubles: Decimal = _ZERO,
    cac_rubles: Decimal = _ZERO,
) -> LaunchScenarioResult:
    """Расчёт одного сценария запуска.

    visitors  = audience_size (все просмотрели)
    buyers    = audience_size * conversion_rate
    revenue   = buyers * avg_check
    ai_cost   = buyers * ai_cost_per_user
    expenses  = fixed_costs + (buyers * cac)
    profit    = revenue - ai_cost - expenses
    """
    buyers = int(
        (Decimal(audience_size) * conversion_rate).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    revenue = (Decimal(buyers) * avg_check_rubles).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    ai_cost = (Decimal(buyers) * ai_cost_per_user_rubles).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    cac_total = (Decimal(buyers) * cac_rubles).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    expenses = fixed_costs_rubles + cac_total
    profit = revenue - ai_cost - expenses
    required_capital = (ai_cost + expenses).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    return LaunchScenarioResult(
        audience_size=audience_size,
        conversion_rate=conversion_rate,
        visitors=audience_size,
        registrations=audience_size,
        buyers=buyers,
        revenue_rubles=revenue,
        ai_cost_rubles=ai_cost,
        expenses_rubles=expenses,
        profit_rubles=profit,
        required_capital_rubles=required_capital,
    )


# =============================================================================
# Stage economics
# =============================================================================


def calculate_stage_economics(
    *,
    user_count: int,
    paying_rate: Decimal,
    avg_tokens_per_user: int,
    input_share: Decimal,
    output_share: Decimal,
    cache_share: Decimal,
    input_price_per_token: Decimal,
    output_price_per_token: Decimal,
    cache_price_per_token: Decimal,
    avg_check_rubles: Decimal,
    fixed_costs_monthly: Decimal,
    acquiring_rate: Decimal,
    tax_rate: Decimal,
) -> StageEconomics:
    """Расчёт экономики для стадии (количества пользователей).

    revenue  = paying_users * avg_check
    ai_cost  = paying_users * (input * price_in + output * price_out + cache * price_cache)
    variable = acquiring + tax
    profit   = revenue - ai_cost - fixed - variable
    """
    paying_users = int(Decimal(user_count) * paying_rate)
    revenue = (Decimal(paying_users) * avg_check_rubles).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    ai_input = Decimal(avg_tokens_per_user) * input_share * input_price_per_token
    ai_output = Decimal(avg_tokens_per_user) * output_share * output_price_per_token
    ai_cache = Decimal(avg_tokens_per_user) * cache_share * cache_price_per_token
    ai_cost_per_user = ai_input + ai_output + ai_cache
    ai_cost = (Decimal(paying_users) * ai_cost_per_user).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    acquiring = (revenue * acquiring_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    tax = (revenue * tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    variable_costs = acquiring + tax

    profit = revenue - ai_cost - fixed_costs_monthly - variable_costs

    return StageEconomics(
        uid="",
        user_count=user_count,
        stage_name=f"{user_count} users",
        revenue_rubles=revenue,
        ai_cost_rubles=ai_cost,
        fixed_costs_rubles=fixed_costs_monthly,
        variable_costs_rubles=variable_costs,
        profit_rubles=profit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        cumulative_cashflow=profit,
        required_capital=_ZERO,
        is_breakeven=profit >= _ZERO,
    )
