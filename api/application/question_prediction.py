"""Контроль семантики, обучение на прошлом, неизменяемый прогноз и отдельная оценка."""
from __future__ import annotations

from dataclasses import asdict
import logging
from time import perf_counter

from application.compare_article_maps import validate_reference
from application.ports.question_prediction import ResearchMaps, QuestionForecastStore, ResearchArtifacts
from domain.article_maps import fingerprint, require, ArticleMapNotFound
from domain.research_semantics import project_map, semantic_audit, VERSION as SEMANTICS_VERSION
from domain.question_prediction import ForecastQuestion, fit_question_forecast, evaluate_question_forecast, VERSION, LIMITS
from domain.comparison_normalization import VERSION as NORMALIZER_VERSION, DICTIONARY_SHA256
from domain.research_diagnostics import VERSION as DIAGNOSTIC_VERSION
from domain.question_readiness import VERSION as READINESS_VERSION, assess_readiness

log = logging.getLogger(__name__)
ANALYSIS_BINDING = {"semantics_version": SEMANTICS_VERSION, "predictor_version": VERSION,
                   "normalizer_version": NORMALIZER_VERSION, "dictionary_sha256": DICTIONARY_SHA256,
                   "diagnostic_version": DIAGNOSTIC_VERSION, "readiness_version": READINESS_VERSION,
                   "workflow_version": "question-workflow-3"}


def load_runs(maps, references, owner):
    require(isinstance(references, list) and bool(references), "Explicit run references required")
    require(len({r["article_id"] for r in references}) == len(references), "Duplicate research source")
    results = []
    for reference in references:
        validate_reference(reference)
        result = maps.get(reference["article_id"], reference["pipeline_id"], owner, reference["run_id"])
        if result is None:
            raise ArticleMapNotFound("Research source run missing")
        require(result["article_id"] == reference["article_id"] and result["run_id"] == reference["run_id"], "Research run identity differs")
        results.append(result)
    return results


def validate_metadata_scope(results, registry, annotations):
    ids = {m["article_id"] for m in results}
    require(set(registry) == ids and set(annotations) <= ids, "Metadata or annotations contain an unlisted article")


class AuditResearchSemantics:
    def __init__(self, maps: ResearchMaps, artifacts: ResearchArtifacts):
        self.maps, self.artifacts = maps, artifacts

    def execute(self, references, registry, annotations, controls, owner):
        start = perf_counter()
        results = load_runs(self.maps, references, owner)
        validate_metadata_scope(results, registry, annotations)
        binding = {"references": references, "registry": registry, "annotations_sha256": fingerprint(annotations),
                   "controls_sha256": fingerprint(controls), "semantics_version": SEMANTICS_VERSION,
                   "graphs": [fingerprint(m["graph"]) for m in results], "analysis_binding": ANALYSIS_BINDING}
        artifact = {"audit_id": fingerprint(binding), "binding": binding, **semantic_audit(results, registry, annotations, controls)}
        self.artifacts.audit(artifact["audit_id"], artifact)
        log.info("research_semantics audit=%s sources=%s controls=%s passed=%s elapsed=%.3f", artifact["audit_id"],
                 len(results), artifact["control_count"], artifact["controls_passed"], perf_counter() - start)
        return artifact


