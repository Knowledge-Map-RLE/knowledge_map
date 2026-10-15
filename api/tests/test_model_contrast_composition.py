"""Композиция сохраняет общую шкалу, все части и неизвестность нового теста."""
from copy import deepcopy
from hashlib import sha256

import pytest

from application.model_contrast_composition import SealModelContrastComposition
from domain.article_maps import ArticleMapError, ArticleMapAccessDenied, fingerprint
from domain.development_prediction import validate_visible_dag
from domain.model_contrast_composition import compose_model_contrasts, exact_difference, extract_parameter_group, LIMITS
from domain.whole_map_forecast import project
from infrastructure.development_prediction_store import FilePredictionStore
from tests.test_schema6_prediction import graph, ref
from tests.test_reported_summary_contrasts import origins
from tests.test_statistical_context_views import coefficient, context, frame


def parameter_frame():
    parts = []; annotations = []
    for i, (category, point) in enumerate([('q1', None), ('q2', '0.50'), ('q3', '1.25')]):
        s = coefficient(point is None)
        for r in s['roles']:
            r['value'] = r['value'].lower()
            if r['role'] == 'category': r['value'] = category
        s['roles'].append({'role': 'cohort', 'value': 'synthetic cohort', 'reference_kind': 'concept'})
        if point is not None:
            for a in s['attributes']:
                if a['name'] == 'estimate': a['value'] = point
                if a['name'] == 'printed coefficient and ci95': a['value'] = point + ' (0.40 to 1.50)'
                if a['name'] == 'ci95': a['value'] = '0.40 to 1.50'
        c = context(point is None, i); c['reference'] = 'q1'
        if point is not None: c['contrast'] = category + ' versus q1'
        parts.append(s); annotations.append(c)
    return frame(parts), {'statements': annotations}


def record(f):
    return {'key': ('one', 'K1'), 'frame': f, 'eligible': True,
            'native_knowledge': {'semantic_frame': {'statements': [{'statement_id': 'S' + str(i)} for i in range(len(f['statements']))]}}}


def source_map(article='one'):
    f, c = parameter_frame(); m = graph(article, ['alpha', 'beta', 'gamma'])
    m['pipeline_id'] = 'text_reified'; g = m['graph']; k = deepcopy(g['knowledge'][0])
    k['semantic_frame'] = {'logic': 'contrast', 'statements': []}; g['concepts'] = []
    concept_ids = {}
    for i, s in enumerate(f['statements']):
        refs = []
        for r in s['roles']:
            if r['value'] not in concept_ids:
                cid = 'C' + str(len(concept_ids)); concept_ids[r['value']] = cid
                g['concepts'].append({'id': cid, 'display_text': r['value'], 'aliases': []})
            refs.append({'role': r['role'], 'concept_id': concept_ids[r['value']], 'knowledge_id': None})
        k['semantic_frame']['statements'].append({'statement_id': 'S' + str(i), 'predicate': s['predicate'],
            'roles': refs, 'negated': s['negated'], 'quantifier': s['scope']['quantifier'],
            'modality': s['scope']['modality'], 'conditions': ['Synthetic same fitted model'],
            'temporal_context': 'baseline', 'qualifiers': {'attributes': [
                {**a, 'name': a['name'].replace(' ', '_')} for a in s['attributes']]},
            'provenance': {'unit_ids': ['U1'], 'source_spans': []}})
    g['knowledge'] = [k]; g['nodes'] = [{'id': 'B1', 'knowledge_id': 'K1'}]; g['edges'] = []; g['transitions'] = []
    text = '😀 Synthetic table ' + article + ': q1 Reference; q2 0.50; q3 1.25; same Tobit model and adjustment.'
    m['source'] = {'text': text, 'sha256': sha256(text.encode()).hexdigest(), 'content_end': len(text),
        'offset_encoding': 'unicode_codepoints', 'units': [{'id': 'U1', 'start': 0, 'end': len(text), 'text': text}]}
    u = m['source']['units'][0]
    entry = {'article_id': article, 'knowledge_id': 'K1', 'run_id': m['run_id'], 'source_sha256': m['source']['sha256'],
        'graph_sha256': fingerprint(g), 'knowledge_sha256': fingerprint(k), 'reason_ru': 'Синтетическая модель для проверки арифметики.',
        'statements': c['statements'], 'evidence': [{**u, 'unit_id': u['id'], 'sha256': m['source']['sha256']}]}
    return m, entry


