"""Внешний перенос не подменяет временной контроль совпадением общего направления."""
from copy import deepcopy
from hashlib import sha256
import json

import pytest

from application.external_operation_transfer import SealExternalOperationTransfer
from domain.article_maps import ArticleMapError, fingerprint
from domain.external_operation_transfer import forecast_external, evaluate_external
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.external_operation_inputs import FileExternalReceivers, FileExternalOutcomes
from tests.test_conditional_operation_transfer import prepared


def external_inputs():
    cases, receivers, groups, coverage = prepared(True)
    receiver = deepcopy(receivers[0]); old_article = receiver['article_id']
    receiver.update(id='external-case', article_id='external-study', primary_family='external-family')
    for part in receiver['body']:
        for field in ('key', 'native_key'):
            part[field] = ['external-study', part[field][1]]
        atom = part['frame']['statements'][0]
        atom['scope']['study_group'] = 'external-study'
        for role in atom['roles']:
            role['value'] = role['value'].replace(old_article, 'external-study')
    training = {'input_run_id': 'upstream', 'input_sha256': 'bound', 'cases': cases,
        'author_groups': groups, 'coverage': coverage,
        'source_article_ids': [c['article_id'] for c in cases] + ['registered-without-case']}
    packet = {'version': 'source-method-only-receivers-1', 'author': 'Codex', 'expert_validated': False,
        'source_packet_sha256': 'bound-source', 'source_sha256': receiver['source_sha256'],
        'receivers': [receiver], 'method_evidence': [{'receiver_id': receiver['id'], 'quotes': []}],
        'model_calls': 0, 'results_previously_disclosed': True, 'blind_control': False,
        'temporal_train_test_split': False, 'author_script_sha256': 'script', 'scope_ru': 'Ретроспективный тест'}
    outcome = {'id': receiver['id'], 'source_sha256': receiver['source_sha256'],
        'qualitative_direction': 'lower_clinical_burden', 'outcome_class': 'clinical_eae_burden',
        'reported_initial_effect_end': '24', 'limitations_ru': ['Позднее потеря ответа'], 'evidence': ['source quote']}
    return training, packet, {receiver['id']: outcome}


def test_external_forecast_preserves_methods_and_excludes_external_heads():
    training, packet, outcomes = external_inputs(); before = deepcopy((training, packet))
    result = forecast_external(training, packet)
    assert (training, packet) == before and result['target_question'] is None
    assert not result['external_results_used_in_training'] and not result['temporal_train_test_split']
    for mode in ('graph', 'without_dependencies'):
        candidate = result['modes'][mode][0]['predictions'][0]
        assert len(candidate['support_families']) == 3
        assert packet['receivers'][0]['primary_family'] not in candidate['support_families']
        assert candidate['receiver'] == packet['receivers'][0]
        assert not candidate['deductive_entailment'] and 'temporal_scope' not in candidate['head']
    assert not result['modes']['permuted_dependencies'][0]['predictions']
    evaluation = evaluate_external(result, outcomes)
    row = evaluation['modes']['graph'][0]
    assert row['relation'] == 'direction_match_temporal_scope_unresolved'
    assert not row['full_fact_equivalence'] and not row['independent_scientific_confirmation']


@pytest.mark.parametrize('change', ['article', 'registered_article', 'family', 'missing_registry',
    'result_field', 'method_identity', 'source', 'blind', 'temporal'])
def test_leaks_and_false_experiment_claims_are_rejected(change):
    training, packet, _ = external_inputs(); receiver = packet['receivers'][0]
    if change == 'article': receiver['article_id'] = training['cases'][0]['article_id']
    elif change == 'registered_article': receiver['article_id'] = 'registered-without-case'
    elif change == 'family': receiver['primary_family'] = training['cases'][0]['primary_family']
    elif change == 'missing_registry': training['source_article_ids'] = []
    elif change == 'result_field': packet['outcomes'] = 'not allowed'
    elif change == 'method_identity': packet['method_evidence'][0]['receiver_id'] = 'other'
    elif change == 'source': receiver['source_sha256'] = 'other'
    elif change == 'blind': packet['blind_control'] = True
    elif change == 'temporal': packet['temporal_train_test_split'] = True
    with pytest.raises(ArticleMapError): forecast_external(training, packet)


