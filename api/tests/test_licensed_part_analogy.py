"""У аналогии сохраняются происхождение, условия и логический статус гипотезы."""
from copy import deepcopy

import pytest

from domain.article_maps import ArticleMapError, fingerprint
from domain.licensed_part_analogy import discover_from_licensed_parts, LIMITS
from domain.semantic_operator_graph import build_graph
from domain.semantic_part_forecast import forecast_parts
from tests.test_analogy_transport import maps_and_origins
from tests.test_semantic_part_forecast import prepare


def inputs(maps=None):
    if maps is None: maps, origins = maps_and_origins()
    else: maps, origins = prepare(maps)
    families = {m['article_id']: m['article_id'] for m in maps}
    return forecast_parts(maps, families, None, None, origins), build_graph(maps), origins, families


def execute(maps=None):
    return discover_from_licensed_parts(*inputs(maps))


def test_general_analogy_preserves_native_proofs_without_empirical_or_graph_claims():
    args = inputs(); before = deepcopy(args); r = discover_from_licensed_parts(*args)
    assert args == before and r['canonical_blocks'] == len(r['coverage']) == 6
    assert r['native_statements'] == r['licensed_parts'] == r['admitted_parts'] == 6
    assert len(r['all_candidates']) == 2
    for c in r['all_candidates']:
        assert c['frame']['statements'][0]['scope']['modality'].startswith('hypothesis;')
        assert c['conclusion_support_families'] == [] and not c['logical_entailment']
        assert not c['conclusion_confirmed'] and c['predicted_p_value'] is None
        assert len(c['witnesses'][0]['premises']) == 3
        for p in c['witnesses'][0]['premises']:
            assert p['projection_proof_id'] in r['proof_registry']
    assert r['ablation']['without_visible_dependencies_same_result'] and r['accuracy'] is None
    assert not r['scientific_success'] and not r['graph_advantage_demonstrated']


def test_method_attributes_and_time_dose_are_retained_as_obligations():
    maps, _ = maps_and_origins()
    s = maps[0]['graph']['knowledge'][2]['semantic_frame']['statements'][0]
    s['temporal_context'] = 'after challenge at 24 hours'
    s['conditions'].append('drug a at 20 mg per kg')
    s['qualifiers']['attributes'] = [{'name': 'assay', 'value': 'qPCR', 'unit': None}]
    r = execute(maps)
    c = next(c for c in r['all_candidates'] if c['donor_article'] == 'one')
    h = c['frame']['statements'][0]
    assert h['attributes'] == [{'name': 'assay', 'value': 'qPCR', 'unit': None}]
    assert h['scope']['time'] == 'after challenge at 24 hours'
    assert 'drug a at 20 mg per kg' in h['scope']['conditions']
    assert c['transport_obligations']['donor_scope_differences']
    assert c['transport_obligations']['donor_attribute_differences']
    assert not c['transport_obligations']['causal_response_transport_established']


def test_explicit_memory_direction_separates_readout_but_preserves_injected_dose():
    maps, _ = maps_and_origins()
    for k in maps[0]['graph']['knowledge'][:2]:
        k['semantic_frame']['statements'][0]['qualifiers']['attributes'] = [
            {'name': 'normal percent', 'value': '67', 'unit': 'percent'},
            {'name': 'ko vs wt p', 'value': '0.04', 'unit': 'dimensionless'},
            {'name': 'injected volume ul', 'value': '5', 'unit': 'ul'}]
    r = execute(maps)
    assert [c for c in r['all_candidates'] if c['donor_article'] == 'one']
    assert len(r['direction_operand_proofs']) == 2
    for proof in r['direction_operand_proofs']:
        assert len(proof['removed_summaries']) == 2
        assert {'name': 'injected volume ul', 'value': '5', 'unit': 'ul'} in proof['output_frame']['statements'][0]['attributes']
        assert not proof['direction_inferred_from_numbers'] and not proof['statistical_significance_transferred']
        assert proof['input_frame']['statements'][0]['scope'] == proof['output_frame']['statements'][0]['scope']


