"""Реальные ловушки знаменателей и интервалов не должны становиться новыми знаниями."""
import copy

import pytest

from domain.article_maps import ArticleMapError, digest
from domain.primary_evidence import audit_measurement, independent_cohorts, transfer_barriers, verify_fragment


def rate(value="14.2", events="123", years="8681", unit="per_1000_person_years"):
    return {"id": "synthetic", "value": value, "unit": unit, "events": events,
            "confidence_interval": None, "denominator": {"person_years": years, "role": "population_at_risk_time"}}


def test_gas_total_rate_uses_population_time():
    r = audit_measurement(rate())
    assert r["status"] == "numerically_consistent"
    assert r["warnings"] == ["confidence_interval_not_reported"]


def test_eventual_mci_group_time_cannot_be_the_risk_denominator():
    o = rate(years="716")
    o["denominator"]["role"] = "eventual_outcome_group_time"
    assert audit_measurement(o)["issues"] == ["denominator_is_not_population_at_risk_time"]


def test_false_denominator_role_still_fails_numerical_consistency():
    assert audit_measurement(rate(years="716"))["issues"] == ["rate_not_reproduced_at_published_precision"]


def test_eas_rate_normalization_preserves_decimal_precision():
    r = audit_measurement(rate("2.57", "19", "739.86", "per_100_person_years"))
    assert r["issues"] == [] and r["value_per_1000_person_years"] == "25.70"


def test_eas_85_89_displayed_precision_mismatch_is_not_silently_repaired():
    o = rate("7.00", "69", "986.86", "per_100_person_years")
    assert audit_measurement(o)["issues"] == ["rate_not_reproduced_at_published_precision"]
    assert o["value"] == "7.00"


def test_pacos_inconsistent_interval_is_quarantined_without_repair():
    o = {"id": "executive", "value": "7.76", "unit": "hazard_ratio", "confidence_interval": ["2.31", "5.64"]}
    old = copy.deepcopy(o)
    assert audit_measurement(o)["issues"] == ["point_outside_published_confidence_interval"]
    assert o == old


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-1", 14.2])
def test_invalid_numeric_input_rejected(bad):
    with pytest.raises(ArticleMapError):
        audit_measurement(rate(value=bad))


def test_units_do_not_create_missing_intervals():
    r = audit_measurement(rate())
    assert r["scientific_validation"] is False
    with pytest.raises(ArticleMapError, match="dimension"):
        audit_measurement({**rate(), "unit": "percent"})


def test_unknown_and_different_context_prevent_automatic_transfer():
    a = {"population": "community", "endpoint_definition": "gas_memory", "baseline_riskset": "gas_selected",
         "sex": "female", "age_band": [80, None], "adjustment": "crude"}
    b = {**a, "endpoint_definition": "mayo_amci", "age_band": [85, 89]}
    assert transfer_barriers(a, b) == ["different:endpoint_definition", "different:age_band"]
    b["population"] = None
    assert "unknown:population" in transfer_barriers(a, b)


def test_same_eas_cohort_never_counts_as_two_independent_sources():
    assert independent_cohorts([{"cohort_id": "eas", "publication": 2012}, {"cohort_id": "eas", "publication": 2019}]) == ["eas"]
    with pytest.raises(ArticleMapError):
        independent_cohorts([{"cohort_id": None}])


def test_unicode_fragment_and_revision_are_verified():
    source = "MCI 🧠 ≥80 years"
    start = source.index("≥")
    p = {"offset_encoding": "unicode_codepoints", "source_sha256": digest(source), "start": start,
         "end": len(source), "text": source[start:], "text_sha256": digest(source[start:])}
    verify_fragment(p, source)
    with pytest.raises(ArticleMapError):
        verify_fragment({**p, "start": start + 1}, source)
    with pytest.raises(ArticleMapError):
        verify_fragment(p, source + "!")
