"""Юнит-тесты формул финансовых расчётов admin-панели.

Все расчёты используют Decimal-арифметику.
"""
from decimal import Decimal, ROUND_HALF_UP

import pytest

from domain.rules.admin_calculations import (
    ProfitabilityResult,
    calculate_ai_cost_per_user,
    calculate_arpu,
    calculate_breakeven_users,
    calculate_cac,
    calculate_capital_requirements,
    calculate_contribution_margin,
    calculate_launch_scenario,
    calculate_profitability,
    calculate_stage_economics,
    calculate_unit_economics,
)


# =============================================================================
# Profitability
# =============================================================================


class TestCalculateProfitability:
    def test_basic_profitability(self):
        result = calculate_profitability(
            revenue=Decimal("100000"),
            ai_cost=Decimal("30000"),
            infrastructure_cost=Decimal("10000"),
            tax=Decimal("6000"),
            acquiring=Decimal("2000"),
            advertising=Decimal("8000"),
            other_costs=Decimal("4000"),
        )
        assert result.profit == Decimal("40000")
        assert result.margin_pct == Decimal("40.00")
        assert result.total_costs == Decimal("60000")

    def test_zero_revenue(self):
        result = calculate_profitability(
            revenue=Decimal("0"),
            ai_cost=Decimal("0"),
            infrastructure_cost=Decimal("5000"),
            tax=Decimal("0"),
            acquiring=Decimal("0"),
            advertising=Decimal("0"),
            other_costs=Decimal("0"),
        )
        assert result.profit == Decimal("-5000")
        assert result.margin_pct == Decimal("0")

    def test_negative_profit(self):
        result = calculate_profitability(
            revenue=Decimal("50000"),
            ai_cost=Decimal("40000"),
            infrastructure_cost=Decimal("10000"),
            tax=Decimal("3000"),
            acquiring=Decimal("1000"),
            advertising=Decimal("2000"),
            other_costs=Decimal("1000"),
        )
        assert result.profit < 0
        assert result.total_costs == Decimal("57000")
        assert result.profit == Decimal("-7000")

    def test_revenue_equals_costs(self):
        result = calculate_profitability(
            revenue=Decimal("100000"),
            ai_cost=Decimal("50000"),
            infrastructure_cost=Decimal("20000"),
            tax=Decimal("15000"),
            acquiring=Decimal("5000"),
            advertising=Decimal("5000"),
            other_costs=Decimal("5000"),
        )
        assert result.profit == Decimal("0")
        assert result.margin_pct == Decimal("0.00")

    def test_all_fields_populated(self):
        result = calculate_profitability(
            revenue=Decimal("100000"),
            ai_cost=Decimal("30000"),
            infrastructure_cost=Decimal("10000"),
            tax=Decimal("6000"),
            acquiring=Decimal("2000"),
            advertising=Decimal("8000"),
            other_costs=Decimal("4000"),
        )
        assert result.revenue == Decimal("100000")
        assert result.ai_cost == Decimal("30000")
        assert result.infrastructure_cost == Decimal("10000")
        assert result.tax == Decimal("6000")
        assert result.acquiring == Decimal("2000")
        assert result.advertising == Decimal("8000")
        assert result.other_costs == Decimal("4000")

    def test_profitability_is_frozen_dataclass(self):
        result = calculate_profitability(
            revenue=Decimal("1000"),
            ai_cost=Decimal("100"),
            infrastructure_cost=Decimal("100"),
            tax=Decimal("60"),
            acquiring=Decimal("20"),
            advertising=Decimal("50"),
            other_costs=Decimal("20"),
        )
        assert isinstance(result, ProfitabilityResult)

    def test_fractional_values(self):
        result = calculate_profitability(
            revenue=Decimal("100000.50"),
            ai_cost=Decimal("30000.25"),
            infrastructure_cost=Decimal("10000.10"),
            tax=Decimal("6000.03"),
            acquiring=Decimal("2000.01"),
            advertising=Decimal("8000.02"),
            other_costs=Decimal("4000.01"),
        )
        assert result.profit == Decimal("40000.08")
        assert isinstance(result.profit, Decimal)
        assert isinstance(result.margin_pct, Decimal)


# =============================================================================
# CAC
# =============================================================================


