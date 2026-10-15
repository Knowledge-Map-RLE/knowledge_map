"""Контрасты, референтные строки и тесты разных областей сохраняются раздельно."""
from copy import deepcopy
import pytest
from domain.statistical_context_views import project_audited_frame
from domain.statistical_context_audit import audit_models
from domain.article_maps import fingerprint,ArticleMapError
from hashlib import sha256


def coefficient(reference=False):
    a={'evidence presentation':'own_result','model':'Tobit regression','analysis n':'494',
       'printed coefficient and ci95':'Reference' if reference else '-2.22 (-3.48 to -0.96)',
       'individual p':'not reported' if reference else '.001','joint p':'.004','joint test scope':'CMV IgG',
       'adjustment':'age, sex, education','reference category':'Q1','source table':'2','joint p origin row':'12'}
    if not reference:a.update(estimate='-2.22',ci95='-3.48 to -0.96')
    return {'predicate':'estimated association','negated':False,
        'scope':{'time':'baseline','conditions':['age ≥85'],'study_group':'source','modality':None,'quantifier':None},
        'roles':[{'role':k,'value':v,'reference_kind':'concept'} for k,v in
            [('exposure','CMV IgG'),('category','Q1' if reference else 'Q4'),('outcome','baseline MMSE'),('adjustment','age, sex, education')]],
        'attributes':[{'name':k,'value':v,'unit':'MMSE latent-scale coefficient' if k in ('estimate','ci95') else None} for k,v in a.items()]}


def context(reference=False,index=0):
    return {'statement_index':index,'kind':'reference_coefficient' if reference else 'category_coefficient',
        'model':'Tobit regression','unit':'MMSE latent-scale coefficient','contrast':'reference category definition' if reference else 'Q4 versus Q1',
        'estimand':'latent baseline MMSE contrast','threshold':'0.05','reference':'Q1','bounds':['0','30'],'evidence_unit_ids':['U1']}


def frame(parts):return {'kind':'state','action_status':None,'logic':'contrast','statements':parts}


def test_reference_rows_and_individual_and_joint_tests_remain_distinct():
    f=frame([coefficient(True),coefficient()]);before=deepcopy(f)
    v,error=project_audited_frame(f,{'statements':[context(True),context(index=1)]})
    assert error is None and f==before and len(v['frame']['statements'])==2
    assert v['statements'][0]['point'] is None and v['statements'][0]['direction']=='reference_definition_only'
    assert v['statements'][0]['tests']['individual_test']=='not reported for reference category'
    assert v['statements'][1]['tests']=={'individual_test':'detected_at_declared_threshold','joint_test':'detected_at_declared_threshold'}
    assert 'latent Tobit response; observed MMSE is censored at 0 and 30' in v['frame']['statements'][1]['scope']['conditions']


def test_category_and_joint_test_cannot_substitute_for_each_other():
    s=coefficient();next(a for a in s['attributes'] if a['name']=='individual p')['value']='.652'
    v,_=project_audited_frame(frame([s]),{'statements':[context()]})
    assert v['statements'][0]['tests']['individual_test']=='not_detected_at_declared_threshold'
    assert v['statements'][0]['tests']['joint_test']=='detected_at_declared_threshold'
    assert v['statements'][0]['direction']=='below_null'


@pytest.mark.parametrize('change', ['reference','bounds','unit','threshold','missing_coefficient','unknown_field'])
def test_unestablished_contrast_or_model_rejects_whole_block(change):
    s=coefficient();c=context()
    if change=='reference':c['reference']='Q0'
    elif change=='bounds':c['bounds']=[]
    elif change=='unit':c['unit']='3MS points/year'
    elif change=='threshold':c['threshold']=None
    elif change=='unknown_field':s['attributes'].append({'name':'unknown coding','value':'unresolved','unit':None})
    else:s['attributes']=[a for a in s['attributes'] if a['name']!='estimate']
    assert project_audited_frame(frame([coefficient(True),s]),{'statements':[context(True),c]})[0] is None


def test_within_group_slope_does_not_reuse_between_group_p_as_zero_test():
    s=coefficient();s['predicate']='estimated cognitive slope'
    s['roles']=[{'role':k,'value':v,'reference_kind':'concept'} for k,v in
        [('population','high risk'),('index','primary index'),('outcome','3MS slope'),('adjustment','age')]]
    values={'evidence presentation':'own_result','n':'112','proportion':'16.6','estimate':'-.74',
            'ci95':'-.89 to -.59','p reference':'lowest risk category','p':'<.001'}
    s['attributes']=[{'name':k,'value':v,'unit':'3MS points/year' if k in ('estimate','ci95') else None} for k,v in values.items()]
    c=context();c.update(kind='time_slope',model='linear regression',unit='3MS points/year',reference='lowest risk category',bounds=[],threshold=None)
    v,error=project_audited_frame(frame([s]),{'statements':[c]})
    assert error is None and v['statements'][0]['direction']=='below_null'
    assert v['statements'][0]['tests']['zero_slope_test']=='not reported'
    assert 'threshold not declared' in v['statements'][0]['tests']['between_group_test']


def audited_map():
    source={'sha256':sha256(b'Methods and table').hexdigest(),'text':'Methods and table','content_end':17,
            'units':[{'id':'U1','start':0,'end':17,'text':'Methods and table'}]}
    k={'knowledge_id':'K1','kind':'state','semantic_frame':{'statements':[{'statement_id':'S1','provenance':{'unit_ids':['U1']}}]}}
    m={'article_id':'A','run_id':'R','source':source,'graph':{'knowledge':[k]}}
    evidence={'unit_id':'U1','start':0,'end':17,'text':source['text'],'sha256':source['sha256']}
    e={'article_id':'A','run_id':'R','knowledge_id':'K1','source_sha256':source['sha256'],
       'graph_sha256':fingerprint(m['graph']),'knowledge_sha256':fingerprint(k),'reason_ru':'Проверено по таблице.',
       'evidence':[evidence],'statements':[context()]}
    return m,{'version':'statistical-context-audit-1','author':'Codex','expert_validated':False,'model_calls':0,'entries':[e]}


def test_model_audit_is_bound_to_source_map_and_complete_frame():
    m,a=audited_map();assert list(audit_models([m],a))==[('A','K1')]
    a['entries'][0]['source_sha256']='changed'
    with pytest.raises(ArticleMapError):audit_models([m],a)


@pytest.mark.parametrize('case',['unlisted','source_text','outside_content','partial_frame','unknown_field','model_calls'])
def test_stale_or_untrusted_audit_cannot_enter_forecast(case):
    m,a=audited_map();e=a['entries'][0]
    if case=='unlisted':e['article_id']='target'
    elif case=='source_text':e['evidence'][0]['text']='different'
    elif case=='outside_content':m['source']['content_end']=5
    elif case=='partial_frame':e['statements']=[]
    elif case=='unknown_field':e['statements'][0]['invented']='context'
    else:a['model_calls']=1
    with pytest.raises(ArticleMapError):audit_models([m],a)


def test_normalized_unit_case_is_accepted_but_dimensions_are_not_changed():
    s=coefficient();a=next(a for a in s['attributes'] if a['name']=='estimate')
    a['unit']='mmse latent-scale coefficient'
    assert project_audited_frame(frame([s]),{'statements':[context()]})[1] is None
    a['unit']='mmse points/year'
    assert project_audited_frame(frame([s]),{'statements':[context()]})[0] is None
