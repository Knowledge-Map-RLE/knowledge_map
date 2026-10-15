"""Полный скрытый граф сохраняет контекст, родительскую логику и локальные сущности."""
from copy import deepcopy
from hashlib import sha256
import socket

import pytest

from domain.article_maps import ArticleMapError, ArticleMapAccessDenied
from domain.semantic_operator_graph import build_graph, match_pattern, inventory_patterns, identifier
from application.semantic_operator_graph import SealSemanticOperatorGraph
from infrastructure.development_prediction_store import FilePredictionStore
from tests.test_schema6_prediction import graph, ref


def fixture(article='one', alternative=False):
    m = graph(article, ['Alpha', 'Beta', 'Gamma'], alternative=alternative)
    text = 'Synthetic source: alpha relates to beta and beta to gamma 🙂.'
    m['source'] = {'text': text, 'sha256': sha256(text.encode()).hexdigest(), 'offset_encoding': 'unicode_codepoints',
                   'content_end': len(text), 'units': [{'id': 'U1', 'start': 0, 'end': len(text), 'text': text}]}
    return m


def pattern():
    return {'statements': [{'predicate': 'causes', 'negated': False, 'state_or_action': 'state', 'action_status': None,
        'roles': [{'role': 'cause', 'variable': '$a'}, {'role': 'effect', 'variable': '$b'}]},
        {'predicate': 'causes', 'negated': False, 'state_or_action': 'state', 'action_status': None,
        'roles': [{'role': 'cause', 'variable': '$b'}, {'role': 'effect', 'variable': '$c'}]}],
        'context_policy': 'same_source_exact_scope'}


def test_all_parents_statements_provenance_and_typed_roles_preserved():
    m = fixture(); before = deepcopy(m); result = build_graph([m])
    assert before == m and result['canonical_blocks'] == 3 and result['statement_count'] == 3
    assert len(result['coverage']) == 3 and len(result['parents']) == 3 and len(result['source_units']) == 1
    for s in result['statements'].values():
        parent = result['parents'][s['parent']]['complete_parent']
        assert s['original_statement'] == parent['semantic_frame']['statements'][s['position']]
        assert not s['independent_premise_licensed']
    assert not result['scientific_success'] and result['cross_source_entities_merged'] == 0


def test_same_names_in_different_studies_remain_distinct_nodes():
    one, two = fixture(), fixture('two'); result = build_graph([one, two])
    a = result['nodes'][identifier('one', 'concept', 'C0')]; b = result['nodes'][identifier('two', 'concept', 'C0')]
    assert a['id'] != b['id'] and a['comparison_key'] == b['comparison_key']
    matches = match_pattern(result, pattern())['matches']
    assert {m['article_id'] for m in matches} == {'one', 'two'}
    for match in matches:
        assert all(result['nodes'][v]['article_id'] == match['article_id'] for v in match['bindings'].values())


def test_structural_chain_is_not_causal_transitivity_or_prediction():
    result = match_pattern(build_graph([fixture()]), pattern())
    assert len(result['matches']) == 1 and not result['predictions'] and not result['scientific_success']
    assert not result['matches'][0]['independent_premises_licensed']


@pytest.mark.parametrize('field,value', [('negated', True), ('temporal_context', 'different time'),
                                      ('modality', 'may'), ('conditions', ['different condition'])])
def test_constraints_do_not_disappear_in_chain_matching(field, value):
    m = fixture(); m['graph']['knowledge'][1]['semantic_frame']['statements'][0][field] = value
    assert not match_pattern(build_graph([m]), pattern())['matches']


def test_unknown_context_does_not_become_licensed_by_presence_in_graph():
    m = fixture(); s = m['graph']['knowledge'][1]['semantic_frame']['statements'][0]; s['conditions'] = []
    result = build_graph([m])
    assert any(v['unknown_context'] for v in result['statements'].values())
    assert not match_pattern(result, pattern())['matches']


def test_same_words_with_swapped_roles_break_the_chain():
    m = fixture(); roles = m['graph']['knowledge'][1]['semantic_frame']['statements'][0]['roles']
    roles[0]['concept_id'], roles[1]['concept_id'] = roles[1]['concept_id'], roles[0]['concept_id']
    result = match_pattern(build_graph([m]), pattern())
    assert not any(m['bindings']['$a'] == identifier('one', 'concept', 'C0')
                   and m['bindings']['$c'] == identifier('one', 'concept', 'C2') for m in result['matches'])


def test_alternative_author_groups_are_not_conjoined():
    result = build_graph([fixture(alternative=True)])
    assert len(result['author_dependencies']) == 2
    assert all(len(g['premises']) == 1 and not g['deductive_rule'] for g in result['author_dependencies'])


