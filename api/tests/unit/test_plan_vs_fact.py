"""Юнит-тесты сравнения плановых и фактических показателей.

Покрытие: _deviation_pct, _deviation_abs, compare_plan_vs_fact,
           detect_anomaly_deviations, summarize_plan_vs_fact.
"""
from decimal import Decimal

import pytest

from domain.models.admin import PlanVsFactItem
from domain.rules.plan_vs_fact import (
    compare_plan_vs_fact,
    detect_anomaly_deviations,
    summarize_plan_vs_fact,
)


# =============================================================================
# compare_plan_vs_fact
# =============================================================================


class TestComparePlanVsFact:
    def test_identical_plan_and_fact(self):
        plan = {"revenue": Decimal("100000"), "profit": Decimal("40000")}
        fact = {"revenue": Decimal("100000"), "profit": Decimal("40000")}
        items = compare_plan_vs_fact(plan, fact)
        assert len(items) > 0
        for item in items:
            assert item.deviation_abs == Decimal("0.00")
            assert item.deviation_pct == Decimal("0.00")

    def test_deviation_abs_positive(self):
        plan = {"revenue": Decimal("100000")}
        fact = {"revenue": Decimal("120000")}
        items = compare_plan_vs_fact(plan, fact)
        rev = [i for i in items if i.metric_name == "revenue"][0]
        assert rev.deviation_abs == Decimal("20000.00")
        assert rev.deviation_pct == Decimal("20.00")

    def test_deviation_abs_negative(self):
        plan = {"revenue": Decimal("100000")}
        fact = {"revenue": Decimal("80000")}
        items = compare_plan_vs_fact(plan, fact)
        rev = [i for i in items if i.metric_name == "revenue"][0]
        assert rev.deviation_abs == Decimal("-20000.00")
        assert rev.deviation_pct == Decimal("-20.00")

    def test_zero_plan_value(self):
        plan = {"revenue": Decimal("0")}
        fact = {"revenue": Decimal("10000")}
        items = compare_plan_vs_fact(plan, fact)
        rev = [i for i in items if i.metric_name == "revenue"][0]
        assert rev.deviation_abs == Decimal("10000.00")
        assert rev.deviation_pct == Decimal("0.00")

    def test_multiple_metrics(self):
        plan = {
            "users": Decimal("1000"),
            "paying_users": Decimal("100"),
            "revenue": Decimal("200000"),
        }
        fact = {
            "users": Decimal("1200"),
            "paying_users": Decimal("80"),
            "revenue": Decimal("160000"),
        }
        items = compare_plan_vs_fact(plan, fact)
        assert len(items) > 0
        users_item = [i for i in items if i.metric_name == "users"][0]
        assert users_item.deviation_pct == Decimal("20.00")
        paying_item = [i for i in items if i.metric_name == "paying_users"][0]
        assert paying_item.deviation_pct == Decimal("-20.00")

    def test_empty_facts(self):
        plan = {"revenue": Decimal("100000")}
        fact = {}
        items = compare_plan_vs_fact(plan, fact)
        rev = [i for i in items if i.metric_name == "revenue"][0]
        assert rev.fact_value == Decimal("0")
        assert rev.deviation_abs == Decimal("-100000.00")

    def test_empty_plan(self):
        plan = {}
        fact = {"revenue": Decimal("50000")}
        items = compare_plan_vs_fact(plan, fact)
        rev = [i for i in items if i.metric_name == "revenue"][0]
        assert rev.plan_value == Decimal("0")
        assert rev.deviation_abs == Decimal("50000.00")
        assert rev.deviation_pct == Decimal("0.00")

    def test_returns_all_metric_definitions(self):
        items = compare_plan_vs_fact({}, {})
        metric_names = [i.metric_name for i in items]
        expected = [
            "users", "paying_users", "conversion_rate",
            "avg_tokens_per_user", "input_share", "output_share",
            "cache_share", "avg_check", "infrastructure_cost",
            "tax", "acquiring", "cac", "ai_cost", "revenue",
            "profit", "margin",
        ]
        assert metric_names == expected

    def test_items_are_plan_vs_fact_instances(self):
        items = compare_plan_vs_fact({"revenue": Decimal("100")}, {"revenue": Decimal("200")})
        for item in items:
            assert isinstance(item, PlanVsFactItem)

    def test_items_have_units(self):
        items = compare_plan_vs_fact({}, {})
        for item in items:
            assert item.unit in ("₽", "%", "шт", "токенов")

    def test_items_have_formula(self):
        items = compare_plan_vs_fact({}, {})
        for item in items:
            assert isinstance(item.formula, str)
            assert len(item.formula) > 0


# =============================================================================
# detect_anomaly_deviations
# =============================================================================


