"""Контроль метода не становится ни генерацией прогноза, ни оценкой эффекта."""
from copy import deepcopy
from hashlib import sha256

import pytest

from application.analogy_method_screening import ScreenSealedAnalogyMethods
from domain.article_maps import ArticleMapError, fingerprint
from domain.analogy_method_screening import VERSION, screen_method_scope
from infrastructure.control_method_packets import method_packet
from infrastructure.development_prediction_store import FilePredictionStore


def fixture():
    raw = b'''<article article-type="research-article"><front><article-meta>
    <article-id pub-id-type="pmc">123</article-id><article-id pub-id-type="doi">10.1/test</article-id>
    </article-meta></front><body><sec><title>Methods</title><p>Mice received MOG to induce EAE.</p>
    </sec><sec><title>Results</title><p>SECRET EFFECT</p></sec></body></article>'''
    packet = method_packet(raw, 'PMC123', '10.1/test'); unit = packet['method_source']['units'][1]
    ref = {'unit_id': unit['id'], 'unit_sha256': unit['sha256'], 'start': unit['start'], 'end': unit['end'], 'quote': unit['text']}
    design = {'population': {'species': 'mouse', 'age': None, 'sex': None},
              'challenge': {'id': 'acute_icv_amyloid_beta_oligomer_mouse_model'}, 'demographic_registration_required': True}
    source = {'binding': {'version': 'sealed-test'}, 'original_budget_slots': [
        {'candidate_id': 'draft', 'status': 'testable_design_hypothesis_not_confirmed',
         'witness_reviews': [{'proposed_protocol': design}]},
        {'candidate_id': 'blocked', 'status': 'blocked_context_mixture', 'witness_reviews': []}]}
    source['run_id'] = fingerprint(source['binding'])
    protocol = {'question': None, 'model_calls': 0, 'outside_budget_promoted': False,
                'source_run_id': source['run_id'], 'source_artifact_sha256': fingerprint(source),
                'fixed_original_slots': ['draft', 'blocked'], 'eligible_draft_ids': ['draft'], 'source_protocols': {'draft': [design]}}
    plan = {'protocol_sha256': fingerprint(protocol), 'selected': [{'pmcid': 'PMC123', 'doi': '10.1/test'}]}
    annotation = {'version': VERSION, 'author': 'Codex', 'expert_validated': False, 'model_calls': 0,
                  'protocol_sha256': fingerprint(protocol), 'method_plan_sha256': fingerprint(plan), 'controls': [
                      {'pmcid': 'PMC123', 'packet_sha256': fingerprint(packet), 'raw_xml_sha256': packet['raw_xml_sha256'],
                       'shared_study_scope_only': True, 'dimensions': {
                           d: {'value': v, 'status': 'codex_source_license', 'evidence': [deepcopy(ref)], 'reason_ru': 'Источник'}
                           for d, v in [('species', 'mouse'), ('disease_model', 'mog_induced_eae_mouse_model')]}}]}
    disclosure = {'model_calls': 0, 'forecasts_changed': False, 'results_scored': 0,
                  'controls': [{'pmcid': 'PMC123', 'partial_outcome_disclosure': True, 'strict_human_blindness_established': False}]}
    return source, protocol, {'PMC123': packet}, plan, annotation, disclosure


def evaluate(values): return screen_method_scope(*values[1:])


def test_real_model_mismatch_is_not_negative_effect_and_does_not_fill_budget():
    data = fixture(); original = deepcopy(data); result = evaluate(data)
    assert data == original and result['counts'] == {'incompatible_shared_study_scope': 1}
    assert result['comparisons'][0]['design_alternatives'][0]['differences'][0]['dimension'] == 'disease_model'
    assert result['original_slots'] == ['draft', 'blocked'] and not result['outside_budget_promoted']
    assert result['future_results_scored'] == 0 and result['accuracy'] is None
    assert not result['scientific_success'] and not result['graph_advantage_demonstrated']


def test_unknown_context_is_insufficient_not_mismatch():
    data = fixture()
    for fact in data[4]['controls'][0]['dimensions'].values():
        fact.update(value=None, status='not_assessed', evidence=[])
    result = evaluate(data)
    assert result['counts'] == {'insufficient_shared_study_scope': 1}


def test_matching_shared_scope_never_confirms_or_licenses_full_protocol():
    data = fixture(); data[1]['source_protocols']['draft'][0]['challenge']['id'] = 'mog_induced_eae_mouse_model'
    data[3]['protocol_sha256'] = fingerprint(data[1]); data[4]['protocol_sha256'] = fingerprint(data[1])
    data[4]['method_plan_sha256'] = fingerprint(data[3])
    result = evaluate(data)
    assert result['counts'] == {'shared_scope_candidate_requires_full_protocol_audit': 1}
    assert not result['full_protocol_eligibility_established'] and result['future_results_scored'] == 0


