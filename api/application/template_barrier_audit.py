"""Неизменяемый аудит явно указанного прогноза, без генерации новых знаний."""
from time import perf_counter
import logging

from domain.article_maps import fingerprint, require
from domain.template_barrier_audit import analyze, VERSION
from application.ports.development_prediction import PredictionStore

log = logging.getLogger(__name__)


class SealTemplateBarrierAudit:
    def __init__(self, store: PredictionStore):
        self.store = store

    def execute(self, artifact, implementation):
        binding = {'input_run_id': artifact['run_id'], 'input_sha256': fingerprint(artifact),
                   'version': VERSION, 'implementation': implementation}
        run = fingerprint(binding)
        previous = self.store.read_seal(run)
        if previous is not None:
            require(previous['binding'] == binding, 'Diagnostic binding differs')
            return previous
        start = perf_counter()
        result = {'run_id': run, 'binding': binding, **analyze(artifact)}
        self.store.seal(run, result)
        log.info('template_barrier_audit_sealed run=%s input=%s blocks=%d seconds=%.3f',
                 run, artifact['run_id'], result['canonical_blocks'], perf_counter() - start)
        return self.store.read_seal(run)
