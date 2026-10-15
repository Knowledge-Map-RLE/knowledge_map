"""Исключение всей семьи, запрет исхода во входе и раздельная фиксация оценки."""
from copy import deepcopy

import pytest

from application.conditional_operation_transfer import SealConditionalOperationTransfer
from domain.article_maps import ArticleMapError, fingerprint
from domain.conditional_operation_transfer import (
    MODES, apply_rules, evaluate_transfers, forecast_transfers, learn, receiver_from_case,
    reapply_without_holdout,
)
from domain.operation_applicability import AXES, analyze
from infrastructure.development_prediction_store import FilePredictionStore
from tests.test_operation_applicability import inputs


def prepared(all_manifest=False):
    values = inputs()
    for m in values[1]:
        m['graph']['concepts'].append({'id': 'C6', 'display_text': 'control '+m['article_id'], 'aliases': []})
        for k in (m['graph']['knowledge'][0], m['graph']['knowledge'][2]):
            k['semantic_frame']['statements'][0]['roles'].append(
                {'role': 'comparator', 'concept_id': 'C6', 'knowledge_id': None})
    # Синтетические представления пересобираются после добавления явно связанного контроля.
    from domain.semantic_part_forecast import forecast_parts
    maps, origin = values[1:3]
    for record in origin['sources']:
        m = next(m for m in maps if m['article_id'] == record['article_id'])
        record['graph_sha256'] = fingerprint(m['graph'])
        for k in record['knowledge']:
            k['knowledge_sha256'] = fingerprint(next(n for n in m['graph']['knowledge'] if n['knowledge_id'] == k['knowledge_id']))
    projected = forecast_parts(maps, {m['article_id']:m['article_id'] for m in maps}, None, None, origin)
    projected['binding'] = values[0]['binding']; projected['run_id'] = values[0]['run_id']
    for c in values[-1]['cases']:
        for field, kid in (('method','K1'), ('measurement','K2'), ('result','K3')):
            c[field] = next(v['key'] for v in projected['part_views'] if v['native_key'] == (c['id'],kid))
        c['graph_sha256'] = fingerprint(next(m['graph'] for m in maps if m['article_id'] == c['id']))
    values = (projected, maps, origin, values[-1])
    values[-1]['input_sha256'] = fingerprint(projected)
    if all_manifest:
        for c in values[-1]['cases']:
            c['features']['phase'] = 'manifest_disease'
    audited = analyze(*values)
    cases = audited['cases']
    receivers = [receiver_from_case(c) for c in cases]
    groups = [[(tuple(c['method']['native_key']), tuple(c['measurement']['native_key'])),
               tuple(c['result']['native_key'])] for c in cases]
    return cases, receivers, groups, audited['coverage']


def outcomes(cases):
    return {c['case_id']: {k: deepcopy(c[k]) for k in ('qualitative_direction', 'outcome_class')}
            for c in cases}


def test_three_independent_training_families_support_held_out_pattern_not_a_theorem():
    data = prepared(True)
    before = deepcopy(data)
    result = forecast_transfers(*data)
    assert data == before and not result['held_out_results_used_for_learning'] and result['question'] is None
    assert result['retrospective_annotation_and_validation_used_results']
    for mode in ('graph', 'without_dependencies'):
        assert sum(len(f['predictions']) for f in result['modes'][mode]) == 3
        for fold in result['modes'][mode]:
            candidate = fold['predictions'][0]
            assert len(candidate['support_families']) == 2
            assert fold['held_out_family'] not in candidate['support_families']
            assert not candidate['deductive_entailment']
            comparator = next(role['value'] for role in candidate['receiver']['body'][0]['frame']['statements'][0]['roles']
                              if role['role'] == 'comparator')
            assert candidate['head']['participants']['comparator'] == comparator
            assert candidate['receiver'] == next(r for r in data[1] if r['id'] == fold['receiver_id'])
    assert not any(f['predictions'] for f in result['modes']['permuted_dependencies'])
    evaluation = evaluate_transfers(result, outcomes(data[0]))
    assert len(evaluation['modes']['graph']) == 3
    assert all(e['relation'] == 'direction_pattern_match' and not e['full_fact_equivalence']
               for e in evaluation['modes']['graph'])
    assert not evaluation['new_scientific_knowledge_confirmed']


def test_two_matching_families_cannot_validate_each_other_at_support_two():
    data = prepared()
    result = forecast_transfers(*data)
    assert not any(f['predictions'] for mode in MODES for f in result['modes'][mode])
    diagnostic = reapply_without_holdout(*data[:3])
    assert len(diagnostic['candidates']) == 2
    assert not diagnostic['is_independent_validation'] and diagnostic['receiving_results_used_in_training']


def test_held_out_result_is_never_read_by_learner():
    cases, receivers, groups, coverage = prepared(True)
    receiver = receivers[0]
    baseline = forecast_transfers(cases, [receiver], groups, coverage)
    poisoned = deepcopy(cases)
    # Доступ к этим полям был бы ошибкой: вся семья должна отсеяться раньше.
    held = poisoned[0]
    for k in ('result', 'qualitative_direction', 'outcome_class', 'source_annotation', 'features'):
        del held[k]
    assert forecast_transfers(poisoned, [receiver], groups, coverage) == baseline


def test_another_article_of_receiving_family_is_excluded_before_learning():
    cases, receivers, groups, coverage = prepared(True)
    cases[1]['primary_family'] = cases[0]['primary_family']
    result = forecast_transfers(cases, [receivers[0]], groups, coverage)
    assert not result['modes']['graph'][0]['predictions']
    assert result['modes']['graph'][0]['excluded']['held_out_family'] == 2


