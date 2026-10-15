"""Прежний доступ и известный общий паттерн не доказывают полного тождества фактов."""
from copy import deepcopy
from hashlib import sha256

import pytest

from domain.article_maps import ArticleMapError, fingerprint
from domain.forecast_claim_qualification import VERSION, citation_occurrences, qualify
from tests.test_external_operation_transfer import external_inputs
from domain.external_operation_transfer import forecast_external
from tests.test_operation_applicability import inputs


def setup():
    training, methods, _ = external_inputs()
    for role in methods['receivers'][0]['body'][0]['frame']['statements'][0]['roles']:
        if role['role'] == 'intervention': role['value'] = 'ATROSAB selective antagonist in external-study'
    frozen = forecast_external(training, methods)
    maps = inputs()[1]
    frozen['coverage']['sources'] = len(maps)
    for m in maps:
        source = m['source']; source['text'] += '\n10.1038/s41598-018-31957-7\n'
        source['sha256'] = sha256(source['text'].encode()).hexdigest()
    candidates = {c['id']: c for folds in frozen['modes'].values() for f in folds for c in f['predictions']}
    audit = {'version': VERSION, 'author': 'Codex', 'expert_validated': False, 'model_calls': 0,
        'forecast_sha256': fingerprint(frozen), 'map_hashes': [fingerprint(m) for m in maps],
        'external_doi': '10.1038/s41598-018-31957-7', 'candidates': [{'prediction_id': cid,
            'known_pattern_evidence': [], 'outcome_temporal_observations': [], 'reason_ru': 'Не установлено'} for cid in candidates]}
    return frozen, maps, audit


def test_complete_corpus_and_unique_candidates_are_retained_without_claiming_novelty():
    frozen, maps, audit = setup(); before = deepcopy((frozen, maps, audit)); result = qualify(frozen, maps, audit)
    assert (frozen, maps, audit) == before
    assert result['canonical_blocks'] == sum(len(m['graph']['knowledge']) for m in maps)
    assert len(result['candidates']) == 1
    assert result['status_counts'] == {'not_established': 1}
    assert len(result['citation_occurrences']) == len(maps)
    assert all(not r['fact_equivalence'] for r in result['citation_occurrences'])
    assert result['candidates'][0]['temporal']['status'] == 'missing_prediction_temporal_contract'
    assert not result['new_scientific_knowledge_confirmed'] and not result['graph_advantage_demonstrated']


def test_citation_is_not_a_prefix_of_other_doi_and_case_is_insensitive():
    _, maps, _ = setup(); m = deepcopy(maps[0]); doi = '10.12345/test'
    m['source']['text'] = '10.12345/test-long X10.12345/test 10.12345/test.long 10.12345/TEST.\n'
    m['source']['content_end'] = 0
    m['source']['sha256'] = sha256(m['source']['text'].encode()).hexdigest()
    rows = citation_occurrences([m], doi)
    assert len(rows) == 1 and rows[0]['text'] == '10.12345/TEST' and rows[0]['section'] == 'references'


def known_setup(text='Atrosab demonstrated therapeutic activity in the EAE model of MS'):
    frozen, maps, audit = setup(); m = maps[0]; source = m['source']; start = source['content_end'] + 1
    insertion = '\n' + text + '\n'
    source['text'] = source['text'][:source['content_end']] + insertion + source['text'][source['content_end']:]
    source['content_end'] += len(insertion); source['sha256'] = sha256(source['text'].encode()).hexdigest()
    u = {'id': 'U-known', 'start': start, 'end': start + len(text), 'text': text}
    source['units'].append(u); audit['map_hashes'] = [fingerprint(m) for m in maps]
    audit['candidates'][0]['known_pattern_evidence'] = [{'article_id': m['article_id'], 'run_id': m['run_id'],
        'source_sha256': m['source']['sha256'], 'unit_id': u['id'], 'start': u['start'], 'end': u['end'],
        'text': text, 'sha256': sha256(text.encode()).hexdigest(), 'relation': 'coarse_direction_already_described',
        'license_kind': 'explicit_therapeutic_activity_eae', 'intervention_alias': 'Atrosab'}]
    return frozen, maps, audit


def test_known_source_fragment_is_coarse_and_never_full_fact_equivalence():
    frozen, maps, audit = known_setup()
    row = qualify(frozen, maps, audit)['candidates'][0]
    assert row['novelty_status'] == 'known_coarse_pattern' and not row['full_fact_equivalence']
    audit['candidates'][0]['known_pattern_evidence'][0]['start'] += 1
    with pytest.raises(ArticleMapError): qualify(frozen, maps, audit)


@pytest.mark.parametrize('text', ['Atrosab had an overlapping epitope in the EAE model',
    'Atrosab demonstrated therapeutic activity in the NASH model',
    'H398 demonstrated therapeutic activity in the EAE model of MS',
    'XAtrosab demonstrated therapeutic activity in the EAE model of MS'])
def test_unrelated_source_quote_cannot_be_licensed_as_a_known_direction(text):
    frozen, maps, audit = known_setup(text)
    with pytest.raises(ArticleMapError): qualify(frozen, maps, audit)


@pytest.mark.parametrize('change', ['maps', 'forecast', 'candidate', 'duplicate', 'model', 'source'])
def test_incomplete_or_changed_inputs_are_rejected(change):
    frozen, maps, audit = setup()
    if change == 'maps': maps.pop()
    elif change == 'forecast': frozen['receivers'][0]['source_sha256'] = 'different'
    elif change == 'candidate': audit['candidates'] = []
    elif change == 'duplicate': audit['candidates'].append(deepcopy(audit['candidates'][0]))
    elif change == 'model': audit['model_calls'] = 1
    elif change == 'source': maps[0]['source']['text'] += 'changed'
    with pytest.raises(ArticleMapError): qualify(frozen, maps, audit)


def test_application_publication_is_immutable_and_changed_audit_has_another_run(tmp_path, monkeypatch):
    import socket
    import httpx
    from application.forecast_claim_qualification import SealForecastClaimQualification
    from infrastructure.development_prediction_store import FilePredictionStore
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('Network forbidden'))
    monkeypatch.setattr(httpx.Client, 'send', lambda *a, **k: pytest.fail('Model calls forbidden'))
    frozen, maps, audit = setup()
    class Port:
        def load(self): return deepcopy((frozen, maps, audit))
    store = FilePredictionStore(tmp_path); app = SealForecastClaimQualification(Port(), store)
    result = app.execute({'code': 'fixed'})
    assert result == app.execute({'code': 'fixed'})
    assert len(list(tmp_path.glob('*/seal.json'))) == 1
    audit['candidates'][0]['reason_ru'] = 'Уточнение сохраняется отдельно'
    changed = app.execute({'code': 'fixed'})
    assert changed['run_id'] != result['run_id'] and store.read_seal(result['run_id']) == result


def test_same_semantics_without_visible_dependencies_has_same_qualification():
    frozen, maps, audit = setup(); original = qualify(frozen, maps, audit)
    flat = deepcopy(maps)
    for m in flat:
        m['graph']['edges'] = []; m['graph']['transitions'] = []
    changed = deepcopy(audit); changed['map_hashes'] = [fingerprint(m) for m in flat]
    result = qualify(frozen, flat, changed)
    for key in ('inventory', 'candidates', 'citation_occurrences', 'source_consequences', 'status_counts'):
        assert result[key] == original[key]
