"""Одинаковый TNFR1 не делает разные препараты и модели совместимыми."""
from copy import deepcopy
from hashlib import sha256
import pytest

from domain.article_maps import ArticleMapError, fingerprint
from domain.analogy_control_screen import compare_context, screen_controls, VERSION
from application.analogy_control_screen import SealAnalogyControlScreen
from infrastructure.development_prediction_store import FilePredictionStore


def inputs():
    training = {'run_id': 'training', 'binding': {'metadata': {'training_cutoff': '2022-12-31'}}}
    h = {'id': 'h', 'proposed_protocol': {'intervention': {'identity': 'TROS', 'route': 'icv'},
        'population': {'species': 'mouse'}, 'challenge': {'identity': 'amyloid'},
        'assessment_time': {'proposed_hours_post_injection': 6}}}
    f = {'run_id': 'forecast', 'binding': {'forecast_run_id': 'training', 'forecast_sha256': fingerprint(training)},
         'hypotheses': [h], 'question': None, 'model_calls': 0, 'future_results_scored': 0}
    text = 'Синтетические методы: иной препарат 🙂 и клеточный опыт.'
    unit = {'id': 'U1', 'start': 0, 'end': len(text), 'text': text}
    packet = {'pmcid': 'PMCsynthetic', 'doi': '10.synthetic/control', 'source': {'text': text, 'sha256': sha256(text.encode()).hexdigest(),
        'offset_encoding': 'unicode_codepoints', 'units': [unit], 'content_end': len(text)}}
    registry = {'forecast_run_id': 'forecast', 'forecast_sha256': fingerprint(f), 'record_count': 1,
        'queries': [{'query': 'specific1'}, {'query': 'specific2'}, {'query': 'specific3'}, {'query': 'broad'}],
        'records': [{'metadata': {'source': 'MED', 'id': '1', 'pmcid': 'PMCsynthetic', 'doi': '10.synthetic/control',
            'firstPublicationDate': '2023-03-10', 'pubTypeList': {'pubType': ['research-article']}}, 'queries': ['specific1']}]}
    e = {**unit, 'unit_id': 'U1', 'sha256': sha256(text.encode()).hexdigest()}; e.pop('id')
    row = {'record_key': 'MED:1', 'status': 'full_primary_context_screen', 'reason_ru': 'Другой препарат и модель.',
        'evidence': [e], 'contexts': [{'intervention': 'affibody', 'biological_system': 'cell_cultures',
            'challenge': 'TNF', 'route': 'cell_media', 'assessment_hours': 24}]}
    a = {'version': VERSION, 'author': 'Codex', 'expert_validated': False, 'model_calls': 0,
        'forecast_sha256': fingerprint(f), 'registry_sha256': fingerprint(registry), 'training_cutoff': '2022-12-31',
        'sources': {'PMCsynthetic': {'packet_sha256': fingerprint(packet), 'source_sha256': packet['source']['sha256']}},
        'decisions': [row]}
    return f, registry, {'PMCsynthetic': packet}, a, training


def test_context_checks_precede_outcome_and_unknown_is_not_equivalence():
    actual = {'intervention': 'TROS', 'biological_system': 'humanized_mouse', 'challenge': 'amyloid', 'route': 'icv', 'assessment_hours': 6}
    assert compare_context(actual, actual)['status'] == 'eligible_for_outcome_assessment'
    for field in actual:
        other = deepcopy(actual); other[field] = None
        assert compare_context(actual, other)['status'] == 'insufficient_information'
        other[field] = 'different'
        assert compare_context(actual, other)['status'] == 'incompatible_context'


def test_real_context_mismatch_is_not_refutation_or_validation():
    args = inputs(); before = deepcopy(args); r = screen_controls(*args)
    assert args == before and r['comparison_counts'] == {'incompatible_context': 1}
    assert r['future_directional_results_scored'] == r['confirmed_predictions'] == 0
    assert r['accuracy'] is None and not r['forecast_modified'] and not r['graph_advantage_demonstrated']


@pytest.mark.parametrize('change', ['forecast', 'registry', 'training', 'cutoff', 'future_date', 'evidence',
    'unknown_unit', 'packet', 'unit', 'missing_decision', 'duplicate_decision', 'review_claim', 'unknown_status', 'model'])
def test_corrupted_scientific_bindings_rejected(change):
    f, r, p, a, t = inputs()
    if change == 'forecast': a['forecast_sha256'] = 'wrong'
    elif change == 'registry': a['registry_sha256'] = 'wrong'
    elif change == 'training': t['run_id'] = 'wrong'
    elif change == 'cutoff': a['training_cutoff'] = '2024-12-31'
    elif change == 'future_date':
        r['records'][0]['metadata']['firstPublicationDate'] = '2022-01-01'; a['registry_sha256'] = fingerprint(r)
    elif change == 'evidence': a['decisions'][0]['evidence'][0]['text'] += 'wrong'
    elif change == 'unknown_unit': a['decisions'][0]['evidence'][0]['unit_id'] = 'wrong'
    elif change == 'packet': p['PMCsynthetic']['pmcid'] = 'wrong'
    elif change == 'unit':
        p['PMCsynthetic']['source']['units'][0]['end'] -= 1
        a['sources']['PMCsynthetic']['packet_sha256'] = fingerprint(p['PMCsynthetic'])
    elif change == 'missing_decision': a['decisions'] = []
    elif change == 'duplicate_decision': a['decisions'].append(deepcopy(a['decisions'][0]))
    elif change == 'review_claim': a['decisions'][0]['status'] = 'review_not_primary'
    elif change == 'unknown_status': a['decisions'][0]['status'] = 'confirmed'
    else: a['model_calls'] = 1
    with pytest.raises(ArticleMapError): screen_controls(f, r, p, a, t)


def test_screening_seal_replays_without_network_and_never_changes_forecast(tmp_path, monkeypatch):
    import socket
    import httpx
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **kw: pytest.fail('Сеть запрещена'))
    monkeypatch.setattr(httpx.Client, 'send', lambda *a, **kw: pytest.fail('Модели запрещены'))
    f, r, p, a, t = inputs(); old = deepcopy(f); store = FilePredictionStore(tmp_path)
    app = SealAnalogyControlScreen(store)
    result = app.execute(f, r, p, a, t, {})
    assert result == app.execute(f, r, p, a, t, {}) and f == old
    a['decisions'] = []
    with pytest.raises(ArticleMapError): app.execute(f, r, p, a, t, {})
    assert len(list(tmp_path.glob('*/seal.json'))) == 1
