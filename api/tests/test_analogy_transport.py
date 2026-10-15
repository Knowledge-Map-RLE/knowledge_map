"""Аналогия не снимает ограничения и не подменяет отсутствие значимости отсутствием эффекта."""
from copy import deepcopy
import pytest

from application.analogy_transport import SealAnalogyTransport
from domain.analogy_transport import propose, discover_analogies, LIMITS
from domain.article_maps import ArticleMapError, ArticleMapAccessDenied
from infrastructure.development_prediction_store import FilePredictionStore
from tests.test_schema6_prediction import graph, ref
from tests.test_semantic_part_forecast import prepare


def view(kid, predicate, factor, outcome, population='same cohort'):
    statement = {'predicate': predicate, 'roles': [
        {'role': 'intervention', 'value': factor, 'reference_kind': 'concept'},
        {'role': 'outcome', 'value': outcome, 'reference_kind': 'concept'},
        {'role': 'population', 'value': population, 'reference_kind': 'concept'}],
        'scope': {'quantifier': None, 'modality': None, 'time': 'baseline', 'conditions': [], 'study_group': None},
        'attributes': [], 'negated': False}
    f = {'kind': 'state', 'action_status': None, 'logic': 'single', 'statements': [statement]}
    return {'key': ('one', 'part-' + kid), 'native_key': ('one', kid), 'run_id': 'run-one',
        'eligible': True, 'text': 'Синтетический пример, не научные данные.', 'frame': f, 'document_kind': 'primary_study',
        'projection_proof': {'origin': {'origin': 'primary_result'}, 'complete_parent_frame': deepcopy(f)}}


def views():
    items = [view('K1', 'memory performance improved', 'drug a', 'memory'),
             view('K2', 'memory performance improved', 'drug b', 'memory'),
             view('K3', 'induction prevented', 'drug a', 'gene response')]
    return {v['key']: v for v in items}


def run(vs=None, extra=None):
    vs = vs or views()
    known = [v['frame']['statements'][0] for v in vs.values()] + (extra or [])
    return propose(vs, known, [((('one', 'K1'),), ('one', 'K3'))], {'one': 'one'})


def test_new_relation_has_three_complete_premises_and_no_transferred_numbers():
    before = views(); r = run(before); assert before == views()
    assert r['pool_counts'] == {'scope_matched': 1, 'transport_required': 0}
    c = r['hypotheses'][0]; s = c['proposed_qualitative_frame']['statements'][0]
    assert s['attributes'] == [] and c['quantitative_prediction'] is None
    assert next(v['value'] for v in s['roles'] if v['role'] == 'intervention') == 'drug b'
    assert len(c['witnesses'][0]['premises']) == 3 and not c['logical_entailment']
    assert c['conclusion_support_families'] == []
    assert c['witnesses'][0]['author_internal_edges'] == [[['one', 'K1'], ['one', 'K3']]]
    assert all(p['complete_projection_proof']['complete_parent_frame'] for p in c['witnesses'][0]['premises'])


def test_donor_attributes_are_an_obligation_and_never_transferred_as_target_result():
    vs = views(); vs['one', 'part-K3']['frame']['statements'][0]['attributes'] = [
        {'name': 'p', 'value': '0.01', 'unit': 'dimensionless'}]
    r = run(vs); assert not r['hypotheses']
    c = r['transport_tasks'][0]
    assert c['proposed_qualitative_frame']['statements'][0]['attributes'] == []
    assert c['transport_obligations']['donor_attributes_not_licensed_for_transfer'][0]['value'] == '0.01'


def test_existing_nondetection_blocks_gap_but_is_not_logical_negation():
    vs = views(); donor = vs['one', 'part-K3']['frame']['statements'][0]
    donor['predicate'] = 'memory performance improved'
    tested = deepcopy(donor); tested['predicate'] = 'improvement not statistically detected'
    tested['roles'][0]['value'] = 'drug b'
    tested['roles'].append({'role': 'challenge', 'value': 'acute insult', 'reference_kind': 'concept'})
    r = run(vs, [tested]); assert not r['all_proposals'] and len(r['already_tested_gaps']) == 1
    assert not r['already_tested_gaps'][0]['explicit_logical_contradiction']


@pytest.mark.parametrize('axis', ['time', 'conditions', 'quantifier', 'study_group'])
def test_context_difference_creates_task_and_never_a_scored_prediction(axis):
    vs = views(); s = vs['one', 'part-K2']['frame']['statements'][0]
    s['scope'][axis] = ['other setting'] if axis == 'conditions' else 'other context'
    r = run(vs); assert not r['hypotheses'] and r['pool_counts']['transport_required'] == 1
    assert axis in r['transport_tasks'][0]['transport_obligations']['anchor_scopes']
    assert r['transport_tasks'][0]['proposed_scope_status'] == 'donor_scope_retained_not_receiver_validated'


def test_cohort_substitution_is_visible_obligation_and_not_identity():
    vs = views(); s = vs['one', 'part-K2']['frame']['statements'][0]
    next(v for v in s['roles'] if v['role'] == 'population')['value'] = 'other cohort'
    c = run(vs)['transport_tasks'][0]
    assert c['transport_obligations']['context_roles']['population'] == {'donor': 'same cohort', 'receiver': 'other cohort'}
    assert not c['causal_transport_established']


def test_unmatched_challenge_is_preserved_as_obligation_not_silently_erased():
    vs = views(); vs['one', 'part-K2']['frame']['statements'][0]['roles'].append(
        {'role': 'challenge', 'value': 'acute challenge', 'reference_kind': 'concept'})
    c = run(vs)['transport_tasks'][0]
    assert c['transport_obligations']['unmatched_context_roles']['challenge'] == {'donor': None, 'receiver': 'acute challenge'}


