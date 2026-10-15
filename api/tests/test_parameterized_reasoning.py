"""Связанные параметры, контексты, существование и честное определение успеха."""
from copy import deepcopy
import pytest
from domain.article_maps import ArticleMapError,fingerprint
from domain.parameterized_reasoning import interpret,p_interval
from domain.categorical_reasoning import catalog,check,apply
from domain.goal_pattern_experience import Goal,assess,summarize

def case(p='0.28',alpha='0.0025',precision='reported_value'):
    return {'case_id':'test','family':'test-family','source_binding':{'article_id':'T','run_id':'R','source_sha256':'a'*64,'map_sha256':'b'*64},
      'context':{'analysis_id':'T-A','exposure':'baseline IL-6','outcome':'annual MMSE change','stratum':'no baseline MCI','model':'linear regression','time':'baseline to year 3','conditions':['age, sex and baseline cognition adjusted']},
      'p':{'expression':p,'precision':precision},'alpha':{'value':alpha,'relation':'<'},
      'assumptions':{'same_analysis':True,'test_identified':True,'declared_threshold':True,'dimensionless':True,'interpretation_basis':'reported_values'},
      'premises':[{'knowledge_id':'p'},{'knowledge_id':'alpha'}]}

@pytest.mark.parametrize('p,a,want', [('0.001','0.0025','below_threshold'),('0.28','0.0025','not_below_threshold'),
 ('<0.001','0.0025','below_threshold'),('>0.1','0.05','not_below_threshold'),('0.05','0.05','not_below_threshold'),
 ('<0.05','0.05','below_threshold'),('<=0.05','0.05','indeterminate'),('>0.0001','0.05','indeterminate')])
def test_parameter_boundaries(p,a,want):
    result=interpret(case(p,a)); assert result['status']==want and result['scientific_prediction'] is False
    assert not any(k in result for k in ['effect_size','effect_direction','causes','absence_of_effect'])

def test_rounding_cannot_silently_cross_a_threshold():
    assert interpret(case('0.002','0.0025','nearest_rounding'))['status']=='indeterminate'
    assert interpret(case('0.002','0.0025'))['status']=='below_threshold'
    assert interpret(case('0.28','0.0025','nearest_rounding'))['status']=='not_below_threshold'

@pytest.mark.parametrize('field',['same_analysis','test_identified','declared_threshold','dimensionless'])
def test_unknown_guard_blocks_interpretation(field):
    raw=case();raw['assumptions'][field]=None
    result=interpret(raw);assert result['status']=='blocked' and field in result['reasons']

@pytest.mark.parametrize('field',['analysis_id','exposure','outcome','stratum','model','time','conditions'])
def test_unknown_context_blocks(field):
    raw=case();raw['context'][field]=None;assert interpret(raw)['status']=='blocked'

@pytest.mark.parametrize('p',['-0.1','1.01','NaN','Infinity','0.02 or 0.1','<0','>1'])
def test_invalid_p_is_rejected(p):
    with pytest.raises(ArticleMapError):interpret(case(p))

def test_outcome_field_forbidden_and_source_unchanged():
    raw=case();before=fingerprint(raw);interpret(raw);assert fingerprint(raw)==before
    raw['expected']='below_threshold'
    with pytest.raises(ArticleMapError):interpret(raw)

def test_all_256_forms_have_fifteen_unconditional_and_twenty_four_conditional():
    forms=catalog();assert len(forms)==24
    assert sum(x['unconditional'] for x in forms)==15
    assert len({x['id'] for x in forms})==24
    assert check('AAA',1)['valid'] and not check('AAA',2)['valid']
    darapti=next(x for x in forms if x['id']=='AAI3')
    assert darapti['minimal_existence_sets']==[['M']]

def test_proof_cache_cannot_be_mutated_by_a_caller():
    proof=check('AAA',2);proof['valid']=True;proof['countermodel'].clear()
    assert not check('AAA',2)['valid'] and check('AAA',2)['countermodel']

def premises(mood='AAI',figure=3):
    from domain.categorical_reasoning import FIGURES
    context={'population':'same objects','time':'same phase','modality':'asserted'}
    return [{'relation_kind':'categorical','quantifier':letter,'subject':sub,'predicate':pred,
      'context':context,'source_binding':{'claim_id':f'{sub}-{pred}'}}
      for letter,(sub,pred) in zip(mood[:2],FIGURES[figure])]

def test_existential_import_requires_grounded_same_context_witness():
    inputs=premises();assert apply('AAI',3,inputs,{})['status']=='not_entailed'
    witness={'M':{'source_binding':{'claim_id':'witness'},'context':inputs[0]['context']}}
    assert apply('AAI',3,inputs,witness)['status']=='valid_conditional_deduction'
    witness['M']['context']={**inputs[0]['context'],'time':'other phase'}
    assert apply('AAI',3,inputs,witness)['status']=='not_entailed'

@pytest.mark.parametrize('difference',['association','time','modality','binding'])
def test_scientific_relations_do_not_become_universal_class_membership(difference):
    p=premises('AAA',1)
    if difference=='association':p[0]['relation_kind']='observational_association'
    elif difference=='binding':p[0]['source_binding']={}
    elif difference=='modality':
        for q in p:q['context']={**q['context'],'modality':'may'}
    else:p[1]['context']={**p[1]['context'],'time':'other phase'}
    assert apply('AAA',1,p,{})['status']=='blocked'

def goal():return Goal('interpret','engineering_interpretation','agreement',1.0,{'phase':'interpretation'},'a'*64)
def trial(value=1):
    return {'pattern_id':'operator','family':'one-cohort','case_id':'one-case','metric':'agreement','value':value,
      'context':{'phase':'interpretation'},'outcome_observed':True,'binding':{'case_sha256':'b'*64},'prospective':False}

@pytest.mark.parametrize('value,status',[(1,'goal_met'),(0,'goal_not_met'),(None,'unknown')])
def test_goal_success_is_not_positive_scientific_result(value,status):
    experience=assess(goal(),trial(value));assert experience['status']==status
    assert not experience['scientific_success'] and not experience['negative_scientific_result_is_failure']
    assert not experience['absence_is_refutation']

def test_different_objectives_and_missing_observation_not_failure():
    t=trial();t['context']={'phase':'clinical forecasting'};assert assess(goal(),t)['status']=='inapplicable'
    t=trial();t['outcome_observed']=False;assert assess(goal(),t)['status']=='unknown'
    t=trial();t['metric']='future_effect_match';assert assess(goal(),t)['status']=='inapplicable'

def test_repeated_case_does_not_inflate_support():
    e=assess(goal(),trial())
    with pytest.raises(ArticleMapError):summarize([e,e])
    t=trial();t['case_id']='second-case';groups=summarize([e,assess(goal(),t)])
    assert groups[0]['goal_met']==2 and len(groups[0]['evaluated_families'])==1
    assert not groups[0]['empirical_transfer_supported']

def test_versions_and_repeated_modified_outcomes_do_not_mix():
    e=assess(goal(),trial());t=trial(0)
    with pytest.raises(ArticleMapError):summarize([e,assess(goal(),t)])
    second_goal=Goal('interpret','engineering_interpretation','agreement',1.0,{'phase':'interpretation'},'b'*64)
    assert len(summarize([e,assess(second_goal,t)]))==2