@pytest.mark.parametrize('field', ['result', 'qualitative_direction', 'outcome_class', 'complete_basis', 'direction_evidence'])
def test_result_fields_in_receiver_are_rejected(field):
    cases, receivers, groups, coverage = prepared(True)
    receivers[0][field] = 'forbidden'
    with pytest.raises(ArticleMapError, match='contains result'):
        forecast_transfers(cases, receivers, groups, coverage)


@pytest.mark.parametrize('axis', AXES)
def test_unknown_receiver_context_blocks_application(axis):
    cases, receivers, groups, coverage = prepared(True)
    receivers[0]['features'][axis] = None
    receivers[0]['feature_evidence'][axis] = []
    r = forecast_transfers(cases, [receivers[0]], groups, coverage)
    assert not r['modes']['graph'][0]['predictions']
    assert r['modes']['graph'][0]['rejected'][0]['compatibility']['unknown'] == [axis]


@pytest.mark.parametrize('change', ['population', 'challenge', 'negation', 'modality', 'planned', 'duplicate', 'foreign', 'role'])
def test_wrong_receiver_participants_or_actions_are_rejected(change):
    cases, receivers, groups, coverage = prepared(True)
    receiver = receivers[0]
    frame = receiver['body'][1]['frame']; atom = frame['statements'][0]
    if change in ('population', 'challenge'):
        next(r for r in atom['roles'] if r['role'] == change)['value'] = 'other'
    elif change == 'negation': atom['negated'] = True
    elif change == 'modality': atom['scope']['modality'] = 'may'
    elif change == 'planned': frame['action_status'] = 'planned'
    elif change == 'duplicate': receiver['body'][1] = deepcopy(receiver['body'][0])
    elif change == 'foreign': receiver['body'][1]['native_key'][0] = 'other'
    elif change == 'role': atom['roles'].append(deepcopy(atom['roles'][0]))
    with pytest.raises(ArticleMapError):
        forecast_transfers(cases, receivers, groups, coverage)


def test_source_numeric_and_scope_differences_are_preserved_not_equated():
    cases, receivers, groups, coverage = prepared(True)
    receivers[0]['body'][0]['frame']['statements'][0]['attributes'].append(
        {'name': 'dose', 'value': '999', 'unit': 'microgram'})
    r = forecast_transfers(cases, [receivers[0]], groups, coverage)
    candidate = r['modes']['graph'][0]['predictions'][0]
    assert candidate['receiver'] == receivers[0]
    assert candidate['complete_support_contexts'] == [
        {'case_id': c['case_id'], 'frames': {f: c[f]['frame'] for f in ('method','measurement','result')}}
        for c in cases[1:]]
    assert candidate['transfer_obligations_ru'] and not candidate['deductive_entailment']


def test_unsupported_rule_cannot_be_injected():
    cases, receivers, groups, _ = prepared(True)
    normalized = {(frozenset(b), h) for b, h in groups}
    rules, _ = learn(cases, receivers[0]['primary_family'], 'graph', normalized)
    rules[0]['primary_families'] = ['invented']
    with pytest.raises(ArticleMapError, match='independent support'):
        apply_rules(rules, receivers[0])


@pytest.mark.parametrize('change', ['missing_method', 'missing_head', 'different_head'])
def test_relative_effect_requires_same_explicit_control_in_training(change):
    cases, receivers, groups, coverage = prepared(True)
    c = cases[1]
    target = c['method'] if change == 'missing_method' else c['result']
    roles = target['frame']['statements'][0]['roles']
    if change == 'different_head': next(r for r in roles if r['role']=='comparator')['value'] = 'unrelated control'
    else: target['frame']['statements'][0]['roles'] = [r for r in roles if r['role']!='comparator']
    result = forecast_transfers(cases, [receivers[0]], groups, coverage)
    fold = result['modes']['graph'][0]
    assert not fold['predictions'] and fold['excluded']['unbound_or_different_comparator'] == 1


def test_evaluation_change_cannot_change_frozen_candidates():
    cases, receivers, groups, coverage = prepared(True)
    r = forecast_transfers(cases, receivers, groups, coverage); before = deepcopy(r)
    observed = outcomes(cases); observed[receivers[0]['id']]['qualitative_direction'] = 'higher_clinical_burden'
    evaluation = evaluate_transfers(r, observed)
    assert r == before and evaluation['modes']['graph'][0]['relation'] == 'direction_pattern_mismatch'
    observed.pop(receivers[0]['id'])
    with pytest.raises(ArticleMapError): evaluate_transfers(r, observed)


def test_application_seals_before_evaluation_and_preserves_forecast_on_failure(tmp_path, monkeypatch):
    import httpx
    import socket
    monkeypatch.setattr(httpx.Client, 'send', lambda *a, **k: pytest.fail('No model calls'))
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('No network'))
    cases, receivers, groups, coverage = prepared(True)
    store = FilePredictionStore(tmp_path)
    class Port:
        fail = False
        def load(self):
            return {'input_run_id': 'upstream', 'input_sha256': 'bound', 'cases': cases,
                    'receivers': receivers, 'author_groups': groups, 'coverage': coverage}
        def outcomes(self):
            assert len(list(tmp_path.glob('*/seal.json'))) == 1
            if self.fail: raise ArticleMapError('Evaluation failed')
            return outcomes(cases)
    port = Port(); app = SealConditionalOperationTransfer(port, store)
    result, eid, evaluation = app.execute({'code': 'fixed'})
    assert (result, eid, evaluation) == app.execute({'code': 'fixed'})
    assert len(list(tmp_path.glob('*/evaluations/*.json'))) == 1
    port.fail = True
    with pytest.raises(ArticleMapError, match='Evaluation failed'): app.execute({'code': 'fixed'})
    assert store.read_seal(result['run_id']) == result
    assert fingerprint(evaluation) == eid
