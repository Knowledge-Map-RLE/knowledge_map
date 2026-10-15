"""Сначала фиксирует все гипотезы, затем загружает удержанные числовые ячейки."""
import logging

from application.ports.cohort_transfer import CohortTransferInputs
from application.ports.empirical_inference import EmpiricalControls
from application.ports.development_prediction import PredictionStore
from domain.article_maps import fingerprint, require
from domain.cohort_transfer import VERSION, POLICY, forecast_fold, evaluate_folds

log=logging.getLogger(__name__)


class SealCohortTransfer:
    def __init__(self, inputs: CohortTransferInputs, store: PredictionStore):
        self.inputs,self.store=inputs,store

    def execute(self, implementation: dict) -> dict:
        data=self.inputs.read_inputs()
        binding={"manifest_sha256":fingerprint(data["manifest"]),"folds_sha256":[fingerprint(f) for f in data["folds"]],
            "source_bindings":data["manifest"]["source_bindings"],"version":VERSION,"policy":POLICY,"implementation":implementation}
        run_id=fingerprint(binding);prior=self.store.read_seal(run_id)
        if prior is not None:
            require(prior["binding"]==binding,"Immutable transfer binding differs");return prior
        folds=[forecast_fold(fold) for fold in data["folds"]]
        result={"run_id":run_id,"binding":binding,"folds":folds,"model_calls":0,"new_scientific_predictions":0,"expert_validated":False}
        self.store.seal(run_id,result)
        log.info("cohort_transfer sealed run=%s folds=%d queries=%d",run_id,len(folds),sum(f["query_count"] for f in folds))
        return self.store.read_seal(run_id)


class EvaluateCohortTransfer:
    def __init__(self,controls: EmpiricalControls,store: PredictionStore):
        self.controls,self.store=controls,store

    def execute(self,run_id: str,implementation: dict) -> dict:
        sealed=self.store.read_seal(run_id)
        require(sealed is not None,"Seal required before loading cohort controls")
        require(sealed["binding"]["version"]==VERSION and sealed["binding"]["implementation"]==implementation,"Frozen transfer implementation changed")
        controls=self.controls.read_controls()
        require(controls["manifest_sha256"]==sealed["binding"]["manifest_sha256"],"Holdouts belong to another manifest")
        binding={"run_id":run_id,"sealed_sha256":fingerprint(sealed),"controls_sha256":fingerprint(controls),"evaluator_version":"cohort-order-holdout-evaluator-1"}
        evaluation={"evaluation_id":fingerprint(binding),"binding":binding,**evaluate_folds(sealed["folds"],controls["controls"]),
            "annotation_author":"Codex","expert_validated":False}
        self.store.save_evaluation(run_id,evaluation["evaluation_id"],evaluation)
        return evaluation
