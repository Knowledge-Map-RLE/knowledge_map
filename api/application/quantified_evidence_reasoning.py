"""Оператор использует только явно выбранный запечатанный источник авторских цепочек."""
import logging
from time import perf_counter

from application.ports.development_prediction import PredictionStore
from domain.article_maps import require, fingerprint, ArticleMapNotFound
from domain.author_argument_circuits import VERSION as CIRCUIT_VERSION
from domain.quantified_evidence_reasoning import reason_over_quantified_evidence, VERSION

log = logging.getLogger(__name__)


class ReasonSealedQuantitativeEvidence:
    def __init__(self, sources: PredictionStore, output: PredictionStore):
        self.sources, self.output = sources, output

    def execute(self, source_run_id, implementation):
        started = perf_counter(); source = self.sources.read_seal(source_run_id)
        if source is None: raise ArticleMapNotFound('Sealed argument source missing')
        require(fingerprint(source['binding']) == source_run_id, 'Argument run identity differs from its binding')
        require(source['argument_circuits']['version'] == CIRCUIT_VERSION and source['target_read'] is False
            and source['model_calls'] == 0 and source['binding']['metadata']['question'] is None, 'Source-only complete argument snapshot required')
        binding = {'source_run_id': source_run_id, 'source_artifact_sha256': fingerprint(source),
            'implementation': implementation, 'operator_version': VERSION}
        run = fingerprint(binding); previous = self.output.read_seal(run)
        if previous is not None:
            require(previous['binding'] == binding, 'Quantitative snapshot binding differs'); return previous
        log.info('quantified_evidence_reasoning_start run=%s source=%s', run, source_run_id)
        result = {'run_id': run, 'binding': binding, **reason_over_quantified_evidence(source['semantic_graph'])}
        self.output.seal(run, result)
        log.info('quantified_evidence_reasoning_sealed run=%s blocks=%d proofs=%d seconds=%.3f',
            run, result['canonical_blocks'], len(result['proofs']), perf_counter() - started)
        return self.output.read_seal(run)
