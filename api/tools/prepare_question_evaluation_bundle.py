"""Ручные атомы Codex → отдельная карта оценщика; данные создаются только после seal."""
from __future__ import annotations
import argparse
import ctypes
import json
import sys
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

API = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API))
from domain.article_maps import digest, fingerprint, parse_json_response, prepare_source, require
from domain.research_semantics import project_map, source_span, validate_context
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.import_codex_article_map import prohibit_generation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path); parser.add_argument("--run-id", required=True)
    parser.add_argument("--source", required=True, type=Path); parser.add_argument("--seed", required=True, type=Path)
    args = parser.parse_args()
    require(bool(ctypes.windll.shell32.IsUserAnAdmin()), "Administrative CLI required")
    prohibit_generation()
    require(FilePredictionStore(args.output).read_seal(args.run_id) is not None, "Seal before preparing evaluation knowledge")
    metadata = parse_json_response((args.source / "metadata.json").read_text(encoding="utf-8"))
    text = (args.source / "article.md").read_bytes().decode("utf-8")
    require(digest(text) == metadata["source_sha256"], "Prepared target source differs")
    seed = parse_json_response(args.seed.read_text(encoding="utf-8"))
    require(seed["pmcid"] == metadata["pmcid"] and seed["author"] == "Codex" and seed["expert_validated"] is False, "Evaluation seed binding differs")
    article = "evaluation-" + seed["pmcid"].lower() + "-" + digest(text)[:16]
    source = prepare_source(article, text)
    concepts, knowledge = {}, []
    for index, raw in enumerate(seed["claims"], 1):
        validate_context(raw["context"])
        spans = []
        for quote in raw.get("quotes", [raw["quote"]]):
            require(text.count(quote) == 1, "Target evidence quotation must be unique and exact")
            start = text.index(quote); spans.append(source_span(source, start, start + len(quote), quote))
        unit_ids = [u["id"] for u in source["units"] if any(u["start"] < s["end"] and u["end"] > s["start"] for s in spans)]
        require(unit_ids, "Target quotation has no source unit")
        roles = []
        for role, value in raw["roles"].items():
            if value not in concepts: concepts[value] = {"id": "C" + str(len(concepts) + 1), "display_text": value, "aliases": []}
            roles.append({"role": role, "concept_id": concepts[value]["id"], "knowledge_id": None})
        attributes = list(raw.get("measurements", []))
        names = {"study": "study_id", "cohort": "cohort_id", "sample": "sample_id", "design": "study_design", "time": "event_time"}
        for key, value in raw["context"].items():
            attributes.append({"name": names.get(key, key) if value["status"] == "known" else "context_status_" + key,
                               "value": value["value"] if value["status"] == "known" else value["status"], "unit": None})
        attributes.append({"name": "evidence_presentation", "value": raw.get("presentation", "own_result"), "unit": None})
        kid = "K" + str(index)
        statement = {"statement_id": kid + "S1", "predicate": raw["predicate"], "roles": roles, "negated": raw.get("negated", False),
            "quantifier": raw.get("quantifier"), "modality": raw.get("modality"), "temporal_context": None, "conditions": [],
            "qualifiers": {"attributes": attributes}, "provenance": {"unit_ids": unit_ids}}
        knowledge.append({"knowledge_id": kid, "kind": "state", "knowledge_kind": "observation", "action_status": None,
            "display_text": raw["text_en"], "semantic_frame": {"logic": "single", "statements": [statement]}, "provenance": {"unit_ids": unit_ids}})
    graph = {"schema_version": 6, "concepts": list(concepts.values()), "knowledge": knowledge,
             "nodes": [{"id": "B" + str(i), "knowledge_id": k["knowledge_id"]} for i, k in enumerate(knowledge, 1)],
             "edges": [], "transitions": []}
    run_id = str(uuid5(NAMESPACE_URL, fingerprint({"source": source["sha256"], "seed": seed, "builder": "prepared-evaluator-1"})))
    result = {"article_id": article, "pipeline_id": "text_reified", "run_id": run_id, "source": source, "graph": graph,
              "generation": {"kind": "codex_manual_evaluation_only", "external_llm_calls": 0, "local_llm_calls": 0, "token_usage": None},
              "translations": {"ru": {"knowledge_labels": {k["knowledge_id"]: raw["text_ru"] for k, raw in zip(knowledge, seed["claims"])}}}}
    registry = {"article_id": article, "run_id": run_id, "source_sha256": source["sha256"], "available_on": metadata["available_on"],
                "family": seed["family"], "presentation": "own_result", "title": metadata["title"], "metadata_source": metadata["metadata_url"]}
    annotation = {"run_id": run_id, "source_sha256": source["sha256"], "graph_sha256": fingerprint(graph), "claims": [], "replaces": []}
    claims = project_map(result, registry, annotation)
    origin = {"author": "Codex", "expert_validated": False, "source_metadata": metadata,
        "coverage": "selected_question_relevant_prose_claims", "full_article_formalization": False,
        "scientific_test_kind": "retrospective_engineering_diagnostic", "selection_disclosure": seed["selection_disclosure"],
        "external_llm_calls": 0, "local_llm_calls": 0, "embeddings": 0, "translator_calls": 0}
    result["evaluation_origin"] = origin
    bundle = {"map": result, "registry": registry, "annotation": annotation, "origin": origin}
    for name, value in (("target.bundle.json", bundle), ("target.claims.json", [c.to_dict() for c in claims]), ("target.seed.json", seed)):
        path = args.source / name; data = FilePredictionStore.encode(value)
        write_immutable(path, data)
    print(json.dumps({"prepared_target": metadata["pmcid"], "run_id": run_id, "claims": len(claims), "full_formalization": False, "model_calls": 0}))


if __name__ == "__main__": main()
