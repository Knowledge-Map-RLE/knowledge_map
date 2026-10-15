"""Контроль качественного прогноза, численных свидетельств и независимости семей."""
from copy import deepcopy
from dataclasses import replace, asdict

import pytest

from domain.article_maps import ArticleMapError, ArticleMapAccessDenied, digest
from domain.research_semantics import SemanticClaim, Evidence, context_value as cv
from domain.question_prediction import ForecastQuestion, make_template
from domain.qualitative_question_prediction import (
    QualitativePolicy, qualitative_projection, finding_label, fit_qualitative_forecast,
    family_time_plan, evaluate_qualitative_holdout, applicability_difference,
)
from application.qualitative_question_prediction import SealQualitativeQuestionExperiment
from infrastructure.development_prediction_store import FilePredictionStore


def question():
    return ForecastQuestion.parse({"question_id": "test-il6", "text_en": "Baseline plasma IL-6 and subsequent global decline",
        "text_ru": "Исходный IL-6 в плазме и последующее глобальное снижение", "predicate": "associated with",
        "roles": {"exposure": "elevated baseline IL-6", "outcome": "subsequent global cognitive decline"},
        "context": {"species": cv("human"), "population": cv("older adults without dementia"), "design": cv("longitudinal"),
                    "specimen": cv("plasma"), "time": cv("followup at least two years")},
        "cutoff": "2022-12-31", "horizon_end": "2025-12-31", "limit": 20})


def policy_raw():
    return {"version": "test-policy-1", "question_id": "test-il6", "min_families": 2,
        "measurement_rules": [{"name": "beta", "unit": "mmse points/year", "higher_means_decline": False},
                              {"name": "hazard ratio", "unit": "dimensionless", "higher_means_decline": True}],
        "measure_groups": {"annual mmse change": "continuous global cognitive change", "binary decline": "global cognitive decline event"},
        "statistical_fields": ["beta", "beta ci", "p", "hazard ratio"], "constraint_fields": ["exposure threshold"]}


def policy():
    return QualitativePolicy.parse(policy_raw(), question())


def claim(article="a", family="family-a", available="2010-01-01", value="-0.1", modality="not statistically detected"):
    q = question()
    return SemanticClaim("K1S1", "K1", q.predicate, q.roles, False, None, modality,
        {**q.context, "study": cv(article), "cohort": cv(family), "measure": cv("annual mmse change"),
         "stratum": cv("at least 75 without baseline mci"), "conditions": cv("age sex education adjusted")},
        ({"name": "beta", "value": value, "unit": "mmse points/year"}, {"name": "p", "value": "0.4", "unit": "dimensionless"}),
        None, "single", "Synthetic source statement", Evidence(article, "run-" + article, digest(article), available, family, "own_result",
        ({"start": 0, "end": 1, "text": "x", "offset_encoding": "unicode_code_points"},)))


def historical():
    claims, episodes = {}, []
    for i in range(2):
        body = claim("prior" + str(i), "prior-family" + str(i), "2010-01-01", "-0.13")
        head = claim("result" + str(i), "result-family" + str(i), "2015-01-01", "0.036")
        for c in (body, head): claims[c.evidence.article_id, c.claim_id] = c
        episodes.append({"id": "episode" + str(i), "premises": [[body.evidence.article_id, body.claim_id]],
                         "conclusion": [head.evidence.article_id, head.claim_id], "transition_id": None})
    return claims, episodes


def test_new_numbers_stay_in_evidence_and_do_not_prevent_a_qualitative_template():
    claims, episodes = historical()
    body, head = [claims[tuple(episodes[0]["premises"][0])]], claims[tuple(episodes[0]["conclusion"])]
    assert make_template(body, head) is None
    before = deepcopy([c.to_dict() for c in claims.values()])
    result = fit_qualitative_forecast(claims, episodes, {}, question(), policy())
    assert len(result["rules"]["semantic"]) == 1
    assert len(result["modes"]["semantic"]) == 1
    candidate = result["modes"]["semantic"][0]
    assert candidate["finding"] == "not_statistically_detected" and candidate["proposition"]["negated"] is False
    assert candidate["proposition"]["measurements"] == []
    assert candidate["numerical_evidence"][0]["measurements"]
    assert before == [c.to_dict() for c in claims.values()]
    assert result["modes"]["dependency"] == []


@pytest.mark.parametrize("value,expected", [("-1", "positive_association"), ("1", "inverse_association"), ("0", "insufficient_data")])
def test_declared_scale_orientation_preserves_direction(value, expected):
    assert finding_label(claim(value=value, modality="statistically detected"), policy())[0] == expected


@pytest.mark.parametrize("value,expected", [("1.5", "positive_association"), ("0.7", "inverse_association")])
def test_ratio_reference_is_one(value, expected):
    c = replace(claim(modality="statistically detected"), measurements=({"name": "hazard ratio", "unit": "dimensionless", "value": value},))
    assert finding_label(c, policy())[0] == expected


