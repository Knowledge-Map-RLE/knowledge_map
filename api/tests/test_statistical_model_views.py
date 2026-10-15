"""Модельные следствия не теряют контекст и не превращаются в причинные выводы."""
from copy import deepcopy
import pytest
from domain.article_maps import fingerprint
from domain.statistical_model_views import project_statement, project_frame
from domain.whole_map_numeric import project_numeric


def statement():
    values={'evidence presentation':'own_result','estimate':'1.20','ci95 printed':'(1.07 to 1.35)',
        'p':'.002','alpha':'.0025','analysis n':'279','model':'Cox regression',
        'estimand':'hazard ratio for ≥5-point 3MSE decline',
        'exposure increment':'one SD higher baseline biomarker in stated transformation',
        'transform':'as modeled','adjustment':'age, sex','time basis':'time to event; clinic-stratified baseline hazard',
        'baseline mci':'baseline MCI'}
    return {'predicate':'estimated hazard ratio',
        'roles':[{'role':r,'value':v,'reference_kind':'concept'} for r,v in
                 [('exposure','pentraxin 3'),('outcome','≥5-point 3MSE decline'),
                  ('population','baseline mci'),('adjustment','age, sex')]],
        'attributes':[{'name':k,'value':v,'unit':'dimensionless' if k in ('estimate','alpha') else None}
                      for k,v in values.items()], 'negated':False,
        'scope':{'time':'up to seven years','conditions':['no baseline dementia'],
                 'study_group':'participants','quantifier':None,'modality':'reported'}}


def attr(s,name):return next(a for a in s['attributes'] if a['name']==name)


def frame(s=None):
    return {'kind':'state','action_status':None,'logic':'conjunction','statements':[s or statement()]}


def test_conditional_model_view_retains_axes_scope_and_original_parent():
    f=frame();before=deepcopy(f)
    record={'frame':f,'eligible':True,'run_id':'r','text':'Exact source text',
            'provenance':[{'unit_ids':['U1']}], 'key':('article','K1')}
    out,diagnostic=project_numeric({record['key']:record})
    proof=diagnostic['proofs'][0]
    assert f==before and proof['parent_frame']==before
    assert proof['parent_frame_sha256']==fingerprint(before)
    assert proof['operator']=='typed_statistical_models'
    assert not proof['new_empirical_measurement'] and not proof['causality_asserted']
    s=out[record['key']]['frame']['statements'][0]
    assert s['roles']==before['statements'][0]['roles']
    assert s['scope']['time']=='up to seven years'
    assert 'no baseline dementia' in s['scope']['conditions']
    assert attr(s,'reported fitted direction')['value']=='above_null'
    assert attr(s,'conditional statistical finding')['value']=='detected_at_declared_threshold'


@pytest.mark.parametrize('field,value,reason',[
    ('exposure increment','one SD lower baseline biomarker','positive_exposure_increment_not_established'),
    ('model','logistic regression','model_or_estimand_mismatch'),
    ('estimand','prevalence odds ratio','model_or_estimand_mismatch'),
    ('evidence presentation','cited background','independent_observation_not_established'),
    ('transform','unknown binary coding','uninterpreted_exposure_transformation'),
    ('estimate','0','nonpositive_hazard_ratio'),
    ('estimate','NaN','ambiguous_model_point_estimate'),
    ('analysis n','279.5','invalid_declared_threshold_or_sample'),
    ('p','.002 2','uninterpreted_model_test'),
    ('baseline mci','without MCI','model_scope_role_mismatch')])
def test_ambiguous_or_incompatible_model_is_rejected(field,value,reason):
    s=statement();attr(s,field)['value']=value
    assert project_statement(s)==(None,reason)


def test_units_and_unknown_constraints_cannot_be_discarded():
    s=statement();attr(s,'estimate')['unit']='per 1000 person-years'
    assert project_statement(s)[1]=='model_effect_unit_mismatch'
    s=statement();s['attributes'].append({'name':'interaction coding','value':'unknown','unit':None})
    assert project_statement(s)[1]=='missing_or_unrecognized_model_fields'


def test_threshold_is_retained_and_nondetection_is_not_no_effect():
    s=statement();attr(s,'p')['value']='.01'
    a=project_statement(s)[0]['statement']
    assert attr(a,'conditional statistical finding')['value']=='not_detected_at_declared_threshold'
    assert attr(a,'reported fitted direction')['value']=='above_null'
    attr(s,'alpha')['value']='.05';b=project_statement(s)[0]['statement']
    assert attr(b,'conditional statistical finding')['value']=='detected_at_declared_threshold'
    assert a['scope']['conditions']!=b['scope']['conditions']


def test_entire_compound_frame_is_preserved_or_rejected():
    f=frame();f['logic']='contrast';second=deepcopy(f['statements'][0]);attr(second,'p')['value']='.08'
    f['statements'].append(second)
    v,error=project_frame(f)
    assert error is None and v['frame']['logic']=='contrast' and len(v['frame']['statements'])==2
    assert [attr(s,'conditional statistical finding')['value'] for s in v['frame']['statements']]==[
        'detected_at_declared_threshold','not_detected_at_declared_threshold']
    second['predicate']='causes'
    assert project_frame(f)[0] is None
    f=frame();f['kind']='action';f['action_status']='unresolved'
    assert project_frame(f)[1]=='model_frame_is_not_observation'


def test_model_time_basis_is_a_matching_constraint():
    a=statement();b=deepcopy(a);attr(b,'time basis')['value']='different time basis'
    assert project_statement(a)[0]['statement']['scope']['conditions']!=project_statement(b)[0]['statement']['scope']['conditions']


@pytest.mark.parametrize('predicate,estimand,unit,expected',[
    ('estimated cognitive level difference','midpoint 3MSE level difference','3MSE points per SD','reported fitted cognitive level direction'),
    ('estimated instantaneous rate difference','instantaneous 3MSE change difference at 3.5 years',
     '3MSE points per centered visit per SD','reported fitted instantaneous rate direction')])
def test_level_and_instantaneous_rate_are_distinct(predicate,estimand,unit,expected):
    s=statement();s['predicate']=predicate;attr(s,'model')['value']='mixed-effects regression'
    attr(s,'estimand')['value']=estimand;attr(s,'estimate')['value']='-.12';attr(s,'estimate')['unit']=unit
    v,error=project_statement(s)
    assert error is None and v['null']=='0' and v['statement']['predicate']==expected
    assert attr(v['statement'],'reported fitted direction')['value']=='below_null'
    assert not v['biological_direction_established']