class TestCalculateCAC:
    def test_basic_cac(self):
        assert calculate_cac(Decimal("10000"), 20) == Decimal("500")

    def test_zero_users(self):
        assert calculate_cac(Decimal("10000"), 0) == Decimal("0")

    def test_negative_users(self):
        assert calculate_cac(Decimal("10000"), -5) == Decimal("0")

    def test_zero_cost(self):
        assert calculate_cac(Decimal("0"), 10) == Decimal("0")

    def test_fractional_result(self):
        assert calculate_cac(Decimal("10000"), 3) == Decimal("3333.333333333333333333333333")


# =============================================================================
# ARPU
# =============================================================================


class TestCalculateARPU:
    def test_basic_arpu(self):
        assert calculate_arpu(Decimal("100000"), 50) == Decimal("2000")

    def test_zero_paying(self):
        assert calculate_arpu(Decimal("100000"), 0) == Decimal("0")

    def test_negative_paying(self):
        assert calculate_arpu(Decimal("100000"), -10) == Decimal("0")

    def test_zero_revenue(self):
        assert calculate_arpu(Decimal("0"), 50) == Decimal("0")


# =============================================================================
# AI Cost per User
# =============================================================================


class TestCalculateAiCostPerUser:
    def test_basic(self):
        assert calculate_ai_cost_per_user(Decimal("30000"), 50) == Decimal("600")

    def test_zero_users(self):
        assert calculate_ai_cost_per_user(Decimal("30000"), 0) == Decimal("0")

    def test_negative_users(self):
        assert calculate_ai_cost_per_user(Decimal("30000"), -1) == Decimal("0")

    def test_zero_cost(self):
        assert calculate_ai_cost_per_user(Decimal("0"), 50) == Decimal("0")


# =============================================================================
# Contribution Margin
# =============================================================================


class TestCalculateContributionMargin:
    def test_basic(self):
        assert calculate_contribution_margin(Decimal("100000"), Decimal("40000")) == Decimal("60.00")

    def test_zero_revenue(self):
        assert calculate_contribution_margin(Decimal("0"), Decimal("40000")) == Decimal("0")

    def test_negative_revenue(self):
        assert calculate_contribution_margin(Decimal("-10000"), Decimal("4000")) == Decimal("0")

    def test_full_margin(self):
        assert calculate_contribution_margin(Decimal("100000"), Decimal("0")) == Decimal("100.00")

    def test_zero_variable_costs(self):
        assert calculate_contribution_margin(Decimal("50000"), Decimal("0")) == Decimal("100.00")

    def test_equal_values(self):
        assert calculate_contribution_margin(Decimal("50000"), Decimal("50000")) == Decimal("0.00")


# =============================================================================
# Unit Economics
# =============================================================================


class TestCalculateUnitEconomics:
    def test_tokens_50m(self):
        result = calculate_unit_economics(
            plan_code="TOKENS_50M",
            plan_name="50M токенов",
            tokens_granted=50_000_000,
            price_rubles=Decimal("2000"),
            ai_cost_rubles=Decimal("500"),
            tax_rate=Decimal("0.06"),
            acquiring_rate=Decimal("0.02"),
            cac_rubles=Decimal("100"),
        )
        assert result.tax_rubles == Decimal("120.00")
        assert result.acquiring_rubles == Decimal("40.00")
        assert result.contribution_profit_rubles == Decimal("1240.00")
        assert result.contribution_margin_pct == Decimal("62.00")

    def test_plan_code_and_name(self):
        result = calculate_unit_economics(
            plan_code="PRO",
            plan_name="Профессионал",
            tokens_granted=100_000_000,
            price_rubles=Decimal("5000"),
            ai_cost_rubles=Decimal("1000"),
        )
        assert result.plan_code == "PRO"
        assert result.plan_name == "Профессионал"
        assert result.tokens_granted == 100_000_000

    def test_defaults_tax_and_acquiring(self):
        result = calculate_unit_economics(
            plan_code="BASIC",
            plan_name="Базовый",
            tokens_granted=10_000_000,
            price_rubles=Decimal("1000"),
            ai_cost_rubles=Decimal("200"),
        )
        # default tax_rate=0.06, acquiring_rate=0.02
        assert result.tax_rubles == Decimal("60.00")
        assert result.acquiring_rubles == Decimal("20.00")
        assert result.contribution_profit_rubles == Decimal("720.00")
        assert result.contribution_margin_pct == Decimal("72.00")

    def test_zero_price(self):
        result = calculate_unit_economics(
            plan_code="FREE",
            plan_name="Бесплатный",
            tokens_granted=1_000_000,
            price_rubles=Decimal("0"),
            ai_cost_rubles=Decimal("10"),
        )
        assert result.tax_rubles == Decimal("0.00")
        assert result.acquiring_rubles == Decimal("0.00")
        assert result.contribution_profit_rubles == Decimal("-10")
        assert result.contribution_margin_pct == Decimal("0")

    def test_high_ai_cost(self):
        result = calculate_unit_economics(
            plan_code="EXPENSIVE",
            plan_name="Дорогой",
            tokens_granted=50_000_000,
            price_rubles=Decimal("1000"),
            ai_cost_rubles=Decimal("900"),
            tax_rate=Decimal("0.06"),
            acquiring_rate=Decimal("0.02"),
            cac_rubles=Decimal("50"),
        )
        # tax=60, acq=20, contribution=1000-900-60-20-50=-30
        assert result.contribution_profit_rubles == Decimal("-30")
        assert result.contribution_margin_pct < Decimal("0")

    def test_cac_zero_default(self):
        result = calculate_unit_economics(
            plan_code="TEST",
            plan_name="Test",
            tokens_granted=1_000_000,
            price_rubles=Decimal("500"),
            ai_cost_rubles=Decimal("100"),
        )
        assert result.cac_rubles == Decimal("0")


