"""Диагностика не лицензирует перенос и сохраняет отрицания и статус действия."""
from copy import deepcopy
import pytest

from domain.article_maps import ArticleMapError
from domain.template_context_diagnostics import diagnostic_signature, audit_templates


def rule(identity, time='6 hours', attr='assay', variable='$0'):
    statement = {'predicate': 'measured using', 'roles': [{'role': 'outcome', 'value': {'variable': variable}}],
        'scope': {'time': time, 'conditions': ['source-specific method'], 'study_group': 'source',
                  'modality': None, 'quantifier': None}, 'attributes': [{'name': 'method', 'value': attr, 'unit': None}], 'negated': False}
    frame = {'kind': 'action', 'action_status': 'performed', 'logic': 'single', 'statements': [statement]}
    head = deepcopy(frame); head['kind'] = 'state'; head['action_status'] = None
    head['statements'][0]['predicate'] = 'expression increased'
    return {'id': identity, 'body': [frame], 'head': head, 'internal_edges': []}


def artifact(rules):
    return {'run_id': 'synthetic', 'question': None, 'model_calls': 0, 'target_read': False,
        'learning_by_mode': {'graph': {'primary_supported_rules': [],
            'learning': {'unsupported_rules': rules},
            'unsupported_origin_support': [{'rule_id': r['id'], 'primary_families': ['family-' + r['id']],
                'examples': []} for r in rules]}}}


def test_context_mask_identifies_difference_without_admitting_rule_or_forecast():
    original = artifact([rule('a'), rule('b', time='16 days')]); before = deepcopy(original)
    result = audit_templates(original)
    assert original == before
    assert not result['levels'][0]['cross_primary_clusters']
    assert result['levels'][1]['cross_primary_clusters']
    assert all(not c['transfer_licensed'] for level in result['levels'] for c in level['cross_primary_clusters'])
    assert not result['new_rules'] and not result['new_predictions'] and not result['scientific_success']


def test_attribute_mask_does_not_mask_context():
    a, b = rule('a'), rule('b', attr='different assay')
    assert diagnostic_signature(a, 'exact') != diagnostic_signature(b, 'exact')
    assert diagnostic_signature(a, 'attributes') == diagnostic_signature(b, 'attributes')
    b['head']['statements'][0]['scope']['time'] = 'different phase'
    assert diagnostic_signature(a, 'attributes') != diagnostic_signature(b, 'attributes')


@pytest.mark.parametrize('change', ['negated', 'modality', 'quantifier', 'action_status', 'predicate', 'edge'])
def test_coarsest_mask_still_preserves_critical_relation_and_logic(change):
    a, b = rule('a'), rule('b')
    if change == 'negated': b['head']['statements'][0]['negated'] = True
    elif change == 'modality': b['head']['statements'][0]['scope']['modality'] = 'may'
    elif change == 'quantifier': b['head']['statements'][0]['scope']['quantifier'] = 'some'
    elif change == 'action_status': b['body'][0]['action_status'] = 'planned'
    elif change == 'predicate': b['head']['statements'][0]['predicate'] = 'expression decreased'
    else:
        a['body'].append(deepcopy(a['body'][0])); b['body'].append(deepcopy(b['body'][0])); b['internal_edges'] = [(0, 1)]
    assert diagnostic_signature(a, 'relation_shape') != diagnostic_signature(b, 'relation_shape')


def test_alpha_equivalence_and_premise_permutation():
    a, b = rule('a'), rule('b', variable='$8')
    assert diagnostic_signature(a, 'exact') == diagnostic_signature(b, 'exact')
    a['body'].append(deepcopy(a['body'][0])); a['body'][1]['statements'][0]['predicate'] = 'intervention applied'
    a['internal_edges'] = [(0, 1)]
    b = deepcopy(a); b['body'].reverse(); b['internal_edges'] = [(1, 0)]
    assert diagnostic_signature(a, 'exact') == diagnostic_signature(b, 'exact')


def test_source_only_complete_support_and_search_budget_required():
    value = artifact([rule('a')])
    for field, invalid in [('question', 'chosen question'), ('target_read', True), ('model_calls', 1)]:
        altered = deepcopy(value); altered[field] = invalid
        with pytest.raises(ArticleMapError): audit_templates(altered)
    altered = deepcopy(value); altered['learning_by_mode']['graph']['unsupported_origin_support'] = []
    with pytest.raises(ArticleMapError): audit_templates(altered)
    excessive = rule('a'); excessive['body'] *= 4
    with pytest.raises(ArticleMapError): diagnostic_signature(excessive, 'exact')
