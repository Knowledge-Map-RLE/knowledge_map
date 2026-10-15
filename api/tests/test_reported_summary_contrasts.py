"""Статистический тип задаёт источник; закрытое сравнение не становится прогнозом наблюдения."""
from copy import deepcopy
from hashlib import sha256

import pytest

from application.closed_summary_contrasts import SealClosedSummaryContrasts
from domain.article_maps import ArticleMapAccessDenied, ArticleMapError, fingerprint
from domain.reported_summary_contrasts import closed_profile, parse_summary, project_closed_summaries
from domain.whole_map_forecast import project
from infrastructure.development_prediction_store import FilePredictionStore
from tests.test_schema6_prediction import graph, ref


def fixture_map(article='one', label='Age in years, median (IQR)', values=None, header=None):
    values = values or ['87.2 (86.1–88.7)', '86.9 (85.9–88.4)', '88.4 (87.5–89.1)']
    m = graph(article, ['alpha', 'beta', 'gamma'])
    m['pipeline_id'] = 'text_reified'
    g = m['graph']; k = deepcopy(g['knowledge'][0]); k['kind'] = 'state'
    k['semantic_frame']['logic'] = 'contrast'; base = k['semantic_frame']['statements'][0]
    k['semantic_frame']['statements'] = []
    g['concepts'] = [{'id': 'C1', 'display_text': label}, {'id': 'C2', 'display_text': 'Cohort ' + article}]
    if header: g['concepts'].append({'id': 'C3', 'display_text': header.split('|')[0].strip()})
    for i, value in enumerate(values):
        g['concepts'].append({'id': 'P' + str(i), 'display_text': 'Population ' + str(i)})
        s = deepcopy(base); s['statement_id'] = 'S' + str(i)
        s['predicate'] = 'reported baseline summary'
        s['roles'] = [{'role': r, 'concept_id': cid, 'knowledge_id': None}
                      for r, cid in [('measure', 'C1'), ('cohort', 'C2'), ('population', 'P' + str(i))]]
        if header: s['roles'].append({'role': 'grouping', 'concept_id': 'C3', 'knowledge_id': None})
        s['qualifiers'] = {'attributes': [{'name': 'printed_summary', 'value': value, 'unit': None},
                                         {'name': 'group_n', 'value': '100', 'unit': 'participants'}]}
        s['quantifier'] = 'some'; s['modality'] = 'reported'; s['conditions'] = ['Source-local observed table']
        s['provenance'] = {'unit_ids': ['U1'], 'source_spans': []}
        k['semantic_frame']['statements'].append(s)
    g['knowledge'] = [k]; g['nodes'] = [{'id': 'B1', 'knowledge_id': k['knowledge_id']}]
    g['edges'] = []; g['transitions'] = []
    table = (header + '\n' if header else '') + label + ' | ' + ' | '.join(values)
    text = '😀 Source ' + article + '\n' + table
    start = text.index(table)
    m['source'] = {'text': text, 'sha256': sha256(text.encode()).hexdigest(), 'content_end': len(text),
        'offset_encoding': 'unicode_codepoints', 'units': [{'id': 'U1', 'text': table, 'start': start, 'end': len(text)}]}
    return m


def profile(m):
    rec = project([m])[0][(m['article_id'], 'K1')]
    return closed_profile(rec, m['graph']['knowledge'][0], m['source'],
                          {c['id']: c['display_text'] for c in m['graph']['concepts']})


@pytest.mark.parametrize('kind,raw,field,expected', [
    ('median_iqr', '87.2 (86.1–88.7)', 'q1', '86.1'),
    ('median_iqr', '-2 (-3–-1)', 'location', '-2'),
    ('mean_sd', '−2.3 ± 0.4', 'sd', '0.4'),
    ('count_percent', '0 (0)', 'percent', '0'),
    ('count_percent', '2 (29)', 'count', '2'),
])
def test_typed_decimal_parse_preserves_each_component(kind, raw, field, expected):
    parsed, error = parse_summary(raw, kind)
    assert error is None and parsed[field] == expected and parsed['raw'] == raw


@pytest.mark.parametrize('kind,raw,error', [
    ('median_iqr', '2.1 (2.3–2.5)', 'median_outside_reported_iqr'),
    ('median_iqr', '2.6 (2.9–3.3)', 'median_outside_reported_iqr'),
    ('median_iqr', '3 (4–2)', 'median_outside_reported_iqr'),
    ('mean_sd', '2 ± -1', 'negative_reported_sd'),
    ('mean_sd', '2 (1)', 'invalid_mean_sd_syntax'),
    ('count_percent', '137 (20.2', 'invalid_count_percent_syntax'),
    ('count_percent', '1.5 (20)', 'invalid_count_percent_syntax'),
    ('count_percent', '1 (101)', 'reported_percent_out_of_range'),
    ('count_percent', '2 (29) extra', 'invalid_count_percent_syntax'),
    (None, '2 (1)', 'summary_definition_missing'),
])
def test_malformed_or_wrong_statistics_never_auto_repaired(kind, raw, error):
    assert parse_summary(raw, kind) == (None, error)