# =============================================================================
# Break-even
# =============================================================================


class TestCalculateBreakeven:
    def test_basic(self):
        assert calculate_breakeven_users(Decimal("15000"), Decimal("1240")) == 13

    def test_zero_contribution(self):
        assert calculate_breakeven_users(Decimal("15000"), Decimal("0")) == 0

    def test_negative_contribution(self):
        assert calculate_breakeven_users(Decimal("15000"), Decimal("-100")) == 0

    def test_exact_division(self):
        assert calculate_breakeven_users(Decimal("10000"), Decimal("100")) == 100

    def test_small_fractional(self):
        assert calculate_breakeven_users(Decimal("1000"), Decimal("300")) == 4

    def test_one_user(self):
        assert calculate_breakeven_users(Decimal("500"), Decimal("1000")) == 1

    def test_zero_fixed_costs(self):
        assert calculate_breakeven_users(Decimal("0"), Decimal("100")) == 0


# =============================================================================
# Capital Requirements
# =============================================================================


class TestCalculateCapitalRequirements:
    def test_basic(self):
        result = calculate_capital_requirements(
            monthly_fixed_costs=Decimal("15000"),
            ai_cost_per_user=Decimal("100"),
            users_before_revenue=100,
            months_to_breakeven=3,
        )
        assert result.min_capital_rubles == Decimal("75000.00")
        assert result.base_capital_rubles == Decimal("97500.00")
        assert result.conservative_capital_rubles == Decimal("112500.00")

    def test_with_acquisition_cost(self):
        result = calculate_capital_requirements(
            monthly_fixed_costs=Decimal("15000"),
            ai_cost_per_user=Decimal("100"),
            users_before_revenue=100,
            months_to_breakeven=3,
            acquisition_cost_per_user=Decimal("50"),
        )
        # min = 15000*3 + 100*100*3 + 50*100 = 45000+30000+5000 = 80000
        assert result.min_capital_rubles == Decimal("80000.00")
        assert result.base_capital_rubles == Decimal("104000.00")
        assert result.conservative_capital_rubles == Decimal("120000.00")

    def test_one_month(self):
        result = calculate_capital_requirements(
            monthly_fixed_costs=Decimal("10000"),
            ai_cost_per_user=Decimal("50"),
            users_before_revenue=10,
            months_to_breakeven=1,
        )
        # min = 10000*1 + 50*10*1 = 10500
        assert result.min_capital_rubles == Decimal("10500.00")
        assert result.months_to_breakeven == 1

    def test_max_negative_cashflow(self):
        result = calculate_capital_requirements(
            monthly_fixed_costs=Decimal("15000"),
            ai_cost_per_user=Decimal("100"),
            users_before_revenue=100,
            months_to_breakeven=3,
        )
        # max_negative = 75000 * 0.8 = 60000
        assert result.max_negative_cashflow_rubles == Decimal("60000.00")

    def test_zero_users_before_revenue(self):
        result = calculate_capital_requirements(
            monthly_fixed_costs=Decimal("20000"),
            ai_cost_per_user=Decimal("100"),
            users_before_revenue=0,
            months_to_breakeven=6,
        )
        # min = 20000*6 + 100*0*6 = 120000
        assert result.min_capital_rubles == Decimal("120000.00")

    def test_monthly_fixed_stored(self):
        result = calculate_capital_requirements(
            monthly_fixed_costs=Decimal("25000"),
            ai_cost_per_user=Decimal("200"),
            users_before_revenue=50,
            months_to_breakeven=4,
        )
        assert result.monthly_fixed_costs_rubles == Decimal("25000")