class SealQuestionForecast:
    def __init__(self, maps: ResearchMaps, store: QuestionForecastStore):
        self.maps, self.store = maps, store

    def execute(self, references, registry, annotations, episodes, question_raw, owner):
        start = perf_counter()
        question = ForecastQuestion.parse(question_raw)
        results = load_runs(self.maps, references, owner)
        require(len({m["source"]["sha256"] for m in results}) == len(results), "Duplicate full-text training source")
        validate_metadata_scope(results, registry, annotations)
        projected = [c for m in results for c in project_map(m, registry[m["article_id"]], annotations.get(m["article_id"]))]
        claims = {(c.evidence.article_id, c.claim_id): c for c in projected}
        binding = {"sources": references, "registry": registry, "annotations_sha256": fingerprint(annotations),
                   "episodes_sha256": fingerprint(episodes), "question": asdict(question), "owner": owner,
                   "semantics_version": SEMANTICS_VERSION, "predictor_version": VERSION, "limits": LIMITS,
                   "analysis_binding": ANALYSIS_BINDING,
                   "source_origin": [{"article_id": m["article_id"], "generation": m.get("generation", {}),
                                      "research_origin": m.get("research_origin", {}),
                                      "display_sha256": fingerprint(m.get("translations", {}))} for m in results],
                   "maps": [{"graph_sha256": fingerprint(m["graph"]), "source_sha256": m["source"]["sha256"]} for m in results]}
        run_id = fingerprint(binding)
        existing = self.store.read_seal(run_id)
        if existing:
            require(existing["binding"] == binding, "Question forecast binding differs")
            return existing
        artifact = {"run_id": run_id, "binding": binding, "episodes": episodes,
                    **fit_question_forecast(claims, episodes, {m["article_id"]: m for m in results}, question)}
        artifact["readiness"] = assess_readiness(artifact, projected, len(results))
        self.store.seal(run_id, artifact)
        log.info("question_forecast sealed run=%s sources=%s claims=%s semantic=%s dependency=%s elapsed=%.3f", run_id,
                 len(results), len(claims), len(artifact["modes"]["semantic"]), len(artifact["modes"]["dependency"]), perf_counter() - start)
        return self.store.read_seal(run_id)


class EvaluateQuestionForecast:
    def __init__(self, maps: ResearchMaps, store: QuestionForecastStore):
        self.maps, self.store = maps, store

    def execute(self, run_id, references, registry, annotations, owner):
        start = perf_counter()
        sealed = self.store.read_seal(run_id)
        require(sealed is not None, "Seal predictions before reading evaluation targets")
        require(sealed["binding"]["owner"] == owner, "Question forecast belongs to another owner")
        require(sealed["binding"]["semantics_version"] == SEMANTICS_VERSION and sealed["binding"]["predictor_version"] == VERSION,
                "Use the compatible evaluator for the sealed forecast")
        require(sealed["binding"].get("analysis_binding") == ANALYSIS_BINDING, "Evaluator normalization or workflow differs")
        source_ids = {r["article_id"] for r in sealed["binding"]["sources"]}
        require(not source_ids.intersection(r["article_id"] for r in references), "Evaluation target leaked into training")
        for ref in sealed["binding"]["sources"]:
            self.maps.authorize(ref["article_id"], owner)
        results = load_runs(self.maps, references, owner)
        validate_metadata_scope(results, registry, annotations)
        source_hashes = {m["source_sha256"] for m in sealed["binding"]["maps"]}
        require(not source_hashes.intersection(m["source"]["sha256"] for m in results), "Target source duplicates a training source")
        claims = [c for m in results for c in project_map(m, registry[m["article_id"]], annotations.get(m["article_id"]))]
        binding = {"run_id": run_id, "prediction_sha256": fingerprint(sealed), "targets": references,
                   "registry": registry, "annotations_sha256": fingerprint(annotations), "semantics_version": SEMANTICS_VERSION,
                   "target_origin": [{"article_id": m["article_id"], "generation": m.get("generation", {}),
                                      "evaluation_origin": m.get("evaluation_origin", {})} for m in results],
                   "target_display_sha256": fingerprint([m.get("translations", {}) for m in results]),
                   "target_maps": [{"graph_sha256": fingerprint(m["graph"]), "source_sha256": m["source"]["sha256"]} for m in results]}
        labels = {m["article_id"]: m.get("translations", {}).get("ru", {}).get("knowledge_labels", {}) for m in results}
        artifact = {"evaluation_id": fingerprint(binding), "binding": binding,
                    "target_claims": [{**c.to_dict(), "text_ru": labels[c.evidence.article_id].get(c.knowledge_id)} for c in claims],
                    **evaluate_question_forecast(sealed, claims)}
        self.store.save_evaluation(run_id, artifact["evaluation_id"], artifact)
        log.info("question_forecast evaluated run=%s evaluation=%s relevant=%s elapsed=%.3f", run_id,
                 artifact["evaluation_id"], artifact["relevant_target_claims"], perf_counter() - start)
        return artifact