@pytest.mark.parametrize('attribute', [
    {'name': 'normal percent', 'value': '101', 'unit': 'percent'},
    {'name': 'normal percent', 'value': '67', 'unit': 'mg'},
    {'name': 'ko vs wt p', 'value': 'NaN', 'unit': 'dimensionless'},
    {'name': 'unknown readout', 'value': '67', 'unit': 'percent'},
    {'name': 'injected volume ul', 'value': '-5', 'unit': 'ul'},
])
def test_unknown_or_invalid_numeric_fields_are_not_removed_to_make_a_candidate(attribute):
    maps, _ = maps_and_origins()
    maps[0]['graph']['knowledge'][1]['semantic_frame']['statements'][0]['qualifiers']['attributes'] = [attribute]
    r = execute(maps)
    assert not [c for c in r['all_candidates'] if c['donor_article'] == 'one']


@pytest.mark.parametrize('change', ['negated', 'modal', 'action', 'numerical', 'nondetection', 'nested'])
def test_unlicensed_operands_do_not_become_positive_observations(change):
    maps, _ = maps_and_origins(); k = maps[0]['graph']['knowledge'][1]
    s = k['semantic_frame']['statements'][0]
    if change == 'negated': s['negated'] = True
    elif change == 'modal': s['modality'] = 'may'
    elif change == 'action': k.update(kind='action', action_status='planned')
    elif change == 'numerical': s['qualifiers']['attributes'] = [{'name': 'unresolved estimate', 'value': '3.5', 'unit': None}]
    elif change == 'nondetection': s['predicate'] = 'improvement not statistically detected'
    else: s['roles'][1].update(concept_id=None, knowledge_id='K3')
    r = execute(maps)
    assert not [c for c in r['all_candidates'] if c['donor_article'] == 'one']
    assert len(r['coverage']) == 6


def test_same_name_different_source_local_entities_are_not_identified():
    maps, _ = maps_and_origins(); m = maps[0]
    duplicate = deepcopy(m['graph']['concepts'][2]); duplicate['id'] = 'C4'
    m['graph']['concepts'].append(duplicate)
    m['graph']['knowledge'][1]['semantic_frame']['statements'][0]['roles'][1]['concept_id'] = 'C4'
    r = execute(maps)
    assert not [c for c in r['all_candidates'] if c['donor_article'] == 'one']
    assert r['rejection_counts']['same_name_different_native_entity'] > 0


def test_missing_challenge_role_remains_an_obligation_not_an_established_match():
    maps, _ = maps_and_origins(); m = maps[0]
    m['graph']['concepts'].append({'id': 'C4', 'display_text': 'acute challenge', 'aliases': []})
    m['graph']['knowledge'][1]['semantic_frame']['statements'][0]['roles'].append(
        {'role': 'challenge', 'concept_id': 'C4', 'knowledge_id': None})
    r = execute(maps)
    c = next(c for c in r['all_candidates'] if c['donor_article'] == 'one')
    assert c['transport_obligations']['unmatched_anchor_context_roles']['challenge'] == {'donor': None, 'recipient': 'acute challenge'}
    assert not c['conclusion_confirmed'] and not c['logical_entailment']


def test_cross_article_same_endpoint_name_is_only_an_unvalidated_bridge():
    maps, _ = maps_and_origins()
    for c, label in zip(maps[1]['graph']['concepts'], ['drug b', 'different drug', 'effect x', 'different effect']):
        c['display_text'] = label
    r = execute(maps)
    cross = [c for c in r['all_candidates'] if c['donor_article'] != c['recipient_article']]
    assert cross and all(not c['transport_obligations']['cross_source_entity_identity_established'] for c in cross)
    assert all(c['donor_article'] != c['recipient_article'] and not c['conclusion_confirmed'] for c in cross)


@pytest.mark.parametrize('predicate,negative', [('induction prevented', False), ('induction prevented', True)])
def test_known_relation_inside_unlicensed_contrast_is_not_a_novel_gap(predicate, negative):
    maps, _ = maps_and_origins(); m = maps[0]
    k = deepcopy(m['graph']['knowledge'][2]); k['knowledge_id'] = 'K4'; k['semantic_frame']['logic'] = 'contrast'
    s = k['semantic_frame']['statements'][0]; s['statement_id'] = 'S4'; s['roles'][0]['concept_id'] = 'C1'
    s['predicate'] = predicate; s['negated'] = negative
    m['graph']['knowledge'].append(k); m['graph']['nodes'].append({'id': 'B4', 'knowledge_id': 'K4'})
    r = execute(maps)
    assert not [c for c in r['all_candidates'] if c['donor_article'] == 'one']
    assert r['rejection_counts']['explicit_opposite' if negative else 'known_relation'] > 0