class TestDetectAnomalyDeviations:
    def _make_item(self, name: str, pct: Decimal) -> PlanVsFactItem:
        return PlanVsFactItem(
            metric_name=name,
            metric_label=name,
            plan_value=Decimal("100"),
            fact_value=Decimal("100"),
            deviation_abs=Decimal("0"),
            deviation_pct=pct,
            formula="test",
            unit="₽",
        )

    def test_no_anomalies(self):
        items = [
            self._make_item("a", Decimal("10")),
            self._make_item("b", Decimal("-10")),
            self._make_item("c", Decimal("5")),
        ]
        anomalies = detect_anomaly_deviations(items)
        assert len(anomalies) == 0

    def test_all_anomalies(self):
        items = [
            self._make_item("a", Decimal("30")),
            self._make_item("b", Decimal("-25")),
        ]
        anomalies = detect_anomaly_deviations(items)
        assert len(anomalies) == 2

    def test_custom_threshold(self):
        items = [
            self._make_item("a", Decimal("15")),
            self._make_item("b", Decimal("25")),
        ]
        anomalies = detect_anomaly_deviations(items, threshold_pct=Decimal("10"))
        assert len(anomalies) == 2

    def test_exactly_at_threshold(self):
        items = [self._make_item("a", Decimal("20"))]
        anomalies = detect_anomaly_deviations(items, threshold_pct=Decimal("20"))
        assert len(anomalies) == 0

    def test_just_above_threshold(self):
        items = [self._make_item("a", Decimal("20.01"))]
        anomalies = detect_anomaly_deviations(items, threshold_pct=Decimal("20"))
        assert len(anomalies) == 1

    def test_negative_anomaly(self):
        items = [self._make_item("a", Decimal("-30"))]
        anomalies = detect_anomaly_deviations(items)
        assert len(anomalies) == 1
        assert anomalies[0].deviation_pct == Decimal("-30")

    def test_empty_list(self):
        assert detect_anomaly_deviations([]) == []


# =============================================================================
# summarize_plan_vs_fact
# =============================================================================


class TestSummarizePlanVsFact:
    def _make_item(self, name: str, abs_dev: Decimal, pct_dev: Decimal) -> PlanVsFactItem:
        return PlanVsFactItem(
            metric_name=name,
            metric_label=name,
            plan_value=Decimal("100"),
            fact_value=Decimal("100") + abs_dev,
            deviation_abs=abs_dev,
            deviation_pct=pct_dev,
            formula="test",
            unit="₽",
        )

    def test_all_on_plan(self):
        items = [
            self._make_item("a", Decimal("0"), Decimal("0")),
            self._make_item("b", Decimal("0"), Decimal("0")),
        ]
        summary = summarize_plan_vs_fact(items)
        assert summary["total_metrics"] == 2
        assert summary["better_than_plan"] == 0
        assert summary["worse_than_plan"] == 0
        assert summary["on_plan"] == 2
        assert summary["anomalies_count"] == 0

    def test_mixed_deviations(self):
        items = [
            self._make_item("a", Decimal("10"), Decimal("10")),
            self._make_item("b", Decimal("-10"), Decimal("-10")),
            self._make_item("c", Decimal("0"), Decimal("0")),
            self._make_item("d", Decimal("30"), Decimal("30")),
        ]
        summary = summarize_plan_vs_fact(items)
        assert summary["total_metrics"] == 4
        assert summary["better_than_plan"] == 2
        assert summary["worse_than_plan"] == 1
        assert summary["on_plan"] == 1
        assert summary["anomalies_count"] == 1

    def test_empty_items(self):
        summary = summarize_plan_vs_fact([])
        assert summary["total_metrics"] == 0
        assert summary["better_than_plan"] == 0
        assert summary["worse_than_plan"] == 0
        assert summary["on_plan"] == 0
        assert summary["anomalies_count"] == 0
        assert summary["anomalies"] == []

    def test_anomalies_populated(self):
        items = [
            self._make_item("a", Decimal("50"), Decimal("50")),
        ]
        summary = summarize_plan_vs_fact(items)
        assert summary["anomalies_count"] == 1
        assert len(summary["anomalies"]) == 1
        assert summary["anomalies"][0].metric_name == "a"

    def test_summary_keys(self):
        summary = summarize_plan_vs_fact([])
        expected_keys = {
            "total_metrics",
            "better_than_plan",
            "worse_than_plan",
            "on_plan",
            "anomalies_count",
            "anomalies",
        }
        assert set(summary.keys()) == expected_keys


# =============================================================================
# Decimal precision
# =============================================================================


class TestDecimalPrecision:
    def test_deviation_is_decimal(self):
        items = compare_plan_vs_fact(
            {"revenue": Decimal("100000.33")},
            {"revenue": Decimal("120000.67")},
        )
        rev = [i for i in items if i.metric_name == "revenue"][0]
        assert isinstance(rev.deviation_abs, Decimal)
        assert isinstance(rev.deviation_pct, Decimal)
        assert isinstance(rev.plan_value, Decimal)
        assert isinstance(rev.fact_value, Decimal)
