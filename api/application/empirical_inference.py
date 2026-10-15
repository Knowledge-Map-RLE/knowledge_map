"""Фиксация источникового вывода предшествует загрузке скрытых заключений."""
import logging

from application.ports.empirical_inference import EmpiricalInputs, EmpiricalControls
from application.ports.development_prediction import PredictionStore
from domain.article_maps import fingerprint, require
from domain.empirical_inference import VERSION, CONTRACT_VERSION, POLICY, run_cases, nominal_baseline, score

log = logging.getLogger(__name__)


class SealEmpiricalInference:
    def __init__(self, inputs: EmpiricalInputs, store: PredictionStore):
        self.inputs, self.store = inputs, store

    def execute(self, implementation: dict) -> dict:
        dataset = self.inputs.read_inputs()
        require(set(dataset) == {"contract_version", "metadata", "source_bindings", "evidence", "labels", "cases"}, "Unknown input fields or leaked controls")
        require(dataset["contract_version"] == CONTRACT_VERSION, "Unsupported empirical contract")
        binding = {"input_sha256": fingerprint(dataset), "source_bindings": dataset["source_bindings"],
                   "operator_version": VERSION, "policy": POLICY, "implementation": implementation}
        run_id = fingerprint(binding)
        existing = self.store.read_seal(run_id)
        if existing is not None:
            require(existing["binding"] == binding, "Empirical seal differs")
            return existing
        results = run_cases(dataset["cases"])
        artifact = {"run_id": run_id, "binding": binding, "results": results,
                    "baseline": nominal_baseline(dataset["cases"]), "model_calls": 0,
                    "new_scientific_predictions": 0, "expert_validated": False}
        self.store.seal(run_id, artifact)
        log.info("empirical_inference sealed run=%s cases=%d abstentions=%d", run_id, len(results), sum(r["status"] == "abstain" for r in results))
        return self.store.read_seal(run_id)


class EvaluateEmpiricalInference:
    def __init__(self, controls: EmpiricalControls, store: PredictionStore):
        self.controls, self.store = controls, store

    def execute(self, run_id: str, implementation: dict) -> dict:
        sealed = self.store.read_seal(run_id)
        require(sealed is not None, "Seal required before loading holdouts")
        require(sealed["binding"]["operator_version"] == VERSION and sealed["binding"]["implementation"] == implementation,
                "Frozen implementation changed")
        controls = self.controls.read_controls()
        require(controls["input_sha256"] == sealed["binding"]["input_sha256"], "Holdouts belong to different inputs")
        binding = {"run_id": run_id, "seal_sha256": fingerprint(sealed), "controls_sha256": fingerprint(controls),
                   "evaluator_version": "empirical-holdout-evaluator-1"}
        result = {"evaluation_id": fingerprint(binding), "binding": binding,
                  "operator": score(sealed["results"], controls["controls"]),
                  "nominal_baseline": score(sealed["baseline"], controls["controls"]),
                  "annotation_author": "Codex", "expert_validated": False, "independent_success": False}
        self.store.save_evaluation(run_id, result["evaluation_id"], result)
        return result
