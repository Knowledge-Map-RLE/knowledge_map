"""Проверяется полный конечный набор, а не удобные три посылки из него."""
from copy import deepcopy
import socket

import pytest

from application.finite_test_synthesis import SynthesizeSealedFiniteTests
from domain.article_maps import ArticleMapError, fingerprint
from domain.author_argument_circuits import VERSION as CIRCUIT_VERSION
from domain.finite_test_synthesis import synthesize_all_finite_tests
from domain.semantic_operator_graph import build_graph
from infrastructure.development_prediction_store import FilePredictionStore
from tests.test_quantified_evidence_reasoning import measured_map


def source(arity=4, values=None, threshold='.05', alternatives=False, distinct_exposures=False):
    m = measured_map(); template = deepcopy(m['graph']['knowledge'][0])
    knowledge = []
    for i in range(arity):
        k = deepcopy(template); k['knowledge_id'] = 'K' + str(i)
        s = k['semantic_frame']['statements'][0]; s['statement_id'] = 'S' + str(i)
        if distinct_exposures:
            next(role for role in s['roles'] if role['role'] == 'cause')['concept_id'] = 'C' + str(i % 2)
        s['roles'].append({'role': 'cohort', 'concept_id': 'C0', 'knowledge_id': None})
        s['qualifiers']['attributes'][0]['value'] = values[i] if values else '.1'
        s['qualifiers']['attributes'].append({'name': 'model_number', 'value': str(i), 'unit': None})
        knowledge.append(k)
    definition = deepcopy(template); definition['knowledge_id'] = 'T'
    ds = definition['semantic_frame']['statements'][0]; ds['statement_id'] = 'TS'
    ds['predicate'] = 'define multiplicity threshold'
    ds['roles'] = [{'role': 'cohort', 'concept_id': 'C0', 'knowledge_id': None}]
    ds['qualifiers']['attributes'] = [{'name': 'alpha', 'value': threshold, 'unit': 'dimensionless'},
                                    {'name': 'comparison', 'value': 'strict p<alpha', 'unit': None}]
    head = deepcopy(template); head['knowledge_id'] = 'H'
    head['semantic_frame']['statements'][0]['statement_id'] = 'HS'
    head['semantic_frame']['statements'][0]['predicate'] = 'summary'
    m['graph']['knowledge'] = [*knowledge, definition, head]
    m['graph']['nodes'] = [{'id': 'B' + k['knowledge_id'], 'knowledge_id': k['knowledge_id']}
                           for k in m['graph']['knowledge']]
    members = ['BK' + str(i) for i in range(arity)] + ['BT']
    m['graph']['transitions'] = [{'sources': members, 'target': 'BH', 'unit_ids': ['U1']}]
    if alternatives:
        m['graph']['transitions'].append({'sources': ['BK0', 'BT'], 'target': 'BH', 'unit_ids': ['U1']})
    m['graph']['edges'] = [{'source': s, 'target': t['target']} for t in m['graph']['transitions'] for s in t['sources']]
    return from_map(m)


def from_map(m):
    graph = build_graph([m]); groups = {}
    for d in graph['author_dependencies']:
        group = {'article_id': d['article_id'], 'head': d['conclusion'], 'premises': d['premises'],
                 'head_occurrence': d['conclusion_occurrence'], 'premise_occurrences': d['premise_occurrences'],
                 'evidence': [deepcopy(graph['source_units'][e]) for e in d['evidence']],
                 'source_sha256': m['source']['sha256'], 'graph_sha256': next(iter(graph['parents'].values()))['graph_sha256'],
                 'connective': 'all_members_required_by_this_author_group', 'alternative_groups_are_jointly_required': False,
                 'deductive_rule': False, 'causal_rule': False, 'transition_evidence_complete': True}
        group['id'] = fingerprint(group); groups[group['id']] = group
    binding = {'metadata': {'question': None, 'excluded_source_sha256': ['b' * 64]}}
    return {'binding': binding, 'run_id': fingerprint(binding), 'model_calls': 0, 'target_read': False,
            'semantic_graph': graph, 'argument_circuits': {'version': CIRCUIT_VERSION,
            'canonical_blocks': len(graph['parents']), 'nodes': deepcopy(graph['visible_occurrences']), 'groups': groups}}


def compute(s):
    return synthesize_all_finite_tests(s['semantic_graph'], s['argument_circuits'])


def change_parent(s, knowledge_id, fn):
    graph = s['semantic_graph']; pid = next(p for p, v in graph['parents'].items() if v['knowledge_id'] == knowledge_id)
    parent = graph['parents'][pid]; fn(parent['complete_parent'])
    parent['knowledge_sha256'] = fingerprint(parent['complete_parent'])
    original = parent['complete_parent']['semantic_frame']['statements']
    parts = sorted((v for v in graph['statements'].values() if v['parent'] == pid), key=lambda x: x['position'])
    for part, native in zip(parts, original):
        part['original_statement'] = deepcopy(native)


