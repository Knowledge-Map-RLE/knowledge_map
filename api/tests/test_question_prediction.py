"""Контроль действительного вывода, времени, независимости и изоляции цели."""
from dataclasses import replace, asdict
import copy

import pytest

from domain.article_maps import ArticleMapError, ArticleMapAccessDenied, fingerprint, digest
from domain.research_semantics import (SemanticClaim, Evidence, context_value as cv, compare_claims,
                                       project_map, valid_date, source_span)
from domain.question_prediction import (ForecastQuestion, make_template, learn_temporal_rules,
                                        fit_question_forecast, evaluate_question_forecast, eligible)
from application.question_prediction import SealQuestionForecast, EvaluateQuestionForecast
from infrastructure.development_prediction_store import FilePredictionStore


def claim(article, predicate="exposure", date="2010-01-01", family=None, negated=False, cohort="a", time="baseline"):
    evidence = Evidence(article, "run-" + article, digest(article), date, family, "own_result",
                        ({"start": 0, "end": 1, "text": "x", "offset_encoding": "unicode_code_points"},))
    return SemanticClaim(article + predicate, "K1", predicate,
        {"exposure": "interleukin 6", "outcome": "cognitive decline"}, negated, None, None,
        {"species": cv("human"), "population": cv("older adults without dementia"),
         "study": cv(cohort), "time": cv(time)}, (), None, "single", "Source statement", evidence)


def question():
    return ForecastQuestion.parse({"question_id": "il6", "text_en": "Does baseline IL-6 predict later cognitive decline?",
        "text_ru": "Связан ли исходный IL-6 с последующим когнитивным снижением?", "predicate": "associated with",
        "roles": {"exposure": "IL-6", "outcome": "cognitive decline"},
        "context": {"species": cv("human"), "population": cv("older adults without dementia"), "time": cv("followup")},
        "cutoff": "2022-12-31", "horizon_end": "2025-12-31", "limit": 20})


def historical():
    claims, episodes = {}, []
    for i in range(2):
        a = claim("prior" + str(i), cohort="cohort" + str(i))
        h = claim("result" + str(i), "associated with", "2015-01-01", "independent" + str(i), cohort="cohort" + str(i), time="observed")
        for c in (a, h):
            claims[c.evidence.article_id, c.claim_id] = c
        episodes.append({"id": "episode" + str(i), "premises": [[a.evidence.article_id, a.claim_id]],
                         "conclusion": [h.evidence.article_id, h.claim_id], "transition_id": None})
    new = claim("new", cohort="cohort-new")
    claims["new", new.claim_id] = new
    return claims, episodes


def test_actual_temporal_learning_and_heldout_result():
    claims, episodes = historical()
    q = question()
    result = fit_question_forecast(claims, episodes, {}, q)
    assert len(result["rules"]["semantic"]) == 1
    assert result["diagnostics"]["dependency"]["accepted_rules"] == 0
    predictions = result["modes"]["semantic"]
    assert predictions and all(p["support"] == 2 for p in predictions)
    assert all(p["status"] == "forecast_hypothesis" and p["proposition"]["context"]["time"] == cv("followup") for p in predictions)
    assert all("study" in p["abstracted_context_fields"] for p in predictions)
    target = claim("heldout", "associated with", "2024-01-01", "heldout-family", cohort="heldout", time="followup")
    evaluation = evaluate_question_forecast({**result, "run_id": "sealed"}, [target])
    assert evaluation["modes"]["semantic"]["confirmed"] == len(predictions)
    assert evaluation["model_calls"] == 0
    assert target.context["study"] == cv("heldout")


def test_general_question_without_future_observation_date_can_forecast():
    claims, episodes = historical()
    q = replace(question(), context={k: v for k, v in question().context.items() if k != "time"})
    result = fit_question_forecast(claims, episodes, {}, q)
    assert result["modes"]["semantic"]
    assert all(p["unbound_context_fields"] == ["time"] and "time" not in p["proposition"]["context"] for p in result["modes"]["semantic"])
    assert result["modes"]["frequency"][0]["support"] == 2
    assert len(result["modes"]["frequency"][0]["evidence"]) == 2