def test_alternative_designs_are_not_joint_obligations():
    data = fixture(); alternative = deepcopy(data[1]['source_protocols']['draft'][0])
    alternative['challenge']['id'] = 'mog_induced_eae_mouse_model'; data[1]['source_protocols']['draft'].append(alternative)
    data[3]['protocol_sha256'] = fingerprint(data[1]); data[4]['protocol_sha256'] = fingerprint(data[1]); data[4]['method_plan_sha256'] = fingerprint(data[3])
    result = evaluate(data)
    assert result['counts'] == {'shared_scope_candidate_requires_full_protocol_audit': 1}
    assert len(result['comparisons'][0]['design_alternatives']) == 2


@pytest.mark.parametrize('mutation', ['identity', 'packet_hash', 'quote', 'offset', 'unit_hash', 'dimension_type',
                                    'wrong_licensed_model', 'unknown_guess', 'outside_slot', 'missing_control',
                                    'extra_control', 'duplicate_control', 'method_text', 'result_flag', 'training_flag',
                                    'model_calls', 'disclosure_scores', 'changed_forecast', 'wrong_plan'])
def test_changed_or_unlicensed_inputs_are_rejected(mutation):
    data = fixture(); _, protocol, packets, plan, annotation, disclosure = data
    row = annotation['controls'][0]; fact = row['dimensions']['species']; ref = fact['evidence'][0]; packet = packets['PMC123']
    if mutation == 'identity': packet['doi'] = '10.1/other'
    elif mutation == 'packet_hash': row['packet_sha256'] = 'wrong'
    elif mutation == 'quote': ref['quote'] = 'Invented mice'
    elif mutation == 'offset': ref['start'] += 1
    elif mutation == 'unit_hash': ref['unit_sha256'] = 'wrong'
    elif mutation == 'dimension_type': fact['value'] = 'mog_induced_eae_mouse_model'
    elif mutation == 'wrong_licensed_model': row['dimensions']['disease_model']['value'] = 'moc2_perineural_invasion_mouse_model'
    elif mutation == 'unknown_guess': fact['status'] = 'not_assessed'
    elif mutation == 'outside_slot': protocol['eligible_draft_ids'] = ['unknown']
    elif mutation == 'missing_control': annotation['controls'] = []
    elif mutation == 'extra_control': packets['PMC999'] = deepcopy(packet)
    elif mutation == 'duplicate_control': annotation['controls'].append(deepcopy(row))
    elif mutation == 'method_text': packet['method_source']['text'] += 'guess'
    elif mutation == 'result_flag': packet['results_section_included'] = True
    elif mutation == 'training_flag': packet['training_source'] = True
    elif mutation == 'model_calls': annotation['model_calls'] = 1
    elif mutation == 'disclosure_scores': disclosure['results_scored'] = 1
    elif mutation == 'changed_forecast': disclosure['forecasts_changed'] = True
    elif mutation == 'wrong_plan': plan['protocol_sha256'] = 'wrong'
    with pytest.raises(ArticleMapError): evaluate(data)


def test_packet_unknown_section_cannot_be_licensed_from_title():
    data = fixture(); packet = data[2]['PMC123']; packet['has_explicit_methods'] = False
    data[4]['controls'][0]['packet_sha256'] = fingerprint(packet)
    with pytest.raises(ArticleMapError): evaluate(data)


def test_application_is_immutable_and_rejects_design_change(tmp_path):
    data = fixture(); source, protocol, packets, plan, annotation, disclosure = data
    inputs = FilePredictionStore(tmp_path / 'in'); outputs = FilePredictionStore(tmp_path / 'out')
    inputs.seal(source['run_id'], source)
    app = ScreenSealedAnalogyMethods(inputs, outputs)
    args = (source['run_id'], protocol, packets, plan, annotation, disclosure, {'module': 'test'})
    a = app.execute(*args); b = app.execute(*args); assert a == b
    assert inputs.read_seal(source['run_id']) == source
    protocol['source_protocols']['draft'][0]['population']['species'] = 'human'
    with pytest.raises(ArticleMapError): app.execute(*args)


def test_application_rejects_changed_source_seal_and_budget(tmp_path):
    data = fixture(); source, protocol, packets, plan, annotation, disclosure = data
    inputs = FilePredictionStore(tmp_path / 'in'); outputs = FilePredictionStore(tmp_path / 'out')
    inputs.seal(source['run_id'], source); protocol['fixed_original_slots'].reverse()
    with pytest.raises(ArticleMapError):
        ScreenSealedAnalogyMethods(inputs, outputs).execute(source['run_id'], protocol, packets, plan, annotation, disclosure, {})


def test_source_raw_results_never_enter_selected_method_comparison():
    data = fixture(); assert 'SECRET' not in data[2]['PMC123']['method_source']['text']
    result = evaluate(data); assert 'SECRET' not in str(result)
    assert result['comparisons'][0]['disclosure']['partial_outcome_disclosure']