def test_whole_contrast_and_unicode_source_proof_unchanged():
    m = fixture_map(); before = deepcopy(m); p, error = profile(m)
    assert error is None and m == before
    assert p['orders'][0]['ascending_dense_ranks'] == [2, 1, 3]
    assert p['proof']['complete_native_knowledge'] == m['graph']['knowledge'][0]
    b = p['proof']['source_binding']; row = b['row']
    assert m['source']['text'][row['start']:row['end']] == row['text']
    assert p['scope']['quantifier'] == 'some' and p['scope']['modality'] == 'reported'
    assert p['measurement_basis']['location_and_spread_unit'] == 'year'
    assert not p['separate_part_premise_license'] and not p['forecast_of_future_article']
    assert not p['proof']['independent_replication'] and not p['proof']['groups_disjoint_or_independent_asserted']


def test_complete_row_rejected_when_one_median_is_invalid():
    m = fixture_map(values=['2 (1–3)', '5 (6–7)', '3 (2–4)'])
    result = project_closed_summaries(project([m])[0], [m])
    assert result['profiles'] == [] and result['counts'] == {'median_outside_reported_iqr': 1}


def test_explicit_source_section_defines_count_percent_and_does_not_recompute_denominator():
    m = fixture_map(label='High school', header='Education, n (%) | |', values=['2 (29)', '4 (50)', '3 (38)'])
    p, error = profile(m)
    assert error is None and p['proof']['source_binding']['definition_from'] == 'explicit_section_header'
    assert p['orders'][0]['ascending_dense_ranks'] == [1, 3, 2]
    assert p['rows'][0]['summary']['percent'] == '29' and p['rows'][0]['summary']['item_denominator'] is None
    assert p['measurement_basis']['count_unit'] == 'reported_category_count'
    assert all(not r['summary']['percent_recomputed'] for r in p['rows'])


def test_row_statistic_overrides_unrelated_inherited_group_label():
    m = fixture_map(label='Age, mean ± SD', header='Sex, n (%) | |', values=['79 ± 3', '78 ± 3', '78 ± 4'])
    p, error = profile(m)
    assert error is None and p['definition'] == 'mean_sd'
    assert p['orders'][0]['ascending_dense_ranks'] == [2, 1, 1]
    assert p['measurement_basis']['location_and_spread_unit'] is None
    assert p['measurement_basis']['unit_basis'] == 'opaque_source_local_same_row'


def test_split_percentage_header_is_explicitly_bound_to_source():
    m = fixture_map(label='1-7', header='Alcohol, n | (%) |', values=['4 (50)', '2 (29)', '3 (38)'])
    p, error = profile(m)
    assert error is None and p['definition'] == 'count_percent'


def test_numbers_alone_do_not_define_statistic():
    assert profile(fixture_map(label='Opaque measure', values=['2 (29)', '4 (50)', '3 (38)']))[1] == 'explicit_row_or_section_definition_missing'


@pytest.mark.parametrize('mutation,error', [
    ('negated', 'negated_report_is_not_a_measurement'), ('unknown', 'unknown_parent_context'),
    ('different_scope', 'different_summary_scope_or_polarity'), ('same_population', 'repeated_summary_population'),
])
def test_polarity_unknown_scope_and_invalid_comparison_guard(mutation, error):
    m = fixture_map(); rec = project([m])[0][('one', 'K1')]
    if mutation == 'negated': rec['frame']['statements'][0]['negated'] = True
    if mutation == 'unknown': rec['eligible'] = False
    if mutation == 'different_scope': rec['frame']['statements'][1]['scope']['time'] = 'another time'
    if mutation == 'same_population':
        for r in rec['frame']['statements'][1]['roles']:
            if r['role'] == 'population': r['value'] = 'population 0'
    assert closed_profile(rec, m['graph']['knowledge'][0], m['source'],
                          {c['id']: c['display_text'] for c in m['graph']['concepts']})[1] == error


def test_changed_native_row_or_normalized_number_rejected():
    m = fixture_map(); rec = project([m])[0][('one', 'K1')]
    for a in rec['frame']['statements'][0]['attributes']:
        if a['name'] == 'printed summary': a['value'] = '88 (87–89)'
    with pytest.raises(ArticleMapError, match='exact native'):
        closed_profile(rec, m['graph']['knowledge'][0], m['source'], {c['id']: c['display_text'] for c in m['graph']['concepts']})
    m['graph']['knowledge'][0]['semantic_frame']['statements'][0]['qualifiers']['attributes'][0]['value'] = '88 (87–89)'
    assert profile(m)[1] == 'printed_summary_differs_from_source_row'


