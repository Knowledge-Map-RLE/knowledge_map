"""Юнит-тесты PriceVersionData и calculate_provider_cost.

Версионирование тарифов провайдеров: трассируемость стоимости AI-запросов.
"""
from decimal import Decimal

import pytest

from domain.rules.ai_pricing import (
    PriceVersionData,
    UsageCost,
    calculate_provider_cost,
)


# =============================================================================
# PriceVersionData
# =============================================================================


class TestPriceVersionData:
    def test_direct_construction(self):
        pvd = PriceVersionData(
            price_version_uid="pv-001",
            model="deepseek-v4-flash",
            input_price_per_token=Decimal("0.00001853"),
            output_price_per_token=Decimal("0.00003708"),
        )
        assert pvd.price_version_uid == "pv-001"
        assert pvd.model == "deepseek-v4-flash"
        assert pvd.input_price_per_token == Decimal("0.00001853")
        assert pvd.output_price_per_token == Decimal("0.00003708")
        assert pvd.cache_price_per_token is None

    def test_with_cache_price(self):
        pvd = PriceVersionData(
            price_version_uid="pv-002",
            model="deepseek-v4-flash",
            input_price_per_token=Decimal("0.00001853"),
            output_price_per_token=Decimal("0.00003708"),
            cache_price_per_token=Decimal("0.000005"),
        )
        assert pvd.cache_price_per_token == Decimal("0.000005")

    def test_from_million_prices_basic(self):
        pvd = PriceVersionData.from_million_prices(
            uid="pv-100",
            model="deepseek-v4-flash",
            input_per_million=Decimal("18.53"),
            output_per_million=Decimal("37.08"),
        )
        assert pvd.price_version_uid == "pv-100"
        assert pvd.model == "deepseek-v4-flash"
        assert pvd.input_price_per_token == Decimal("0.00001853")
        assert pvd.output_price_per_token == Decimal("0.00003708")
        assert pvd.cache_price_per_token is None

    def test_from_million_prices_with_cache(self):
        pvd = PriceVersionData.from_million_prices(
            uid="pv-200",
            model="gpt-4o",
            input_per_million=Decimal("25.00"),
            output_per_million=Decimal("50.00"),
            cache_per_million=Decimal("12.50"),
        )
        assert pvd.cache_price_per_token == Decimal("0.0000125")

    def test_from_million_prices_integer_millions(self):
        pvd = PriceVersionData.from_million_prices(
            uid="pv-300",
            model="test-model",
            input_per_million=Decimal("10"),
            output_per_million=Decimal("20"),
        )
        assert pvd.input_price_per_token == Decimal("0.00001")
        assert pvd.output_price_per_token == Decimal("0.00002")

    def test_from_million_prices_zero(self):
        pvd = PriceVersionData.from_million_prices(
            uid="pv-free",
            model="free-model",
            input_per_million=Decimal("0"),
            output_per_million=Decimal("0"),
        )
        assert pvd.input_price_per_token == Decimal("0")
        assert pvd.output_price_per_token == Decimal("0")

    def test_is_frozen(self):
        pvd = PriceVersionData(
            price_version_uid="pv-001",
            model="test",
            input_price_per_token=Decimal("0.00001"),
            output_price_per_token=Decimal("0.00002"),
        )
        with pytest.raises(AttributeError):
            pvd.model = "changed"  # type: ignore[misc]


# =============================================================================
# calculate_provider_cost
# =============================================================================


