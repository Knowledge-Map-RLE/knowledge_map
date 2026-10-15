"""Сначала фиксируется прогноз; удержанные результаты читает только оценщик."""
import logging
from domain.article_maps import require, fingerprint
from domain.empirical_question_forecast import ForecastRequest, Observation, forecast, score_prediction
from domain.guarded_empirical_transfer import VERSION, POLICY_SHA256, transfer, verify_record
from application.ports.guarded_empirical_transfer import TransferCorpus, TransferStore

log = logging.getLogger(__name__)


def payload_hash(value):
    return fingerprint({k: v for k, v in value.items() if k not in {'run_id', 'evaluation_id'}})


class SealEmpiricalTransfer:
    def __init__(self, corpus: TransferCorpus, store: TransferStore):
        self.corpus, self.store = corpus, store

    def execute(self, protocol):
        require(protocol.get('blind_test') is False and protocol.get('scientific_success') is False,
                'Previously inspected diagnostic cannot claim blind scientific success')
        training, requests = self.corpus.training(), self.corpus.requests()
        records = training['records']
        observations = [verify_record(r) for r in records]
        require(len({o.reference for o in observations}) == len(observations), 'Repeated training observation')
        require(len({r['id'] for r in requests['requests']}) == len(requests['requests']), 'Repeated target request')
        forecasts = []
        for row in requests['requests']:
            require(set(row) == {'id', 'request', 'context_evidence'}, 'Target requests must be context-only')
            request = ForecastRequest.parse(row['request'])
            # Физический обучающий пакет не должен содержать даже отфильтрованные ответы удержанной семьи.
            require(all(o.family not in request.excluded_families and o.available_on < request.as_of for o in observations),
                    'Training package contains target family or future source')
            require(set(row['context_evidence']) == {'source_sha256', 'run_id', 'context_sha256', 'origin', 'method_spans', 'temporal_status'},
                    'Context evidence cannot contain findings or outcome frames')
            require(row['context_evidence']['context_sha256'] == fingerprint(request.context), 'Target context changed')
            require(row['context_evidence']['temporal_status'] == 'retrospective_design_specification', 'Unproved prospectivity cannot be asserted')
            result = {mode: forecast(observations, request, mode) for mode in ['known_union', 'frequency', 'semantic']}
            result['guarded_transport'] = transfer(records, request)
            forecasts.append({'id': row['id'], 'context_evidence': row['context_evidence'], 'modes': result})
        artifact = {'version': VERSION, 'policy_sha256': POLICY_SHA256, 'protocol': protocol,
                    'training_sha256': fingerprint(training), 'requests_sha256': fingerprint(requests),
                    'forecasts': forecasts, 'model_calls': 0, 'blind_test': False, 'scientific_success': False}
        artifact['run_id'] = payload_hash(artifact)
        self.store.seal(artifact['run_id'], artifact)
        log.info('empirical_transfer sealed run=%s requests=%s families=%s', artifact['run_id'], len(forecasts), len({o.family for o in observations}))
        return artifact


class EvaluateEmpiricalTransfer:
    def __init__(self, corpus: TransferCorpus, store: TransferStore):
        self.corpus, self.store = corpus, store

    def execute(self, run_id):
        sealed = self.store.read_seal(run_id)
        require(sealed['run_id'] == run_id == payload_hash(sealed), 'Sealed forecast changed')
        require(sealed['version'] == VERSION and sealed['policy_sha256'] == POLICY_SHA256, 'Incompatible transfer version')
        controls = self.corpus.outcomes()
        require(controls['requests_sha256'] == sealed['requests_sha256'], 'Outcomes belong to another context revision')
        require(set(controls['targets']) == {row['id'] for row in sealed['forecasts']}, 'Evaluator targets differ from sealed requests')
        scores = []
        for row in sealed['forecasts']:
            control = controls['targets'][row['id']]
            observation = verify_record(control)
            request = row['modes']['frequency']['request']
            require(observation.context == request['context'] and observation.family in request['excluded_families']
                    and observation.available_on == request['as_of'], 'Heldout outcome differs from sealed scope')
            evidence = row['context_evidence']
            require(observation.binding['source_sha256'] == evidence['source_sha256'] and observation.binding['run_id'] == evidence['run_id'],
                    'Heldout source revision changed')
            modes = {mode: score_prediction(prediction, [observation]) for mode, prediction in row['modes'].items()}
            scores.append({'id': row['id'], 'observed_findings': observation.findings, 'semantic_evidence': control['semantic_evidence'], 'modes': modes})
        evaluation = {'version': VERSION, 'run_id': run_id, 'sealed_sha256': fingerprint(sealed),
                      'outcomes_sha256': fingerprint(controls), 'scores': scores, 'blind_test': False,
                      'scientific_success': False, 'expert_validated': False, 'model_calls': 0}
        evaluation['evaluation_id'] = payload_hash(evaluation)
        self.store.evaluate(run_id, evaluation['evaluation_id'], evaluation)
        log.info('empirical_transfer evaluated run=%s requests=%s', run_id, len(scores))
        return evaluation