def test_compound_parts_remain_linked_to_their_full_parent():
    m = fixture(); k = m['graph']['knowledge'][0]; other = deepcopy(k['semantic_frame']['statements'][0])
    other['statement_id'] = 'S1-other'; other['negated'] = True; k['semantic_frame']['logic'] = 'contrast'
    k['semantic_frame']['statements'].append(other); result = build_graph([m])
    assert result['statement_count'] == 4 and len(result['coverage'][0]['statements']) == 2
    assert all(s['parent_logic'] == 'contrast' for s in result['statements'].values() if s['parent'] == result['coverage'][0]['parent'])
    assert not any(s['independent_premise_licensed'] for s in result['statements'].values())


def test_hidden_cycles_allowed_and_original_links_not_recursively_cut():
    m = fixture()
    for index, target in [(0, 'K2'), (1, 'K1')]:
        m['graph']['knowledge'][index]['semantic_frame']['statements'][0]['roles'][0].update(concept_id=None, knowledge_id=target)
    result = build_graph([m])
    assert len(result['hidden_semantic_cycles']) == 1 and result['visible_dag_preserved']
    assert len(result['hidden_semantic_cycles'][0]) == 4


@pytest.mark.parametrize('mutation', ['source', 'coords', 'bibliography', 'unknown_role', 'duplicate_statement', 'visible_cycle', 'group_edges'])
def test_invalid_graph_or_provenance_rejected(mutation):
    m = fixture()
    if mutation == 'source': m['source']['text'] += '!'
    elif mutation == 'coords': m['source']['units'][0]['end'] -= 1
    elif mutation == 'bibliography': m['source']['content_end'] -= 1
    elif mutation == 'unknown_role': m['graph']['knowledge'][0]['semantic_frame']['statements'][0]['roles'][0]['concept_id'] = 'unknown'
    elif mutation == 'duplicate_statement': m['graph']['knowledge'][1]['semantic_frame']['statements'][0]['statement_id'] = 'S1'
    elif mutation == 'visible_cycle': m['graph']['edges'].append({'source': 'B3', 'target': 'B1'})
    elif mutation == 'group_edges': m['graph']['transitions'][0]['sources'] = ['B1']
    with pytest.raises(ArticleMapError): build_graph([m])


def test_structural_motifs_are_not_counted_as_independent_scientific_support():
    g = build_graph([fixture(), fixture('two')]); motifs = inventory_patterns(g, {'one': 'same-cited-study', 'two': 'same-cited-study'})
    assert motifs['patterns_in_multiple_publications'] and not motifs['independent_primary_support_certified']
    assert all(not m['independent_premises_licensed'] for p in motifs['patterns'] for m in p['examples'])
    assert not motifs['predictions']


def test_budget_overflow_rejects_whole_query(monkeypatch):
    import domain.semantic_operator_graph as module
    monkeypatch.setitem(module.LIMITS, 'pattern_steps', 1)
    with pytest.raises(ArticleMapError, match='budget'): match_pattern(build_graph([fixture()]), pattern())


def test_immutable_full_snapshot_no_network_and_no_target_read(tmp_path, monkeypatch):
    class Maps:
        def __init__(self): self.reads = []
        def get(self, article, pipeline, owner, run):
            if owner != 'owner': raise ArticleMapAccessDenied('Owner mismatch')
            assert article in {'one', 'two'}; self.reads.append(article); return fixture(article)
    def forbidden(*args, **kwargs): raise AssertionError('No external/model transport')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    maps = Maps(); store = FilePredictionStore(tmp_path / 'snapshots')
    metadata = {'question': None, 'model_calls': 0, 'training_cutoff': '2023-12-31', 'source_dates': {'one': '2010-01-01', 'two': '2011-01-01'}}
    use = SealSemanticOperatorGraph(maps, store)
    a = use.execute([ref('one'), ref('two')], 'owner', {'one': 'f1', 'two': 'f2'}, metadata, {'implementation': 'fixed'})
    b = use.execute([ref('one'), ref('two')], 'owner', {'one': 'f1', 'two': 'f2'}, metadata, {'implementation': 'fixed'})
    assert a == b and a['semantic_graph']['canonical_blocks'] == 6 and not a['target_read']
    assert len(list(store.root.iterdir())) == 1
    with pytest.raises(ArticleMapAccessDenied): use.execute([ref('one'), ref('two')], 'other', {'one': 'f1', 'two': 'f2'}, metadata, {})


def test_future_map_rejected_before_access(tmp_path):
    class Maps:
        def get(self, *args): raise AssertionError('Future map was read')
    metadata = {'question': None, 'model_calls': 0, 'training_cutoff': '2023-12-31', 'source_dates': {'one': '2024-01-01', 'two': '2011-01-01'}}
    with pytest.raises(ArticleMapError): SealSemanticOperatorGraph(Maps(), FilePredictionStore(tmp_path)).execute(
        [ref('one'), ref('two')], 'owner', {'one': 'f1', 'two': 'f2'}, metadata, {})