def test_repeated_publications_in_one_cohort_do_not_count_twice():
    claims, episodes = historical()
    claims = {k: replace(c, evidence=replace(c.evidence, family="same-cohort")) for k, c in claims.items()}
    rules, diagnostics = learn_temporal_rules(claims, episodes, {}, "2022-12-31")
    assert rules == []
    assert diagnostics["rejected"][0]["reason"] == "insufficient_independent_families"


def test_explicit_negative_trial_and_absence_are_distinct():
    claims, episodes = historical()
    a = claim("negative-prior", cohort="negative")
    h = claim("negative-result", "associated with", "2018-01-01", "negative-family", True, "negative", "observed")
    for c in (a, h): claims[c.evidence.article_id, c.claim_id] = c
    episodes.append({"id": "negative", "premises": [[a.evidence.article_id, a.claim_id]], "conclusion": [h.evidence.article_id, h.claim_id]})
    rule = learn_temporal_rules(claims, episodes, {}, "2022-12-31")[0][0]
    assert rule["support"] == 2 and rule["tested_families"] == 3
    assert rule["ranking_score"] == 3 / 5
    result = fit_question_forecast(claims, episodes, {}, question())
    unrelated = replace(claim("heldout", date="2024-01-01"), predicate="unrelated")
    evaluated = evaluate_question_forecast({**result, "run_id": "sealed"}, [unrelated])
    assert evaluated["modes"]["semantic"]["contradicted"] == 0
    assert evaluated["modes"]["semantic"]["unresolved"] > 0


@pytest.mark.parametrize("date", ["2009-01-01", "2010-01-01", "2023-01-01"])
def test_future_or_same_publication_cannot_train(date):
    claims, episodes = historical()
    key = tuple(episodes[0]["conclusion"])
    claims[key] = replace(claims[key], evidence=replace(claims[key].evidence, available_on=date))
    with pytest.raises(ArticleMapError, match="future|same-publication"):
        learn_temporal_rules(claims, episodes, {}, "2022-12-31")


def test_unbound_outcome_numbers_are_not_invented():
    claims, episodes = historical()
    body, head = [claims[tuple(episodes[0]["premises"][0])]], claims[tuple(episodes[0]["conclusion"])]
    head = replace(head, measurements=({"name": "risk", "value": "1.7", "unit": "ratio"},))
    assert make_template(body, head) is None


def test_independent_future_study_identity_is_a_scope_not_an_invented_fact():
    claims, episodes = historical()
    for episode in episodes:
        key = tuple(episode["conclusion"])
        head = claims[key]
        claims[key] = replace(head, context={**head.context, "study": cv("new-" + head.evidence.article_id),
            "cohort": cv("cohort-" + head.evidence.article_id), "sample": cv("sample-" + head.evidence.article_id)})
    result = fit_question_forecast(claims, episodes, {}, question())
    assert result["learning_status"] == "ready"
    assert len(result["rules"]["semantic"]) == 1
    prediction = result["modes"]["semantic"][0]
    assert {"study", "cohort", "sample"} <= set(prediction["unbound_context_fields"])
    assert not {"study", "cohort", "sample"}.intersection(prediction["proposition"]["context"])


def test_native_coverage_diagnoses_fields_and_does_not_modify_claim():
    from domain.research_diagnostics import coverage_detail, eligibility_summary
    native = claim("native")
    expected = replace(native, predicate="associated with", context={**native.context, "time": cv("followup")})
    before = asdict(native)
    detail = coverage_detail(expected, [native])
    assert not detail["represented"]
    assert {"predicate", "context:time"} <= {d["field"] for d in detail["field_differences"]}
    assert detail["source_spans_overlap"]
    assert asdict(native) == before
    unknown = replace(native, context={**native.context, "time": cv(None, "not_reported")})
    summary = eligibility_summary([native, unknown])
    assert summary["eligible"] == 1 and summary["reason_counts"] == {"unknown_context:time": 1}


