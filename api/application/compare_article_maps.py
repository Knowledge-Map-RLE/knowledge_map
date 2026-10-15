"""Сравнение читает только явно выбранные неизменяемые карты, без AI-клиентов."""
from __future__ import annotations

import logging
import time
from collections import Counter

from application.ports.article_comparisons import ComparisonRepository, ComparisonMaps, ComparisonControls
from domain.article_comparison import compare_corpus, VERSION, MODES
from domain.comparison_normalization import VERSION as NORMALIZER_VERSION, DICTIONARY_SHA256
from domain.article_maps import fingerprint, timestamp, require, ArticleMapNotFound

log = logging.getLogger(__name__)


def validate_reference(ref):
    require(isinstance(ref, dict) and set(ref) == {"article_id", "pipeline_id", "run_id"}, "Explicit map run reference required")
    require(ref["pipeline_id"] == "text_reified", "Comparison requires text_reified runs")
    require(all(isinstance(v, str) and 0 < len(v) < 200 for v in ref.values()), "Invalid map run reference")


def control_metrics(pairs, controls):
    observations = []
    for control in controls.get("pairs", []):
        row = [p for p in pairs if p["left_knowledge_id"] in control["left_knowledge_ids"]]
        relevant = [p for p in row if p["right_article_id"] == control["right_article_id"]
                    and p["right_knowledge_id"] in control["right_knowledge_ids"]]
        ranks = {mode: min((p[f"{mode}_rank"] for p in relevant if p[f"{mode}_rank"] is not None), default=None) for mode in MODES}
        observations.append({**control, "ranks": ranks, "retrieved_relations": sorted({r for p in relevant for r in p["relations"]}),
                             "retrieved_pairs": [p["pair_id"] for p in relevant],
                             "expected_relation_found": any(r in control.get("expected_relations", []) for p in relevant for r in p["relations"]),
                             "detected_difference_fields": sorted({d["field"] for p in relevant for m in p["statement_matches"] for d in m["differences"]})})
    anchors = [o for o in observations if o["kind"] == "citation"]
    metrics = {mode: {str(k): {"found": sum(o["ranks"][mode] is not None and o["ranks"][mode] <= k for o in anchors),
                             "total": len(anchors)} for k in (1, 5, 10)} for mode in MODES}
    return {"retrieval_at_k": metrics, "observations": observations, "author": "Codex", "needs_expert_review": True,
            "note": "Small exploratory citation control set; citation does not establish equivalence or scientific validity"}


class CompareArticleMaps:
    def __init__(self, maps: ComparisonMaps, repository: ComparisonRepository, controls: ComparisonControls):
        self.maps, self.repository, self.controls = maps, repository, controls

    def execute(self, target, sources, user_uid):
        started = time.monotonic()
        require(isinstance(sources, list) and 1 <= len(sources) <= 20, "Select 1–20 explicit source runs")
        references = [target, *sources]
        for ref in references:
            validate_reference(ref)
        require(len({r["article_id"] for r in references}) == len(references), "A target or source article cannot occur twice")
        maps = []
        for ref in references:
            result = self.maps.get(ref["article_id"], ref["pipeline_id"], user_uid, ref["run_id"])
            if result is None:
                raise ArticleMapNotFound("Selected map run not found")
            require(result["graph"]["schema_version"] == 6, "Comparison requires schema 6 for every selected map")
            require(result["run_id"] == ref["run_id"] and result["article_id"] == ref["article_id"], "Selected map identity differs")
            maps.append(result)
        controls = self.controls.select(references)
        binding = {"references": references, "map_bindings": [{"graph_sha256": fingerprint(m["graph"]),
            "source_sha256": m["source"]["sha256"]} for m in maps], "normalizer_version": NORMALIZER_VERSION,
            "dictionary_sha256": DICTIONARY_SHA256, "comparator_version": VERSION,
            "control_version": controls["version"], "control_sha256": fingerprint(controls)}
        cid = fingerprint(binding)
        existing = self.repository.get(cid, user_uid)
        if existing is not None:
            require(existing["binding"] == binding, "Immutable comparison binding differs")
            return existing
        log.info("article_comparison start id=%s articles=%s normalizer=%s comparator=%s", cid, len(maps), NORMALIZER_VERSION, VERSION)
        analysis = compare_corpus(maps[0], maps[1:])
        pairs = analysis.pop("pairs")
        normalization = analysis.pop("normalization")
        log.info("article_comparison aligned id=%s pairs=%s elapsed_seconds=%.3f", cid, len(pairs), time.monotonic() - started)
        evaluation = control_metrics(pairs, controls)
        summary = {"relations": dict(Counter(r for p in pairs for r in p["relations"])),
                   "equivalent_pairs": sum(p["relations"] == ["equivalent"] for p in pairs),
                   "unique_target_knowledge_by_relation": {r: sorted({p["left_knowledge_id"] for p in pairs if r in p["relations"]})
                                                         for r in ("equivalent", "partial", "template", "topical", "contradiction")},
                   "shared_attribute_targets": sorted({p["left_knowledge_id"] for p in pairs
                                                       if any(m["shared_attributes"] for m in p["statement_matches"])}),
                   "auxiliary_description_count": sum(bool(s["auxiliary_attributes"]) for k in normalization["target"] for s in k["statements"]),
                   "covered_target_statements": sorted({m["left_statement"] for p in pairs for m in p["statement_matches"]
                                                        if m["compatible"] and m["relation"] in ("equivalent", "partial")})}
        summary["one_to_many"] = [{"left_knowledge_id": k["knowledge_id"],
            "matches": [{"article_id": p["right_article_id"], "knowledge_id": p["right_knowledge_id"],
                         "left_statements": [m["left_statement"] for m in p["statement_matches"] if m["compatible"] and m["relation"] in ("equivalent", "partial")]}
                        for p in pairs if p["left_knowledge_id"] == k["knowledge_id"] and p["coverage_left"] > 0]}
            for k in maps[0]["graph"]["knowledge"]]
        result = {"comparison_id": cid, "created_at": timestamp(), "binding": binding, "references": references,
                  "analysis": analysis, "summary": summary, "controls": controls, "evaluation": evaluation,
                  "maps": maps, "normalization": normalization, "pairs": pairs}
        self.repository.save(result, user_uid)
        log.info("article_comparison saved id=%s pairs=%s elapsed_seconds=%.3f model_calls=0", cid, len(pairs), time.monotonic() - started)
        return self.repository.get(cid, user_uid)
