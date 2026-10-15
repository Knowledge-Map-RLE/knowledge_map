"""Парное обучение принимает только явный запечатанный корпус через порт."""
import logging
from typing import Protocol
from domain.article_maps import fingerprint, require
from domain.typed_participant_forecast import VERSION, forecast
from application.ports.development_prediction import PredictionStore

log = logging.getLogger(__name__)


class ParticipantCorpus(Protocol):
    def load(self): ...


class SealTypedParticipantForecast:
    def __init__(self, corpus: ParticipantCorpus, store: PredictionStore):
        self.corpus, self.store = corpus, store

    def execute(self, implementation):
        source, maps, audit = self.corpus.load()
        binding = {'version': VERSION, 'source_run_id': source['run_id'], 'source_sha256': fingerprint(source),
            'map_hashes': [fingerprint(m) for m in maps], 'origin_audit_sha256': fingerprint(audit), 'implementation': implementation}
        run_id = fingerprint(binding); previous = self.store.read_seal(run_id)
        if previous is not None:
            require(previous['binding'] == binding, 'Participant binding changed'); return previous
        result = {'run_id': run_id, 'binding': binding, **forecast(source, maps, audit)}
        self.store.seal(run_id, result)
        log.info('typed_participant_forecast_sealed run=%s blocks=%d parts=%d', run_id, result['canonical_blocks'], result['licensed_parts'])
        return self.store.read_seal(run_id)
