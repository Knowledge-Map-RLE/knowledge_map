"""Запечатанный сценарий синтеза читает только выбранный полный корпус."""
import logging
from time import perf_counter

from application.ports.development_prediction import PredictionStore
from domain.article_maps import ArticleMapNotFound, fingerprint, require
from domain.finite_test_synthesis import VERSION, synthesize_all_finite_tests

log = logging.getLogger(__name__)


class SynthesizeSealedFiniteTests:
    def __init__(self, sources: PredictionStore, output: PredictionStore):
        self.sources, self.output = sources, output

    def execute(self, source_run_id, implementation):
        started = perf_counter(); source = self.sources.read_seal(source_run_id)
        if source is None:
            raise ArticleMapNotFound('Sealed finite-test source missing')
        require(fingerprint(source['binding']) == source_run_id and source['model_calls'] == 0
                and source['target_read'] is False and source['binding']['metadata']['question'] is None,
                'Source-only finite-test snapshot required')
        excluded = source['binding']['metadata']['excluded_source_sha256']
        require(excluded and all(p['source_sha256'] not in excluded for p in source['semantic_graph']['parents'].values()),
                'Excluded target source entered finite synthesis')
        binding = {'source_run_id': source_run_id, 'source_artifact_sha256': fingerprint(source),
                   'implementation': implementation, 'operator_version': VERSION}
        run = fingerprint(binding); previous = self.output.read_seal(run)
        if previous is not None:
            require(previous['binding'] == binding, 'Finite synthesis binding differs'); return previous
        log.info('finite_test_synthesis_start run=%s source=%s', run, source_run_id)
        result = {'run_id': run, 'binding': binding,
                  **synthesize_all_finite_tests(source['semantic_graph'], source['argument_circuits'])}
        self.output.seal(run, result)
        log.info('finite_test_synthesis_sealed run=%s groups=%d computed=%d seconds=%.3f',
                 run, len(result['author_groups']), result['counts'].get('finite_profile_computed', 0), perf_counter() - started)
        return self.output.read_seal(run)
