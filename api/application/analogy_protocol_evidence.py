"""Отдельная неизменяемая проверка протокола сохраняет исходные карты и прогноз."""
import logging
from time import perf_counter

from application.ports.development_prediction import PredictionStore
from domain.article_maps import fingerprint, require
from domain.analogy_protocol_evidence import assess_protocol_evidence, VERSION

log = logging.getLogger(__name__)


class SealAnalogyProtocolEvidence:
    def __init__(self, store: PredictionStore): self.store = store

    def execute(self, forecast, packets, audit, implementation):
        started = perf_counter()
        binding = {'version': VERSION, 'forecast_run_id': forecast['run_id'], 'forecast_sha256': fingerprint(forecast),
            'packets': {key: fingerprint(value) for key, value in sorted(packets.items())},
            'audit_sha256': fingerprint(audit), 'implementation': implementation}
        # Повторно проверяем свидетельства до переиспользования результата.
        result = assess_protocol_evidence(forecast, packets, audit)
        run = fingerprint(binding); previous = self.store.read_seal(run)
        if previous is not None:
            require(previous['binding'] == binding, 'Protocol evidence binding differs'); return previous
        self.store.seal(run, {'run_id': run, 'binding': binding, **result})
        log.info('analogy_protocol_sealed run=%s sources=%d candidates=%d confirmed=%d seconds=%.3f',
                 run, len(packets), result['candidate_count'], result['confirmed_transfers'], perf_counter() - started)
        return self.store.read_seal(run)
