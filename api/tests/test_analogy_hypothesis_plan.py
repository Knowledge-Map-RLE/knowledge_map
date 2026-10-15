"""Неизвестный механизм не запрещает гипотезу и не становится подтверждением."""
from copy import deepcopy
import pytest

from domain.article_maps import ArticleMapError, fingerprint
from domain.analogy_hypothesis_plan import generate_hypothesis_plan, VERSION
from application.analogy_hypothesis_plan import SealAnalogyHypothesisPlan
from infrastructure.development_prediction_store import FilePredictionStore


def inputs():
    frame = {'kind': 'state', 'action_status': None, 'logic': 'single', 'statements': [{
        'predicate': 'induction attenuated', 'negated': False, 'attributes': [],
        'roles': [{'role': 'gene', 'value': 'synthetic gene'}, {'role': 'intervention', 'value': 'synthetic intervention'},
                  {'role': 'population', 'value': 'synthetic population'}],
        'scope': {'time': '6 hours', 'conditions': ['constraint'], 'modality': None, 'quantifier': 'some'}}]}
    task = {'id': 'candidate', 'proposed_qualitative_frame': frame, 'transport_obligations': {'unknown': 'mechanism'},
            'logical_entailment': False, 'causal_transport_established': False, 'witnesses': [{'complete_parent': 'retained'}]}
    forecast = {'run_id': 'baseline', 'question': None, 'target_read': False, 'model_calls': 0,
        'transport_tasks': [task], 'hypotheses': [], 'canonical_blocks': 3, 'native_statements': 4,
        'ablation': {'same_proposal_ids': True}}
    review = {'candidate_id': 'candidate', 'decision': 'transfer_not_established',
        'unresolved': ['mechanism'], 'findings': ['finding']}
    audit = {'run_id': 'audit', 'forecast_run_id': 'baseline', 'binding': {'forecast_sha256': fingerprint(forecast)},
        'target_read': False, 'model_calls': 0, 'confirmed_transfers': 0, 'candidate_reviews': [review]}
    row = {'candidate_id': 'candidate', 'frame_sha256': fingerprint(frame),
        'obligations_sha256': fingerprint(task['transport_obligations']), 'review_sha256': fingerprint(review),
        'unknown_dimensions': ['mechanism'], 'statement_ru': 'Синтетическая гипотеза снижения.',
        'falsification_ru': 'Надёжное противоположное направление.', 'assumptions_ru': ['Перенос не установлен.'],
        'probability': None, 'effect_size': None, 'predicted_p_value': None,
        'proposed_protocol': {'status': 'proposed_design_not_observed_fact', 'intervention': {'identity': 'synthetic intervention'},
            'population': {'source_population_label': 'synthetic population'}, 'challenge': {'identity': 'challenge'},
            'comparator': {'identity': 'vehicle'}, 'measurement': {'endpoint_role': 'gene', 'endpoint_value': 'synthetic gene'},
            'assessment_time': {'source_scope': '6 hours'}, 'design_choices': ['Предложенный опыт.'], 'evidence_findings': ['finding']}}
    plan = {'version': VERSION, 'author': 'Codex', 'expert_validated': False,
        'forecast_sha256': fingerprint(forecast), 'protocol_audit_sha256': fingerprint(audit), 'target_read': False,
        'model_calls': 0, 'question': None, 'registered_at_utc': '2026-10-10T14:00:00+00:00',
        'historical_debug_corpus': True, 'prospective_scientific_validation': False, 'candidate_protocols': [row],
        'evaluation_policy': {'unmeasured_is_not_refuted': True, 'statistical_nondetection': 'inconclusive',
            'unknown_context': 'not_confirmed', 'repeated_known_outcome': 'exclude',
            'condition_on_predicted_response': False, 'unit_of_scoring': 'prespecified_endpoint', 'candidate_budget': 1}}
    return forecast, audit, plan