# =============================================================================
# Launch Scenario
# =============================================================================


class TestCalculateLaunchScenario:
    def test_basic(self):
        result = calculate_launch_scenario(
            audience_size=20000,
            conversion_rate=Decimal("0.01"),
            avg_check_rubles=Decimal("2000"),
            ai_cost_per_user_rubles=Decimal("100"),
        )
        assert result.buyers == 200
        assert result.revenue_rubles == Decimal("400000.00")
        assert result.ai_cost_rubles == Decimal("20000.00")

    def test_profit_and_expenses(self):
        result = calculate_launch_scenario(
            audience_size=20000,
            conversion_rate=Decimal("0.01"),
            avg_check_rubles=Decimal("2000"),
            ai_cost_per_user_rubles=Decimal("100"),
            fixed_costs_rubles=Decimal("50000"),
            cac_rubles=Decimal("200"),
        )
        # buyers=200, revenue=400000, ai=20000
        # cac_total = 200*200 = 40000, expenses = 50000+40000 = 90000
        # profit = 400000 - 20000 - 90000 = 290000
        assert result.buyers == 200
        assert result.revenue_rubles == Decimal("400000.00")
        assert result.ai_cost_rubles == Decimal("20000.00")
        assert result.expenses_rubles == Decimal("90000.00")
        assert result.profit_rubles == Decimal("290000.00")

    def test_required_capital(self):
        result = calculate_launch_scenario(
            audience_size=1000,
            conversion_rate=Decimal("0.05"),
            avg_check_rubles=Decimal("1000"),
            ai_cost_per_user_rubles=Decimal("200"),
            fixed_costs_rubles=Decimal("10000"),
        )
        # buyers=50, ai=10000, expenses=10000
        # required_capital = 10000+10000 = 20000
        assert result.required_capital_rubles == Decimal("20000.00")

    def test_zero_conversion(self):
        result = calculate_launch_scenario(
            audience_size=5000,
            conversion_rate=Decimal("0"),
            avg_check_rubles=Decimal("2000"),
            ai_cost_per_user_rubles=Decimal("100"),
        )
        assert result.buyers == 0
        assert result.revenue_rubles == Decimal("0.00")
        assert result.ai_cost_rubles == Decimal("0.00")
        assert result.profit_rubles == Decimal("0.00")

    def test_high_conversion(self):
        result = calculate_launch_scenario(
            audience_size=100,
            conversion_rate=Decimal("0.5"),
            avg_check_rubles=Decimal("3000"),
            ai_cost_per_user_rubles=Decimal("300"),
        )
        assert result.buyers == 50
        assert result.revenue_rubles == Decimal("150000.00")

    def test_fractional_conversion_rounds(self):
        result = calculate_launch_scenario(
            audience_size=1000,
            conversion_rate=Decimal("0.033"),
            avg_check_rubles=Decimal("1500"),
            ai_cost_per_user_rubles=Decimal("50"),
        )
        # 1000 * 0.033 = 33.0 → ROUND_HALF_UP → 33
        assert result.buyers == 33

    def test_visitors_and_registrations_equal_audience(self):
        result = calculate_launch_scenario(
            audience_size=5000,
            conversion_rate=Decimal("0.02"),
            avg_check_rubles=Decimal("1000"),
            ai_cost_per_user_rubles=Decimal("50"),
        )
        assert result.visitors == 5000
        assert result.registrations == 5000
        assert result.audience_size == 5000


