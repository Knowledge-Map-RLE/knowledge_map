"""Совместные мотивы сохраняют роли, полярность и условия без лицензии вывода."""
from copy import deepcopy

import pytest

from domain.article_maps import ArticleMapError
from domain.joint_operator_patterns import census, extract, signature
from tests.test_operator_pattern_forecast import article


def joint(article_id='a'):
    value = article(article_id)
    value['graph']['transitions'][0]['sources'] = ['N1', 'N2']
    value['graph']['edges'].append({'source': 'N1', 'target': 'N3'})
    for item in value['graph']['knowledge']:
        item['semantic_frame']['statements'][0]['roles'][0]['concept_id'] = 'C1'
    return value


def test_alpha_names_and_premise_order_do_not_change_motif():
    first = joint()
    second = deepcopy(first['graph']['knowledge'])
    for item in second:
        item['knowledge_id'] += '-renamed'
        item['semantic_frame']['statements'][0]['roles'][0]['concept_id'] = 'different-local-id'
    assert signature(first['graph']['knowledge']) == signature([second[1], second[0], second[2]])


def test_shared_participant_topology_is_not_discarded():
    first = joint()['graph']['knowledge']
    second = deepcopy(first)
    second[-1]['semantic_frame']['statements'][0]['roles'][0]['concept_id'] = 'C2'
    assert signature(first)['id'] != signature(second)['id']
    assert signature(first, structural=True)['id'] != signature(second, structural=True)['id']


def test_internal_edge_direction_is_preserved_under_premise_permutation():
    items = joint()['graph']['knowledge']
    forward = signature(items, internal_edges=[('K1', 'K2')])
    assert forward == signature([items[1], items[0], items[2]], internal_edges=[('K1', 'K2')])
    assert forward['id'] != signature(items, internal_edges=[('K2', 'K1')])['id']


def test_new_conclusion_participant_is_reported_without_inventing_binding():
    value = joint()
    assert extract(value)['counts']['groups_with_new_head_participants'] == 0
    value['graph']['knowledge'][-1]['semantic_frame']['statements'][0]['roles'][0]['concept_id'] = 'C2'
    assert extract(value)['groups'][0]['new_head_participant_count'] == 1


@pytest.mark.parametrize('field,value', [('negated', True), ('quantifier', 'all'), ('modality', 'may')])
def test_logical_flags_survive_both_projections(field, value):
    first = joint()['graph']['knowledge']
    second = deepcopy(first)
    second[-1]['semantic_frame']['statements'][0][field] = value
    for structural in (False, True):
        assert signature(first, structural=structural)['id'] != signature(second, structural=structural)['id']


def test_numerical_and_context_loss_is_confined_to_discovery_mode():
    first = joint()['graph']['knowledge']
    for item in first:
        item['semantic_frame']['statements'][0]['qualifiers']['attributes'] = [{'name': 'dose', 'value': 5, 'unit': 'mg'}]
    second = deepcopy(first)
    second[-1]['semantic_frame']['statements'][0]['qualifiers']['attributes'][0]['value'] = 10
    second[-1]['semantic_frame']['statements'][0]['conditions'] = ['a different study population']
    assert signature(first)['id'] != signature(second)['id']
    assert signature(first, structural=True) == signature(second, structural=True)
    second[-1]['semantic_frame']['statements'][0]['qualifiers']['attributes'][0]['unit'] = 'g'
    assert signature(first, structural=True)['id'] != signature(second, structural=True)['id']


def test_alternatives_are_not_merged_into_joint_premises():
    value = joint()
    first = extract(value)
    value['graph']['transitions'] = [
        {'sources': ['N1'], 'target': 'N3', 'unit_ids': ['U1']},
        {'sources': ['N2'], 'target': 'N3', 'unit_ids': ['U1']},
    ]
    second = extract(value)
    assert first['counts']['arity_2'] == 1
    assert second['counts']['arity_1'] == 2
    assert all(row['faithful']['arity'] == 1 for row in second['groups'])


def test_cycles_of_hidden_knowledge_references_are_finite():
    value = joint()
    items = value['graph']['knowledge']
    for item, reference in ((items[0], 'K3'), (items[2], 'K1')):
        role = item['semantic_frame']['statements'][0]['roles'][0]
        role.update(concept_id=None, knowledge_id=reference)
    assert extract(value)['counts']['arity_2'] == 1


def test_family_support_is_distinct_from_publication_count_and_forecast():
    values = [joint('a'), joint('b')]
    result = census(values, {'a': 'same-cohort', 'b': 'same-cohort'})
    assert result['modes']['faithful']['cross_source_patterns'] == 1
    assert result['modes']['faithful']['cross_family_patterns'] == 0
    assert result['new_predictions'] == 0
    assert all(not p['inference_licensed'] for p in result['modes']['faithful']['patterns'])


def test_unknown_references_are_rejected_before_mining():
    value = joint()
    value['graph']['knowledge'][0]['semantic_frame']['statements'][0]['roles'][0]['concept_id'] = 'missing'
    with pytest.raises(ArticleMapError):
        extract(value)