def inputs():
    pairs = [source_map('one'), source_map('two')]
    maps = [p[0] for p in pairs]
    model = {'version': 'statistical-context-audit-1', 'author': 'Codex', 'expert_validated': False,
             'model_calls': 0, 'entries': [p[1] for p in pairs]}
    return maps, model, origins(maps)


def test_actual_new_comparison_and_closed_proof_no_new_p_or_ci():
    maps, model, origin = inputs(); before = deepcopy(maps)
    result = compose_model_contrasts(maps, None, model, origin)
    assert maps == before and len(result['consequences']) == 2
    for r in result['consequences']:
        assert r['reported_parameter_difference'] == '0.75' and r['direction'] == 'higher_as_printed'
        assert (r['from_category'], r['to_category']) == ('q2', 'q3')
        assert r['confidence_interval'] is None and r['p'] is None and r['statistical_finding'] == 'not_established'
        assert not r['future_empirical_prediction'] and not r['transfer_to_other_model_or_population']
        p = r['proof']; assert p['all_parent_positions_retained'] == [0, 1, 2]
        assert p['selected_positions'] == [1, 2] and p['reference_position'] == 0
        assert p['complete_native_knowledge'] == next(m for m in maps if m['article_id'] == p['parent_key'][0])['graph']['knowledge'][0]
        assert not p['conditions_removed'] and not p['parts_independently_asserted']
        assert not p['causality_asserted'] and not p['independent_replication']
        f = r['conclusion_frame']; s = f['statements'][0]
        assert f['kind'] == 'state' and f['logic'] == 'single' and f['action_status'] is None
        assert s['scope']['study_group'] == p['parent_key'][0]
        assert set(r['basis']['scope']['conditions']) <= set(s['scope']['conditions'])
        assert next(a for a in s['attributes'] if a['name'] == 'reported coefficient difference')['value'] == '0.75'
        validate_visible_dag(r['proof_graph'])
    assert result['ablation']['graph'] == result['ablation']['same_semantics_without_dependencies']
    assert not result['graph_advantage_demonstrated'] and not result['scientific_success']


@pytest.mark.parametrize('left,right,result', [('0.10', '0.30', '0.20'), ('1.25', '0.50', '-0.75'),
    ('0.50', '0.50', '0.00'), ('100000000000000000000000000000.1', '100000000000000000000000000000.3', '0.2')])
def test_decimal_consequence_is_exact_beyond_default_decimal_precision(left, right, result):
    assert str(exact_difference(left, right)) == result


def test_extreme_precision_aborts_instead_of_rounding():
    with pytest.raises(ArticleMapError, match='precision budget'): exact_difference('1e20000', '1')
    with pytest.raises(ArticleMapError, match='Finite'): exact_difference('not reported', '1')


@pytest.mark.parametrize('change', ['scope', 'unit', 'reference', 'adjustment', 'sample', 'table', 'estimand', 'evidence'])
def test_incompatible_parameter_basis_never_composes(change):
    f, audit = parameter_frame(); s = f['statements'][2]; c = audit['statements'][2]
    if change == 'scope': s['scope']['time'] = 'followup'
    elif change == 'unit': c['unit'] = 'MMSE points/year'
    elif change == 'reference': c['reference'] = 'q0'
    elif change == 'adjustment':
        next(a for a in s['attributes'] if a['name'] == 'adjustment')['value'] = 'unadjusted'
        next(r for r in s['roles'] if r['role'] == 'adjustment')['value'] = 'unadjusted'
    elif change == 'sample': next(a for a in s['attributes'] if a['name'] == 'analysis n')['value'] = '300'
    elif change == 'table': next(a for a in s['attributes'] if a['name'] == 'source table')['value'] = '3'
    elif change == 'estimand': c['estimand'] = 'another response estimand'
    else: c['evidence_unit_ids'] = ['U2']
    groups, reason = extract_parameter_group(record(f), audit)
    assert groups is None and reason


@pytest.mark.parametrize('change', ['no_reference', 'duplicate_category', 'negated', 'unknown', 'intended', 'continuous', 'missing_point'])
def test_unlicensed_whole_parent_rejected(change):
    f, audit = parameter_frame(); r = record(f)
    if change == 'no_reference':
        f['statements'].pop(0); audit['statements'].pop(0)
    elif change == 'duplicate_category':
        next(x for x in f['statements'][2]['roles'] if x['role'] == 'category')['value'] = 'q2'
    elif change == 'negated': f['statements'][2]['negated'] = True
    elif change == 'unknown': r['eligible'] = False
    elif change == 'intended': f.update(kind='action', action_status='intended')
    elif change == 'continuous': audit['statements'][2]['kind'] = 'continuous_coefficient'
    else: f['statements'][2]['attributes'] = [a for a in f['statements'][2]['attributes'] if a['name'] != 'estimate']
    assert extract_parameter_group(r, audit)[0] is None


