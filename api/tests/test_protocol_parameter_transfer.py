"""Синтетические проверки передачи протокола не считаются научными подтверждениями."""
from copy import deepcopy
import pytest
from domain.article_maps import ArticleMapError, fingerprint
from domain.protocol_parameter_transfer import protocol_copy_plan, values, specification, protocol_frame_identity
from domain.whole_map_forecast import template, bind, instantiate, learn
from domain.semantic_part_forecast import apply_templates
from domain.qualitative_result_projection import summary_kind


def attribute(name='dose', value='2', unit='mg/kg'):
    return {'name': name, 'value': value, 'unit': unit}


def record(article, identifier, dose, kind='state', name='dose', unit='mg/kg'):
    method = kind == 'action'
    frame = {'kind': kind, 'action_status': 'performed' if method else None, 'logic': 'single',
        'statements': [{'predicate': 'perform procedure' if method else 'reduced after intervention',
            'roles': [{'role': 'intervention', 'value': article + ' drug', 'reference_kind': 'concept'},
                      {'role': 'population', 'value': article + ' population', 'reference_kind': 'concept'},
                      {'role': 'outcome', 'value': 'clinical score', 'reference_kind': 'concept'}],
            'scope': {'modality': None, 'quantifier': None, 'time': 'manifest disease',
                'conditions': ['explicit mouse protocol', 'source-local report: ' + article], 'study_group': article},
            'attributes': [attribute(name, dose, unit)], 'negated': False}]}
    frame['statements'][0]['roles'].sort(key=lambda r: r['role'])
    native = {'knowledge_id': identifier, 'kind': kind, 'action_status': frame['action_status'],
        'display_text': 'Synthetic procedure or result on days of manifest disease', 'semantic_frame': deepcopy(frame)}
    proof = {'parent_key': [article, identifier], 'run_id': 'synthetic-' + article,
        'origin': {'origin': 'primary_method' if method else 'primary_result'},
        'complete_native_knowledge': native, 'parent_knowledge_sha256': fingerprint(native),
        'view_frame_sha256': fingerprint(frame), 'qualitative_result_proof_id': None if method else 'synthetic-qualitative-proof'}
    proof['id'] = fingerprint(proof)
    return {'key': (article, identifier), 'native_key': (article, identifier), 'run_id': proof['run_id'],
        'frame': frame, 'projection_proof': proof, 'eligible': True}


def reseal(r):
    p = r['projection_proof']; n = p['complete_native_knowledge']
    n['kind'] = r['frame']['kind']; n['action_status'] = r['frame']['action_status']
    p['parent_knowledge_sha256'] = fingerprint(n); p['view_frame_sha256'] = fingerprint(r['frame'])


def pair(dose='2'):
    return record('source', 'M', dose, 'action'), record('source', 'R', dose)


def test_source_bound_parameter_is_instantiated_from_receiving_procedure_and_inputs_unchanged():
    body, head = pair(); before = deepcopy((body, head))
    proof = protocol_copy_plan([body], head)
    assert proof and not proof['measured_response_created'] and not proof['causal_effect_proven']
    pattern = template([body], head, proof)[1]
    receiving = record('receiving', 'M', '7.5', 'action')
    bindings = bind(pattern['body'][0], receiving['frame'], {}, receiving)
    output = instantiate(pattern['head'], bindings)
    assert output['statements'][0]['attributes'] == [attribute(value='7.5')]
    assert output['statements'][0]['scope']['study_group'] == 'receiving'
    assert (body, head) == before


@pytest.mark.parametrize('case', ['other_drug', 'other_population', 'other_scope', 'other_source', 'other_run',
    'planned', 'unresolved', 'negative_method', 'modal_method', 'negative_head', 'modal_head', 'cited_method',
    'cited_head', 'unlicensed_direction', 'not_action', 'wrong_unit', 'unknown_unit', 'different_value',
    'result_instead_of_protocol', 'ambiguous_attribute', 'unknown_numeric_field', 'subset_not_same_vector'])
