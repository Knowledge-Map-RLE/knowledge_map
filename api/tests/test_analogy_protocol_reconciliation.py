"""Синтетические контексты проверяют запреты переноса, не изображая клинические данные."""
from copy import deepcopy
import socket

import pytest

from application.analogy_protocol_reconciliation import ReconcileSealedAnalogyProtocols
from application.licensed_part_analogy import DiscoverSealedPartAnalogies
from domain.article_maps import ArticleMapError, ArticleMapNotFound, fingerprint
from domain.analogy_protocol_reconciliation import reconcile_protocols, VERSION, DIMENSIONS
from infrastructure.development_prediction_store import FilePredictionStore
from tests.test_licensed_part_analogy_application import stores


def fixture(tmp_path):
    parts, args, forecasts, pp, aa, origin = stores(tmp_path)
    f = DiscoverSealedPartAnalogies(parts, args, forecasts).execute(pp['run_id'], aa['run_id'], origin, {})
    g = aa['semantic_graph']
    used = {p['projection_proof_id']: p for c in f['all_candidates'] for w in c['witnesses'] for p in w['premises']}
    contexts = []
    for key in sorted(used):
        proof = f['proof_registry'][key]
        unit = next(u for u in g['source_units'].values() if u['article_id'] == proof['parent_key'][0])
        evidence = [{'source_unit': unit['id'], 'source_sha256': unit['source_sha256'], 'unit_sha256': unit['sha256'], 'quote': unit['text']}]
        values = dict(species='synthetic_species', disease_model={'id': 'synthetic_model'}, challenge_anchor='synthetic_challenge',
            target_mechanism={'mechanism': 'pharmacological_antagonism', 'target_species': 'human', 'expressed_receptor_species': 'human'},
            route='synthetic_route', tissue='synthetic_tissue', assessment={'elapsed': 6, 'unit': 'hour', 'origin': 'synthetic_challenge'},
            recipe={'substance': 'synthetic_drug', 'dose': 1, 'unit': 'synthetic_unit'}, genotype='synthetic_genotype', age=None, sex=None)
        dims = {d: {'value': deepcopy(values[d]), 'status': 'unknown' if values[d] is None else 'source_stated',
                    'evidence': [] if values[d] is None else deepcopy(evidence)} for d in DIMENSIONS}
        contexts.append({'projection_proof_id': key, 'parent_key': proof['parent_key'], 'native_statement_id': proof['native_statement_id'],
            'projection_proof_sha256': fingerprint(proof), 'reason_ru': 'Техническая синтетическая разметка; не клиническое утверждение.', 'dimensions': dims})
    rows = {r['projection_proof_id']: r for r in contexts}
    recipients = {w['premises'][1]['projection_proof_id'] for c in f['all_candidates'] for w in c['witnesses']}
    designs = [{'projection_proof_id': k, 'status': 'source_recipe_design_proposal', 'reason_ru': 'Синтетический проект проверки.',
        'design': {'recipe': deepcopy(rows[k]['dimensions']['recipe']['value']),
                   'target_mechanism': deepcopy(rows[k]['dimensions']['target_mechanism']['value']),
                   'observed_recipient_response': False, 'is_original_unique_dose_established': False,
                   'condition_on_predicted_response': False}} for k in sorted(recipients)]
    audit = {'version': VERSION, 'author': 'Codex', 'expert_validated': False, 'model_calls': 0, 'target_read': False,
        'forecast_run_id': f['run_id'], 'forecast_sha256': fingerprint(f), 'semantic_graph_sha256': fingerprint(g),
        'contexts': contexts, 'recipient_designs': designs}
    return forecasts, FilePredictionStore(tmp_path / 'protocols'), f, aa, audit


def selected_rows(forecast, audit):
    witness = forecast['all_candidates'][0]['witnesses'][0]
    rows = {r['projection_proof_id']: r for r in audit['contexts']}
    return [rows[p['projection_proof_id']] for p in witness['premises']]


def retie(f, a): a['forecast_sha256'] = fingerprint(f)