@pytest.mark.parametrize('change', ['unknown', 'negated', 'modal', 'action', 'cited', 'review', 'nested', 'duplicate', 'nondetection'])
def test_unlicensed_anchor_cannot_support_analogy(change):
    vs = views(); v = vs['one', 'part-K2']; s = v['frame']['statements'][0]
    if change == 'unknown': v['eligible'] = False
    elif change == 'negated': s['negated'] = True
    elif change == 'modal': s['scope']['modality'] = 'may'
    elif change == 'action': v['frame'].update(kind='action', action_status='intended')
    elif change == 'cited': v['projection_proof']['origin']['origin'] = 'cited_result'
    elif change == 'review': v['document_kind'] = 'review'
    elif change == 'nested': s['roles'][0]['value'] = {'unresolved cycle': True}
    elif change == 'duplicate': s['roles'].append(deepcopy(s['roles'][0]))
    else: s['predicate'] = 'improvement not statistically detected'
    assert not run(vs)['all_proposals']


def test_known_relation_with_numbers_or_different_context_is_not_renamed_novel():
    s = deepcopy(views()['one', 'part-K3']['frame']['statements'][0]); s['roles'][0]['value'] = 'drug b'
    s['scope']['time'] = 'another followup'; s['attributes'] = [{'name': 'estimate', 'value': '3', 'unit': 'points'}]
    assert not run(extra=[s])['all_proposals']
    s['negated'] = True
    assert not run(extra=[s])['all_proposals']


def maps_and_origins():
    maps = []
    for article, prefix in [('one', ''), ('two', 'other ' )]:
        m = graph(article, [prefix + t for t in ('drug a', 'drug b', 'effect x', 'effect y')])
        m['graph']['transitions'] = []; m['graph']['edges'] = []
        for k, (predicate, a, b) in zip(m['graph']['knowledge'], [
                ('memory performance improved', 0, 2), ('memory performance improved', 1, 2), ('induction prevented', 0, 3)]):
            k['knowledge_kind'] = 'observation'; s = k['semantic_frame']['statements'][0]; s['predicate'] = predicate
            s['roles'] = [{'role': role, 'concept_id': 'C' + str(i), 'knowledge_id': None}
                          for role, i in [('intervention', a), ('outcome', b)]]
        maps.append(m)
    return prepare(maps)


def test_source_projection_preserves_all_blocks_and_rejects_visible_cycle():
    maps, origin = maps_and_origins(); before = deepcopy(maps)
    r = discover_analogies(maps, {'one': 'one', 'two': 'two'}, None, origin)
    assert maps == before and r['canonical_blocks'] == len(r['coverage']['coverage']) == 6
    assert len(r['hypotheses']) == 2 and r['future_results_scored'] == 0 and r['accuracy'] is None
    assert not r['scientific_success'] and not r['graph_advantage_demonstrated']
    maps[0]['graph']['edges'] = [{'source': 'B1', 'target': 'B1'}]
    with pytest.raises(ArticleMapError): discover_analogies(maps, {'one': 'one', 'two': 'two'}, None, origin)


def test_author_arrow_does_not_upgrade_analogy_to_causal_transport_or_graph_advantage():
    maps, origin = maps_and_origins()
    before = discover_analogies(maps, {'one': 'one', 'two': 'two'}, None, origin)
    maps[0]['graph']['transitions'] = [{'sources': ['B1'], 'target': 'B3'}]
    maps[0]['graph']['edges'] = [{'source': 'B1', 'target': 'B3'}]
    maps, origin = prepare(maps)
    after = discover_analogies(maps, {'one': 'one', 'two': 'two'}, None, origin)
    assert [c['id'] for c in before['hypotheses']] == [c['id'] for c in after['hypotheses']]
    assert after['ablation']['same_proposal_ids'] and not after['graph_advantage_demonstrated']
    assert any(w['author_internal_edges'] for c in after['hypotheses'] for w in c['witnesses'])


def test_repeat_seal_owner_cutoff_and_network_prohibition(tmp_path, monkeypatch):
    import socket
    import httpx
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **kw: pytest.fail('Сеть запрещена'))
    monkeypatch.setattr(httpx.Client, 'send', lambda *a, **kw: pytest.fail('Модели запрещены'))
    maps, origin = maps_and_origins()
    class Port:
        def get(self, article, pipeline, owner, run):
            if owner != 'owner': raise ArticleMapAccessDenied('Owner differs')
            return next(m for m in maps if m['article_id'] == article)
    app = SealAnalogyTransport(Port(), FilePredictionStore(tmp_path)); refs = [ref(m['article_id']) for m in maps]
    families = {'one': 'one', 'two': 'two'}
    metadata = {'question': None, 'training_cutoff': '2022-12-31', 'source_dates': {'one': '2020-01-01', 'two': '2020-01-01'}}
    r = app.execute(refs, families, 'owner', metadata, {}, None, origin)
    assert r == app.execute(refs, families, 'owner', metadata, {}, None, origin)
    assert len(list(tmp_path.glob('*/seal.json'))) == 1
    with pytest.raises(ArticleMapAccessDenied): app.execute(refs, families, 'other', metadata, {}, None, origin)
    wrong = deepcopy(metadata); wrong['source_dates']['one'] = '2023-01-01'
    with pytest.raises(ArticleMapError, match='Future'): app.execute(refs, families, 'owner', wrong, {}, None, origin)
    monkeypatch.setitem(LIMITS, 'search_steps', 0)
    other = FilePredictionStore(tmp_path / 'budget')
    with pytest.raises(ArticleMapError, match='budget'):
        SealAnalogyTransport(Port(), other).execute(refs, families, 'owner', metadata, {}, None, origin)
    assert not list((tmp_path / 'budget').glob('*/seal.json'))
