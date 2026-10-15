"""Подготовленные вручную утверждения → изолированное представление опыта, без AI-клиентов."""
from uuid import NAMESPACE_URL, uuid5
from domain.article_maps import digest, fingerprint, prepare_source, require
from domain.research_semantics import project_map, source_span, validate_context, valid_date

VERSION = "prepared-research-bundle-1"


def prepare_bundle(text, metadata, seed, purpose):
    require(purpose in {"training", "evaluation"}, "Explicit research bundle purpose required")
    require(digest(text) == metadata["source_sha256"], "Prepared research source differs")
    require(seed["pmcid"] == metadata["pmcid"] and seed["author"] == "Codex"
            and seed["expert_validated"] is False, "Research seed binding differs")
    require(isinstance(seed["claims"], list) and bool(seed["claims"]), "Prepared claims required")
    valid_date(metadata["available_on"])
    article = purpose + "-" + seed["pmcid"].lower() + "-" + digest(text)[:16]
    source = prepare_source(article, text)
    concepts, knowledge, annotations = {}, [], []
    for index, raw in enumerate(seed["claims"], 1):
        validate_context(raw["context"])
        require(raw["text_en"] and raw["text_ru"], "Both research display languages required")
        spans = []
        quotes = raw.get("quotes") or [raw["quote"]]
        for quote in quotes:
            require(isinstance(quote, str) and bool(quote) and text.count(quote) == 1,
                    "Research evidence quotation must be unique and exact")
            start = text.index(quote)
            spans.append(source_span(source, start, start + len(quote), quote))
        unit_ids = [u["id"] for u in source["units"] if any(u["start"] < s["end"] and u["end"] > s["start"] for s in spans)]
        require(unit_ids, "Research quotation has no source unit")
        roles = []
        for role, value in raw["roles"].items():
            require(isinstance(value, str) and bool(value), "Explicit research participant required")
            if value not in concepts:
                concepts[value] = {"id": "C" + str(len(concepts) + 1), "display_text": value, "aliases": []}
            roles.append({"role": role, "concept_id": concepts[value]["id"], "knowledge_id": None})
        attributes = list(raw.get("measurements", []))
        names = {"study": "study_id", "cohort": "cohort_id", "sample": "sample_id", "design": "study_design", "time": "event_time"}
        for key, value in raw["context"].items():
            attributes.append({"name": names.get(key, key) if value["status"] == "known" else "context_status_" + key,
                               "value": value["value"] if value["status"] == "known" else value["status"], "unit": None})
        attributes.append({"name": "evidence_presentation", "value": raw.get("presentation", "own_result"), "unit": None})
        kid = "K" + str(index)
        statement = {"statement_id": kid + "S1", "predicate": raw["predicate"], "roles": roles,
            "negated": raw.get("negated", False), "quantifier": raw.get("quantifier"), "modality": raw.get("modality"),
            "temporal_context": None, "conditions": [], "qualifiers": {"attributes": attributes}, "provenance": {"unit_ids": unit_ids}}
        knowledge.append({"knowledge_id": kid, "kind": "state", "knowledge_kind": "observation", "action_status": None,
            "display_text": raw["text_en"], "semantic_frame": {"logic": "single", "statements": [statement]}, "provenance": {"unit_ids": unit_ids}})
        # Точные цитаты принадлежат аналитическому слою; исходные единицы карты также сохранены.
        annotations.append({"claim_id": kid + "S1", "knowledge_id": kid, "predicate": raw["predicate"], "roles": raw["roles"],
            "negated": raw.get("negated", False), "quantifier": raw.get("quantifier"), "modality": raw.get("modality"),
            "context": raw["context"], "measurements": raw.get("measurements", []), "spans": spans,
            "text": raw["text_en"], "presentation": raw.get("presentation", "own_result")})
    graph = {"schema_version": 6, "concepts": list(concepts.values()), "knowledge": knowledge,
             "nodes": [{"id": "B" + str(i), "knowledge_id": k["knowledge_id"]} for i, k in enumerate(knowledge, 1)],
             "edges": [], "transitions": []}
    run_id = str(uuid5(NAMESPACE_URL, fingerprint({"source": source["sha256"], "seed": seed, "builder": VERSION, "purpose": purpose})))
    result = {"article_id": article, "pipeline_id": "text_reified", "run_id": run_id, "source": source, "graph": graph,
        "generation": {"kind": "codex_manual_research_only", "external_llm_calls": 0, "local_llm_calls": 0, "token_usage": None},
        "translations": {"ru": {"knowledge_labels": {k["knowledge_id"]: raw["text_ru"] for k, raw in zip(knowledge, seed["claims"])}}}}
    registry = {"article_id": article, "run_id": run_id, "source_sha256": source["sha256"], "available_on": metadata["available_on"],
        "family": seed["family"], "presentation": "own_result", "title": metadata["title"], "metadata_source": metadata["metadata_url"]}
    annotation = {"run_id": run_id, "source_sha256": source["sha256"], "graph_sha256": fingerprint(graph),
        "author": "Codex", "expert_validated": False, "claims": annotations, "replaces": [a["claim_id"] for a in annotations]}
    origin = {"author": "Codex", "expert_validated": False, "source_metadata": metadata, "purpose": purpose,
        "coverage": "selected_question_relevant_claims", "full_article_formalization": False,
        "scientific_test_kind": "retrospective_engineering_diagnostic", "selection_disclosure": seed["selection_disclosure"],
        "seed_sha256": fingerprint(seed), "builder_version": VERSION,
        "external_llm_calls": 0, "local_llm_calls": 0, "embeddings": 0, "translator_calls": 0}
    result["evaluation_origin" if purpose == "evaluation" else "research_origin"] = origin
    project_map(result, registry, annotation)
    return {"map": result, "registry": registry, "annotation": annotation, "origin": origin}