# =============================================================================
# Stage Economics
# =============================================================================


class TestCalculateStageEconomics:
    def test_basic(self):
        result = calculate_stage_economics(
            user_count=1000,
            paying_rate=Decimal("0.10"),
            avg_tokens_per_user=100_000,
            input_share=Decimal("0.60"),
            output_share=Decimal("0.30"),
            cache_share=Decimal("0.10"),
            input_price_per_token=Decimal("0.00001853"),
            output_price_per_token=Decimal("0.00003708"),
            cache_price_per_token=Decimal("0.000005"),
            avg_check_rubles=Decimal("2000"),
            fixed_costs_monthly=Decimal("50000"),
            acquiring_rate=Decimal("0.02"),
            tax_rate=Decimal("0.06"),
        )
        # paying_users = int(1000 * 0.10) = 100
        # revenue = 100 * 2000 = 200000.00
        assert result.user_count == 1000
        assert result.revenue_rubles == Decimal("200000.00")
        assert result.fixed_costs_rubles == Decimal("50000")

    def test_ai_cost_calculation(self):
        result = calculate_stage_economics(
            user_count=100,
            paying_rate=Decimal("0.10"),
            avg_tokens_per_user=10_000,
            input_share=Decimal("0.50"),
            output_share=Decimal("0.50"),
            cache_share=Decimal("0"),
            input_price_per_token=Decimal("0.00002"),
            output_price_per_token=Decimal("0.00004"),
            cache_price_per_token=Decimal("0"),
            avg_check_rubles=Decimal("1000"),
            fixed_costs_monthly=Decimal("10000"),
            acquiring_rate=Decimal("0.02"),
            tax_rate=Decimal("0.06"),
        )
        # paying = int(100 * 0.10) = 10
        # revenue = 10 * 1000 = 10000.00
        # ai per user = 10000*0.5*0.00002 + 10000*0.5*0.00004 + 10000*0*0 = 0.3
        # ai total = 10 * 0.3 = 3.00
        # acquiring = 10000*0.02 = 200.00
        # tax = 10000*0.06 = 600.00
        # variable = 800.00
        # profit = 10000 - 3 - 10000 - 800 = -803.00
        assert result.revenue_rubles == Decimal("10000.00")
        assert result.ai_cost_rubles == Decimal("3.00")
        assert result.is_breakeven is False

    def test_profit_and_breakeven_flag(self):
        result = calculate_stage_economics(
            user_count=100,
            paying_rate=Decimal("1.00"),
            avg_tokens_per_user=50_000,
            input_share=Decimal("0.60"),
            output_share=Decimal("0.30"),
            cache_share=Decimal("0.10"),
            input_price_per_token=Decimal("0.00001"),
            output_price_per_token=Decimal("0.00002"),
            cache_price_per_token=Decimal("0.000005"),
            avg_check_rubles=Decimal("500"),
            fixed_costs_monthly=Decimal("10000"),
            acquiring_rate=Decimal("0.02"),
            tax_rate=Decimal("0.06"),
        )
        # paying = int(100 * 1.00) = 100, revenue = 50000.00
        # ai per user = 50000*0.6*0.00001 + 50000*0.3*0.00002 + 50000*0.1*0.000005
        #            = 0.3 + 0.3 + 0.025 = 0.625
        # ai total = 100 * 0.625 = 62.50
        # acquiring = 50000 * 0.02 = 1000.00
        # tax = 50000 * 0.06 = 3000.00
        # variable = 4000.00
        # profit = 50000 - 62.50 - 10000 - 4000 = 35937.50
        assert result.is_breakeven is True
        assert result.profit_rubles == Decimal("35937.50")

    def test_loss_stage(self):
        result = calculate_stage_economics(
            user_count=10,
            paying_rate=Decimal("0.10"),
            avg_tokens_per_user=500_000,
            input_share=Decimal("0.60"),
            output_share=Decimal("0.30"),
            cache_share=Decimal("0.10"),
            input_price_per_token=Decimal("0.00002"),
            output_price_per_token=Decimal("0.00004"),
            cache_price_per_token=Decimal("0.00001"),
            avg_check_rubles=Decimal("2000"),
            fixed_costs_monthly=Decimal("50000"),
            acquiring_rate=Decimal("0.02"),
            tax_rate=Decimal("0.06"),
        )
        # paying = int(10*0.1) = 1
        # revenue = 1*2000 = 2000.00
        # ai per user = 500000*0.6*0.00002 + 500000*0.3*0.00004 + 500000*0.1*0.00001
        #            = 60 + 60 + 0.5 = 120.5
        # ai total = 1*120.5 = 120.50
        # acquiring = 2000*0.02 = 40.00
        # tax = 2000*0.06 = 120.00
        # variable = 160.00
        # profit = 2000 - 120.50 - 50000 - 160 = -48280.50
        assert result.is_breakeven is False
        assert result.profit_rubles < 0

    def test_stage_name(self):
        result = calculate_stage_economics(
            user_count=500,
            paying_rate=Decimal("0.20"),
            avg_tokens_per_user=20_000,
            input_share=Decimal("0.70"),
            output_share=Decimal("0.20"),
            cache_share=Decimal("0.10"),
            input_price_per_token=Decimal("0.00001"),
            output_price_per_token=Decimal("0.00002"),
            cache_price_per_token=Decimal("0.000005"),
            avg_check_rubles=Decimal("1500"),
            fixed_costs_monthly=Decimal("30000"),
            acquiring_rate=Decimal("0.02"),
            tax_rate=Decimal("0.06"),
        )
        assert result.stage_name == "500 users"

    def test_zero_paying_rate(self):
        result = calculate_stage_economics(
            user_count=1000,
            paying_rate=Decimal("0"),
            avg_tokens_per_user=10_000,
            input_share=Decimal("0.60"),
            output_share=Decimal("0.30"),
            cache_share=Decimal("0.10"),
            input_price_per_token=Decimal("0.00001"),
            output_price_per_token=Decimal("0.00002"),
            cache_price_per_token=Decimal("0.000005"),
            avg_check_rubles=Decimal("2000"),
            fixed_costs_monthly=Decimal("50000"),
            acquiring_rate=Decimal("0.02"),
            tax_rate=Decimal("0.06"),
        )
        assert result.revenue_rubles == Decimal("0.00")
        assert result.ai_cost_rubles == Decimal("0.00")
        assert result.is_breakeven is False


