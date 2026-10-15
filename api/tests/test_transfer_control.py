"""Непубликация коэффициента не становится успехом или опровержением прогноза."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from application.transfer_control import AuditTransferControl
from domain.article_maps import ArticleMapError, fingerprint
from domain.transfer_control import audit_control
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.transfer_control import FileControlInputs

ROOT = Path(__file__).resolve().parents[2] / "eval/free_prediction/frozen-transfer-control-screening-v1"


def inputs():
    return FileControlInputs(ROOT / "prepared/manifest.json").read_inputs()


def observation(data, direction="higher", finding="detected"):
    # Синтетическое контрольное утверждение служит только проверкой оценщика.
    c = deepcopy(next(c for c in data["forecast"]["generation"]["training_claims"] if c["id"] == "M-age"))
    c.update(id="synthetic-control", source_id=data["control"]["source_id"], family_id="ROS", provenance=["model"])
    c["context"]["critical"].update(measure="hazard_ratio", unit="dimensionless")
    c["result"].update(direction=direction, statistical_finding=finding)
    c["semantic_frame"]["statements"][0]["value"] = direction
    c["semantic_frame"]["statements"][1]["value"] = finding
    data["control"]["observations"] = [c]
    return c


def age_row(audit, mode="semantic"):
    return next(r for r in audit["modes"][mode]["rows"] if r["signature"]["factor"] == "age" and r["signature"]["phenotype"] == "any_domain_mci")


def test_real_candidate_has_no_reported_forecast_coefficients():
    d = inputs()
    before = fingerprint(d["forecast"])
    result = audit_control(d["forecast"], d["control"])
    assert fingerprint(d["forecast"]) == before
    assert result["modes"]["semantic"]["counts"] == {"not_addressed": 2}
    assert result["independent_pattern_matches"] == 0
    assert result["decisive_semantic_candidates"] == 0
    assert not result["empirical_test_performed"] and result["source_audit_performed"]
    assert result["graph_gain"] is None and not result["scientific_success"]
    for mode in result["modes"].values():
        assert mode["direction_accuracy"] is None
        assert mode["compatible_reported_candidates"] == 0


def test_compatible_detected_direction_counts_only_as_pattern_match():
    d = inputs(); observation(d)
    result = audit_control(d["forecast"], d["control"])
    assert result["independent_pattern_matches"] == 1 and result["empirical_test_performed"]
    assert age_row(result)["status"] == "qualitative_pattern_match"
    assert not age_row(result)["scientific_fact_equivalence"]
    assert result["modes"]["known_union"]["counts"]["qualitative_pattern_match"] == 1
    assert result["modes"]["frequency"]["counts"]["qualitative_pattern_match"] == 1
    assert not result["graph_advantage_demonstrated"] and not result["scientific_success"]


def test_detected_opposite_direction_is_inconsistent_transfer_not_logical_refutation():
    d = inputs(); observation(d, "lower")
    result = audit_control(d["forecast"], d["control"])
    assert age_row(result)["status"] == "inconsistent_transfer"
    assert result["independent_pattern_matches"] == 0


def test_nondetection_retains_point_direction_without_confirming_hypothesis():
    d = inputs(); observation(d, finding="not_detected")
    row = age_row(audit_control(d["forecast"], d["control"]))
    assert row["status"] == "uncertain"
    assert row["comparisons"][0]["direction_agreement"] is True


@pytest.mark.parametrize("field", ["general_older_adults", "baseline_free_of_mci_and_dementia", "prospective_incidence"])
@pytest.mark.parametrize("value", [False, None])
def test_unknown_or_incompatible_hard_context_blocks_positive(field, value):
    d = inputs(); observation(d); d["control"]["hard_context"][field] = value
    row = age_row(audit_control(d["forecast"], d["control"]))
    assert row["status"] == "unassessable" and field in row["blockers"]


@pytest.mark.parametrize("key,value,blocker", [
    ("baseline_status", "baseline_mci", "observation_baseline_status"),
    ("baseline_status", None, "observation_baseline_status"),
    ("population", "clinical_mci", "observation_population"),
    ("phenotype", "memory_mci_inclusive", "observation_phenotype"),
    ("measure", "incidence_rate", "hazard_measurement_metadata"),
    ("unit", "per1000personyears", "hazard_measurement_metadata")])
def test_article_level_eligibility_cannot_override_incompatible_observation(key, value, blocker):
    d = inputs(); c = observation(d); c["context"]["critical"][key] = value
    row = age_row(audit_control(d["forecast"], d["control"]))
    assert row["status"] == "unassessable"
    assert blocker in row["comparisons"][0]["blockers"]


def test_incomplete_fulltext_review_cannot_confirm_absence_or_direction():
    d = inputs(); d["control"]["full_source_review"] = False
    assert age_row(audit_control(d["forecast"], d["control"]))["status"] == "unassessable"
    observation(d)
    assert age_row(audit_control(d["forecast"], d["control"]))["status"] == "unassessable"


@pytest.mark.parametrize("field,value", [("estimand", "odds_association"), ("phenotype", "memory_inclusive_mci"), ("contrast", "younger_vs_older")])
def test_similar_terms_do_not_hide_incompatible_signature(field, value):
    d = inputs(); c = observation(d); c[field] = value
    if field == "phenotype":
        for s in c["semantic_frame"]["statements"]: s["roles"]["outcome"] = value
    row = age_row(audit_control(d["forecast"], d["control"]))
    assert row["status"] == "not_addressed"
    assert field in row["incompatible_observations"][0]["different_fields"]


def test_ambiguous_union_is_not_cherry_picked_after_control():
    d = inputs(); observation(d)
    modes = d["forecast"]["generation"]["forecast"]["predictions"]
    p = deepcopy(next(p for p in modes["known_union"] if p["signature"]["factor"] == "age" and p["signature"]["phenotype"] == "any_domain_mci"))
    p.update(id="synthetic-opposite", expected_direction="lower"); modes["known_union"].append(p)
    assert age_row(audit_control(d["forecast"], d["control"]), "known_union")["status"] == "ambiguous_baseline"


def test_training_cohort_and_pre_cutoff_target_rejected():
    d = inputs(); d["control"]["cohort_ids"] = ["WHICAP"]
    with pytest.raises(ArticleMapError, match="Training cohort"): audit_control(d["forecast"], d["control"])
    d = inputs(); d["control"]["publication_date"] = "2023-11-14"
    with pytest.raises(ArticleMapError, match="cutoff"): audit_control(d["forecast"], d["control"])


@pytest.mark.parametrize("value", ["2024", "2024-11", "2024-02-31", "20240125"])
def test_partial_or_invalid_dates_cannot_establish_order(value):
    d = inputs(); d["control"]["publication_date"] = value
    with pytest.raises(ArticleMapError, match="ISO"): audit_control(d["forecast"], d["control"])


def test_evaluation_is_idempotent_and_keeps_frozen_store_bytes(tmp_path):
    manifest = json.loads((ROOT / "prepared/manifest.json").read_text(encoding="utf8"))
    forecast = Path(manifest["forecast_store"]) / manifest["forecast_run_id"] / "predictions.json"
    before = forecast.read_bytes()
    usecase = AuditTransferControl(FileControlInputs(ROOT / "prepared/manifest.json"), FilePredictionStore(tmp_path))
    first = usecase.execute({"test": "v1"})
    assert first == usecase.execute({"test": "v1"})
    assert first["run_id"] != usecase.execute({"test": "v2"})["run_id"]
    assert forecast.read_bytes() == before


def test_no_model_client_or_generation_import_in_new_modules():
    api = ROOT.parents[2] / "api"
    for name in ["domain/transfer_control.py", "application/transfer_control.py", "infrastructure/transfer_control.py", "tools/audit_transfer_control.py"]:
        text = (api / name).read_text(encoding="utf8")
        assert not any(token in text for token in ["AIClient", "OpenAI(", "generate_transfer(", "forecast_fold("])