class TestCalculateProviderCost:
    def _make_version(
        self,
        input_price: str = "0.00001853",
        output_price: str = "0.00003708",
        cache_price: str | None = None,
    ) -> PriceVersionData:
        kwargs = {
            "price_version_uid": "pv-test",
            "model": "deepseek-v4-flash",
            "input_price_per_token": Decimal(input_price),
            "output_price_per_token": Decimal(output_price),
        }
        if cache_price is not None:
            kwargs["cache_price_per_token"] = Decimal(cache_price)
        return PriceVersionData(**kwargs)

    def test_basic_input_output(self):
        pvd = self._make_version()
        cost = calculate_provider_cost(
            input_tokens=1000,
            output_tokens=500,
            price_version=pvd,
        )
        # input: 1000 * 0.00001853 = 0.01853
        # output: 500 * 0.00003708 = 0.01854
        assert cost.input_cost == Decimal("0.01853")
        assert cost.output_cost == Decimal("0.01854")
        assert cost.total == Decimal("0.03707")

    def test_with_cached_tokens(self):
        pvd = self._make_version(cache_price="0.000005")
        cost = calculate_provider_cost(
            input_tokens=1000,
            output_tokens=500,
            cached_tokens=200,
            price_version=pvd,
        )
        # input: 1000 * 0.00001853 = 0.01853
        # output: 500 * 0.00003708 = 0.01854
        # cache: 200 * 0.000005 = 0.001
        assert cost.input_cost == Decimal("0.01853")
        assert cost.output_cost == Decimal("0.01854")
        assert cost.tool_cost == Decimal("0.001")
        assert cost.total == Decimal("0.03807")

    def test_no_cache_price_cached_tokens_zero(self):
        pvd = self._make_version()
        cost = calculate_provider_cost(
            input_tokens=1000,
            output_tokens=500,
            cached_tokens=100,
            price_version=pvd,
        )
        # No cache price → cache cost is 0 even if cached_tokens > 0
        assert cost.tool_cost == Decimal("0")

    def test_zero_tokens(self):
        pvd = self._make_version()
        cost = calculate_provider_cost(price_version=pvd)
        assert cost.input_cost == Decimal("0")
        assert cost.output_cost == Decimal("0")
        assert cost.tool_cost == Decimal("0")
        assert cost.total == Decimal("0")

    def test_only_input_tokens(self):
        pvd = self._make_version()
        cost = calculate_provider_cost(
            input_tokens=5000,
            price_version=pvd,
        )
        assert cost.input_cost == Decimal("0.09265")
        assert cost.output_cost == Decimal("0")
        assert cost.total == Decimal("0.09265")

    def test_only_output_tokens(self):
        pvd = self._make_version()
        cost = calculate_provider_cost(
            output_tokens=3000,
            price_version=pvd,
        )
        assert cost.input_cost == Decimal("0")
        assert cost.output_cost == Decimal("0.11124")
        assert cost.total == Decimal("0.11124")

    def test_uses_version_prices_not_env(self):
        pvd = self._make_version(input_price="0.001", output_price="0.002")
        cost = calculate_provider_cost(
            input_tokens=100,
            output_tokens=100,
            price_version=pvd,
        )
        assert cost.input_cost == Decimal("0.1")
        assert cost.output_cost == Decimal("0.2")

    def test_large_token_count(self):
        pvd = self._make_version()
        cost = calculate_provider_cost(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            price_version=pvd,
        )
        assert cost.input_cost == Decimal("18.53")
        assert cost.output_cost == Decimal("37.08")
        assert cost.total == Decimal("55.61")

    def test_returns_usage_cost_instance(self):
        pvd = self._make_version()
        cost = calculate_provider_cost(
            input_tokens=100,
            output_tokens=100,
            price_version=pvd,
        )
        assert isinstance(cost, UsageCost)


# =============================================================================
# PriceVersionData + calculate_provider_cost integration
# =============================================================================


class TestVersionedCostIntegration:
    def test_from_million_then_calculate(self):
        pvd = PriceVersionData.from_million_prices(
            uid="pv-int-001",
            model="deepseek-v4-flash",
            input_per_million=Decimal("18.53"),
            output_per_million=Decimal("37.08"),
            cache_per_million=Decimal("5.00"),
        )
        cost = calculate_provider_cost(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cached_tokens=500_000,
            price_version=pvd,
        )
        assert cost.input_cost == Decimal("18.53")
        assert cost.output_cost == Decimal("37.08")
        assert cost.tool_cost == Decimal("2.50")
        assert cost.total == Decimal("58.11")

    def test_different_versions_different_costs(self):
        v1 = PriceVersionData.from_million_prices(
            uid="v1",
            model="deepseek-v4-flash",
            input_per_million=Decimal("18.53"),
            output_per_million=Decimal("37.08"),
        )
        v2 = PriceVersionData.from_million_prices(
            uid="v2",
            model="gpt-4o",
            input_per_million=Decimal("100"),
            output_per_million=Decimal("200"),
        )
        cost1 = calculate_provider_cost(input_tokens=1000, output_tokens=1000, price_version=v1)
        cost2 = calculate_provider_cost(input_tokens=1000, output_tokens=1000, price_version=v2)
        assert cost1.total < cost2.total

    def test_version_uid_traceability(self):
        pvd = PriceVersionData.from_million_prices(
            uid="trace-123",
            model="model-x",
            input_per_million=Decimal("10"),
            output_per_million=Decimal("20"),
        )
        assert pvd.price_version_uid == "trace-123"