def test_numeric_coincidence_or_missing_license_never_permits_copy(case):
    body, head = pair(); bs = body['frame']['statements'][0]; hs = head['frame']['statements'][0]
    if case == 'other_drug': bs['roles'][0]['value'] = 'other drug'
    elif case == 'other_population': next(r for r in bs['roles'] if r['role'] == 'population')['value'] = 'other population'
    elif case == 'other_scope': bs['scope']['time'] = 'before disease'
    elif case == 'other_source': body['native_key'] = ('other', 'M'); body['projection_proof']['parent_key'] = ['other','M']
    elif case == 'other_run': body['run_id'] = body['projection_proof']['run_id'] = 'another-run'
    elif case in {'planned','unresolved'}: body['frame']['action_status'] = case
    elif case == 'negative_method': bs['negated'] = True
    elif case == 'modal_method': bs['scope']['modality'] = 'may'
    elif case == 'negative_head': hs['negated'] = True
    elif case == 'modal_head': hs['scope']['modality'] = 'may'
    elif case == 'cited_method': body['projection_proof']['origin']['origin'] = 'cited_result'
    elif case == 'cited_head': head['projection_proof']['origin']['origin'] = 'cited_result'
    elif case == 'unlicensed_direction': head['projection_proof']['qualitative_result_proof_id'] = None
    elif case == 'not_action': body['frame']['kind'] = 'state'; body['frame']['action_status'] = None
    elif case == 'wrong_unit': bs['attributes'][0]['unit'] = 'mg'
    elif case == 'unknown_unit': hs['attributes'][0]['unit'] = None
    elif case == 'different_value': bs['attributes'][0]['value'] = '3'
    elif case == 'result_instead_of_protocol': body['projection_proof']['origin']['origin'] = 'primary_result'
    elif case == 'ambiguous_attribute': hs['attributes'].append(attribute(value='4'))
    elif case == 'unknown_numeric_field': hs['attributes'].append(attribute('estimate', '.5', 'score'))
    else: bs['attributes'][0]['value'] = '2; 4'
    reseal(body); reseal(head)
    assert protocol_copy_plan([body], head) is None


@pytest.mark.parametrize('field', ['p', 'HR', 'estimate', 'temperature', 'n', 'reported mean', 'reported SD'])
def test_measured_response_or_statistical_evidence_cannot_be_copied_even_if_numbers_equal(field):
    body, head = pair()
    for r in [body,head]: r['frame']['statements'][0]['attributes'] = [attribute(field, '2', 'mg/kg')]; reseal(r)
    assert protocol_copy_plan([body], head) is None


def test_schedule_requires_same_explicit_manifest_clock_and_preserves_order():
    body = record('source','M','1; 4; 8; 12','action','disease-relative days','day')
    head = record('source','R','1; 4; 8; 12','state','days of manifest disease','day')
    proof = protocol_copy_plan([body],head); assert proof
    pattern = template([body],head,proof)[1]
    receiving = record('next','M','2; 5; 9; 13','action','disease-relative days','day')
    output = instantiate(pattern['head'],bind(pattern['body'][0],receiving['frame'],{},receiving))
    assert output['statements'][0]['attributes'][0]['value'] == '2; 5; 9; 13'
    body['projection_proof']['complete_native_knowledge']['display_text'] = 'Injected after immunization; manifestation not established'
    reseal(body); assert protocol_copy_plan([body],head) is None


@pytest.mark.parametrize('value', ['0', '-1', 'n.d.', '1-3', '<2', '2 ± 1', 'NaN', 'inf', '2; ?'])
def test_uncertain_range_zero_or_negative_value_is_not_assumed(value):
    assert values(value) is None


def test_two_primary_examples_with_different_doses_learn_one_parameterized_rule():
    records, groups, families = {}, [], {}
    for article, dose in [('first','2'),('second','5')]:
        body = record(article,'M',dose,'action'); head = record(article,'R',dose)
        records[body['key']], records[head['key']] = body, head
        groups.append(((body['key'],),head['key'])); families[article] = article
    receiving = record('third','M','9','action'); records[receiving['key']] = receiving; families['third'] = 'third'
    rules, diagnostic = learn(records,groups,families)
    assert len(rules) == 1 and not diagnostic['rejected']
    disabled, control = learn(records,groups,families,protocol_parameters=False)
    assert not disabled and control['rejected']['unmodelled_numeric_conclusion'] == 2
    assert all('protocol_parameter_proof' in example for example in rules[0]['examples'])
    rule = {**rules[0],'primary_families':['first','second']}
    by_parent = {k:[k] for k in records}; known = {protocol_frame_identity(r['frame']) for r in records.values()}
    candidates, _ = apply_templates(records,by_parent,[rule],groups,known,False)
    assert len(candidates) == 1
    assert candidates[0]['frame']['statements'][0]['attributes'] == [attribute(value='9')]
    assert not candidates[0]['logical_entailment'] and not candidates[0]['causality_asserted']


