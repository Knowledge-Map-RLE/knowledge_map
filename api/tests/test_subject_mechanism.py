"""Механизм, контрпримеры и разделение математического и научного результата."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import pytest
from domain.article_maps import ArticleMapError, fingerprint
from domain.subject_mechanism import (capture,rational,relative_capture,fixed_window_comparison,mixture_capture,
                                     mixture_counterexample,generate,evaluate_eligibility,proof_graph)
from domain.knowledge_foundation import validate_dag
from application.subject_mechanism import SealSubjectMechanism,AuditSubjectMechanism
from infrastructure.subject_mechanism import FileMechanismInputs,FileMechanismProfiles
from infrastructure.development_prediction_store import FilePredictionStore

ROOT=Path(__file__).resolve().parents[2]/'eval/free_prediction/subject-mechanism-pilot-v1'
def read(name):return json.loads((ROOT/'prepared-v2'/name).read_text(encoding='utf-8'))
def inputs():return deepcopy(read('inputs.json'))
def candidate():return generate(inputs())['candidates'][0]

@pytest.mark.parametrize('value',['0','-1','NaN','inf','1/0',1,None])
def test_positive_exact_durations_required(value):
    with pytest.raises(ArticleMapError):rational(value)

def test_capture_probability_saturates():
    assert capture('2','4')==Fraction(1,2) and capture('4','2')==1

@pytest.mark.parametrize('high,low,shorter,longer,attenuated',[
    ('4','2','1','2',False),('4','2','2','4',True),('4','2','5','8',False),('2','2','1','4',False)])
def test_fixed_window_regimes_preserve_weak_vs_strict(high,low,shorter,longer,attenuated):
    r=fixed_window_comparison(high,low,shorter,longer)
    assert r['nonincrease'] and r['attenuation']==attenuated and not r['clinical_measurement']

def test_generated_exact_grid_of_all_ordered_windows_and_intervals():
    checked=0
    values=['1/10','1/2','1','2','3','10','100']
    for high in values:
        for low in values:
            if Fraction(high)<Fraction(low):continue
            for shorter in values:
                for longer in values:
                    if Fraction(shorter)>=Fraction(longer):continue
                    r=fixed_window_comparison(high,low,shorter,longer)
                    assert Fraction(r['after'])<=Fraction(r['before']);checked+=1
    assert checked==588

def test_reversed_duration_or_interval_rejected():
    with pytest.raises(ArticleMapError):relative_capture('1','2','3')
    with pytest.raises(ArticleMapError):fixed_window_comparison('2','1','3','2')

def test_even_stochastic_dominance_does_not_prove_mixture_ratio_attenuation():
    c=mixture_counterexample()
    def cdf(points,x):return sum((Fraction(p['probability']) for p in points if Fraction(p['duration'])<=x),Fraction(0))
    for x in [Fraction(0),Fraction(1,10),Fraction(1),Fraction(2),Fraction(100),Fraction(101)]:
        assert cdf(c['high'],x)<=cdf(c['low'],x)
    assert Fraction(c['before'])==Fraction(170,167) and Fraction(c['after'])==Fraction(10,7)
    assert c['synthetic'] and not c['clinical_estimate']

def test_invalid_mixture_weights_rejected():
    with pytest.raises(ArticleMapError):mixture_capture([{'duration':'1','probability':'1/2'}],'2')

def test_conditional_candidate_has_all_joint_premises_no_background_arrow():
    c=candidate();g=c['graph']
    assert len(c['premises'])==4 and len(g['edges'])==4
    assert set(g['joint_premises'])==set(c['premises'])
    assert 'reserve-background' not in c['premises']
    assert max(validate_dag(g['occurrences'],g['edges']).values())==1
    assert not c['empirical_prediction_released'] and not c['new_scientific_knowledge_confirmed']
    assert c['measurement_task']['action_status']=='unresolved'
    assert c['source_support_families']==['PAQUID']

@pytest.mark.parametrize('mutation',[
    lambda f:f.update(negated=True),lambda f:f['context'].update(phenotype='nonmemory_mci'),
    lambda f:f['context'].update(cohort=None),lambda f:f.update(context={})])
def test_source_negation_different_or_unknown_context_blocks_composition(mutation):
    i=inputs();mutation(i['knowledge'][1]['frame']);r=generate(i)
    assert not r['candidates'] and r['diagnostics']

@pytest.mark.parametrize('mutation',[
    lambda i:i['knowledge'][3]['frame'].update(negated=True),
    lambda i:i['knowledge'][4]['frame'].update(negated=True),
    lambda i:i['knowledge'][3]['frame']['conditions'].pop(),
    lambda i:i['knowledge'][1]['frame'].update(modality='reported'),
    lambda i:i['knowledge'][4]['frame'].update(quantifier='general_background'),
    lambda i:i['knowledge'][1].update(available_on='2024-01-01'),
    lambda i:i['knowledge'][1].update(available_on='wrong'),
    lambda i:i['protocol'].update(model_calls=1)])
def test_unlicensed_promotion_or_changed_assumptions_rejected(mutation):
    i=inputs();mutation(i)
    with pytest.raises(ArticleMapError):generate(i)

@pytest.mark.parametrize('field,value',[('factor','sex'),('higher_group','another_group'),('state','alzheimer_disease')])
def test_operator_cannot_relabel_another_factor_or_state_as_education_mci(field,value):
    i=inputs();i['knowledge'][1]['frame']['roles'][field]=value
    with pytest.raises(ArticleMapError):generate(i)

def test_no_implicit_missing_premise_fallback():
    i=inputs();i['knowledge'].pop();assert not generate(i)['candidates']

def test_profile_audit_is_not_outcome_validation():
    rows=evaluate_eligibility(candidate(),read('hidden-profiles.json')['profiles'])
    assert len(rows)==7 and all(r['agreement'] is None and not r['scientific_success'] for r in rows)
    assert all(r['status']=='not_testable_from_selected_data' for r in rows)

def test_even_fully_eligible_profile_is_only_ready_for_separate_test():
    p=read('hidden-profiles.json')['profiles'][0]
    for field in ['regular_grid','uniform_phase','fixed_group_durations','perfect_detection','complete_followup','education_duration_order_measured','matched_protocol_interval_comparison']:p[field]=True
    p['context']['phenotype']=candidate()['frame']['context']['phenotype']
    r=evaluate_eligibility(candidate(),[p])[0]
    assert r['status']=='eligible_for_separate_test' and r['agreement'] is None and not r['scientific_success']

def test_proof_graph_rejects_visible_cycle_and_unknown_reference():
    g=proof_graph(['a','b'],'c')
    for e in [{'source':'c','target':'a'},{'source':'unknown','target':'c'}]:
        with pytest.raises(ArticleMapError):validate_dag(g['occurrences'],g['edges']+[e])

def test_generator_input_reads_no_hidden_profile_or_ai(tmp_path):
    port=FileMechanismInputs(ROOT/'prepared-v2/manifest.json');store=FilePredictionStore(tmp_path)
    first=SealSubjectMechanism(port,store).execute({'code':'frozen'})
    assert all('hidden-profiles' not in p for p in port.reads)
    assert first==SealSubjectMechanism(port,store).execute({'code':'frozen'})
    assert first['model_calls']==0 and first['new_scientific_predictions']==0

def test_profile_port_never_read_before_seal_or_after_code_change(tmp_path):
    store=FilePredictionStore(tmp_path);port=FileMechanismProfiles(ROOT/'prepared-v2/hidden-profiles.json')
    with pytest.raises(ArticleMapError):AuditSubjectMechanism(port,store).execute('missing',{})
    assert port.reads==[]
    seal=SealSubjectMechanism(FileMechanismInputs(ROOT/'prepared-v2/manifest.json'),store).execute({'code':'frozen'})
    with pytest.raises(ArticleMapError):AuditSubjectMechanism(port,store).execute(seal['run_id'],{'code':'changed'})
    assert port.reads==[]
    result=AuditSubjectMechanism(port,store).execute(seal['run_id'],{'code':'frozen'})
    assert result['empirical_forecasts_released']==0 and result['scientific_success'] is False

def test_changed_training_bytes_and_provenance_rejected(tmp_path):
    for name in ['manifest.json','inputs.json','evidence.json']:(tmp_path/name).write_text(json.dumps(read(name)),encoding='utf-8')
    i=read('inputs.json');i['knowledge'][0]['text']='changed';(tmp_path/'inputs.json').write_text(json.dumps(i),encoding='utf-8')
    with pytest.raises(ArticleMapError):FileMechanismInputs(tmp_path/'manifest.json').read_inputs()