def test_variadic_21_parents_preserve_all_models_and_do_not_infer_biological_null():
    s = source(20); before = deepcopy(s); result = compute(s); row = result['author_groups'][0]
    assert s == before and row['arity'] == 21 and row['summary']['profile']['listed_tests'] == 20
    assert row['summary']['profile']['none_of_listed_tests_below']
    models = [a['value'] for t in row['summary']['tests'] for a in t['original_statement']['qualifiers']['attributes']
              if a['name'] == 'model_number']
    assert set(models) == {str(i) for i in range(20)}
    assert not row['summary']['biological_effect_or_absence_established']
    assert not row['summary']['independent_tests_assumed'] and not result['new_predictions']


def test_unknown_bound_produces_interval_count_not_false_universal_negative():
    row = compute(source(4, ['.01', '>.01', '.1', '<.1']))['author_groups'][0]
    profile = row['summary']['profile']
    assert profile['passing_count_lower_bound'] == 1 and profile['passing_count_upper_bound'] == 3
    assert profile['at_least_one_listed_test_below'] and not profile['none_of_listed_tests_below']


def test_no_computable_test_is_not_a_vacuous_universal_conclusion():
    s = source(); graph = s['semantic_graph']; group = next(iter(s['argument_circuits']['groups'].values()))
    threshold = next(p for p, v in graph['parents'].items() if v['knowledge_id'] == 'T')
    oid = next(o for o, v in graph['visible_occurrences'].items() if v['parent'] == threshold)
    group['premises'] = [threshold]; group['premise_occurrences'] = [oid]; group.pop('id')
    group['id'] = fingerprint(group); s['argument_circuits']['groups'] = {group['id']: group}
    d = graph['author_dependencies'][0]; d['premises'] = [threshold]; d['premise_occurrences'] = [oid]
    graph['visible_occurrence_edges'] = [{'source': oid, 'target': group['head_occurrence']}]
    row = compute(s)['author_groups'][0]
    assert row['status'] == 'no_measured_tests' and row['summary'] is None


@pytest.mark.parametrize('change', ['missing_alpha', 'footnote', 'wrong_unit'])
def test_one_unsupported_input_prevents_whole_group_synthesis(change):
    s = source(8)
    def modify(k):
        attrs = k['semantic_frame']['statements'][0]['qualifiers']['attributes']
        if change == 'missing_alpha': attrs.pop(1)
        elif change == 'footnote': attrs[0]['value'] = '.01*'
        else: attrs[0]['unit'] = 'percent'
    change_parent(s, 'K7', modify)
    row = compute(s)['author_groups'][0]
    assert row['status'] == 'unsupported_member_in_complete_group' and row['summary'] is None
    assert len(row['member_audit']) == 9


def test_compound_parent_keeps_every_clause_and_unknown_clause_blocks_summary():
    m = measured_map(); k = m['graph']['knowledge'][0]
    k['semantic_frame']['logic'] = 'contrast'; a = k['semantic_frame']['statements'][0]
    a['roles'].append({'role': 'cohort', 'concept_id': 'C0', 'knowledge_id': None})
    b = deepcopy(a); b['statement_id'] = 'Sextra'; b['qualifiers']['attributes'].pop(1)
    k['semantic_frame']['statements'].append(b)
    # Обычная группа fixture использует оба первых родителя: неизвестный компонент первого не исчезает.
    result = compute(from_map(m))
    assert result['author_groups'][0]['summary'] is None
    assert len(result['quantitative']['proofs'][0]['complete_parent']['semantic_frame']['statements']) == 2


def test_explicit_threshold_conflict_is_not_silently_replaced_by_measurement_alpha():
    result = compute(source(threshold='.001'))
    assert result['author_groups'][0]['status'] == 'incompatible_cohort_or_explicit_threshold'
    assert len(result['semantic_sets_without_author_groups']) == 1


def test_equivalent_decimal_threshold_representations_preserve_raw_source_and_merge_only_value():
    result = compute(source(threshold='0.0500')); summary = result['author_groups'][0]['summary']
    assert summary['cutoff'] == '0.05'
    definition = next(p for p in summary['whole_parents'].values() if p['knowledge_id'] == 'T')
    raw = definition['complete_parent']['semantic_frame']['statements'][0]['qualifiers']['attributes'][0]['value']
    assert raw == '0.0500' and summary['profile']['listed_tests'] == 4


def test_alternative_groups_remain_separate_finite_lists():
    result = compute(source(4, ['.01', '.1', '.1', '.1'], alternatives=True))
    assert sorted(r['summary']['profile']['listed_tests'] for r in result['author_groups']) == [1, 4]
    assert all(not r['alternative_groups_merged'] for r in result['author_groups'])


