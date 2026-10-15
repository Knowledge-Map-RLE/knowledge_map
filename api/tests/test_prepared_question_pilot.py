"""Ручной корпус, происхождение, запрет утечки и порог готовности на реальных ограничениях."""
import copy
from dataclasses import asdict, replace
import pytest

from domain.article_maps import digest, ArticleMapError, ArticleMapAccessDenied
from domain.research_semantics import project_map, context_value as cv
from domain.question_prediction import fit_question_forecast
from domain.question_readiness import assess_readiness
from application.prepare_research_bundle import prepare_bundle
from infrastructure.prepared_research_maps import PreparedResearchMaps
from tests.test_question_prediction import historical, question


def prepared(purpose="training"):
    text = "# Research\n\nPlasma IL-6 😀 was measured at baseline.\n\n## References\nCitation only.\n"
    metadata = {"pmcid": "PMC1", "source_sha256": digest(text), "title": "Research", "available_on": "2010-01-01", "metadata_url": "https://example.org"}
    seed = {"pmcid": "PMC1", "author": "Codex", "expert_validated": False, "family": "verified-family",
        "selection_disclosure": "Synthetic engineering fixture", "claims": [{"text_en": "IL-6 was measured in plasma at baseline.",
        "text_ru": "IL-6 измерен в плазме исходно.", "quote": "Plasma IL-6 😀 was measured at baseline.",
        "predicate": "measured in", "roles": {"subject": "IL-6", "specimen": "plasma"}, "presentation": "method",
        "context": {"time": cv("baseline"), "specimen": cv("plasma")}}]}
    return text, metadata, seed, prepare_bundle(text, metadata, seed, purpose)


def test_preparation_keeps_exact_unicode_evidence_and_separate_russian_labels(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **k: pytest.fail("No network or model calls allowed"))
    text, metadata, seed, bundle = prepared()
    c = project_map(bundle["map"], bundle["registry"], bundle["annotation"])[0]
    span = c.evidence.spans[0]
    assert text[span["start"]:span["end"]] == seed["claims"][0]["quote"]
    assert c.evidence.presentation == "method" and c.context["specimen"] == cv("plasma")
    assert bundle["origin"]["full_article_formalization"] is False
    assert bundle["map"]["translations"]["ru"]["knowledge_labels"]["K1"] == seed["claims"][0]["text_ru"]
    assert prepare_bundle(text, metadata, seed, "training") == bundle
    assert prepared("evaluation")[3]["map"]["run_id"] != bundle["map"]["run_id"]


@pytest.mark.parametrize("changed", ["hash", "quote", "references", "context"])
def test_prepared_source_integrity(changed):
    text, metadata, seed, _ = prepared()
    if changed == "hash": metadata["source_sha256"] = "wrong"
    if changed == "quote": seed["claims"][0]["quote"] = "fabricated evidence"
    if changed == "references": seed["claims"][0]["quote"] = "Citation only."
    if changed == "context": seed["claims"][0]["context"]["specimen"] = {"status": "known", "value": "Plasma"}
    with pytest.raises(ArticleMapError): prepare_bundle(text, metadata, seed, "training")


def test_source_adapter_cannot_expand_corpus_or_admit_target():
    bundle = prepared()[3]; m = bundle["map"]
    maps = PreparedResearchMaps([bundle], "owner", "training")
    assert maps.get(m["article_id"], "text_reified", "owner", m["run_id"]) == m
    with pytest.raises(ArticleMapAccessDenied): maps.authorize(m["article_id"], "other")
    with pytest.raises(ArticleMapError, match="Unlisted"): maps.get("unlisted-target", "text_reified", "owner", "run")
    with pytest.raises(ArticleMapError, match="Target"): PreparedResearchMaps([prepared("evaluation")[3]], "owner", "training")