def test_nonsignificance_is_not_negation_or_proof_of_no_effect():
    c = claim(value="-7")
    result, _ = qualitative_projection(c, policy())
    assert result.modality == "not_statistically_detected" and not result.negated
    assert finding_label(replace(c, negated=True), policy())[0] == "insufficient_data"


@pytest.mark.parametrize("field,value", [("stratum", "baseline mci"), ("conditions", "different adjustments"),
                                         ("specimen", "serum"), ("time", "cross sectional"), ("phase", "post treatment")])
def test_unsupported_context_transfer_is_rejected(field, value):
    claims, episodes = historical()
    key = tuple(episodes[0]["conclusion"])
    claims[key] = replace(claims[key], context={**claims[key].context, field: cv(value)})
    result = fit_qualitative_forecast(claims, episodes[:1], {}, question(), policy())
    assert not result["rules"]["semantic"]
    assert result["diagnostics"]["semantic"]["rejected"][0]["reason"] in {"unsupported_context_transfer", "question_or_qualitative_applicability_failed"}


def test_unknown_context_and_unperformed_tasks_cannot_be_applied():
    c = claim()
    assert qualitative_projection(replace(c, context={**c.context, "stratum": cv(None, "not_reported")}), policy())[0] is None
    for status in ("unresolved", "planned", "prescribed"):
        assert qualitative_projection(replace(c, action_status=status), policy())[0] is None


def test_exposure_thresholds_and_unclassified_numbers_are_not_erased():
    c = replace(claim(), measurements=claim().measurements + ({"name": "exposure threshold", "value": "2.47", "unit": "pg/ml"},))
    projected, _ = qualitative_projection(c, policy())
    assert projected.measurements == (c.measurements[-1],)
    changed = replace(projected, measurements=({"name": "exposure threshold", "value": "9", "unit": "pg/ml"},))
    assert applicability_difference(projected, changed) == ["constraint:exposure threshold"]
    assert qualitative_projection(replace(c, measurements=c.measurements + ({"name": "unknown effect", "value": "3", "unit": "mmse"},)), policy())[0] is None


def test_endpoint_and_continuous_change_do_not_merge():
    a, _ = qualitative_projection(claim(), policy())
    b, _ = qualitative_projection(replace(claim(), context={**claim().context, "measure": cv("binary decline")}), policy())
    assert "context:measure" in applicability_difference(a, b)


def test_repeated_study_publications_are_not_independent_support():
    claims, episodes = historical()
    for e in episodes:
        key = tuple(e["conclusion"])
        claims[key] = replace(claims[key], evidence=replace(claims[key].evidence, family="same-family"))
    result = fit_qualitative_forecast(claims, episodes, {}, question(), policy())
    assert result["modes"]["semantic"] == []
    assert result["diagnostics"]["semantic"]["rejected"][0]["reason"] == "insufficient_independent_families"


def test_frequency_counts_a_family_once_for_repeated_identical_estimates():
    a = claim("a", "same-family")
    b = claim("b", "same-family", value="0.2")
    result = fit_qualitative_forecast({("a", a.claim_id): a, ("b", b.claim_id): b}, [], {}, question(), policy())
    assert len(result["modes"]["frequency"]) == 1
    assert result["modes"]["frequency"][0]["support"] == 1
    assert len(result["modes"]["frequency"][0]["evidence"]) == 2


def test_family_time_split_excludes_every_family_publication_and_same_date():
    registry = {"a": {"family": "same", "available_on": "2015-01-01"}, "b": {"family": "same", "available_on": "2018-01-01"},
                "c": {"family": "other", "available_on": "2012-01-01"}, "d": {"family": "tied", "available_on": "2015-01-01"}}
    fold = next(f for f in family_time_plan(registry, question()) if f["family"] == "same")
    assert fold["heldout"] == ["a", "b"] and fold["training"] == ["c"]


def test_same_family_and_invalid_chronology_cannot_train():
    claims, episodes = historical()
    key = tuple(episodes[0]["conclusion"])
    head = claims[key]
    claims[key] = replace(head, evidence=replace(head.evidence, family="prior-family0"))
    assert fit_qualitative_forecast(claims, episodes[:1], {}, question(), policy())["diagnostics"]["semantic"]["rejected"][0]["reason"] == "same_study_family"
    claims[key] = replace(head, evidence=replace(head.evidence, available_on="2010-01-01"))
    with pytest.raises(ArticleMapError, match="future|same-publication"):
        fit_qualitative_forecast(claims, episodes[:1], {}, question(), policy())


