"""Отдельная публикация протоколов не меняет прогноз, ранжирование или исходные карты."""
import logging
from time import perf_counter

from application.ports.development_prediction import PredictionStore
from domain.article_maps import require, fingerprint, ArticleMapNotFound
from domain.analogy_protocol_reconciliation import reconcile_protocols, VERSION

log = logging.getLogger(__name__)


class ReconcileSealedAnalogyProtocols:
    def __init__(self, forecasts: PredictionStore, output: PredictionStore): self.forecasts, self.output = forecasts, output

    def execute(self, run_id, arguments, annotation, implementation):
        started = perf_counter(); forecast = self.forecasts.read_seal(run_id)
        if forecast is None: raise ArticleMapNotFound('Explicit sealed analogy forecast missing')
        require(fingerprint(forecast['binding']) == run_id and annotation['forecast_sha256'] == fingerprint(forecast),
                'Immutable forecast binding differs')
        require(fingerprint(arguments) == forecast['binding']['arguments_artifact_sha256']
                and arguments['run_id'] == forecast['binding']['arguments_run_id']
                and fingerprint(arguments['binding']) == arguments['run_id']
                and arguments['model_calls'] == 0 and arguments['target_read'] is False
                and arguments['binding']['metadata']['question'] is None, 'Explicit sealed source argument differs')
        graph = arguments['semantic_graph']
        excluded = arguments['binding']['metadata']['excluded_source_sha256']
        require(isinstance(excluded, list) and bool(excluded)
                and not ({p['source_sha256'] for p in graph['parents'].values()} & set(excluded)), 'Target source in protocol corpus')
        binding = {'version': VERSION, 'forecast_run_id': run_id, 'forecast_sha256': fingerprint(forecast),
            'arguments_artifact_sha256': fingerprint(arguments), 'semantic_graph_sha256': fingerprint(graph),
            'annotation_sha256': fingerprint(annotation), 'implementation': implementation}
        result = reconcile_protocols(forecast, graph, annotation)
        run = fingerprint(binding); previous = self.output.read_seal(run)
        if previous is not None:
            require(previous['binding'] == binding, 'Protocol immutable binding differs'); return previous
        self.output.seal(run, {'run_id': run, 'binding': binding, **result})
        log.info('analogy_protocol_reconciliation_sealed run=%s candidates=%d counts=%s seconds=%.3f',
            run, result['all_candidates_reviewed'], result['counts'], perf_counter() - started)
        return self.output.read_seal(run)
