"""Фиксация фундамента и прогнозов до программного доступа к контролю."""
from collections import Counter
from domain.article_maps import fingerprint, require
from domain.knowledge_foundation import VERSION, MODES, forecast_native_fold, evaluate_native_fold
from application.ports.knowledge_foundation import FoundationInputs, FoundationControls
from application.ports.development_prediction import PredictionStore

class SealFoundationPilot:
    def __init__(self, inputs: FoundationInputs, store: PredictionStore):
        self.inputs, self.store = inputs, store

    def execute(self, implementation):
        inputs = self.inputs.read_inputs()
        binding = {'version': VERSION, 'manifest_sha256': fingerprint(inputs['manifest']),
                   'foundation_sha256': fingerprint(inputs['foundation']),
                   'folds_sha256': [fingerprint(f) for f in inputs['folds']], 'implementation': implementation}
        run_id = fingerprint(binding); prior = self.store.read_seal(run_id)
        if prior: return prior
        result = {'run_id': run_id, 'binding': binding, 'foundation': inputs['foundation'],
                  'folds': [forecast_native_fold(f, inputs['foundation']) for f in inputs['folds']],
                  'retrospective': True, 'expert_validated': False, 'model_calls': 0, 'new_scientific_predictions': 0}
        self.store.seal(run_id, result)
        return self.store.read_seal(run_id)

class EvaluateFoundationPilot:
    def __init__(self, controls: FoundationControls, store: PredictionStore):
        self.controls, self.store = controls, store

    def execute(self, run_id, implementation):
        seal = self.store.read_seal(run_id); require(seal is not None, 'Seal required before controls')
        require(seal['binding']['implementation'] == implementation, 'Frozen implementation changed')
        controls = self.controls.read_controls()
        require(controls['manifest_sha256'] == seal['binding']['manifest_sha256'], 'Control corpus changed')
        require(set(controls['controls']) == {f['fold_id'] for f in seal['folds']}, 'Missing or extra control fold')
        folds = [evaluate_native_fold(f, controls['controls'][f['fold_id']], seal['foundation']) for f in seal['folds']]
        totals = {m: dict(sum((Counter(f['modes'][m]['counts']) for f in folds), Counter())) for m in MODES}
        binding = {'run_id': run_id, 'seal_sha256': fingerprint(seal), 'controls_sha256': fingerprint(controls), 'version': VERSION}
        result = {'evaluation_id': fingerprint(binding), 'binding': binding, 'folds': folds, 'totals': totals,
                  'retrospective': True, 'independent_scientific_success': False, 'new_scientific_predictions': 0}
        self.store.save_evaluation(run_id, result['evaluation_id'], result)
        return result
