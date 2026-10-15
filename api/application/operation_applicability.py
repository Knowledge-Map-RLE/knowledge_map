"""Публикует отдельный контракт, не изменяя карты и старые прогнозы."""
import logging
from time import perf_counter
from typing import Protocol

from application.ports.development_prediction import PredictionStore
from domain.article_maps import fingerprint, require
from domain.operation_applicability import analyze, VERSION

log = logging.getLogger(__name__)


class ForecastCorpus(Protocol):
    def load(self): ...


class SealOperationApplicability:
    def __init__(self, corpus: ForecastCorpus, store: PredictionStore):
        self.corpus, self.store = corpus, store

    def execute(self, audit, implementation):
        started = perf_counter(); forecast, maps, origin = self.corpus.load()
        binding = {'version': VERSION, 'input_run_id': forecast['run_id'], 'input_sha256': fingerprint(forecast),
                   'audit_sha256': fingerprint(audit), 'map_hashes': [fingerprint(m) for m in maps],
                   'implementation': implementation}
        run = fingerprint(binding); previous = self.store.read_seal(run)
        if previous is not None:
            require(previous['binding'] == binding, 'Applicability binding changed'); return previous
        log.info('operation_applicability_start run=%s sources=%d', run, len(maps))
        result = {'run_id': run, 'binding': binding, **analyze(forecast, maps, origin, audit)}
        self.store.seal(run, result)
        log.info('operation_applicability_sealed run=%s contracts=%d supported_shapes=%d seconds=%.3f',
                 run, len(result['cases']), sum(s['minimum_primary_support'] for s in result['schemata']), perf_counter() - started)
        return self.store.read_seal(run)