def test_bind_rejects_changed_units_arity_scope_and_unbound_instantiation():
    body, head = pair(); pattern = template([body],head,protocol_copy_plan([body],head))[1]
    for case in ['unit','arity','scope']:
        r = deepcopy(body['frame']); s = r['statements'][0]
        if case == 'unit': s['attributes'][0]['unit'] = 'ug/kg'
        elif case == 'arity': s['attributes'][0]['value'] = '2; 4'
        else: s['scope']['time'] = 'other phase'
        assert bind(pattern['body'][0],r,{}) is None
    with pytest.raises(ArticleMapError,match='Unbound protocol'):
        instantiate(pattern['head'], {'$0':'x','$1':'y','$2':'z','$study':'source'})


def test_mutated_source_view_or_license_is_rejected():
    body,head = pair(); plan = protocol_copy_plan([body],head)
    body['frame']['statements'][0]['attributes'][0]['value'] = '9'
    with pytest.raises(ArticleMapError,match='view changed'): protocol_copy_plan([body],head)
    body,head = pair(); plan['copies'][0]['head_parameter']['value'] = '7'
    with pytest.raises(ArticleMapError,match='license does not match'): template([body],head,plan)


def test_generic_n_requires_explicit_sample_unit_and_stays_statistical_evidence():
    assert summary_kind(attribute('n','6','mice per group'),'reduced after intervention') == 'sample_size'
    assert summary_kind(attribute('n','6',None),'reduced after intervention') is None
    assert specification(attribute('n','6','mice per group')) is None


def test_protocol_identity_preserves_precision_units_and_order_without_false_novelty():
    a = record('source','R','200.00')['frame']; b = record('source','R','2e2')['frame']
    before = deepcopy((a,b)); assert protocol_frame_identity(a) == protocol_frame_identity(b)
    b['statements'][0]['attributes'][0]['unit'] = 'ug/kg'
    assert protocol_frame_identity(a) != protocol_frame_identity(b)
    b = deepcopy(a); b['statements'][0]['attributes'][0]['value'] = '200.0000000000000000000000000001'
    assert protocol_frame_identity(a) != protocol_frame_identity(b)
    assert a == before[0]


def test_receiving_protocol_needs_source_license_and_its_own_clock():
    body = record('source','M','1; 4','action','disease-relative days','day')
    head = record('source','R','1; 4','state','days of manifest disease','day')
    pattern = template([body],head,protocol_copy_plan([body],head))[1]['body'][0]
    assert bind(pattern,body['frame'],{}) is None
    receiving = record('next','M','2; 5','action','disease-relative days','day')
    receiving['projection_proof']['complete_native_knowledge']['display_text'] = 'Administered before manifest disease, after induction'
    reseal(receiving); assert bind(pattern,receiving['frame'],{},receiving) is None
    receiving['projection_proof']['complete_native_knowledge']['display_text'] = 'Administered on days of manifest disease'
    reseal(receiving); assert bind(pattern,receiving['frame'],{},receiving) is not None
    receiving['projection_proof']['origin']['origin'] = 'cited_result'
    assert bind(pattern,receiving['frame'],{},receiving) is None


@pytest.mark.parametrize('case',['other_route','missing_route','other_phase','other_duration'])
def test_equal_dose_does_not_identify_a_different_protocol(case):
    body,head = pair()
    b=body['frame']['statements'][0]['attributes']; h=head['frame']['statements'][0]['attributes']
    h.append(attribute('route','i.v.',None))
    if case != 'missing_route': b.append(attribute('route','i.p.' if case == 'other_route' else 'i.v.',None))
    if case == 'other_phase': h.append(attribute('phase','therapeutic',None)); b.append(attribute('phase','prophylactic',None))
    if case == 'other_duration': h.append(attribute('duration','10','day')); b.append(attribute('duration','20','day'))
    reseal(body); reseal(head); assert protocol_copy_plan([body],head) is None