def test_count_does_not_exceed_declared_population_size():
    assert profile(fixture_map(label='Disease, n (%)', values=['101 (20)', '4 (30)', '3 (50)']))[1] == 'count_exceeds_declared_group_size'


def test_visible_cycle_and_changed_source_hash_rejected():
    m = fixture_map(); m['graph']['edges'] = [{'source': 'B1', 'target': 'B1'}]
    with pytest.raises(ArticleMapError, match='DAG'): project([m])
    m['graph']['edges'] = []; m['source']['text'] += 'changed'
    with pytest.raises(ArticleMapError, match='source hash'): project_closed_summaries(project([m])[0], [m])


def origins(maps):
    sources = []
    for m in maps:
        u = m['source']['units'][0]
        sources.append({'article_id': m['article_id'], 'run_id': m['run_id'], 'source_sha256': m['source']['sha256'],
            'graph_sha256': fingerprint(m['graph']), 'document_kind': 'primary_study', 'dataset_family': m['article_id'],
            'reason_ru': 'Синтетический источник.', 'evidence': [{**u, 'unit_id': u['id'], 'sha256': sha256(u['text'].encode()).hexdigest()}],
            'knowledge': [{'knowledge_id': k['knowledge_id'], 'knowledge_sha256': fingerprint(k),
                'statements': [{'statement_id': s['statement_id'], 'origin': 'primary_result',
                    'evidence_unit_ids': ['U1'], 'reason_ru': 'Синтетическая таблица.'} for s in k['semantic_frame']['statements']]}
                for k in m['graph']['knowledge']]})
    return {'version': 'whole-map-evidence-origin-1', 'author': 'Codex', 'model_calls': 0, 'expert_validated': False, 'sources': sources}


def test_immutable_seal_replay_no_network_owner_identity_and_cutoff(tmp_path, monkeypatch):
    import socket
    import httpx
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('Сеть запрещена'))
    monkeypatch.setattr(httpx.Client, 'send', lambda *a, **k: pytest.fail('Вызов моделей запрещён'))
    maps = [fixture_map('one'), fixture_map('two')]; reads = []
    class Port:
        def get(self, article, pipeline, owner, run):
            if owner != 'owner': raise ArticleMapAccessDenied('Owner differs')
            assert article in {'one', 'two'}; reads.append(article)
            return next(m for m in maps if m['article_id'] == article)
    store = FilePredictionStore(tmp_path); app = SealClosedSummaryContrasts(Port(), store)
    refs = [ref(m['article_id']) for m in maps]; families = {m['article_id']: m['article_id'] for m in maps}
    metadata = {'question': None, 'training_cutoff': '2022-12-31', 'source_dates': {i: '2020-01-01' for i in families}}
    origin = origins(maps)
    first = app.execute(refs, families, 'owner', metadata, {}, None, origin)
    assert len(first['profiles']) == 2 and len(first['coverage']) == 2 and not first['scientific_success']
    assert first == app.execute(refs, families, 'owner', metadata, {}, None, origin)
    assert len(list(tmp_path.glob('*/seal.json'))) == 1
    with pytest.raises(ArticleMapAccessDenied): app.execute(refs, families, 'other', metadata, {}, None, origin)
    bad = deepcopy(refs); bad[0]['run_id'] = 'wrong'
    with pytest.raises(ArticleMapError, match='identity'): app.execute(bad, families, 'owner', metadata, {}, None, origin)
    bad = deepcopy(metadata); bad['source_dates']['one'] = '2023-01-01'
    with pytest.raises(ArticleMapError, match='Future'): app.execute(refs, families, 'owner', bad, {}, None, origin)
    assert set(reads) == {'one', 'two'}


def test_corrupt_source_origin_never_publishes_partial_result(tmp_path):
    maps = [fixture_map('one'), fixture_map('two')]
    class Port:
        def get(self, article, pipeline, owner, run): return next(m for m in maps if m['article_id'] == article)
    origin = origins(maps); origin['sources'][1]['source_sha256'] = 'wrong'
    store = FilePredictionStore(tmp_path)
    with pytest.raises(ArticleMapError, match='binding'):
        SealClosedSummaryContrasts(Port(), store).execute([ref(m['article_id']) for m in maps],
            {m['article_id']: m['article_id'] for m in maps}, 'owner',
            {'question': None, 'training_cutoff': '2022-12-31', 'source_dates': {'one': '2020-01-01', 'two': '2020-01-01'}}, {}, None, origin)
    assert not list(tmp_path.glob('*/seal.json'))
