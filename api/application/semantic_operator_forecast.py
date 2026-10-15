"""Обучение и фиксация выполняются до отдельного чтения удержанного вывода."""
from dataclasses import asdict
import logging
from application.ports.semantic_operator_forecast import OperatorCorpus, OperatorForecastStore
from domain.article_maps import fingerprint, require
from domain.semantic_operator_learning import learn, apply, VERSION, LIMITS, ordered_frame

log = logging.getLogger(__name__)


class SealOperatorForecast:
    def __init__(self, corpus: OperatorCorpus, store: OperatorForecastStore):
        self.corpus, self.store = corpus, store

    def execute(self, sources, application_ref, as_of, heldout_families, protocol_sha256):
        require(isinstance(sources, list) and sources and len(set(sources)) == len(sources), 'Explicit distinct source references required')
        require(application_ref not in sources and isinstance(application_ref, str) and application_ref, 'Separate premise-only application reference required')
        require(len(protocol_sha256) == 64, 'Protocol digest required')
        training = self.corpus.training(sources)
        require(len(training['bindings']) == len(sources), 'Exact source bindings required')
        require(not {k.family for k in training['knowledge']} & set(heldout_families), 'Heldout family leaked into training')
        request = self.corpus.premises(application_ref)
        require(all(k.family in heldout_families for k in request['knowledge']), 'Application must use explicitly heldout families')
        learned = learn(training['knowledge'], training['examples'], as_of, heldout_families)
        forecasts = {channel: apply(learned, request['knowledge'], as_of, channel, heldout_families)
                     for channel in ('clinical', 'research_task', 'method', 'reconstruction')}
        binding = {'sources': sources, 'training': training['bindings'], 'application_ref': application_ref,
                   'premises': request['binding'], 'as_of': as_of, 'heldout_families': list(heldout_families),
                   'protocol_sha256': protocol_sha256, 'version': VERSION, 'limits': LIMITS}
        # Семантический результат также включён в идентичность; несовместимый код не переиспользуется.
        payload = {'binding': binding, 'learned': learned, 'forecasts': forecasts,
                   'application_knowledge': [asdict(k) for k in request['knowledge']],
                   'projection_rejections': training.get('rejected', []), 'scientific_success': False, 'model_calls': 0}
        run_id = fingerprint(payload)
        artifact = {'run_id': run_id, **payload}
        self.store.seal(run_id, artifact)
        log.info('semantic_operator sealed run=%s sources=%d operators=%d clinical=%d', run_id, len(sources), len(learned['rules']), len(forecasts['clinical']['predictions']))
        return self.store.read_seal(run_id)


class EvaluateOperatorForecast:
    def __init__(self, corpus: OperatorCorpus, store: OperatorForecastStore):
        self.corpus, self.store = corpus, store

    def execute(self, run_id):
        sealed = self.store.read_seal(run_id)
        require(sealed and sealed['binding']['version'] == VERSION, 'Compatible seal required before evaluator read')
        require(sealed['run_id'] == fingerprint({k: v for k, v in sealed.items() if k != 'run_id'}), 'Prediction content changed')
        target = self.corpus.outcomes(sealed['binding']['application_ref'])
        require(target['binding']['premises_sha256'] == fingerprint(sealed['binding']['premises']), 'Evaluator premise version differs')
        require(target['binding']['source']['article_id'] == sealed['binding']['premises']['article_id']
                and target['binding']['source']['source_sha256'] == sealed['binding']['premises']['source_sha256'],
                'Evaluator article or source revision differs')
        require(all(k.family in sealed['binding']['heldout_families'] for k in target['knowledge']), 'Evaluator family differs')
        rows = {}
        for channel, result in sealed['forecasts'].items():
            rows[channel] = []
            for prediction in result['predictions']:
                matches = [k.claim_id for k in target['knowledge'] if k.source_id == prediction['source_id']
                           and ordered_frame(k.frame) == prediction['frame']]
                rows[channel].append({'prediction_id': prediction['id'], 'matched_semantic_units': matches,
                                      'status': 'exact_match_requires_review' if matches else 'not_confirmed_by_target',
                                      'absence_is_not_refutation': not bool(matches)})
        payload = {'prediction_run_id': run_id, 'prediction_sha256': fingerprint(sealed), 'target_binding': target['binding'],
                   'rows': rows, 'scientific_success': False, 'blind_test': False,
                   'note': 'Historical debugging material already inspected; task and method matches are not clinical success.'}
        evaluation_id = fingerprint(payload)
        result = {'evaluation_id': evaluation_id, **payload}
        self.store.save_evaluation(run_id, evaluation_id, result)
        log.info('semantic_operator evaluated run=%s target_units=%d', run_id, len(target['knowledge']))
        return result
