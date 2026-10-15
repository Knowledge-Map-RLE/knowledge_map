"""Проверка разметки не может незаметно расширять корпус или подменять происхождение."""
import copy

import pytest

from application.primary_qualification import validate_primary_qualification
from domain.article_maps import ArticleMapError, digest


def example():
    text = "Rate 14.2 per 1000 person-years.\n\n## References\nCitation."
    fragment = text[:text.index("\n\n")]
    proof = {"id": "p", "source_id": "s", "source_sha256": digest(text), "offset_encoding": "unicode_codepoints",
             "start": 0, "end": len(fragment), "text": fragment, "text_sha256": digest(fragment)}
    a = {"author": "Codex", "expert_validated": False, "model_calls": 0, "predictions": [],
         "sources": {"s": {"pmcid": "PMC1", "cohort_id": "c", "evidence_ids": ["p"]}}, "evidence": {"p": proof},
         "measurements": [{"id": "m", "source_id": "s", "context": {"cohort_id": "c"}, "evidence_ids": ["p"],
                           "value": "14.2", "unit": "per_1000_person_years", "confidence_interval": None}], "diagnostics": []}
    records = [{"entry": {"id": "s"}, "status": "training_fulltext_saved", "source_sha256": digest(text), "metadata": {"pmcid": "PMC1"}}]
    return a, records, {"s": text}


def test_validation_is_read_only_and_does_not_claim_scientific_success(monkeypatch):
    import socket
    monkeypatch.setattr(socket, "socket", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Network forbidden")))
    args = example()
    old = copy.deepcopy(args)
    result = validate_primary_qualification(*args)
    assert result["verified_fragments"] == 1 and result["new_predictions"] == 0 and not result["scientific_success"]
    assert args == old


def test_unknown_measurement_evidence_is_rejected():
    a, records, texts = example()
    a["measurements"][0]["evidence_ids"] = ["unknown"]
    with pytest.raises(ArticleMapError, match="evidence"):
        validate_primary_qualification(a, records, texts)


def test_extra_source_or_changed_revision_is_rejected():
    a, records, texts = example()
    with pytest.raises(ArticleMapError, match="corpus"):
        validate_primary_qualification(a, records, {**texts, "target": "unapproved"})
    with pytest.raises(ArticleMapError, match="revision"):
        validate_primary_qualification(a, records, {"s": texts["s"] + "x"})


def test_reference_list_cannot_support_primary_result():
    a, records, texts = example()
    p = a["evidence"]["p"]
    start = texts["s"].index("Citation")
    p.update(start=start, end=len(texts["s"]), text=texts["s"][start:], text_sha256=digest(texts["s"][start:]))
    with pytest.raises(ArticleMapError, match="Bibliography"):
        validate_primary_qualification(a, records, texts)


def test_prediction_and_cohort_substitution_are_rejected():
    a, records, texts = example()
    a["predictions"] = [{"claim": "not sealed"}]
    with pytest.raises(ArticleMapError, match="predictions"):
        validate_primary_qualification(a, records, texts)
    a["predictions"] = []
    a["measurements"][0]["context"]["cohort_id"] = "other"
    with pytest.raises(ArticleMapError, match="cohort"):
        validate_primary_qualification(a, records, texts)