def test_readiness_requires_actual_learning_and_question_relevant_independence():
    claims, episodes = historical()
    q = question()
    forecast = fit_question_forecast(claims, episodes, {}, q)
    scoped = [replace(c, context={**c.context, "time": cv("followup")}) for c in claims.values()]
    ready = assess_readiness(forecast, scoped, 5)
    assert ready["target_reading_allowed"] and ready["independent_families"] == ["independent0", "independent1"]
    assert not assess_readiness(forecast, scoped, 4)["target_reading_allowed"]
    empty = fit_question_forecast(claims, [], {}, q)
    assert "historical_learning_present" in assess_readiness(empty, scoped, 5)["failed_checks"]
    same = [replace(c, evidence=replace(c.evidence, family="single-family")) for c in scoped]
    assert not assess_readiness(forecast, same, 5)["target_reading_allowed"]


def test_specimen_and_population_remain_hard_question_constraints():
    claims, episodes = historical()
    q = replace(question(), context={**question().context, "specimen": cv("plasma")})
    claims = {k: replace(c, context={**c.context, "specimen": cv("serum")}) for k, c in claims.items()}
    forecast = fit_question_forecast(claims, episodes, {}, q)
    assert not forecast["modes"]["semantic"]
    assert not assess_readiness(forecast, claims.values(), 5)["target_reading_allowed"]


def test_empirical_null_counts_as_tested_family_without_becoming_negation():
    from domain.question_prediction import learn_temporal_rules
    from tests.test_question_prediction import claim
    claims, episodes = historical()
    for episode in episodes:
        key = tuple(episode["conclusion"])
        claims[key] = replace(claims[key], modality="statistically detected")
    a = claim("null-prior", cohort="null")
    h = replace(claim("null-result", "associated with", "2018-01-01", "null-family", cohort="null", time="observed"),
                modality="not statistically detected")
    claims[a.evidence.article_id, a.claim_id] = a
    claims[h.evidence.article_id, h.claim_id] = h
    episodes.append({"id": "null-test", "premises": [[a.evidence.article_id, a.claim_id]],
                     "conclusion": [h.evidence.article_id, h.claim_id]})
    rules, _ = learn_temporal_rules(claims, episodes, {}, "2022-12-31")
    assert rules[0]["support"] == 2 and rules[0]["tested_families"] == 3
    assert rules[0]["template"]["conclusion"]["modality"] == "statistically detected"
    assert not h.negated and h.modality == "not statistically detected"


def test_cli_refuses_to_open_target_seed_before_readiness(tmp_path, monkeypatch):
    from argparse import Namespace
    from tools import run_prepared_question_pilot as cli
    monkeypatch.setattr(cli, "prohibit_generation", lambda: None)
    monkeypatch.setattr(cli.ctypes.windll.shell32, "IsUserAnAdmin", lambda: True)
    args = Namespace(command="prepare", purpose="evaluation", forecasts=tmp_path, run_id="0" * 64,
        source=tmp_path / "missing-target", seed=tmp_path / "missing-seed", destination=tmp_path / "bundle.json")
    with pytest.raises(ArticleMapError, match="readiness failed"): cli.run(args)
    assert not args.destination.exists()


def test_adapter_recovers_only_explicit_duration_units_without_changing_raw_map():
    from domain.comparison_normalization import normalize_attribute
    raw = {"name": "mean age years", "value": 73.7, "unit": None}
    before = copy.deepcopy(raw)
    assert normalize_attribute(raw) == {"name": "mean age years", "value": "884.4", "unit": "month"}
    assert raw == before
    assert normalize_attribute({"name": "sample size", "value": 3140, "unit": None})["unit"] is None
    assert normalize_attribute({"name": "publication years", "value": 2013, "unit": None})["unit"] is None
    assert normalize_attribute({"name": "mean age years", "value": 73.7, "unit": "day"})["unit"] == "day"


def test_public_html_preserves_scientific_tables_and_places_bibliography_last():
    from infrastructure.public_article_text import convert_pmc_html
    markup = '<nav>Ignore navigation</nav><article><h1>Paper 😀</h1><section class="body main-article-body">' \
        '<section><h2>Methods</h2><p>Plasma &amp; cognition.</p></section><section><h2>Results</h2>' \
        '<p>Observed effect.</p><table><tr><th>IL-6</th><th>p</th></tr><tr><td>0.5</td><td>.02</td></tr></table></section>' \
        '<section class="ref-list"><h2>References</h2><ul><li><span class="label">1.</span><cite>Author. Title.</cite><a>PubMed</a></li></ul></section>' \
        '<section><h2>Associated Data</h2><p>Supplement caption.</p></section></section></article>'
    md = convert_pmc_html(markup)
    assert 'IL-6 | p\n0.5 | .02' in md and 'Plasma & cognition.' in md
    assert md.index('Supplement caption.') < md.index('## References')
    assert 'PubMed' not in md and 'Ignore navigation' not in md and 'Paper 😀' in md
    with pytest.raises(ArticleMapError, match="complete public"): convert_pmc_html('<h1>Checking your browser</h1>')