@pytest.mark.parametrize("changed", ["modality", "quantifier", "unit", "population", "time", "action"])
def test_qualifiers_cannot_be_erased_for_equivalence(changed):
    left = claim("left")
    right = replace(left, evidence=replace(left.evidence, article_id="right"))
    if changed == "modality": right = replace(right, modality="may")
    if changed == "quantifier": right = replace(right, quantifier="some")
    if changed in {"population", "time"}: right = replace(right, context={**right.context, changed: cv("different")})
    if changed == "action": right = replace(right, action_status="planned")
    if changed == "unit":
        left = replace(left, measurements=({"name": "rate", "value": "22.5", "unit": "percent"},))
        right = replace(right, measurements=({"name": "rate", "value": "22.5", "unit": "per1000personyear"},))
    assert compare_claims(left, right)["relation"] != "equivalent"


def test_unknown_context_is_neither_not_applicable_nor_equivalent():
    a = claim("a")
    b = replace(a, context={**a.context, "time": cv(None, "not_reported")})
    assert compare_claims(a, b)["unknown"] == ["time"]
    assert not eligible(b)
    assert compare_claims(a, replace(a, negated=True))["relation"] == "contradiction"
    assert compare_claims(a, replace(b, negated=True))["relation"] != "contradiction"


def test_joint_premises_and_alternatives_are_distinct():
    claims, episodes = historical()
    maps = {}
    for e in episodes:
        a = claims[tuple(e["premises"][0])]; h = claims[tuple(e["conclusion"])]
        local = replace(a, evidence=h.evidence, knowledge_id="K0", claim_id="local-" + a.claim_id)
        claims[h.evidence.article_id, local.claim_id] = local
        maps[h.evidence.article_id] = {"graph": {"nodes": [{"id": "B0", "knowledge_id": "K0"}, {"id": "B1", "knowledge_id": "K1"}],
                                     "transitions": [{"id": "T1", "sources": ["B0"], "target": "B1"}]}}
        e["transition_id"] = "T1"
    assert len(learn_temporal_rules(claims, episodes, maps, "2022-12-31", True)[0]) == 1
    # Дополнительная совместная предпосылка должна присутствовать, а альтернативная не дописывается молча.
    for m in maps.values():
        m["graph"]["nodes"].append({"id": "B2", "knowledge_id": "K2"})
        m["graph"]["transitions"][0]["sources"].append("B2")
    # Отсутствие утверждения обязательного входа не разрешает пропустить этот вход.
    assert learn_temporal_rules(claims, episodes, maps, "2022-12-31", True)[0] == []


def map_fixture(article="source"):
    from tests.test_schema6_prediction import graph
    result = graph(article, ["IL-6", "cognitive decline", "inflammation"])
    result["pipeline_id"] = "text_reified"
    result["source"] = {"sha256": digest("x😀 scientific evidence"), "text": "x😀 scientific evidence", "content_end": 22,
                        "units": [{"id": "U1", "start": 0, "end": 22}]}
    for i, t in enumerate(result["graph"]["transitions"]): t["id"] = "T" + str(i)
    return result


def registry(result, date="2020-01-01"):
    return {"article_id": result["article_id"], "run_id": result["run_id"], "source_sha256": result["source"]["sha256"],
            "available_on": date, "family": None, "presentation": "unknown"}


class Maps:
    def __init__(self, *maps): self.data = {m["article_id"]: m for m in maps}; self.reads = []
    def authorize(self, article, owner):
        if owner != "owner": raise ArticleMapAccessDenied("Owner differs")
    def get(self, article, pipeline, owner, run):
        self.authorize(article, owner); self.reads.append(article)
        return self.data.get(article)


def reference(m):
    return {"article_id": m["article_id"], "pipeline_id": "text_reified", "run_id": m["run_id"]}


