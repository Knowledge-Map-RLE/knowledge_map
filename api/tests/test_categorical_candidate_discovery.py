"""Поиск логических фрагментов сохраняет исходный контекст без автоматического лицензирования."""
from hashlib import sha256

from domain.categorical_candidate_discovery import inspect_maps
from tests.test_schema6_prediction import graph


def test_categorical_candidate_is_evidence_queue_not_article_local_premise():
    m = graph("one", ["MCI", "amnestic MCI", "daily impairment"])
    source_text = "The article defines amnestic MCI as a subtype of MCI."
    quote = "amnestic MCI as a subtype of MCI"
    start = source_text.index(quote)
    m.update({"graph_schema_version": 6, "article_title": "Example review"})
    m["source"].update({
        "text": source_text,
        "sha256": sha256(source_text.encode("utf-8")).hexdigest(),
        "content_end": len(source_text),
        "pmcid": "PMC1",
        "units": [{"id": "U1", "start": 0, "end": len(source_text), "text": source_text}],
    })
    knowledge = m["graph"]["knowledge"][0]
    knowledge["knowledge_kind"] = "definition"
    statement = knowledge["semantic_frame"]["statements"][0]
    statement["predicate"] = "subtype_of"
    statement["quantifier"] = "all"
    statement["roles"] = [
        {"role": "subtype", "concept_id": "C1", "knowledge_id": None},
        {"role": "class", "concept_id": "C0", "knowledge_id": None},
    ]
    statement["provenance"]["source_spans"] = [{
        "start": start, "end": start + len(quote), "section_id": "H1",
        "sha256": sha256(quote.encode("utf-8")).hexdigest(),
    }]

    audit = inspect_maps([m])
    assert audit["candidate_statement_count"] == 1
    assert audit["definition_kind_candidate_count"] == 1
    assert audit["unique_candidate_parent_blocks"] == 1
    assert audit["categorical_relation_without_quantifier_count"] == 0
    assert audit["quantifier_without_categorical_relation_count"] == 0
    assert audit["explicit_relation_and_quantifier_count"] == 1
    candidate = audit["candidates"][0]
    assert candidate["licensed_for_inference"] is False
    assert candidate["scope_requires_manual_resolution"] is True
    assert candidate["source_scope"] == "article_context_requires_attribution_review"
    assert candidate["source_evidence"][0]["text"] == quote
    assert candidate["source_evidence"][0]["sha256"] == sha256(quote.encode("utf-8")).hexdigest()