def test_forecast_binds_manual_source_origin_and_display_without_model_calls(tmp_path):
    from application.question_prediction import SealQuestionForecast, AuditResearchSemantics
    from infrastructure.development_prediction_store import FilePredictionStore
    from infrastructure.research_artifacts import FileResearchArtifacts
    from infrastructure.question_prediction_report import build_report
    bundle = prepared()[3]
    maps = PreparedResearchMaps([bundle], "owner", "training")
    m = bundle["map"]
    refs = [{k: m[k] for k in ("article_id", "pipeline_id", "run_id")}]
    metadata = {m["article_id"]: bundle["registry"]}
    annotations = {m["article_id"]: bundle["annotation"]}
    forecast = SealQuestionForecast(maps, FilePredictionStore(tmp_path)).execute(
        refs, metadata, annotations, [], asdict(question()), "owner")
    origin = forecast["binding"]["source_origin"][0]
    assert origin["research_origin"] == bundle["origin"]
    assert origin["generation"]["external_llm_calls"] == 0
    audit = AuditResearchSemantics(maps, FileResearchArtifacts(tmp_path / "audits")).execute(
        refs, metadata, annotations, {"pairs": []}, "owner")
    markdown, markup = build_report(audit, forecast)
    assert "полная формализация статей" in markdown
    assert "origin-disclosure" in markup and "full article formalization" in markup
    assert forecast["readiness"]["target_reading_allowed"] is False


def test_primary_review_rejects_a_different_run_and_changed_evidence(tmp_path):
    from application.question_prediction import SealQuestionForecast, AuditResearchSemantics
    from infrastructure.development_prediction_store import FilePredictionStore
    from infrastructure.research_artifacts import FileResearchArtifacts
    from infrastructure.primary_question_report import save_primary_review
    bundle = prepared()[3]; m = bundle["map"]
    maps = PreparedResearchMaps([bundle], "owner", "training")
    refs = [{k: m[k] for k in ("article_id", "pipeline_id", "run_id")}]
    metadata = {m["article_id"]: bundle["registry"]}
    annotations = {m["article_id"]: bundle["annotation"]}
    forecast = SealQuestionForecast(maps, FilePredictionStore(tmp_path / "seals")).execute(
        refs, metadata, annotations, [], asdict(question()), "owner")
    audit = AuditResearchSemantics(maps, FileResearchArtifacts(tmp_path / "audits")).execute(
        refs, metadata, annotations, {"pairs": []}, "owner")
    span = bundle["annotation"]["claims"][0]["spans"][0]
    screening = {"independent_study_families": 1, "eligible_full_sources": 0, "rows": [{
        "pmcid": "PMC1", "source_sha256": m["source"]["sha256"], "specimen": "plasma",
        "age": "not reported", "reasons": ["age_unknown"], "caveats": [],
        "evidence": [{"start": span["start"], "end": span["end"], "quote": span["text"]}]}]}
    save_primary_review(tmp_path / "review", screening, [bundle], audit, forecast)
    changed = copy.deepcopy(bundle); changed["map"]["run_id"] = "another"
    with pytest.raises(ArticleMapError, match="runs differ"):
        save_primary_review(tmp_path / "invalid", screening, [changed], audit, forecast)
    changed = copy.deepcopy(screening); changed["rows"][0]["evidence"][0]["quote"] = "invented"
    with pytest.raises(ArticleMapError, match="evidence differs"):
        save_primary_review(tmp_path / "invalid", changed, [bundle], audit, forecast)
    assert not (tmp_path / "invalid").exists()
