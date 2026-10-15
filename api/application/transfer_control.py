"""Оценка сохраняется отдельно, зафиксированный прогноз не изменяется."""
from application.ports.transfer_control import ControlInputs
from application.ports.development_prediction import PredictionStore
from domain.article_maps import fingerprint
from domain.transfer_control import VERSION, audit_control


class AuditTransferControl:
    def __init__(self, inputs: ControlInputs, store: PredictionStore):
        self.inputs, self.store = inputs, store

    def execute(self, implementation):
        data = self.inputs.read_inputs()
        binding = {"version": VERSION, "input_sha256": fingerprint(data), "implementation": implementation}
        run_id = fingerprint(binding)
        previous = self.store.read_seal(run_id)
        if previous:
            return previous
        result = {"run_id": run_id, "binding": binding, "inputs": data,
                  "audit": audit_control(data["forecast"], data["control"]), "model_calls": 0}
        self.store.seal(run_id, result)
        return self.store.read_seal(run_id)
