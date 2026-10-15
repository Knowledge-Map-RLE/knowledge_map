"""Раздельный аудит контекста и математические выводы без чтения оценочной цели."""
import logging
from domain.article_maps import require, fingerprint
from domain.empirical_question_forecast import ForecastRequest
from domain.semantic_context_bridges import VERSION, POLICY, audit_context, derive_representation, counterexamples
from application.ports.context_bridges import BridgeCorpus, BridgeStore
log = logging.getLogger(__name__)


class AuditContextBridges:
    def __init__(self, corpus: BridgeCorpus, store: BridgeStore): self.corpus, self.store = corpus, store

    def execute(self, protocol):
        data = self.corpus.contexts()
        require(len({s['reference'] for s in data['sources']}) == len(data['sources']), 'Repeated source')
        require(len({r['id'] for r in data['requests']}) == len(data['requests']), 'Repeated request')
        audits = []
        for target in data['requests']:
            require(set(target) == {'id', 'request'}, 'Context audit cannot receive outcomes')
            request = ForecastRequest.parse(target['request'])
            require(all(s['family'] not in request.excluded_families and s['available_on'] < request.as_of for s in data['sources']), 'Context package includes target family or future source')
            audits.append({'id': target['id'], 'request': target['request'],
                           'sources': [audit_context(s, request) for s in data['sources']]})
        artifact = {'version': VERSION, 'kind': 'context_audit_not_forecast', 'policy': POLICY,
                    'protocol': protocol, 'input_sha256': fingerprint(data), 'audits': audits,
                    'counterexamples': counterexamples(), 'model_calls': 0, 'scientific_prediction': False,
                    'clinical_predictions': 0, 'blind_test': False}
        artifact['run_id'] = fingerprint(artifact); self.store.seal(artifact['run_id'], artifact)
        log.info('context_bridges audited run=%s requests=%s', artifact['run_id'], len(audits))
        return artifact


class DeriveNumericalRepresentations:
    def __init__(self, corpus: BridgeCorpus, store: BridgeStore): self.corpus, self.store = corpus, store

    def execute(self):
        data = self.corpus.mathematical_cases()
        rows = [{**case, 'derived': derive_representation(case['effect'], case['mapping'])} for case in data['cases']]
        artifact = {'version': VERSION, 'kind': 'same_analysis_mathematical_representations',
                    'input_sha256': fingerprint(data), 'rows': rows, 'model_calls': 0,
                    'scientific_prediction': False, 'clinical_predictions': 0}
        artifact['run_id'] = fingerprint(artifact); self.store.seal(artifact['run_id'], artifact)
        log.info('context_bridges reparameterized run=%s cases=%s', artifact['run_id'], len(rows))
        return artifact
