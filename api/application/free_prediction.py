"""Свободный прогноз фиксируется до доступа оценщика к целевой карте."""
import logging

from application.compare_article_maps import validate_reference
from application.ports.article_comparisons import ComparisonMaps, ComparisonControls
from application.ports.development_prediction import PredictionStore
from domain.article_maps import fingerprint, require, ArticleMapNotFound
from domain.comparison_normalization import VERSION as NORMALIZER_VERSION, DICTIONARY_SHA256
from domain.article_comparison import VERSION as COMPARATOR_VERSION
from domain.development_prediction import evaluate_sealed
from domain.free_prediction import forecast, VERSION, POLICY, LIMITS

log = logging.getLogger(__name__)


class SealFreePrediction:
    def __init__(self, maps: ComparisonMaps, store: PredictionStore):
        self.maps, self.store = maps, store

    def execute(self, sources, families, owner, corpus_metadata):
        require(isinstance(sources, list) and 2 <= len(sources) <= 20, "Explicit source-only corpus required")
        require(len({r["article_id"] for r in sources}) == len(sources), "Duplicate source article")
        results = []
        for ref in sources:
            validate_reference(ref)
            result = self.maps.get(ref["article_id"], ref["pipeline_id"], owner, ref["run_id"])
            if result is None:
                raise ArticleMapNotFound("Source run missing")
            require(result["article_id"] == ref["article_id"] and result["run_id"] == ref["run_id"], "Source identity differs")
            results.append(result)
        require(len({m["source"]["sha256"] for m in results}) == len(results), "Duplicate source text under different article IDs")
        binding = {"sources": sources, "families": families, "corpus_metadata": corpus_metadata,
                   "maps": [{"map_sha256": fingerprint(m), "graph_sha256": fingerprint(m["graph"]),
                             "source_sha256": m["source"]["sha256"]} for m in results],
                   "predictor_version": VERSION, "normalizer_version": NORMALIZER_VERSION,
                   "dictionary_sha256": DICTIONARY_SHA256, "policy": POLICY, "limits": LIMITS}
        run_id = fingerprint(binding)
        prior = self.store.read_seal(run_id)
        if prior is not None:
            require(prior["binding"] == binding, "Immutable forecast binding differs")
            return prior
        log.info("free_prediction start run=%s sources=%d", run_id, len(results))
        artifact = {"run_id": run_id, "binding": binding, **forecast(results, families)}
        self.store.seal(run_id, artifact)
        log.info("free_prediction sealed run=%s candidates=%d", run_id, len(artifact["predictions"]["free"]))
        return self.store.read_seal(run_id)


class EvaluateFreePrediction:
    def __init__(self, maps: ComparisonMaps, store: PredictionStore, controls: ComparisonControls):
        self.maps, self.store, self.controls = maps, store, controls

    def execute(self, run_id, target, owner):
        sealed = self.store.read_seal(run_id)
        require(sealed is not None, "Forecast must be sealed before target loading")
        require(sealed["predictor_version"] == VERSION and sealed["binding"]["normalizer_version"] == NORMALIZER_VERSION
                and sealed["binding"]["dictionary_sha256"] == DICTIONARY_SHA256,
                "Frozen forecast requires compatible versions")
        validate_reference(target)
        require(target["article_id"] not in {r["article_id"] for r in sealed["binding"]["sources"]}, "Target leaked into sources")
        for ref in sealed["binding"]["sources"]:
            self.maps.authorize(ref["article_id"], owner)
        result = self.maps.get(target["article_id"], target["pipeline_id"], owner, target["run_id"])
        require(result is not None and result["article_id"] == target["article_id"] and result["run_id"] == target["run_id"], "Target identity differs")
        require(result["source"]["sha256"] not in {m["source_sha256"] for m in sealed["binding"]["maps"]}, "Target source duplicated under another ID")
        controls = self.controls.select([target, *sealed["binding"]["sources"]])
        binding = {"run_id": run_id, "prediction_sha256": fingerprint(sealed), "target": target,
                   "target_map_sha256": fingerprint(result), "target_source_sha256": result["source"]["sha256"],
                   "comparator_version": COMPARATOR_VERSION, "evaluator_version": "free-evaluator-1",
                   "controls_sha256": fingerprint(controls)}
        evaluation = {"evaluation_id": fingerprint(binding), "binding": binding,
                      **evaluate_sealed(sealed, result, controls)}
        free = evaluation["modes"]["free"]
        evaluation["debugging_success"] = free["matched_candidate_count"] > 0
        evaluation["independent_success"] = False
        evaluation["absence_is_not_refutation"] = True
        self.store.save_evaluation(run_id, evaluation["evaluation_id"], evaluation)
        log.info("free_prediction evaluated run=%s matched=%d", run_id, free["matched_candidate_count"])
        return evaluation
