"""Полные составные знания и удаление зависимостей проверяются независимо."""
from copy import deepcopy
import pytest
from domain.article_maps import ArticleMapError
from domain.whole_map_forecast import project, forecast, template, bind, instantiate
from tests.test_schema6_prediction import graph


def corpus():
    return [graph('one', ['alpha', 'beta', 'gamma']), graph('two', ['delta', 'epsilon', 'zeta']),
            graph('three', ['theta', 'iota', 'kappa'], head=False)]


def families(maps):
    return {m['article_id']: m['article_id'] for m in maps}


def test_full_corpus_has_no_factor_or_predicate_whitelist():
    maps = corpus()
    before = deepcopy(maps)
    result = forecast(maps, families(maps))
    assert maps == before and result['canonical_blocks'] == 8
    assert result['factor_whitelist'] is None and result['predicate_whitelist'] is None
    assert result['rules']
    # В третьей карте нет авторской совместной группы: граф запрещает применение.
    assert not result['predictions']['graph']
    assert result['predictions']['same_rules_without_dependencies']
    assert not result['graph_advantage_demonstrated']


@pytest.mark.parametrize('logic', ['contrast', 'argument', 'conjunction'])
def test_compound_blocks_keep_logic_and_all_statements(logic):
    maps = corpus()
    for m in maps:
        for k in m['graph']['knowledge']:
            k['semantic_frame']['logic'] = logic
            extra = deepcopy(k['semantic_frame']['statements'][0])
            extra['statement_id'] += '-extra'
            extra['predicate'] = 'modulates'
            extra['negated'] = True
            k['semantic_frame']['statements'].append(extra)
    records, _, coverage = project(maps)
    assert len(coverage) == 8
    assert all(r['frame']['logic'] == logic and len(r['frame']['statements']) == 2 for r in records.values())
    assert forecast(maps, families(maps))['rules']


def test_graph_requires_whole_joint_group_and_known_conclusions_are_excluded():
    maps = corpus()
    m = maps[-1]
    # Независимый известный блок удостоверяет совместное использование двух входов.
    extra = deepcopy(m['graph']['knowledge'][0])
    extra['knowledge_id'] = 'K3'
    extra['semantic_frame']['statements'][0]['statement_id'] = 'S3'
    extra['semantic_frame']['statements'][0]['predicate'] = 'joint use'
    m['graph']['knowledge'].append(extra)
    m['graph']['nodes'].append({'id': 'B3', 'knowledge_id': 'K3'})
    m['graph']['transitions'] = [{'sources': ['B1', 'B2'], 'target': 'B3'}]
    m['graph']['edges'] = [{'source': 'B1', 'target': 'B3'}, {'source': 'B2', 'target': 'B3'}]
    result = forecast(maps, families(maps))
    assert result['predictions']['graph']
    assert all(len(c['premises']) == 2 and not c['logical_entailment'] for c in result['predictions']['graph'])
    m['graph']['transitions'][0]['sources'] = ['B1']
    m['graph']['edges'].pop()
    assert not forecast(maps, families(maps))['predictions']['graph']


def test_same_family_cannot_support_rule():
    maps = corpus()
    result = forecast(maps, {m['article_id']: 'same' for m in maps})
    assert not result['rules']


def test_quantifier_modality_and_units_are_not_erased():
    maps = corpus()
    frame = project(maps)[0][('one', 'K1')]['frame']
    pattern = template([{'frame': frame, 'key': ('one', 'K1')}], {'frame': frame})[1]['body'][0]
    changed = deepcopy(frame)
    changed['statements'][0]['scope']['modality'] = 'may'
    assert bind(pattern, changed, {}) is None
    assert instantiate(pattern, bind(pattern, frame, {})) == frame


def test_visible_cycles_rejected():
    maps = corpus()
    maps[0]['graph']['edges'].append({'source': 'B3', 'target': 'B1'})
    with pytest.raises(ArticleMapError, match='DAG'):
        project(maps)


def test_sealing_is_reproducible_and_never_reads_target(tmp_path):
    from application.whole_map_forecast import SealWholeMapForecast
    from infrastructure.development_prediction_store import FilePredictionStore
    from tests.test_schema6_prediction import ref
    maps = corpus()
    class Port:
        def __init__(self):
            self.reads = []
        def get(self, article, pipeline, owner, run):
            assert owner == 'owner'
            assert article != 'target'
            self.reads.append(article)
            return next(m for m in maps if m['article_id'] == article)
    port = Port()
    store = FilePredictionStore(tmp_path)
    app = SealWholeMapForecast(port, store)
    metadata = {'question': None, 'training_cutoff': '2023-12-31', 'source_dates': {m['article_id']: '2022-01-01' for m in maps}}
    first = app.execute([ref(m['article_id']) for m in maps], families(maps), 'owner', metadata, {'test': 'fixed'})
    second = app.execute([ref(m['article_id']) for m in maps], families(maps), 'owner', metadata, {'test': 'fixed'})
    assert first == second and len(list(tmp_path.glob('*/seal.json'))) == 1
    assert set(port.reads) == {'one', 'two', 'three'}
    metadata['source_dates']['one'] = '2024-01-01'
    with pytest.raises(ArticleMapError, match='Future'):
        app.execute([ref(m['article_id']) for m in maps], families(maps), 'owner', metadata, {'test': 'fixed'})


def test_graph_mode_does_not_assert_success_from_candidate_difference():
    result = forecast(corpus(), families(corpus()))
    assert len(result['predictions']['same_rules_without_dependencies']) > len(result['predictions']['graph'])
    assert not result['graph_advantage_demonstrated']


def test_study_context_is_parameterized_without_merging_participants():
    maps = corpus()
    for m in maps:
        m['graph']['concepts'][0]['display_text'] += ' study participants'
        for k in m['graph']['knowledge']:
            s = k['semantic_frame']['statements'][0]
            s['roles'].append({'role': 'sample', 'concept_id': 'C0', 'knowledge_id': None})
            s['conditions'].append('A second explicit condition')
    result = forecast(maps, families(maps))
    assert result['rules']
    candidates = result['predictions']['same_rules_without_dependencies']
    assert candidates
    for c in candidates:
        assert len({p['article_id'] for p in c['premises']}) == 1
        assert c['frame']['statements'][0]['scope']['study_group'] == c['premises'][0]['article_id']
        assert set(c['frame']['statements'][0]['scope']['conditions']) == {'synthetic conditional example', 'a second explicit condition'}


def test_source_local_report_variable_is_not_a_universal_context():
    frame = project(corpus())[0][('one', 'K1')]['frame']
    for s in frame['statements']:
        s['scope']['study_group'] = 'one'
        s['scope']['conditions'] = ['source-local report: one', 'population-specific boundary']
    rule = template([{'key': ('one', 'K1'), 'frame': frame}], {'key': ('one', 'K1'), 'frame': frame})[1]
    target = deepcopy(frame)
    target['statements'][0]['scope']['study_group'] = 'three'
    target['statements'][0]['scope']['conditions'][0] = 'source-local report: three'
    bindings = bind(rule['body'][0], target, {})
    assert bindings and bindings['$study'] == 'three'
    target['statements'][0]['scope']['conditions'].sort()
    assert instantiate(rule['head'], bindings) == target
    assert bind(rule['body'][0], target, {'$study': 'another-study'}) is None
    target['statements'][0]['scope']['conditions'][0] = 'different population'
    assert bind(rule['body'][0], target, {}) is None