def test_flat_semantic_baseline_uses_same_tests_without_head_or_group_membership():
    s = source(4); result = compute(s)
    assert result['same_members_without_arrows_identical'] and result['exact_test_sets_also_found_without_groups'] == 1
    without = deepcopy(s); without['argument_circuits']['groups'] = {}
    without['semantic_graph']['author_dependencies'] = []; without['semantic_graph']['visible_occurrence_edges'] = []
    assert compute(without)['semantic_sets_without_author_groups'] == result['semantic_sets_without_author_groups']


def test_semantic_baseline_also_searches_exact_analysis_scopes_without_edges():
    result = compute(source(4, distinct_exposures=True))
    rows = result['semantic_sets_without_author_groups']
    by_level = {level: [row for row in rows if level in row['grouping_levels']]
                for level in ('source_family', 'exact_analysis_scope')}
    assert len(by_level['source_family']) == 1
    assert by_level['source_family'][0]['summary']['profile']['listed_tests'] == 4
    assert len(by_level['exact_analysis_scope']) == 2
    assert sorted(row['summary']['profile']['listed_tests'] for row in by_level['exact_analysis_scope']) == [2, 2]
    assert result['exact_test_sets_also_found_without_groups'] == 1
    assert result['same_members_without_arrows_identical']


def test_changing_head_text_does_not_change_synthesized_knowledge():
    s = source(); before = compute(s)['author_groups'][0]['summary']
    change_parent(s, 'H', lambda k: k.update(display_text='An entirely different proposed conclusion'))
    assert compute(s)['author_groups'][0]['summary'] == before


def test_different_local_cohort_cannot_enter_same_threshold_summary():
    s = source(); graph = s['semantic_graph']
    threshold = next(p for p, v in graph['parents'].items() if v['knowledge_id'] == 'T')
    part = next(v for v in graph['statements'].values() if v['parent'] == threshold)
    part['roles'][0]['target'] = 'another-source-local-cohort'
    assert compute(s)['author_groups'][0]['status'] == 'incompatible_cohort_or_explicit_threshold'


def test_corrupted_cyclic_author_snapshot_is_rejected_even_if_groups_and_edges_agree():
    s = source(); graph = s['semantic_graph']; groups = s['argument_circuits']['groups']
    first = next(iter(groups.values())); reverse = deepcopy(first)
    reverse['head'], reverse['premises'] = first['premises'][0], [first['head']]
    reverse['head_occurrence'], reverse['premise_occurrences'] = first['premise_occurrences'][0], [first['head_occurrence']]
    reverse.pop('id'); reverse['id'] = fingerprint(reverse); groups[reverse['id']] = reverse
    graph['author_dependencies'].append({'conclusion': reverse['head'], 'premises': reverse['premises'],
        'conclusion_occurrence': reverse['head_occurrence'], 'premise_occurrences': reverse['premise_occurrences']})
    graph['visible_occurrence_edges'].append({'source': first['head_occurrence'], 'target': first['premise_occurrences'][0]})
    with pytest.raises(ArticleMapError, match='DAG'): compute(s)


@pytest.mark.parametrize('change', ['source', 'group', 'occurrence', 'evidence', 'coverage'])
def test_changed_provenance_or_complete_group_fails_before_sealing(change):
    s = source(); graph = s['semantic_graph']; groups = s['argument_circuits']['groups']; group = next(iter(groups.values()))
    if change == 'source': graph['parents'][group['premises'][0]]['source_sha256'] = 'c' * 64
    elif change == 'group': group['premises'] = group['premises'][:3]
    elif change == 'occurrence': s['argument_circuits']['nodes'][group['premise_occurrences'][0]]['parent'] = group['head']
    elif change == 'evidence': next(iter(graph['source_units'].values()))['text'] += 'bad'
    else: graph['statement_count'] += 1
    with pytest.raises(ArticleMapError): compute(s)


def test_application_immutable_replay_no_network_or_model_and_excluded_target(tmp_path, monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *args: (_ for _ in ()).throw(AssertionError('Network forbidden')))
    s = source(); inputs = FilePredictionStore(tmp_path / 'inputs'); output = FilePredictionStore(tmp_path / 'runs')
    inputs.seal(s['run_id'], s); app = SynthesizeSealedFiniteTests(inputs, output)
    a = app.execute(s['run_id'], {'code': 'fixture'}); b = app.execute(s['run_id'], {'code': 'fixture'})
    assert a == b and inputs.read_seal(s['run_id']) == s and not a['scientific_success']
    s['binding']['metadata']['excluded_source_sha256'] = [next(iter(s['semantic_graph']['parents'].values()))['source_sha256']]
    s['run_id'] = fingerprint(s['binding']); inputs.seal(s['run_id'], s)
    with pytest.raises(ArticleMapError, match='Excluded target'): app.execute(s['run_id'], {'code': 'fixture'})
