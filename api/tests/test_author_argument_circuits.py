"""Совместные входы и альтернативы не смешиваются при раскрытии авторских цепочек."""
from copy import deepcopy
import pytest

from domain.article_maps import ArticleMapError, fingerprint
from domain.author_argument_circuits import build_circuits, LIMITS
from domain.semantic_operator_graph import build_graph, identifier
from domain.evidence_origin_audit import validate_origins
from tests.test_semantic_operator_graph import fixture
from tests.test_semantic_part_forecast import prepare


def run(m):
    maps, origins = prepare([m]); return build_circuits(build_graph(maps), validate_origins(maps, origins))


def test_joint_group_is_and_and_source_constraints_remain_in_parent():
    m = fixture(); before = deepcopy(m); result = run(m)
    root = next(r for r in result['roots'] if r['knowledge_id'] == 'K3')
    node = result['nodes'][root['root']]
    assert node['branch_connective'] == 'or' and len(node['branches']) == 1
    assert node['branches'][0]['connective'] == 'and' and len(node['branches'][0]['members']) == 2
    assert len(root['possible_state_leaves']) == 2 and root['union_of_leaves_is_not_a_joint_premise_group']
    assert not result['new_predictions'] and not result['scientific_success']
    assert all(not g['deductive_rule'] and not g['causal_rule'] for g in result['groups'].values())
    assert m['graph'] == before['graph']


def test_alternatives_stay_two_branches_not_one_two_input_conjunction():
    result = run(fixture(alternative=True)); root = next(r for r in result['roots'] if r['knowledge_id'] == 'K3')
    node = result['nodes'][root['root']]
    assert len(node['branches']) == 2 and all(len(b['members']) == 1 for b in node['branches'])
    assert all(not g['alternative_groups_are_jointly_required'] for g in result['groups'].values())


def test_performed_methods_are_conditions_and_do_not_imply_effect_direction():
    m = fixture()
    for k in m['graph']['knowledge'][:2]: k['kind'] = 'action'; k['action_status'] = 'performed'
    result = run(m); root = next(r for r in result['roots'] if r['knowledge_id'] == 'K3')
    assert root['classification'] == 'procedure_only_basis'
    assert not root['possible_state_leaves'] and len(root['possible_action_conditions']) == 2
    assert next(iter(result['groups'].values()))['classification'] == 'procedure_to_report'


@pytest.mark.parametrize('status', ['planned', 'prescribed', 'unresolved'])
def test_nonperformed_action_is_not_counted_as_observed_result(status):
    m = fixture(); m['graph']['knowledge'][0]['kind'] = 'action'; m['graph']['knowledge'][0]['action_status'] = status
    result = run(m)
    assert any(n['action_status'] == status and not n['nonperformed_action_is_observed_fact'] for n in result['nodes'].values())


def test_joint_groups_larger_than_three_are_preserved_without_flat_product():
    m = fixture()
    for i in (4, 5):
        add_knowledge(m, i)
        m['graph']['transitions'][0]['sources'].append('B' + str(i))
        m['graph']['edges'].append({'source': 'B' + str(i), 'target': 'B3'})
    result = run(m); root = next(r for r in result['roots'] if r['knowledge_id'] == 'K3')
    assert len(result['nodes'][root['root']]['branches'][0]['members']) == 4


def test_hidden_semantic_cycle_does_not_create_causal_transition():
    m = fixture(); s = m['graph']['knowledge'][0]['semantic_frame']['statements'][0]
    s['roles'][0] = {'role': 'cause', 'concept_id': None, 'knowledge_id': 'K1'}
    result = run(m)
    assert len(result['groups']) == 1 and not result['new_predictions']


def test_unknown_source_origin_and_budget_fail_closed(monkeypatch):
    maps, origins = prepare([fixture()]); graph = build_graph(maps); index = validate_origins(maps, origins)
    with pytest.raises(ArticleMapError): build_circuits(graph, {**index, 'knowledge': {}})
    monkeypatch.setitem(LIMITS, 'steps', 1)
    with pytest.raises(ArticleMapError): build_circuits(graph, index)


def test_group_grounds_must_stay_in_one_source():
    maps, origins = prepare([fixture(), fixture('two')]); graph = build_graph(maps)
    graph['author_dependencies'][0]['premises'][0] = identifier('two', 'knowledge', 'K1')
    with pytest.raises(ArticleMapError): build_circuits(graph, validate_origins(maps, origins))


