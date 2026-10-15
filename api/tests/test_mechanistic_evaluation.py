"""Оценщик сохраняет контекст, отсутствие измерения и неизменяемую фиксацию."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import socket

import pytest

from domain.article_maps import ArticleMapError, fingerprint
from domain.mechanistic_evaluation import evaluate
from application.mechanistic_evaluation import EvaluateMechanisticOpportunities
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.mechanistic_controls import FileMechanisticControls


def fixture():
    text = 'Synthetic methods and direct result 🙂. References excluded.'
    end = text.index(' References')
    source = {'text': text, 'sha256': sha256(text.encode()).hexdigest(), 'offset_encoding': 'Unicode code points',
              'content_end': end, 'doi': '10.test/control', 'pmcid': 'PMC-test',
              'units': [{'id': 'U1', 'start': 0, 'end': end, 'text': text[:end]}]}
    proof = {'unit_id': 'U1', 'start': 0, 'end': end, 'text': text[:end], 'sha256': sha256(text[:end].encode()).hexdigest()}
    conclusion = {'species': 'mouse', 'disease': 'disease', 'intervention': 'fusion', 'compartment': 'brain',
                  'routes': ['intravenous'], 'outcome': 'outcome', 'expected_direction': 'decrease'}
    candidate = {'id': 'candidate', 'conclusion': conclusion, 'outcome_ru': 'Исход'}
    forecast = {'run_id': 'a' * 64, 'candidates': {'graph': [candidate], 'without_dependencies': [candidate],
                                               'permuted_dependencies': [], 'source_neighborhood': []}}
    plan = {'version': 'mechanistic-opportunity-evaluation-1', 'model_calls': 0, 'forecast_run_id': forecast['run_id'],
            'forecast_sha256': fingerprint(forecast), 'contexts_required_equal': ['species', 'disease', 'intervention', 'compartment'],
            'statuses': ['direction_match', 'direction_contradiction', 'not_addressed', 'incompatible_context', 'insufficient_information'],
            'hypothesis_ids': ['candidate'], 'training_cutoff': '2017-05-15', 'intervention_aliases': ['fusion'], 'outcome_policy': {'outcome': ['direct outcome']}}
    context = {k: conclusion[k] for k in ('species', 'disease', 'intervention', 'compartment')}
    row = {'id': 'result', 'context': context, 'route': 'intravenous', 'outcome': 'outcome', 'measurement': 'direct outcome',
           'polarity': 'identity', 'direction': 'decrease', 'finding': 'detected', 'p': '<0.05', 'negated': False,
           'modality': 'observed', 'action_status': 'performed', 'direct_experiment': True, 'comparator': 'saline',
           'context_evidence': [proof], 'evidence': [proof], 'reason_ru': 'Прямое измерение.', 'limits_ru': 'Только измеренный показатель.'}
    control = {'author': 'Codex', 'expert_validated': False, 'model_calls': 0, 'primary_study': True, 'fulltext': True,
               'source_sha256': source['sha256'], 'doi': source['doi'], 'pmcid': source['pmcid'], 'published_on': '2022-10-16',
               'source_version': 'test-source-1', 'limitations_ru': ['Ограничения.'], 'coverage_reason_ru': 'Полный просмотр.',
               'identity_licenses': [], 'observations': [row], 'unmeasured': []}
    return forecast, plan, control, source


def result(f, p, c, s):
    return evaluate(f, p, c, s)['modes']['without_dependencies']['rows'][0]


def test_direct_match_is_not_causality_or_graph_advantage():
    f, p, c, s = fixture(); r = evaluate(f, p, c, s)
    assert r['modes']['graph']['counts'] == {'direction_match': 1}
    assert not r['graph_advantage_demonstrated'] and not r['scientific_success'] and not r['forecast_changed']
    assert not result(f, p, c, s)['causality_confirmed']


def test_opposite_observed_direction_is_contradiction():
    f, p, c, s = fixture(); c['observations'][0]['direction'] = 'increase'
    assert result(f, p, c, s)['status'] == 'direction_contradiction'


def test_inverse_measurement_and_nondetection_preserve_distinct_layers():
    f, p, c, s = fixture(); row = c['observations'][0]
    row.update(polarity='inverse', direction='increase', finding='not_detected', p='0.07')
    r = result(f, p, c, s)
    assert r['status'] == 'direction_match' and r['comparisons'][0]['statistical_finding'] == 'not_detected'
    assert r['comparisons'][0]['p'] == '0.07'


@pytest.mark.parametrize('field', ['species', 'disease', 'intervention', 'compartment'])
def test_different_context_is_not_a_match(field):
    f, p, c, s = fixture(); c['observations'][0]['context'][field] = 'different'
    assert result(f, p, c, s)['status'] == 'incompatible_context'


@pytest.mark.parametrize('field', ['species', 'disease', 'intervention', 'compartment'])
def test_unknown_context_blocks_match(field):
    f, p, c, s = fixture(); c['observations'][0]['context'][field] = None
    assert result(f, p, c, s)['status'] == 'insufficient_information'


@pytest.mark.parametrize('field,value', [('route', 'intracerebroventricular'), ('route', None),
    ('modality', 'cited'), ('action_status', 'unresolved'), ('direct_experiment', False), ('negated', True), ('direction', 'unknown')])
def test_missing_direct_compatible_observation_does_not_confirm(field, value):
    f, p, c, s = fixture(); c['observations'][0][field] = value
    assert result(f, p, c, s)['status'] in {'incompatible_context', 'insufficient_information'}


def test_alias_needs_separate_source_identity_license():
    f, p, c, s = fixture(); c['observations'][0]['context']['intervention'] = 'short name'
    assert result(f, p, c, s)['status'] == 'incompatible_context'
    c['identity_licenses'] = [{'alias': 'short name', 'canonical': 'fusion', 'reason_ru': 'Описание конструкции.', 'evidence': c['observations'][0]['evidence']}]
    assert result(f, p, c, s)['status'] == 'direction_match'


def test_absence_requires_explicit_fulltext_audit():
    f, p, c, s = fixture(); proof = c['observations'][0]['evidence']; c['observations'] = []
    with pytest.raises(ArticleMapError): result(f, p, c, s)
    c['unmeasured'] = [{'outcome': 'outcome', 'reason_ru': 'Не измерялся.', 'evidence': proof}]
    assert result(f, p, c, s)['status'] == 'not_addressed'


def test_opposing_direct_results_are_reported_as_mixed():
    f, p, c, s = fixture(); other = deepcopy(c['observations'][0]); other.update(id='other', direction='increase')
    c['observations'].append(other); r = result(f, p, c, s)
    assert r['mixed_directions'] and r['status'] == 'insufficient_information'


@pytest.mark.parametrize('mutation', ['forecast', 'hypotheses', 'source', 'quote', 'reference', 'unit', 'duplicate', 'old', 'abstract', 'model', 'nonprimary'])
def test_tampering_and_unavailable_control_rejected(mutation):
    f, p, c, s = fixture()
    if mutation == 'forecast': f['new'] = True
    elif mutation == 'hypotheses': p['hypothesis_ids'] = []
    elif mutation == 'source': s['text'] += '!'
    elif mutation == 'quote': c['observations'][0]['evidence'][0]['text'] += '!'
    elif mutation == 'reference': c['observations'][0]['evidence'][0]['end'] += 1
    elif mutation == 'unit': c['observations'][0]['evidence'][0]['unit_id'] = 'missing'
    elif mutation == 'duplicate': c['observations'].append(deepcopy(c['observations'][0]))
    elif mutation == 'old': c['published_on'] = p['training_cutoff']
    elif mutation == 'abstract': c['fulltext'] = False
    elif mutation == 'model': c['model_calls'] = 1
    elif mutation == 'nonprimary': c['primary_study'] = False
    with pytest.raises(ArticleMapError): result(f, p, c, s)


def test_immutable_evaluation_replays_without_network_or_map_port(tmp_path, monkeypatch):
    f, p, c, s = fixture(); store = FilePredictionStore(tmp_path / 'runs'); store.seal(f['run_id'], f)
    class Controls:
        def get(self, control_id):
            assert control_id == 'listed'; return c, s
    def forbidden(*args, **kwargs): raise AssertionError('Network/model transport forbidden')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    use = EvaluateMechanisticOpportunities(store, Controls()); before = (store.path(f['run_id']) / 'predictions.json').read_bytes()
    a = use.execute(f['run_id'], p, 'listed', {'evaluator': 'fixed'})
    b = use.execute(f['run_id'], p, 'listed', {'evaluator': 'fixed'})
    assert a == b and before == (store.path(f['run_id']) / 'predictions.json').read_bytes()
    assert len(list((store.path(f['run_id']) / 'evaluations').iterdir())) == 1


def test_file_port_reads_only_explicit_hash_bound_artifacts(tmp_path):
    f, p, c, s = fixture(); manifest = {'listed': {}}
    for kind, value in [('control', c), ('source', s)]:
        path = tmp_path / (kind + '.json'); raw = json.dumps(value).encode(); path.write_bytes(raw)
        manifest['listed'][kind] = {'path': str(path), 'sha256': sha256(raw).hexdigest()}
    port = FileMechanisticControls(manifest)
    assert port.get('listed') == (c, s) and len(port.reads) == 2
    with pytest.raises(ArticleMapError): port.get('unlisted')
    Path(manifest['listed']['source']['path']).write_text('{}')
    with pytest.raises(ArticleMapError): port.get('listed')
