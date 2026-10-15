"""Фиксация интервальных следствий отделена от файлов и источниковых лицензий."""
import logging
from typing import Protocol
from domain.article_maps import fingerprint, require
from domain.interval_knowledge import VERSION, analyze
from application.ports.development_prediction import PredictionStore

log = logging.getLogger(__name__)


class IntervalInputs(Protocol):
    def load(self): ...


class SealIntervalKnowledge:
    def __init__(self, inputs: IntervalInputs, store: PredictionStore):
        self.inputs, self.store = inputs, store

    def execute(self, implementation):
        baseline, frozen, maps, origins, audit = self.inputs.load()
        binding = {'version': VERSION, 'baseline_sha256': fingerprint(baseline), 'source_sha256': fingerprint(frozen),
            'map_hashes': [fingerprint(m) for m in maps], 'origin_audit_sha256': fingerprint(origins),
            'audit_sha256': fingerprint(audit), 'implementation': implementation}
        run = fingerprint(binding); old = self.store.read_seal(run)
        if old is not None:
            require(old['binding'] == binding, 'Interval binding changed'); return old
        result = {'run_id': run, 'binding': binding, **analyze(baseline, frozen, maps, origins, audit)}
        self.store.seal(run, result)
        log.info('interval_knowledge_sealed run=%s blocks=%d consequences=%d', run, result['canonical_blocks'], len(result['interval_consequences']))
        return self.store.read_seal(run)