def test_source_only_seal_then_separate_evaluation_and_ownership(tmp_path, monkeypatch):
    import httpx
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **k: pytest.fail("AI/network must not be used"))
    a, b = map_fixture(), map_fixture("target")
    b["source"]["text"] += " target"; b["source"]["sha256"] = digest(b["source"]["text"])
    maps = Maps(a, b); store = FilePredictionStore(tmp_path)
    r = SealQuestionForecast(maps, store).execute([reference(a)], {a["article_id"]: registry(a)}, {}, [], asdict(question()), "owner")
    assert maps.reads == ["source"] and r["modes"]["semantic"] == []
    assert SealQuestionForecast(maps, store).execute([reference(a)], {a["article_id"]: registry(a)}, {}, [], asdict(question()), "owner") == r
    with pytest.raises(ArticleMapError, match="unlisted"):
        SealQuestionForecast(maps, store).execute([reference(a)], {a["article_id"]: registry(a), b["article_id"]: registry(b)}, {}, [], asdict(question()), "owner")
    with pytest.raises(ArticleMapError, match="Seal predictions"):
        EvaluateQuestionForecast(maps, store).execute("0" * 64, [reference(b)], {}, {}, "owner")
    with pytest.raises(ArticleMapError, match="leaked"):
        EvaluateQuestionForecast(maps, store).execute(r["run_id"], [reference(a)], {}, {}, "owner")
    with pytest.raises(ArticleMapError, match="another owner"):
        EvaluateQuestionForecast(maps, store).execute(r["run_id"], [reference(b)], {}, {}, "intruder")
    evaluation = EvaluateQuestionForecast(maps, store).execute(r["run_id"], [reference(b)], {b["article_id"]: registry(b, "2024-01-01")}, {}, "owner")
    assert evaluation["relevant_target_claims"] == 0
    assert store.read_seal(r["run_id"]) == r


def test_unicode_hash_cycle_and_annotation_binding():
    m = map_fixture()
    projected = project_map(m, registry(m))
    assert projected and source_span(m["source"], 1, 2, "😀")["text"] == "😀"
    bad = copy.deepcopy(m); bad["source"]["sha256"] = "wrong"
    with pytest.raises(ArticleMapError, match="hash"): project_map(bad, registry(bad))
    bad = copy.deepcopy(m); bad["graph"]["edges"].append({"source": "B3", "target": "B1"})
    with pytest.raises(ArticleMapError, match="DAG"): project_map(bad, registry(bad))
    with pytest.raises(ArticleMapError, match="binding"):
        project_map(m, registry(m), {"run_id": "wrong", "source_sha256": m["source"]["sha256"], "graph_sha256": fingerprint(m["graph"])})
    with pytest.raises(ArticleMapError, match="ISO"): valid_date("2024")


@pytest.mark.parametrize("count", [1, 2, 3])
def test_generated_cases_require_every_premise(count):
    claims, episodes = historical()
    for e in episodes:
        first = claims[tuple(e["premises"][0])]
        for i in range(1, count):
            extra = replace(first, claim_id=first.claim_id + str(i), predicate="premise " + str(i))
            claims[extra.evidence.article_id, extra.claim_id] = extra
            e["premises"].append([extra.evidence.article_id, extra.claim_id])
    new = next(c for c in claims.values() if c.evidence.article_id == "new")
    for i in range(1, count):
        extra = replace(new, claim_id=new.claim_id + str(i), predicate="premise " + str(i))
        claims[extra.evidence.article_id, extra.claim_id] = extra
    result = fit_question_forecast(claims, episodes, {}, question())
    assert result["modes"]["semantic"] and all(len(p["premises"]) == count for p in result["modes"]["semantic"])
    if count > 1:
        last = replace(new, claim_id=new.claim_id + str(count - 1), predicate="premise " + str(count - 1))
        del claims["new", last.claim_id]
        result = fit_question_forecast(claims, episodes, {}, question())
        assert not any(any(c["evidence"]["article_id"] == "new" for c in p["premises"]) for p in result["modes"]["semantic"])


def test_template_canonicalization_preserves_roles_independent_of_local_order():
    a, b = claim("a"), claim("b")
    a = replace(a, roles={"cause": "alpha", "effect": "beta"})
    b = replace(b, roles={"cause": "beta", "effect": "gamma"})
    head = replace(a, predicate="associated with", roles={"cause": "alpha", "effect": "gamma"})
    x = replace(a, roles={"cause": "delta", "effect": "epsilon"})
    y = replace(b, roles={"cause": "epsilon", "effect": "zeta"})
    h = replace(head, roles={"cause": "delta", "effect": "zeta"})
    assert make_template([a, b], head) == make_template([y, x], h)