@pytest.mark.parametrize('change', ['unknown_phase', 'prophylaxis', 'different_target', 'single_family'])
def test_insufficient_or_incompatible_support_does_not_predict(change):
    training, packet, _ = external_inputs()
    if change == 'single_family':
        for c in training['cases']: c['primary_family'] = 'same-family'
    else:
        receiver = packet['receivers'][0]
        axis = 'target' if change == 'different_target' else 'phase'
        receiver['features'][axis] = None if change == 'unknown_phase' else change
        if change == 'unknown_phase': receiver['feature_evidence'][axis] = []
    result = forecast_external(training, packet)
    assert not any(f['predictions'] for folds in result['modes'].values() for f in folds)


def test_changed_outcome_never_changes_forecast_and_temporal_scope_is_not_auto_confirmed():
    training, packet, outcomes = external_inputs(); result = forecast_external(training, packet)
    before = deepcopy(result)
    outcomes['external-case']['qualitative_direction'] = 'higher_clinical_burden'
    assert evaluate_external(result, outcomes)['modes']['graph'][0]['relation'] == 'direction_mismatch'
    assert result == before
    outcomes['external-case']['qualitative_direction'] = 'lower_clinical_burden'
    result['modes']['graph'][0]['predictions'][0]['head']['temporal_scope'] = 'until day 28'
    row = evaluate_external(result, outcomes)['modes']['graph'][0]
    assert row['relation'] == 'requires_typed_temporal_evaluator' and not row['full_fact_equivalence']
    outcomes['external-case']['source_sha256'] = 'foreign'
    with pytest.raises(ArticleMapError): evaluate_external(result, outcomes)


def test_application_seals_before_outcomes_and_keeps_failed_evaluation_resumable(tmp_path, monkeypatch):
    import socket
    import httpx
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('Network forbidden'))
    monkeypatch.setattr(httpx.Client, 'send', lambda *a, **k: pytest.fail('Model calls forbidden'))
    training, packet, outcomes = external_inputs(); store = FilePredictionStore(tmp_path)
    class Training:
        def load(self): return deepcopy(training)
    class Receiver:
        def load(self): return deepcopy(packet)
    class Outcome:
        fail = True
        def load(self):
            assert len(list(tmp_path.glob('*/seal.json'))) == 1
            if self.fail: raise ArticleMapError('Separate evaluation unavailable')
            return deepcopy(outcomes)
    port = Outcome(); app = SealExternalOperationTransfer(Training(), Receiver(), port, store)
    with pytest.raises(ArticleMapError): app.execute({'code': 'fixed'})
    assert not list(tmp_path.glob('*/evaluations/*.json'))
    port.fail = False
    result = app.execute({'code': 'fixed'})
    assert result == app.execute({'code': 'fixed'})
    assert len(list(tmp_path.glob('*/evaluations/*.json'))) == 1


def test_external_source_offsets_hash_and_separate_files_are_verified(tmp_path):
    _, packet, outcomes = external_inputs(); text = 'Метод 🧠 проверен. Результат измерен.'
    fragment = 'Метод 🧠 проверен.'
    evidence = {'unit_id': 'U1', 'start': 0, 'end': len(fragment), 'text': fragment,
                'sha256': sha256(fragment.encode()).hexdigest()}
    full = {'source': {'text': text, 'sha256': sha256(text.encode()).hexdigest(),
        'offset_encoding': 'unicode_codepoints', 'content_end': len(text),
        'units': [{'id': 'U1', 'start': 0, 'end': len(text)}]}}
    receiver = packet['receivers'][0]; receiver['source_sha256'] = full['source']['sha256']
    packet.update(source_packet_sha256=fingerprint(full), source_sha256=full['source']['sha256'])
    for axis in receiver['feature_evidence']: receiver['feature_evidence'][axis] = [deepcopy(evidence)]
    packet['method_evidence'][0]['quotes'] = [deepcopy(evidence)]
    outcomes['external-case'].update(source_sha256=full['source']['sha256'], evidence=[deepcopy(evidence)])
    paths = [tmp_path / name for name in ('source.json', 'methods.json', 'outcomes.json')]
    for path, value in zip(paths, [full, packet, {'source_packet_sha256': fingerprint(full),
        'model_calls': 0, 'outcomes': list(outcomes.values())}]):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    assert FileExternalReceivers(paths[1], paths[0]).load() == packet
    assert FileExternalOutcomes(paths[2], paths[0]).load() == outcomes
    packet['method_evidence'][0]['quotes'][0]['end'] += 1
    paths[1].write_text(json.dumps(packet), encoding='utf-8')
    with pytest.raises(ArticleMapError): FileExternalReceivers(paths[1], paths[0]).load()
