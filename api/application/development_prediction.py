"""Фиксация источников и оценщик имеют отдельные входы и отдельные стадии."""
import logging

from application.compare_article_maps import validate_reference
from application.ports.article_comparisons import ComparisonMaps, ComparisonControls
from application.ports.development_prediction import PredictionStore
from domain.article_maps import require, fingerprint, ArticleMapNotFound
from domain.comparison_normalization import VERSION as NORMALIZER_VERSION, DICTIONARY_SHA256
from domain.article_comparison import VERSION as COMPARATOR_VERSION
from domain.development_prediction import fit_predict, evaluate_sealed, VERSION, EVALUATOR_VERSION, LIMITS

log = logging.getLogger(__name__)
MIN_SOURCE_MAPS = 2
MAX_SOURCE_MAPS = 100


class SealSourcePrediction:
    def __init__(self, maps: ComparisonMaps, store: PredictionStore):
        self.maps, self.store = maps, store

    def execute(self, sources, user_uid):
        require(isinstance(sources, list) and MIN_SOURCE_MAPS <= len(sources) <= MAX_SOURCE_MAPS,
                f"Explicit list of {MIN_SOURCE_MAPS}–{MAX_SOURCE_MAPS} sources required")
        for ref in sources:
            validate_reference(ref)
        require(len({r["article_id"] for r in sources}) == len(sources), "Duplicate source article")
        results = []
        for ref in sources:
            m = self.maps.get(ref["article_id"], ref["pipeline_id"], user_uid, ref["run_id"])
            if m is None:
                raise ArticleMapNotFound("Source run missing")
            require(m["article_id"] == ref["article_id"] and m["run_id"] == ref["run_id"], "Source identity differs")
            results.append(m)
        binding = {"sources": sources, "maps": [{"graph_sha256": fingerprint(m["graph"]), "source_sha256": m["source"]["sha256"]} for m in results],
                   "normalizer_version": NORMALIZER_VERSION, "dictionary_sha256": DICTIONARY_SHA256,
                   "predictor_version": VERSION, "limits": LIMITS}
        run_id = fingerprint(binding)
        existing = self.store.read_seal(run_id)
        if existing:
            require(existing["binding"] == binding, "Immutable prediction binding differs")
            return existing
        log.info("schema6_prediction start run=%s sources=%s", run_id, len(sources))
        artifact = {"run_id": run_id, "binding": binding, **fit_predict(results)}
        self.store.seal(run_id, artifact)
        log.info("schema6_prediction sealed run=%s known=%s semantic=%s graph=%s", run_id,
                 *(len(artifact["predictions"][m]) for m in ("known_union", "semantic", "graph")))
        return self.store.read_seal(run_id)


class EvaluateSourcePrediction:
    def __init__(self, maps: ComparisonMaps, store: PredictionStore, controls: ComparisonControls):
        self.maps, self.store, self.controls = maps, store, controls

    def execute(self, run_id, target, user_uid):
        sealed = self.store.read_seal(run_id)
        require(sealed is not None, "Predictions must be sealed before evaluation")
        validate_reference(target)
        require(target["article_id"] not in {r["article_id"] for r in sealed["binding"]["sources"]}, "Target leaked into training sources")
        # Владельцы проверяются повторно; оценщик не пересчитывает кандидатов и не обучает правила.
        for ref in sealed["binding"]["sources"]:
            self.maps.authorize(ref["article_id"], user_uid)
        m = self.maps.get(target["article_id"], target["pipeline_id"], user_uid, target["run_id"])
        if m is None:
            raise ArticleMapNotFound("Target run missing")
        require(m["article_id"] == target["article_id"] and m["run_id"] == target["run_id"], "Target identity differs")
        require(sealed["binding"]["normalizer_version"] == NORMALIZER_VERSION and sealed["binding"]["predictor_version"] == VERSION
                and sealed["binding"]["dictionary_sha256"] == DICTIONARY_SHA256,
                "Sealed prediction requires its original compatible normalizer and predictor")
        controls = self.controls.select([target, *sealed["binding"]["sources"]])
        binding = {"prediction_run_id": run_id, "prediction_sha256": fingerprint(sealed), "target": target,
                   "target_graph_sha256": fingerprint(m["graph"]), "target_source_sha256": m["source"]["sha256"],
                   "comparator_version": COMPARATOR_VERSION, "controls_sha256": fingerprint(controls)}
        binding["evaluator_version"] = EVALUATOR_VERSION
        result = {"evaluation_id": fingerprint(binding), "binding": binding, **evaluate_sealed(sealed, m, controls)}
        self.store.save_evaluation(run_id, result["evaluation_id"], result)
        log.info("schema6_prediction evaluated run=%s evaluation=%s", run_id, result["evaluation_id"])
        return result
