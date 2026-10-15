"""Точная цитата и поддержка доставки не превращаются в доказанный перенос эффекта."""
from copy import deepcopy
from hashlib import sha256
import pytest

from application.analogy_protocol_evidence import SealAnalogyProtocolEvidence
from domain.analogy_protocol_evidence import assess_protocol_evidence, VERSION
from domain.article_maps import ArticleMapError, fingerprint
from infrastructure.development_prediction_store import FilePredictionStore


def inputs():
    text = 'Синтетический источник 🙂: разные режимы и исходы.'
    unit = {'id': 'U1', 'start': 0, 'end': len(text), 'text': text}
    packet = {'source': {'text': text, 'sha256': sha256(text.encode()).hexdigest(),
                         'content_end': len(text), 'units': [unit], 'offset_encoding': 'unicode_codepoints'}}
    forecast = {'question': None, 'model_calls': 0, 'target_read': False, 'run_id': 'baseline',
        'binding': {'metadata': {'training_cutoff': '2022-12-31'}},
        'transport_tasks': [{'id': 'candidate', 'transport_obligations': {'unknown': ['target tissue']}}]}
    finding = {'id': 'finding', 'kind': 'binding_context', 'statement_ru': 'Синтетическое описание мишени.',
        'scope': {'target_tissue': 'unknown'}, 'causal_transfer_established': False, 'clinical_efficacy_established': False,
        'evidence': [{'source_id': 'source', 'unit_id': 'U1', 'start': 0, 'end': len(text), 'text': text,
                      'sha256': sha256(text.encode()).hexdigest()}]}
    audit = {'version': VERSION, 'author': 'Codex', 'expert_validated': False, 'model_calls': 0,
        'forecast_run_id': 'baseline', 'forecast_sha256': fingerprint(forecast),
        'sources': {'source': {'packet_sha256': fingerprint(packet), 'source_sha256': packet['source']['sha256'], 'published_on': '2020-01-01'}},
        'findings': [finding], 'candidate_reviews': [{'candidate_id': 'candidate',
            'obligations_sha256': fingerprint(forecast['transport_tasks'][0]['transport_obligations']),
            'findings': ['finding'], 'decision': 'transfer_not_established', 'remains_research_task': True,
            'unresolved': ['target_tissue_engagement'], 'reason_ru': 'Одна мишень не доказывает перенос.'}]}
    return forecast, {'source': packet}, audit


def test_complete_source_binding_retains_unknown_and_no_predictions():
    f, packets, a = inputs(); before = deepcopy((f, packets, a))
    r = assess_protocol_evidence(f, packets, a)
    assert before == (f, packets, a)
    assert r['candidate_count'] == 1 and r['confirmed_transfers'] == r['new_empirical_predictions'] == 0
    assert r['candidate_reviews'][0]['unresolved'] == ['target_tissue_engagement']
    assert not r['scientific_success'] and not r['graph_advantage_demonstrated']


@pytest.mark.parametrize('change', ['forecast', 'source_text', 'unit_text', 'unit_offset', 'reference', 'future_date',
                                 'evidence_text', 'evidence_hash', 'unknown_unit', 'unknown_source', 'unknown_finding',
                                 'duplicate_finding', 'missing_review', 'duplicate_review', 'obligations', 'promote',
                                 'missing_unknown', 'claim_causality', 'claim_clinical', 'scope_erased', 'model_called'])
def test_corrupted_or_overclaimed_protocol_is_rejected(change):
    f, packets, a = inputs(); finding = a['findings'][0]; row = a['candidate_reviews'][0]
    if change == 'forecast': f['run_id'] = 'different'
    elif change == 'source_text': packets['source']['source']['text'] += 'changed'
    elif change == 'unit_text':
        packets['source']['source']['units'][0]['text'] += 'changed'
        a['sources']['source']['packet_sha256'] = fingerprint(packets['source'])
    elif change == 'unit_offset':
        packets['source']['source']['units'][0]['end'] -= 1
        a['sources']['source']['packet_sha256'] = fingerprint(packets['source'])
    elif change == 'reference':
        packets['source']['source']['content_end'] -= 1
        a['sources']['source']['packet_sha256'] = fingerprint(packets['source'])
    elif change == 'future_date': a['sources']['source']['published_on'] = '2023-01-01'
    elif change == 'evidence_text': finding['evidence'][0]['text'] += 'changed'
    elif change == 'evidence_hash': finding['evidence'][0]['sha256'] = 'wrong'
    elif change == 'unknown_unit': finding['evidence'][0]['unit_id'] = 'unknown'
    elif change == 'unknown_source': finding['evidence'][0]['source_id'] = 'unknown'
    elif change == 'unknown_finding': row['findings'] = ['unknown']
    elif change == 'duplicate_finding': a['findings'].append(deepcopy(finding))
    elif change == 'missing_review': a['candidate_reviews'] = []
    elif change == 'duplicate_review': a['candidate_reviews'].append(deepcopy(row))
    elif change == 'obligations': row['obligations_sha256'] = 'wrong'
    elif change == 'promote': row['decision'] = 'verified_transfer'
    elif change == 'missing_unknown': row['unresolved'] = []
    elif change == 'claim_causality': finding['causal_transfer_established'] = True
    elif change == 'claim_clinical': finding['clinical_efficacy_established'] = True
    elif change == 'scope_erased': finding['scope'] = {}
    else: a['model_calls'] = 1
    with pytest.raises(ArticleMapError): assess_protocol_evidence(f, packets, a)


def test_seal_replay_network_forbidden_and_failure_does_not_create_result(tmp_path, monkeypatch):
    import socket
    import httpx
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **kw: pytest.fail('Сеть запрещена'))
    monkeypatch.setattr(httpx.Client, 'send', lambda *a, **kw: pytest.fail('Модели запрещены'))
    f, p, a = inputs(); store = FilePredictionStore(tmp_path); app = SealAnalogyProtocolEvidence(store)
    r = app.execute(f, p, a, {})
    assert r == app.execute(f, p, a, {}) and len(list(tmp_path.glob('*/seal.json'))) == 1
    wrong = deepcopy(a); wrong['candidate_reviews'][0]['decision'] = 'verified_transfer'
    with pytest.raises(ArticleMapError): app.execute(f, p, wrong, {})
    assert len(list(tmp_path.glob('*/seal.json'))) == 1