def add_knowledge(m, i):
    k = deepcopy(m['graph']['knowledge'][0]); k['knowledge_id'] = 'K' + str(i)
    k['display_text'] = 'Distinct synthetic knowledge ' + str(i)
    k['semantic_frame']['statements'][0]['statement_id'] = 'S' + str(i)
    m['graph']['knowledge'].append(k)
    m['graph']['nodes'].append({'id': 'B' + str(i), 'knowledge_id': k['knowledge_id']})


def set_transitions(m, transitions):
    m['graph']['transitions'] = [{'sources': sources, 'target': target, 'unit_ids': ['U1']}
        for sources, target in transitions]
    m['graph']['edges'] = [{'source': source, 'target': target} for sources, target in transitions for source in sources]


@pytest.mark.parametrize('body_kind,head_kind', [('state', 'state'), ('state', 'action'), ('action', 'state'), ('action', 'action')])
def test_all_four_transition_forms_preserve_status_and_chain(body_kind, head_kind):
    m = fixture()
    for k, kind in zip(m['graph']['knowledge'], [body_kind, body_kind, head_kind]):
        k['kind'] = kind; k['action_status'] = 'performed' if kind == 'action' else None
    result = run(m)
    assert result['transition_forms'] == {body_kind + '_to_' + head_kind: 2}
    root = next(r for r in result['roots'] if r['knowledge_id'] == 'K3')
    assert result['nodes'][root['root']]['branches'] and root['depth'] == 1


def test_complete_chain_beyond_three_levels_and_alternative_subcircuits():
    m = fixture()
    for i in range(4, 8): add_knowledge(m, i)
    set_transitions(m, [(['B1', 'B2'], 'B3'), (['B3'], 'B4'), (['B2'], 'B4'),
        (['B4'], 'B5'), (['B5'], 'B6'), (['B6'], 'B7')])
    result = run(m)
    root = next(r for r in result['roots'] if r['knowledge_id'] == 'K7')
    alternative = result['nodes'][identifier('one', 'occurrence', 'B4')]
    assert root['depth'] == 5 and not root['depth_truncated']
    assert len(alternative['branches']) == 2 and all(len(b['members']) == 1 for b in alternative['branches'])
    assert len(result['groups']) == 6 and len(result['nodes']) == 7


def test_repeated_canonical_knowledge_does_not_merge_occurrence_chains():
    m = fixture(); m['graph']['nodes'].append({'id': 'B4', 'knowledge_id': 'K1',
        'context': 'Distinct later use', 'repeat_reason': 'Preserve this source chain'})
    set_transitions(m, [(['B1'], 'B2'), (['B2'], 'B4')])
    result = run(m)
    first, later = [result['nodes'][identifier('one', 'occurrence', x)] for x in ('B1', 'B4')]
    assert first['parent'] == later['parent'] and first['depth'] == 0 and later['depth'] == 2
    assert not first['branches'] and later['branches'] and result['visible_occurrences'] == 4


def test_transition_only_fragment_preserved_even_if_not_used_by_statements():
    m = fixture(); maps, origins = prepare([m]); source = maps[0]['source']; start = len(source['text']) - 1
    source['units'].append({'id': 'U2', 'start': start, 'end': start + 1, 'text': source['text'][start:]})
    maps[0]['graph']['transitions'][0]['unit_ids'] = ['U2']
    origins['sources'][0]['graph_sha256'] = fingerprint(maps[0]['graph'])
    graph = build_graph(maps); result = build_circuits(graph, validate_origins(maps, origins))
    assert result['transition_evidence_incomplete'] == 0
    evidence = next(iter(result['groups'].values()))['evidence']
    assert [e['unit_id'] for e in evidence] == ['U2'] and evidence[0]['text'] == source['text'][start:]


def test_unknown_transition_fragment_and_visible_cycle_rejected():
    m = fixture(); m['graph']['transitions'][0]['unit_ids'] = ['unknown']
    with pytest.raises(ArticleMapError, match='Unknown transition'): run(m)
    m = fixture(); set_transitions(m, [(['B1'], 'B2'), (['B2'], 'B1')])
    with pytest.raises(ArticleMapError, match='DAG'): run(m)


def test_unknown_action_status_is_not_silently_classified():
    m = fixture(); m['graph']['knowledge'][0]['kind'] = 'action'; m['graph']['knowledge'][0]['action_status'] = 'unknown'
    with pytest.raises(ArticleMapError, match='action status'): run(m)