def test_parent_parts_are_not_counted_as_independent_source_support():
    maps, _ = maps_and_origins(); m = maps[0]
    k = m['graph']['knowledge'][0]; k['semantic_frame']['logic'] = 'conjunction'
    k['semantic_frame']['statements'].extend(deepcopy(m['graph']['knowledge'][2]['semantic_frame']['statements']))
    m['graph']['knowledge'].pop(); m['graph']['nodes'].pop()
    r = execute(maps); c = next(c for c in r['all_candidates'] if c['donor_article'] == 'one')
    assert len({tuple(p['native_key']) for p in c['witnesses'][0]['premises']}) == 2
    assert c['witnesses'][0]['premise_publication_families'] == ['one']
    assert not c['conclusion_support_families']


def test_different_witnesses_of_the_same_frame_do_not_consume_multiple_budget_slots():
    maps, _ = maps_and_origins(); m = maps[0]
    duplicate = deepcopy(m['graph']['knowledge'][0]); duplicate['knowledge_id'] = 'K4'
    duplicate['semantic_frame']['statements'][0]['statement_id'] = 'S4'
    duplicate['semantic_frame']['statements'][0]['temporal_context'] = 'other anchor measurement time'
    m['graph']['knowledge'].append(duplicate); m['graph']['nodes'].append({'id': 'B4', 'knowledge_id': 'K4'})
    r = execute(maps); rows = [c for c in r['all_candidates'] if c['donor_article'] == 'one']
    assert len(rows) == 1 and len(rows[0]['witnesses']) == 2
    assert len(rows[0]['all_transport_obligations']) == 2


def test_already_tested_endpoint_is_blocked_even_with_an_extra_context_role():
    maps, _ = maps_and_origins(); m = maps[0]
    m['graph']['concepts'].append({'id': 'C4', 'display_text': 'acute challenge', 'aliases': []})
    k = deepcopy(m['graph']['knowledge'][2]); k['knowledge_id'] = 'K4'
    s = k['semantic_frame']['statements'][0]; s['statement_id'] = 'S4'; s['roles'][0]['concept_id'] = 'C1'
    s['roles'].append({'role': 'challenge', 'concept_id': 'C4', 'knowledge_id': None})
    m['graph']['knowledge'].append(k); m['graph']['nodes'].append({'id': 'B4', 'knowledge_id': 'K4'})
    r = execute(maps)
    assert not [c for c in r['all_candidates'] if c['donor_article'] == 'one']
    assert r['rejection_counts']['known_relation']


@pytest.mark.parametrize('damage', ['projection', 'native_parent', 'source', 'coverage'])
def test_changed_or_incomplete_source_proofs_are_rejected(damage):
    parts, graph, origins, families = inputs()
    if damage == 'projection': parts['part_views'][0]['frame']['statements'][0]['negated'] = True
    elif damage == 'native_parent': graph['parents'][next(iter(graph['parents']))]['complete_parent']['display_text'] = 'changed'
    elif damage == 'source': graph['source_units'][next(iter(graph['source_units']))]['text'] += 'changed'
    else: parts['coverage']['coverage'].pop()
    with pytest.raises(ArticleMapError): discover_from_licensed_parts(parts, graph, origins, families)


def test_budget_exhaustion_cannot_publish_a_partial_pool(monkeypatch):
    monkeypatch.setitem(LIMITS, 'search_steps', 0)
    with pytest.raises(ArticleMapError, match='budget'): execute()


def test_original_visible_edges_do_not_license_analogy():
    maps, _ = maps_and_origins(); before = execute(maps)
    maps[0]['graph']['transitions'] = [{'sources': ['B1'], 'target': 'B3'}]
    maps[0]['graph']['edges'] = [{'source': 'B1', 'target': 'B3'}]
    after = execute(maps)
    assert [c['id'] for c in before['all_candidates']] == [c['id'] for c in after['all_candidates']]