# =============================================================================
# Decimal Precision
# =============================================================================


class TestDecimalPrecision:
    def test_profitability_uses_decimal(self):
        result = calculate_profitability(
            revenue=Decimal("100000.50"),
            ai_cost=Decimal("30000.25"),
            infrastructure_cost=Decimal("10000.10"),
            tax=Decimal("6000.03"),
            acquiring=Decimal("2000.01"),
            advertising=Decimal("8000.02"),
            other_costs=Decimal("4000.01"),
        )
        assert isinstance(result.profit, Decimal)
        assert isinstance(result.margin_pct, Decimal)

    def test_unit_economics_uses_decimal(self):
        result = calculate_unit_economics(
            plan_code="TEST",
            plan_name="Test",
            tokens_granted=1_000_000,
            price_rubles=Decimal("999.99"),
            ai_cost_rubles=Decimal("123.45"),
        )
        assert isinstance(result.tax_rubles, Decimal)
        assert isinstance(result.acquiring_rubles, Decimal)
        assert isinstance(result.contribution_profit_rubles, Decimal)
        assert isinstance(result.contribution_margin_pct, Decimal)

    def test_capital_uses_decimal(self):
        result = calculate_capital_requirements(
            monthly_fixed_costs=Decimal("12345.67"),
            ai_cost_per_user=Decimal("99.99"),
            users_before_revenue=50,
            months_to_breakeven=6,
        )
        assert isinstance(result.min_capital_rubles, Decimal)
        assert isinstance(result.base_capital_rubles, Decimal)
        assert isinstance(result.conservative_capital_rubles, Decimal)

    def test_launch_scenario_uses_decimal(self):
        result = calculate_launch_scenario(
            audience_size=1000,
            conversion_rate=Decimal("0.03"),
            avg_check_rubles=Decimal("1500.75"),
            ai_cost_per_user_rubles=Decimal("45.25"),
        )
        assert isinstance(result.revenue_rubles, Decimal)
        assert isinstance(result.ai_cost_rubles, Decimal)
        assert isinstance(result.profit_rubles, Decimal)
        assert isinstance(result.required_capital_rubles, Decimal)