def test_hidden_cycles_are_preserved_but_not_used_as_resolved_premises():
    m = map_fixture()
    for i, k in enumerate(m["graph"]["knowledge"][:2]):
        role = k["semantic_frame"]["statements"][0]["roles"][0]
        role.update(concept_id=None, knowledge_id="K2" if i == 0 else "K1")
    claims = project_map(m, registry(m))
    assert any(c.unresolved for c in claims)
    assert all(not eligible(c) for c in claims if c.unresolved)


def test_model_clients_cannot_be_constructed_or_called_in_cli_flow(monkeypatch):
    from tools.import_codex_article_map import prohibit_generation
    import httpx
    monkeypatch.setattr(httpx.Client, "request", httpx.Client.request)
    monkeypatch.setattr(httpx.Client, "send", httpx.Client.send)
    monkeypatch.setattr(httpx.AsyncClient, "send", httpx.AsyncClient.send)
    monkeypatch.setattr(httpx.AsyncClient, "post", httpx.AsyncClient.post)
    monkeypatch.setattr(httpx.AsyncClient, "stream", httpx.AsyncClient.stream)
    prohibit_generation()
    with pytest.raises(RuntimeError, match="prohibited"):
        httpx.Client().post("http://127.0.0.1:50059")


def test_current_and_historical_prompts_are_packaged_and_hash_bound():
    from application.text_to_development_map import prompt_binding, registered_prompt_paths
    binding = prompt_binding()
    assert binding["prompt"]["version"] == "4" and binding["dependency_prompt"]["version"] == "16"
    paths = registered_prompt_paths(binding)
    assert all(p.exists() for p in paths)
    from pathlib import Path
    base = Path(__file__).resolve().parents[1] / "application"
    old = {"prompt": {"id": "KM.TEXT_TO_MAP", "version": "3", "sha256": digest((base / "text_to_map.v3.en.md").read_text(encoding="utf-8"))},
           "dependency_prompt": {"id": "KM.TEXT_TO_MAP.DEPENDENCIES", "version": "15", "sha256": digest((base / "text_to_map_dependencies.v15.en.md").read_text(encoding="utf-8"))}}
    assert registered_prompt_paths(old) == (base / "text_to_map.v3.en.md", base / "text_to_map_dependencies.v15.en.md")
    old["prompt"]["sha256"] = "incorrect"
    with pytest.raises(ArticleMapError, match="hashes"): registered_prompt_paths(old)


def test_effect_modifying_stratum_is_not_abstracted_with_sample_identity():
    from domain.question_prediction import hypothesis_scope
    a = replace(claim("a"), context={**claim("a").context, "stratum": cv("apoe ε4 non carriers")})
    b = replace(a, context={**a.context, "stratum": cv("apoe ε4 carriers")})
    p, removed = hypothesis_scope(a.proposition, question())
    assert "stratum" not in removed and p["context"]["stratum"] == cv("apoe ε4 non carriers")
    assert compare_claims(a, b)["relation"] == "context_mismatch"


def report_case(tmp_path):
    from application.question_prediction import AuditResearchSemantics
    from infrastructure.research_artifacts import FileResearchArtifacts
    source = map_fixture()
    maps = Maps(source)
    metadata = {source["article_id"]: registry(source)}
    audit = AuditResearchSemantics(maps, FileResearchArtifacts(tmp_path / "audits")).execute(
        [reference(source)], metadata, {}, {"pairs": []}, "owner")
    raw_question = asdict(question())
    raw_question["text_en"] = '<script>alert("untrusted text")</script>'
    forecast = SealQuestionForecast(maps, FilePredictionStore(tmp_path / "forecast")).execute(
        [reference(source)], metadata, {}, [], raw_question, "owner")
    return copy.deepcopy(audit), forecast