def test_uncertainty_not_borrowed_from_two_significant_source_coefficients():
    maps, model, origin = inputs()
    r = compose_model_contrasts(maps, None, model, origin)['consequences'][0]
    assert r['reported_parameter_difference'] == '0.75' and r['statistical_finding'] == 'not_established'
    assert 'Cov' in r['proof']['foundation']['variance_equation']


def test_discarding_development_groups_does_not_create_false_graph_advantage(monkeypatch):
    import domain.model_contrast_composition as module
    maps, model, origin = inputs(); original = module.project
    before = compose_model_contrasts(maps, None, model, origin)
    def flat(*args):
        records, groups, coverage = original(*args)
        return records, [], coverage
    monkeypatch.setattr(module, 'project', flat)
    assert compose_model_contrasts(maps, None, model, origin) == before


def test_visible_cycle_and_hidden_cycle_do_not_become_parameter_equivalence():
    maps, model, origin = inputs()
    maps[0]['graph']['edges'] = [{'source': 'B1', 'target': 'B1'}]
    with pytest.raises(ArticleMapError): compose_model_contrasts(maps, None, model, origin)
    maps, _, _ = inputs()
    s = maps[0]['graph']['knowledge'][0]['semantic_frame']['statements'][0]
    s['roles'][0].update(concept_id=None, knowledge_id='K1')
    assert not project(maps)[0][('one', 'K1')]['eligible']


def test_reproducible_seal_owner_cutoff_identity_and_network_forbidden(tmp_path, monkeypatch):
    import socket
    import httpx
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('Сеть запрещена'))
    monkeypatch.setattr(httpx.Client, 'send', lambda *a, **k: pytest.fail('Модельные вызовы запрещены'))
    maps, model, origin = inputs(); reads = []
    class Port:
        def get(self, article, pipeline, owner, run):
            if owner != 'owner': raise ArticleMapAccessDenied('Owner differs')
            assert article in {'one', 'two'}; reads.append(article)
            return next(m for m in maps if m['article_id'] == article)
    app = SealModelContrastComposition(Port(), FilePredictionStore(tmp_path))
    refs = [ref(m['article_id']) for m in maps]; families = {m['article_id']: m['article_id'] for m in maps}
    metadata = {'question': None, 'training_cutoff': '2022-12-31', 'source_dates': {'one': '2020-01-01', 'two': '2020-01-01'}}
    r = app.execute(refs, families, 'owner', metadata, {}, None, model, origin)
    assert r == app.execute(refs, families, 'owner', metadata, {}, None, model, origin)
    assert len(r['consequences']) == 2 and len(list(tmp_path.glob('*/seal.json'))) == 1
    with pytest.raises(ArticleMapAccessDenied): app.execute(refs, families, 'another', metadata, {}, None, model, origin)
    wrong = deepcopy(refs); wrong[0]['run_id'] = 'another-run'
    with pytest.raises(ArticleMapError, match='identity'): app.execute(wrong, families, 'owner', metadata, {}, None, model, origin)
    wrong = deepcopy(metadata); wrong['source_dates']['one'] = '2023-01-01'
    with pytest.raises(ArticleMapError, match='Future'): app.execute(refs, families, 'owner', wrong, {}, None, model, origin)
    assert set(reads) == {'one', 'two'}


def test_budget_failure_never_publishes_partial_result(tmp_path, monkeypatch):
    maps, model, origin = inputs(); monkeypatch.setitem(LIMITS, 'pair_steps', 0)
    class Port:
        def get(self, article, pipeline, owner, run): return next(m for m in maps if m['article_id'] == article)
    store = FilePredictionStore(tmp_path)
    with pytest.raises(ArticleMapError, match='budget'):
        SealModelContrastComposition(Port(), store).execute([ref(m['article_id']) for m in maps],
            {m['article_id']: m['article_id'] for m in maps}, 'owner',
            {'question': None, 'training_cutoff': '2022-12-31', 'source_dates': {'one': '2020-01-01', 'two': '2020-01-01'}},
            {}, None, model, origin)
    assert not list(tmp_path.glob('*/seal.json'))
