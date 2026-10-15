"""Реальные неподходящие источники не превращаются в подтверждения прогноза."""
from copy import deepcopy
import json
from pathlib import Path

from domain.article_maps import fingerprint
from domain.transfer_control import audit_control
from infrastructure.transfer_control import FileControlInputs

ROOT = Path(__file__).resolve().parents[2] / "eval/free_prediction/frozen-transfer-continuation-v1"


def inputs(source):
    return FileControlInputs(ROOT / "prepared" / source / "manifest.json").read_inputs()


def test_user_skip_preserves_original_registry_and_forecast():
    decision = json.loads((ROOT / "decision.json").read_text(encoding="utf8"))
    assert decision["skip_doi"] == "10.1176/appi.neuropsych.20230180"
    registry = json.loads((ROOT / "prepared/screening-v2.json").read_text(encoding="utf8"))
    row = next(r for r in registry["records"] if r.get("doi") == decision["skip_doi"])
    assert row["status"] == "skipped_by_user_fulltext_unavailable"
    assert registry["forecast_changed"] is False and registry["training_changed"] is False
    old = json.loads((ROOT.parent / "frozen-transfer-control-screening-v1/prepared/screening.json").read_text(encoding="utf8"))
    assert next(r for r in old["records"] if r.get("doi") == decision["skip_doi"])["status"] == "fulltext_access_unresolved"


def test_real_claims_age_direction_does_not_confirm_general_older_adult_prediction():
    data = inputs("pain2024")
    before = fingerprint(data["forecast"])
    claim = data["control"]["observations"][0]
    assert claim["context"]["analysis"]["estimate"] == "1.10"
    assert claim["result"]["direction"] == "higher"
    result = audit_control(data["forecast"], data["control"])
    assert result["modes"]["semantic"]["counts"] == {"unassessable": 2}
    assert result["modes"]["semantic"]["direction_accuracy"] is None
    assert result["independent_pattern_matches"] == 0 and not result["scientific_success"]
    assert fingerprint(data["forecast"]) == before


def test_biocard_nondetection_and_different_phenotype_are_preserved():
    data = inputs("PMC13392838")
    claim = data["control"]["observations"][0]
    assert claim["phenotype"] == "biocard_clinical_mci"
    assert claim["result"] == {"direction": "lower", "statistical_finding": "not_detected", "causal_status": "observational"}
    row = next(r for r in audit_control(data["forecast"], data["control"])["modes"]["semantic"]["rows"] if r["signature"]["factor"] == "education")
    assert row["status"] == "unassessable"
    assert "phenotype" in row["incompatible_observations"][0]["different_fields"]


def test_even_synthetic_eligibility_cannot_turn_cumulative_risk_into_hazard():
    # Контрфактический контекст служит только проверке запрета подмены estimand.
    data = inputs("PMC13392838")
    control = deepcopy(data["control"])
    control["hard_context"] = {k: True for k in control["hard_context"]}
    control["full_source_review"] = True
    observation = deepcopy(control["observations"][0])
    observation.update(factor="age", contrast="older_vs_younger", phenotype="any_domain_mci", estimand="cumulative_incidence")
    for statement in observation["semantic_frame"]["statements"]:
        statement["roles"] = {"exposure": "age", "outcome": "any_domain_mci"}
    control["observations"] = [observation]
    row = next(r for r in audit_control(data["forecast"], control)["modes"]["semantic"]["rows"] if r["signature"]["factor"] == "age")
    assert row["status"] == "not_addressed"
    assert "estimand" in row["incompatible_observations"][0]["different_fields"]


def test_each_new_source_decision_has_code_point_provenance():
    registry = json.loads((ROOT / "prepared/screening-v2.json").read_text(encoding="utf8"))
    assert len(registry["new_method_audits"]) == registry["new_fulltexts_obtained"] == 9
    from hashlib import sha256
    for source in registry["new_method_audits"]:
        text = Path(source["text_path"]).read_text(encoding="utf8")
        assert sha256(text.encode("utf8")).hexdigest() == source["text_sha256"]
        assert source["anchors"]
        for anchor in source["anchors"]:
            assert anchor["coordinate_unit"] == "Unicode code points"
            assert 0 <= anchor["start"] < anchor["end"] <= len(text)
            assert sha256(text[anchor["start"]:anchor["end"]].encode("utf8")).hexdigest() == anchor["sha256"]


def test_charls_interaction_is_not_direct_education_hazard_and_discrepancy_is_visible():
    registry = json.loads((ROOT / "prepared/screening-v2.json").read_text(encoding="utf8"))
    source = next(s for s in registry["new_method_audits"] if s["family"] == "CHARLS")
    assert {d["code"] for d in source["diagnostics"]} == {"interaction_exposure_not_main_effect", "source_subgroup_narrative_discrepancy"}
    assert source["doi"] not in registry["unresolved_dois"]


def test_indexed_decisions_are_not_presented_as_fulltext_reviews():
    registry = json.loads((ROOT / "prepared/screening-v2.json").read_text(encoding="utf8"))
    rows = {r.get("doi"): r for r in registry["records"] if r.get("doi")}
    assert rows["10.1080/07317115.2025.2537696"]["evidence_level"] == "indexed_abstract"
    assert rows["10.1212/wnl.0000000000213826"]["status"] == "excluded_publication_type_verified"
    assert registry["selected_assessable_control"] is None and registry["ordering_not_fully_resolved"]


def test_early_online_date_not_issue_date_drives_registry_order():
    registry = json.loads((ROOT / "prepared/screening-v2.json").read_text(encoding="utf8"))
    rows = registry["records"]
    index = {r.get("doi"): i for i, r in enumerate(rows) if r.get("doi")}
    assert rows[index["10.1136/jnnp-2024-333837"]]["verified_date"] == "2024-08-13"
    assert index["10.1136/jnnp-2024-333837"] < index["10.1093/gerona/glae275"]
