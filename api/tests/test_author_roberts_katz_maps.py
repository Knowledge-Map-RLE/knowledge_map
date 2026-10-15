import pytest

from domain.article_maps import ArticleMapError
from tools import author_roberts_katz_maps
from tools.author_roberts_katz_maps import validate_authored_polarity


def test_double_encoded_negative_predicate_is_rejected():
    authored = {"knowledge": [{
        "key": "negative-result",
        "predicate": "positive result",
        "claims": [{"predicate": "no statistically significant association", "negated": True}],
    }]}

    with pytest.raises(ArticleMapError, match="encoded twice"):
        validate_authored_polarity(authored)


def test_negative_result_uses_positive_predicate_and_one_negation_flag():
    authored = {"knowledge": [{
        "key": "negative-result",
        "predicate": "positive result",
        "claims": [{"predicate": "statistically significant association", "negated": True}],
    }]}

    validate_authored_polarity(authored)


def test_cohort_maps_reify_incidence_and_model_fitting_as_performed_actions(monkeypatch):
    monkeypatch.setattr(author_roberts_katz_maps, "source_unit",
                        lambda source, page_ranges, page, anchor: ["U1"])

    expected = {
        "roberts2012": {"incidence-estimation-operation", "fit-adjusted-hazard-models"},
        "katz2012": {"calculate-person-time", "calculate-incidence-rates", "fit-adjusted-cox-models"},
    }
    for article_id, expected_actions in expected.items():
        authored = author_roberts_katz_maps.build_authored(article_id, {"units": []}, [])
        actions = {item["key"] for item in authored["knowledge"] if item["kind"] == "action"}
        assert expected_actions <= actions
        assert all(item["type"] == "operation" and item["units"] == ["U1"]
                   for item in authored["knowledge"] if item["key"] in expected_actions)
        connected = {key for transition in authored["transitions"]
                     for key in [*transition["sources"], transition["target"]]}
        assert expected_actions <= connected
