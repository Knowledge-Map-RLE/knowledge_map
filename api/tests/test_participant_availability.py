"""Знание заключения и его скрытых потребителей не становится новой предпосылкой."""
from copy import deepcopy

from domain.participant_availability import audit
from tests.test_joint_operator_patterns import joint


def case():
    value = joint()
    head = value['graph']['knowledge'][-1]
    head['semantic_frame']['statements'][0]['roles'][0]['concept_id'] = 'C2'
    return value


def add_provider(value, *, upstream=False, refers_to_head=False):
    graph = value['graph']
    item = deepcopy(graph['knowledge'][-1])
    item['knowledge_id'] = 'K4'
    if refers_to_head:
        item['semantic_frame']['statements'][0]['roles'].append(
            {'role': 'basis', 'knowledge_id': 'K3', 'concept_id': None})
    graph['knowledge'].append(item)
    graph['nodes'].append({'id': 'N4', 'knowledge_id': 'K4', 'rank': 0})
    if upstream:
        graph['edges'].append({'source': 'N4', 'target': 'N1'})
        graph['transitions'].append({'sources': ['N4'], 'target': 'N1', 'unit_ids': ['U1']})
        for node in graph['nodes']:
            if node['id'] != 'N4':
                node['rank'] += 1


def test_registry_and_head_do_not_supply_new_participant():
    result = audit(case())
    assert result['counts']['groups_with_unavailable_symbols'] == 1
    assert result['groups'][0]['participants'][0]['providers'] == []


def test_off_chain_knowledge_can_supply_symbol_but_not_inference_license():
    value = case()
    add_provider(value)
    result = audit(value)
    assert result['groups'][0]['all_new_symbols_elsewhere']
    assert result['groups'][0]['participants'][0]['status'] == 'off_chain_symbol'
    assert not result['groups'][0]['inference_licensed']


def test_hidden_target_reference_blocks_apparent_provider():
    value = case()
    add_provider(value, refers_to_head=True)
    result = audit(value)
    assert not result['groups'][0]['all_new_symbols_elsewhere']


def test_upstream_provider_is_distinguished_from_unrelated_symbol():
    value = case()
    add_provider(value, upstream=True)
    result = audit(value)
    group = next(r for r in result['groups'] if r['head'] == 'K3')
    assert group['participants'][0]['status'] == 'other_ancestor_symbol'


def test_hidden_cycles_terminate_without_leaking_head():
    value = case()
    add_provider(value, refers_to_head=True)
    value['graph']['knowledge'][-2]['semantic_frame']['statements'][0]['roles'].append(
        {'role': 'basis', 'knowledge_id': 'K4', 'concept_id': None})
    assert not audit(value)['groups'][0]['all_new_symbols_elsewhere']


def test_even_original_premise_cannot_supply_symbol_if_it_references_head():
    value = joint()
    for item in value['graph']['knowledge'][:-1]:
        item['semantic_frame']['statements'][0]['roles'].append(
            {'role': 'basis', 'knowledge_id': 'K3', 'concept_id': None})
    result = audit(value)
    assert result['counts']['groups_with_target_dependent_premises'] == 1
    assert not result['groups'][0]['all_new_symbols_elsewhere']
    assert result['groups'][0]['excluded_target_dependent_premises'] == ['K1', 'K2']
