"""Отдельные стадии фиксации и оценки аналитического представления."""
import logging
from application.ports.article_comparisons import ComparisonMaps, ComparisonControls
from application.ports.development_prediction import PredictionStore
from application.compare_article_maps import validate_reference
from domain.article_maps import require, fingerprint
from domain.comparison_normalization import VERSION as NORMALIZER_VERSION, DICTIONARY_SHA256 as NORMALIZER_SHA
from domain.article_comparison import VERSION as COMPARATOR_VERSION
from domain.scoped_free_prediction import forecast, evaluate, VERSION, ADAPTER_VERSION, DICTIONARY_SHA256, POLICY, LIMITS

log=logging.getLogger(__name__)


class SealScopedPrediction:
    def __init__(self,maps:ComparisonMaps,store:PredictionStore):self.maps,self.store=maps,store

    def execute(self,sources,families,owner,metadata):
        require(2<=len(sources)<=20 and len({r["article_id"] for r in sources})==len(sources),"Explicit unique source corpus required")
        results=[]
        for ref in sources:
            validate_reference(ref)
            m=self.maps.get(ref["article_id"],ref["pipeline_id"],owner,ref["run_id"])
            require(m is not None and m["article_id"]==ref["article_id"] and m["run_id"]==ref["run_id"],"Source identity differs")
            results.append(m)
        require(len({m["source"]["sha256"] for m in results})==len(results),"Duplicate source text")
        binding={"sources":sources,"families":families,"corpus_metadata":metadata,"predictor_version":VERSION,"adapter_version":ADAPTER_VERSION,
            "adapter_dictionary_sha256":DICTIONARY_SHA256,"normalizer_version":NORMALIZER_VERSION,"dictionary_sha256":NORMALIZER_SHA,
            "policy":POLICY,"limits":LIMITS,"maps":[{"map_sha256":fingerprint(m),"graph_sha256":fingerprint(m["graph"]),
                "source_sha256":m["source"]["sha256"]} for m in results]}
        rid=fingerprint(binding);prior=self.store.read_seal(rid)
        if prior is not None:
            require(prior["binding"]==binding,"Immutable binding differs");return prior
        log.info("scoped_free_prediction start run=%s sources=%d",rid,len(sources))
        result={"run_id":rid,"binding":binding,**forecast(results,families)}
        self.store.seal(rid,result)
        log.info("scoped_free_prediction sealed run=%s candidates=%d",rid,len(result["predictions"]["free"]))
        return self.store.read_seal(rid)


class EvaluateScopedPrediction:
    def __init__(self,maps:ComparisonMaps,store:PredictionStore,controls:ComparisonControls):
        self.maps,self.store,self.controls=maps,store,controls

    def execute(self,run_id,target,owner):
        sealed=self.store.read_seal(run_id)
        require(sealed is not None,"Seal required before target loading")
        require(sealed["predictor_version"]==VERSION and sealed["adapter_version"]==ADAPTER_VERSION
            and sealed["dictionary_sha256"]==DICTIONARY_SHA256 and sealed["binding"]["dictionary_sha256"]==NORMALIZER_SHA,
            "Frozen analysis versions changed")
        validate_reference(target)
        require(target["article_id"] not in {r["article_id"] for r in sealed["binding"]["sources"]},"Target leaked into sources")
        for ref in sealed["binding"]["sources"]:self.maps.authorize(ref["article_id"],owner)
        m=self.maps.get(target["article_id"],target["pipeline_id"],owner,target["run_id"])
        require(m is not None and m["article_id"]==target["article_id"] and m["run_id"]==target["run_id"],"Target identity differs")
        require(m["source"]["sha256"] not in {v["source_sha256"] for v in sealed["binding"]["maps"]},"Target text leaked under another ID")
        controls=self.controls.select([target,*sealed["binding"]["sources"]])
        binding={"run_id":run_id,"prediction_sha256":fingerprint(sealed),"target":target,"target_map_sha256":fingerprint(m),
            "target_source_sha256":m["source"]["sha256"],"comparator_version":COMPARATOR_VERSION,"adapter_version":ADAPTER_VERSION,
            "controls_sha256":fingerprint(controls),"evaluator_version":"scoped-free-evaluator-1"}
        result={"evaluation_id":fingerprint(binding),"binding":binding,**evaluate(sealed,m,controls)}
        result["debugging_success"]=result["modes"]["free"]["matched_candidate_count"]>0
        result["independent_success"]=False
        self.store.save_evaluation(run_id,result["evaluation_id"],result)
        return result