def test_uncertainty_allows_falsifiable_direction_not_verified_result():
    f, a, p = inputs(); before = deepcopy((f, a, p))
    r = generate_hypothesis_plan(f, a, p); h = r['hypotheses'][0]
    assert (f, a, p) == before and r['hypothesis_count'] == 1
    assert h['direction'] == 'lower_induction' and h['unknown_dimensions'] == ['mechanism']
    assert h['frame']['statements'][0]['scope']['conditions'] == ['constraint']
    assert h['frame']['statements'][0]['scope']['quantifier'] == 'some'
    assert h['witnesses'] == f['transport_tasks'][0]['witnesses']
    assert h['unmodified_analogy_frame'] == f['transport_tasks'][0]['proposed_qualitative_frame']
    assert h['knowledge_status'] == 'hypothesis' and not h['confirmed']
    assert r['accuracy'] is None and r['confirmed_predictions'] == r['future_results_scored'] == 0
    assert not r['scientific_success'] and not r['graph_advantage_demonstrated']


@pytest.mark.parametrize('change', ['source', 'audit', 'frame', 'obligations', 'review', 'unknown', 'subset', 'duplicate',
    'outcome', 'factor', 'population', 'time', 'observed', 'confidence', 'effect', 'significance', 'future_read',
    'model', 'question', 'mechanism_as_eligibility', 'nondetection', 'timestamp', 'prospective_claim'])
def test_rejects_context_erasure_and_post_outcome_plan(change):
    f, a, p = inputs(); row = p['candidate_protocols'][0]; protocol = row['proposed_protocol']
    if change == 'source': p['forecast_sha256'] = 'wrong'
    elif change == 'audit': p['protocol_audit_sha256'] = 'wrong'
    elif change == 'frame': row['frame_sha256'] = 'wrong'
    elif change == 'obligations': row['obligations_sha256'] = 'wrong'
    elif change == 'review': row['review_sha256'] = 'wrong'
    elif change == 'unknown': row['unknown_dimensions'] = []
    elif change == 'subset': p['candidate_protocols'] = []
    elif change == 'duplicate': p['candidate_protocols'].append(deepcopy(row))
    elif change == 'outcome': protocol['measurement']['endpoint_value'] = 'other gene'
    elif change == 'factor': protocol['intervention']['identity'] = 'other drug'
    elif change == 'population': protocol['population']['source_population_label'] = 'humans'
    elif change == 'time': protocol['assessment_time']['source_scope'] = 'years'
    elif change == 'observed': protocol['status'] = 'observed_effect'
    elif change == 'confidence': row['probability'] = 0.9
    elif change == 'effect': row['effect_size'] = 10
    elif change == 'significance': row['predicted_p_value'] = 0.001
    elif change == 'future_read': p['target_read'] = True
    elif change == 'model': p['model_calls'] = 1
    elif change == 'question': p['question'] = 'Chosen endpoint?'
    elif change == 'mechanism_as_eligibility': p['evaluation_policy']['condition_on_predicted_response'] = True
    elif change == 'nondetection': p['evaluation_policy']['statistical_nondetection'] = 'confirmed'
    elif change == 'timestamp': p['registered_at_utc'] = '2026-10-10T14:00:00'
    else: p['prospective_scientific_validation'] = True
    with pytest.raises(ArticleMapError): generate_hypothesis_plan(f, a, p)


def test_replay_and_bad_plan_never_publishes_second_result(tmp_path, monkeypatch):
    import socket
    import httpx
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **kw: pytest.fail('Запрещена сеть'))
    monkeypatch.setattr(httpx.Client, 'send', lambda *a, **kw: pytest.fail('Запрещены модели'))
    f, a, p = inputs(); store = FilePredictionStore(tmp_path); app = SealAnalogyHypothesisPlan(store)
    r = app.execute(f, a, p, {}); assert r == app.execute(f, a, p, {})
    p['candidate_protocols'][0]['probability'] = .95
    with pytest.raises(ArticleMapError): app.execute(f, a, p, {})
    assert len(list(tmp_path.glob('*/seal.json'))) == 1
