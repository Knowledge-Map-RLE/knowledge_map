"""Адресный аудит неизменяемого прогноза не заменяет его новой генерацией."""
import logging
from typing import Protocol

from domain.article_maps import fingerprint, require
from domain.forecast_claim_qualification import VERSION, qualify
from application.ports.development_prediction import PredictionStore

log = logging.getLogger(__name__)


class QualificationInputs(Protocol):
    def load(self): ...


class SealForecastClaimQualification:
    def __init__(self, inputs: QualificationInputs, store: PredictionStore):
        self.inputs, self.store = inputs, store

    def execute(self, implementation):
        frozen, maps, audit = self.inputs.load()
        binding = {'version': VERSION, 'forecast_sha256': fingerprint(frozen),
            'map_hashes': [fingerprint(m) for m in maps], 'audit_sha256': fingerprint(audit),
            'implementation': implementation}
        run = fingerprint(binding); previous = self.store.read_seal(run)
        if previous is not None:
            require(previous['binding'] == binding, 'Qualification binding changed'); return previous
        result = {'run_id': run, 'binding': binding, **qualify(frozen, maps, audit)}
        self.store.seal(run, result)
        log.info('forecast_claim_qualification_sealed run=%s blocks=%d candidates=%d',
                 run, result['canonical_blocks'], len(result['candidates']))
        return self.store.read_seal(run)