def test_proposal_preserves_source_limits_and_removes_donor_actors_from_measurement(tmp_path):
    _, _, f, aa, audit = fixture(tmp_path); before = deepcopy((f, aa, audit))
    r = reconcile_protocols(f, aa['semantic_graph'], audit)
    assert (f, aa, audit) == before and r['all_candidates_reviewed'] == 2
    assert r['counts'] == {'testable_design_hypothesis_not_confirmed': 2}
    for c in r['candidate_reviews']:
        for w in c['witness_reviews']:
            p = w['proposed_protocol']
            assert not ({x['role'] for x in p['measurement']['endpoint_roles']} & {'intervention', 'population', 'challenge'})
            assert p['population']['age'] is p['population']['sex'] is None
            assert p['demographic_registration_required'] and not p['scope_equivalence_established']
            assert not p['observed_recipient_response'] and not p['condition_on_predicted_response']
            assert not p['future_control_eligible_without_scope_audit'] and not w['conclusion_confirmed']
    assert r['new_confirmed_predictions'] == r['future_results_scored'] == r['model_calls'] == 0
    assert not r['scientific_success'] and not r['graph_advantage_demonstrated']


@pytest.mark.parametrize('dimension', ['species', 'disease_model', 'challenge_anchor', 'tissue'])
def test_mixed_model_event_or_anchor_tissue_is_not_a_ready_hypothesis(tmp_path, dimension):
    _, _, f, aa, audit = fixture(tmp_path); a, b, q = selected_rows(f, audit)
    q['dimensions'][dimension]['value'] = {'id': 'different'} if dimension == 'disease_model' else 'different'
    if dimension == 'tissue': b['dimensions']['tissue']['value'] = 'different'
    result = reconcile_protocols(f, aa['semantic_graph'], audit)
    c = next(r for r in result['candidate_reviews'] if r['candidate_id'] == f['all_candidates'][0]['id'])
    assert c['status'] == 'blocked_context_mixture' and c['witness_reviews'][0]['proposed_protocol'] is None


@pytest.mark.parametrize('dimension', ['species', 'disease_model', 'challenge_anchor', 'assessment', 'tissue'])
def test_unknown_required_donor_measurement_is_not_filled_by_recipient(tmp_path, dimension):
    _, _, f, aa, audit = fixture(tmp_path); a, b, q = selected_rows(f, audit)
    q['dimensions'][dimension] = {'value': None, 'status': 'unknown', 'evidence': []}
    result = reconcile_protocols(f, aa['semantic_graph'], audit)
    c = next(r for r in result['candidate_reviews'] if r['candidate_id'] == f['all_candidates'][0]['id'])
    assert c['status'] == 'unresolved_source_context'


def test_human_only_target_cannot_be_proposed_in_mouse_receptor_group(tmp_path):
    _, _, f, aa, audit = fixture(tmp_path); a, b, q = selected_rows(f, audit)
    b['dimensions']['target_mechanism']['value']['expressed_receptor_species'] = 'mouse'
    design = next(d for d in audit['recipient_designs'] if d['projection_proof_id'] == b['projection_proof_id'])
    design['design']['target_mechanism'] = deepcopy(b['dimensions']['target_mechanism']['value'])
    r = reconcile_protocols(f, aa['semantic_graph'], audit)
    c = next(c for c in r['candidate_reviews'] if c['candidate_id'] == f['all_candidates'][0]['id'])
    assert c['status'] == 'blocked_context_mixture'
    assert any(b['dimension'] == 'drug_target_not_expressed' for b in c['witness_reviews'][0]['blocking_differences'])


def test_donor_time_and_dose_not_copied_as_observed_recipient_protocol(tmp_path):
    _, _, f, aa, audit = fixture(tmp_path); a, b, q = selected_rows(f, audit)
    b['dimensions']['assessment']['value']['elapsed'] = 24
    q['dimensions']['recipe']['value']['dose'] = 99
    r = reconcile_protocols(f, aa['semantic_graph'], audit)
    c = next(c for c in r['candidate_reviews'] if c['candidate_id'] == f['all_candidates'][0]['id'])
    p = c['witness_reviews'][0]['proposed_protocol']
    assert p['recipe']['dose'] == 1 and p['measurement']['assessment']['elapsed'] == 6
    assert p['measurement']['assessment_from_donor_is_design_choice']
    assert 'assessment_response_transfer_not_established' in p['uncertain_assumptions']