def test_research_report_is_self_contained_and_escapes_source_html(tmp_path):
    from infrastructure.question_prediction_report import save_report
    audit, forecast = report_case(tmp_path)
    save_report(tmp_path, audit, forecast)
    markup = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert 'src="http' not in markup and 'href="http' not in markup
    assert "English" in markup and "Русский" in markup
    assert '<script>alert(' not in markup and '\\u003cscript>' in markup
    assert "Утверждений источников" in markup and "Исходных в диагностике" in markup
    assert 'id="predictions"' in markup
    save_report(tmp_path, audit, forecast)
    changed = copy.deepcopy(audit); changed["native_claim_count"] += 1
    with pytest.raises(ArticleMapError, match="Immutable"): save_report(tmp_path, changed, forecast)


@pytest.mark.parametrize("mismatch", ["analysis", "source", "evaluation"])
def test_report_cannot_mix_different_runs_or_source_versions(tmp_path, mismatch):
    from infrastructure.question_prediction_report import save_report
    audit, forecast = report_case(tmp_path)
    evaluation = None
    if mismatch == "analysis":
        audit["binding"]["analysis_binding"]["predictor_version"] = "incompatible"
        audit["audit_id"] = fingerprint(audit["binding"])
        expected = "analysis versions"
    elif mismatch == "source":
        audit["maps"][0]["graph_sha256"] = "0" * 64
        expected = "Audited source differs"
    else:
        evaluation = {"binding": {"run_id": "0" * 64, "prediction_sha256": "1" * 64}, "evaluation_id": "2" * 64}
        expected = "different forecast"
    with pytest.raises(ArticleMapError, match=expected):
        save_report(tmp_path / "review", audit, forecast, evaluation)
    assert not (tmp_path / "review" / "report.html").exists()


def test_concurrent_seals_with_typed_tuples_are_equivalent_and_immutable(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    claims, episodes = historical()
    artifact = {"run_id": "e" * 64, **fit_question_forecast(claims, episodes, {}, question())}
    store = FilePredictionStore(tmp_path); barrier = Barrier(2)
    def write():
        barrier.wait()
        store.seal(artifact["run_id"], artifact)
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(write) for _ in range(2)]
        for future in futures: future.result()
    store.seal(artifact["run_id"], artifact)
    assert fingerprint(store.read_seal(artifact["run_id"])) == fingerprint(artifact)
    assert not list(tmp_path.glob('.staging-*'))


def test_evaluation_converter_preserves_nested_bibliography_and_marks_image_tables():
    from tools.download_question_evaluation_source import convert_xml
    xml = '<article><front><article-meta><title-group><article-title>Test</article-title></title-group></article-meta></front>' \
          '<body><sec><title>Results</title><p>IL-6 😀</p><table-wrap id="T1"><label>Table 1</label><graphic/></table-wrap></sec>' \
          '<sec><title>References</title><ref-list><ref><label>1</label><mixed-citation>Exact bibliography</mixed-citation></ref></ref-list></sec></body></article>'
    converted = convert_xml(xml)
    assert converted.count("Exact bibliography") == 1 and converted.count("## References") == 1
    assert "no numerical transcription is claimed" in converted and "IL-6 😀" in converted


def test_missing_numerical_dimension_blocks_equivalence_and_learning():
    a = replace(claim("a"), measurements=({"name": "beta", "value": "0.11", "unit": None},))
    assert not eligible(a)
    assert compare_claims(a, a)["relation"] == "partial"
    assert compare_claims(a, a)["unknown"] == ["unit:beta"]
    p = replace(a, measurements=({"name": "p", "value": "0.01", "unit": None},))
    assert eligible(p)


def test_physical_setting_does_not_replace_statistical_conditions():
    m = map_fixture()
    s = m["graph"]["knowledge"][0]["semantic_frame"]["statements"][0]
    s["qualifiers"]["attributes"].append({"name": "setting", "value": "community", "unit": None})
    c = project_map(m, registry(m))[0]
    assert c.context["setting"] == cv("community")
    assert "synthetic conditional example" in c.context["conditions"]["value"]