def test_qualitative_evaluation_does_not_reproduce_future_numbers_or_refute_absence():
    claims, episodes = historical()
    forecast = fit_qualitative_forecast(claims, episodes, {}, question(), policy())
    forecast["binding"] = {"training_families": sorted({c.evidence.family for c in claims.values()})}
    target = claim("target", "heldout", "2024-01-01", value="0.812345")
    evaluated = evaluate_qualitative_holdout(forecast, [target])
    assert evaluated["modes"]["semantic"]["agreements"] == 1
    assert evaluated["modes"]["semantic"]["scorable_answers"] == 1
    absent = replace(target, predicate="different")
    empty = evaluate_qualitative_holdout(forecast, [absent])
    assert empty["modes"]["semantic"]["scorable_answers"] == 0
    assert empty["modes"]["semantic"]["agreement_at_k"]["1"] is None
    with pytest.raises(ArticleMapError, match="leaked"):
        evaluate_qualitative_holdout(forecast, [replace(target, evidence=replace(target.evidence, family="prior-family0"))])


def test_context_mismatch_is_unscorable_not_an_error_or_match():
    claims, episodes = historical()
    forecast = fit_qualitative_forecast(claims, episodes, {}, question(), policy())
    forecast["binding"] = {"training_families": []}
    t = claim("target", "heldout", "2024-01-01")
    t = replace(t, context={**t.context, "stratum": cv("baseline mci")})
    result = evaluate_qualitative_holdout(forecast, [t])["modes"]["semantic"]
    assert result["scorable_answers"] == 0 and result["agreements"] == 0
    assert result["results"][0]["matches"][0]["status"] == "context_mismatch"


def test_duplicate_episodes_and_out_of_horizon_targets_are_rejected():
    claims, episodes = historical()
    with pytest.raises(ArticleMapError, match="Duplicate"):
        fit_qualitative_forecast(claims, [episodes[0], episodes[0]], {}, question(), policy())
    forecast = fit_qualitative_forecast(claims, episodes, {}, question(), policy())
    forecast["binding"] = {"training_families": []}
    with pytest.raises(ArticleMapError, match="horizon"):
        evaluate_qualitative_holdout(forecast, [claim("future", "future-family", "2026-01-01")])


def test_different_statistical_findings_are_not_logical_contradictions():
    claims, episodes = historical()
    forecast = fit_qualitative_forecast(claims, episodes, {}, question(), policy())
    forecast["binding"] = {"training_families": []}
    target = claim("future", "future-family", "2024-01-01", value="-0.5", modality="statistically detected")
    evaluated = evaluate_qualitative_holdout(forecast, [target])
    assert evaluated["different_statistical_findings_are_not_logical_contradictions"]
    assert evaluated["modes"]["semantic"]["different_findings"] == 1


def test_projection_policy_is_explicit_and_roundtrips():
    assert QualitativePolicy.parse(policy().to_dict(), question()) == policy()
    raw = policy_raw(); raw["min_families"] = 1
    with pytest.raises(ArticleMapError, match="independent"):
        QualitativePolicy.parse(raw, question())
    raw = policy_raw(); raw["constraint_fields"].append("beta")
    with pytest.raises(ArticleMapError, match="overlap"):
        QualitativePolicy.parse(raw, question())


def test_application_seals_before_evaluation_and_preserves_ownership(tmp_path, monkeypatch):
    from tests.test_question_prediction import Maps, map_fixture, registry, reference
    import httpx
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **k: pytest.fail("Network must not be called"))
    a, b = map_fixture("a"), map_fixture("b")
    for m in (a, b):
        m["source"]["text"] += m["article_id"]
        m["source"]["sha256"] = digest(m["source"]["text"])
    metadata = {a["article_id"]: {**registry(a, "2010-01-01"), "family": "family-a"}, b["article_id"]: {**registry(b, "2015-01-01"), "family": "family-b"}}
    before = deepcopy([a, b])
    maps, store = Maps(a, b), FilePredictionStore(tmp_path)
    scenario = SealQualitativeQuestionExperiment(maps, store)
    result = scenario.execute([reference(a), reference(b)], metadata, {}, [], asdict(question()), policy_raw(), "owner")
    assert not result["readiness"]["target_reading_allowed"]
    for fold in result["retrospective_folds"]:
        sealed = store.read_seal(fold["forecast_run_id"])
        assert fold["plan"]["family"] not in sealed["binding"]["training_families"]
        assert (store.path(fold["forecast_run_id"]) / "evaluations" / (fold["evaluation_id"] + ".json")).exists()
    assert scenario.execute([reference(a), reference(b)], metadata, {}, [], asdict(question()), policy_raw(), "owner") == result
    assert [a, b] == before
    with pytest.raises(ArticleMapAccessDenied):
        scenario.execute([reference(a), reference(b)], metadata, {}, [], asdict(question()), policy_raw(), "intruder")