@pytest.mark.parametrize('damage', ['source_hash', 'quote', 'unknown_guessed', 'proof', 'coverage', 'observed', 'response_condition', 'recipe', 'target_read'])
def test_invalid_annotations_rejected_whole(tmp_path, damage):
    _, _, f, aa, audit = fixture(tmp_path); row = audit['contexts'][0]
    if damage == 'source_hash': row['dimensions']['species']['evidence'][0]['source_sha256'] = 'changed'
    elif damage == 'quote': row['dimensions']['species']['evidence'][0]['quote'] = 'Absent quotation'
    elif damage == 'unknown_guessed': row['dimensions']['age']['value'] = 12
    elif damage == 'proof': row['projection_proof_sha256'] = 'changed'
    elif damage == 'coverage': audit['contexts'].pop()
    elif damage == 'observed': audit['recipient_designs'][0]['design']['observed_recipient_response'] = True
    elif damage == 'response_condition': audit['recipient_designs'][0]['design']['condition_on_predicted_response'] = True
    elif damage == 'recipe': audit['recipient_designs'][0]['design']['recipe']['dose'] = 99
    else: audit['target_read'] = True
    with pytest.raises(ArticleMapError): reconcile_protocols(f, aa['semantic_graph'], audit)


def test_frozen_budget_is_not_refilled_after_rejections(tmp_path):
    _, _, f, aa, audit = fixture(tmp_path); f['ranked_candidates'] = f['ranked_candidates'][:1]; retie(f, audit)
    first = f['ranked_candidates'][0]
    recipient = first['witnesses'][0]['premises'][1]['projection_proof_id']
    design = next(d for d in audit['recipient_designs'] if d['projection_proof_id'] == recipient)
    design.update(status='no_design_proposed', design=None)
    r = reconcile_protocols(f, aa['semantic_graph'], audit)
    assert len(r['original_budget_slots']) == 1 and r['original_budget_slots'][0]['status'] == 'unresolved_source_context'
    assert not r['outside_budget_promoted']


def test_explicit_same_behavioral_test_allows_absent_tissue_without_inventing_tissue(tmp_path):
    _, _, f, aa, audit = fixture(tmp_path); a, b, q = selected_rows(f, audit)
    for row in (a, b): row['dimensions']['tissue'] = {'value': None, 'status': 'unknown', 'evidence': []}
    # Только технический тест: исходные синтетические данные дополняются явной ролью теста.
    for premise in f['all_candidates'][0]['witnesses'][0]['premises'][:2]:
        premise['frame']['statements'][0]['roles'].append({'role': 'test', 'value': 'synthetic_behavioral_test', 'reference_kind': 'concept'})
    retie(f, audit)
    c = reconcile_protocols(f, aa['semantic_graph'], audit)['candidate_reviews'][0]
    assert c['status'] == 'testable_design_hypothesis_not_confirmed'


def test_immutable_source_only_application_and_no_network(tmp_path, monkeypatch):
    forecasts, output, f, aa, audit = fixture(tmp_path)
    def forbidden(*args, **kwargs): raise AssertionError('Network and models forbidden')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    import httpx
    monkeypatch.setattr(httpx.Client, 'send', forbidden)
    app = ReconcileSealedAnalogyProtocols(forecasts, output)
    first = app.execute(f['run_id'], aa, audit, {'fixed': 'implementation'})
    assert app.execute(f['run_id'], aa, audit, {'fixed': 'implementation'}) == first
    assert len(list(output.root.iterdir())) == 1 and forecasts.read_seal(f['run_id']) == f
    damaged = deepcopy(aa); damaged['semantic_graph']['source_units'].clear()
    with pytest.raises(ArticleMapError): app.execute(f['run_id'], damaged, audit, {'fixed': 'implementation'})
    assert output.read_seal(first['run_id']) == first


def test_missing_source_cannot_publish(tmp_path):
    forecasts, output, f, aa, audit = fixture(tmp_path)
    with pytest.raises(ArticleMapNotFound): ReconcileSealedAnalogyProtocols(forecasts, output).execute('a' * 64, aa, audit, {})
    assert not output.root.exists()
