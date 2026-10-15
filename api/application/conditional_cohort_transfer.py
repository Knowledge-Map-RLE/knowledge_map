"""Фиксирует вложенный выбор оператора до доступа к внешним числовым контролям."""
import logging

from application.ports.cohort_transfer import CohortTransferInputs
from application.ports.empirical_inference import EmpiricalControls
from application.ports.development_prediction import PredictionStore
from domain.article_maps import fingerprint, require
from domain.conditional_cohort_transfer import VERSION, POLICY, forecast_conditional_fold, evaluate

log = logging.getLogger(__name__)


class SealConditionalTransfer:
    def __init__(self, inputs: CohortTransferInputs, store: PredictionStore):
        self.inputs, self.store = inputs, store

    def execute(self, implementation):
        data = self.inputs.read_inputs()
        binding = {"version": VERSION, "policy": POLICY, "implementation": implementation,
                   "manifest_sha256": fingerprint(data["manifest"]), "folds_sha256": [fingerprint(f) for f in data["folds"]],
                   "source_bindings": data["manifest"]["source_bindings"]}
        run_id = fingerprint(binding)
        previous = self.store.read_seal(run_id)
        if previous is not None:
            require(previous["binding"] == binding, "Immutable conditional binding differs")
            return previous
        folds = [forecast_conditional_fold(f) for f in data["folds"]]
        result = {"run_id": run_id, "binding": binding, "folds": folds, "model_calls": 0,
                  "new_scientific_predictions": 0, "expert_validated": False}
        self.store.seal(run_id, result)
        log.info("conditional_transfer sealed run=%s folds=%d", run_id, len(folds))
        return self.store.read_seal(run_id)


class EvaluateConditionalTransfer:
    def __init__(self, controls: EmpiricalControls, store: PredictionStore):
        self.controls, self.store = controls, store

    def execute(self, run_id, implementation):
        sealed = self.store.read_seal(run_id)
        require(sealed is not None, "Seal required before controls")
        require(sealed["binding"]["version"] == VERSION and sealed["binding"]["implementation"] == implementation, "Frozen conditional implementation changed")
        controls = self.controls.read_controls()
        require(controls["manifest_sha256"] == sealed["binding"]["manifest_sha256"], "Controls belong to another corpus")
        binding = {"run_id": run_id, "sealed_sha256": fingerprint(sealed), "controls_sha256": fingerprint(controls),
                   "evaluator_version": "conditional-cohort-evaluator-1"}
        result = {"evaluation_id": fingerprint(binding), "binding": binding, **evaluate(sealed["folds"], controls["controls"]),
                  "annotation_author": "Codex", "expert_validated": False}
        self.store.save_evaluation(run_id, result["evaluation_id"], result)
        return result
