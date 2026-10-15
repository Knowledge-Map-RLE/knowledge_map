"""Фиксация гипотез до открытия нового контрольного результата."""
import logging
from time import perf_counter

from application.ports.development_prediction import PredictionStore
from domain.article_maps import fingerprint, require
from domain.analogy_hypothesis_plan import VERSION, generate_hypothesis_plan

log = logging.getLogger(__name__)


class SealAnalogyHypothesisPlan:
    def __init__(self, store: PredictionStore): self.store = store

    def execute(self, forecast, audit, plan, implementation):
        started = perf_counter()
        binding = {'version': VERSION, 'forecast_run_id': forecast['run_id'], 'forecast_sha256': fingerprint(forecast),
            'protocol_audit_run_id': audit['run_id'], 'protocol_audit_sha256': fingerprint(audit),
            'plan_sha256': fingerprint(plan), 'implementation': implementation}
        result = generate_hypothesis_plan(forecast, audit, plan)
        run = fingerprint(binding)
        previous = self.store.read_seal(run)
        if previous is not None:
            require(previous['binding'] == binding, 'Hypothesis plan changed'); return previous
        self.store.seal(run, {'run_id': run, 'binding': binding, **result})
        log.info('analogy_hypotheses_sealed run=%s candidates=%d scored=%d seconds=%.3f',
                 run, result['hypothesis_count'], result['future_results_scored'], perf_counter() - started)
        return self.store.read_seal(run)
