"""Оценщик использует отдельные контрольные данные и не меняет предсказатель."""
import logging
from time import perf_counter

from application.ports.development_prediction import PredictionStore
from domain.article_maps import fingerprint, require
from domain.analogy_control_screen import VERSION, screen_controls

log = logging.getLogger(__name__)


class SealAnalogyControlScreen:
    def __init__(self, store: PredictionStore): self.store = store

    def execute(self, forecast, registry, packets, annotation, training_forecast, implementation):
        started = perf_counter()
        binding = {'version': VERSION, 'forecast_run_id': forecast['run_id'], 'forecast_sha256': fingerprint(forecast),
            'registry_sha256': fingerprint(registry), 'source_packets': {sid: fingerprint(p) for sid, p in sorted(packets.items())},
            'annotation_sha256': fingerprint(annotation), 'training_forecast_sha256': fingerprint(training_forecast),
            'implementation': implementation}
        result = screen_controls(forecast, registry, packets, annotation, training_forecast); run = fingerprint(binding)
        previous = self.store.read_seal(run)
        if previous is not None:
            require(previous['binding'] == binding, 'Control screening changed'); return previous
        self.store.seal(run, {'run_id': run, 'binding': binding, **result})
        log.info('analogy_control_screen run=%s full_controls=%d eligible=%d seconds=%.3f',
                 run, len(packets), result['eligible_protocol_comparisons'], perf_counter() - started)
        return self.store.read_seal(run)
