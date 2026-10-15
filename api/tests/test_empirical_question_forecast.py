"""Проверки утечки, независимости, контекста и неизменяемости эмпирического прогноза."""
from dataclasses import replace
from copy import deepcopy
import pytest
from domain.article_maps import ArticleMapError
from domain.empirical_question_forecast import Observation, ForecastRequest, forecast, context_agreement, eligibility, score_prediction, LABELS, QUESTION
from application.empirical_question_forecast import SealEmpiricalForecast, EvaluateEmpiricalForecast
from infrastructure.empirical_forecast_store import FileEmpiricalForecastStore, PreparedEmpiricalCorpus
from infrastructure.empirical_schema6_observations import findings
from types import SimpleNamespace

CONTEXT={'age_min':70,'dementia_excluded':True,'specimen':'plasma','timing':'single_baseline','exposure':'IL6',
         'outcome_scope':'global_change','followup_min':3,'instrument':'mmse','estimand':'annual_change',
         'contrast':'high_low','mci':None,'adjustment_class':'basic_baseline'}

def observation(name='A',family='A',direction='more_decline',detection='not_detected',date='2010-01-01',**kwargs):
    return Observation(name,family,date,deepcopy(CONTEXT),{'direction':direction,'detection':detection},
                       {'source_sha256':'a'*64,'run_id':'run-'+name,'claim_sha256':'b'*64},**kwargs)

def request(**kwargs):
    return ForecastRequest.parse({'question_id':QUESTION,'as_of':'2014-01-01','excluded_families':['T'],'context':deepcopy(CONTEXT),**kwargs})

@pytest.mark.parametrize('key,value',[('specimen','serum'),('timing','trajectory'),('age_min',55),('dementia_excluded',False),('followup_min',1),('exposure','CRP'),('outcome_scope','dementia_incidence')])
def test_question_cannot_be_relaxed(key,value):
    ctx={**CONTEXT,key:value}
    prediction=forecast([observation(),observation('B','B')],request(context=ctx),'semantic')
    assert prediction['status']=='abstained' and 'mismatch:'+key in prediction['reasons']

@pytest.mark.parametrize('key',['specimen','timing','age_min','dementia_excluded','followup_min','exposure','outcome_scope'])
def test_unknown_core_context_abstains(key):
    assert 'unknown:'+key in eligibility({**CONTEXT,key:None})

@pytest.mark.parametrize('bad',[True,float('nan'),float('inf'),-1])
def test_invalid_quantities_rejected(bad):
    with pytest.raises(ArticleMapError): request(context={**CONTEXT,'age_min':bad})

def test_target_finding_cannot_enter_request():
    raw={'question_id':QUESTION,'as_of':'2014-01-01','excluded_families':['T'],'context':CONTEXT,'finding':'more_decline'}
    with pytest.raises(ArticleMapError): ForecastRequest.parse(raw)

def test_family_duplicate_does_not_multiply_support():
    data=[observation(),observation('A2','A'),observation('B','B')]
    a=forecast(data,request(),'frequency')['findings']['direction']
    b=forecast([data[0],data[2]],request(),'frequency')['findings']['direction']
    assert a['probabilities']==b['probabilities'] and a['families']==2

def test_one_family_abstains_despite_many_publications():
    assert forecast([observation(str(i),'A') for i in range(8)],request(),'semantic')['status']=='abstained'

def test_unknown_not_equivalent_to_unknown():
    agreement=context_agreement(CONTEXT,CONTEXT)
    assert 'mci' in agreement['unknown'] and agreement['similarity']==.8 and not agreement['knowledge_equivalence']

def test_different_facts_are_not_equivalent_even_when_ranked():
    ctx={**CONTEXT,'instrument':'3ms','contrast':'log_per_sd'}
    agree=context_agreement(CONTEXT,ctx)
    assert agree['differences']==['instrument','contrast'] and not agree['knowledge_equivalence']

def test_nondetection_can_have_negative_point_estimate():
    a=forecast([observation(),observation('B','B')],request(),'frequency')
    assert a['findings']['direction']['top_label']=='more_decline'
    assert a['findings']['detection']['top_label']=='not_detected'
    assert not a['causal_effect_established'] and not a['predicts_numeric_effect']

def test_conflicting_strata_remain_one_family_distribution():
    data=[observation(),observation('A2','A','less_decline'),observation('B','B','less_decline')]
    channel=forecast(data,request(),'frequency')['findings']['direction']
    first=next(e for e in channel['evidence'] if e['family']=='A')
    assert first['votes']['more_decline']==.5 and first['votes']['less_decline']==.5 and first['weight']==1

def test_dependency_does_not_replace_empty_result():
    prediction=forecast([observation(),observation('B','B')],request(),'dependency')
    assert prediction['status']=='abstained' and all('author_use_not_grounded' in row['reasons'] for row in prediction['exclusions'])

def test_dependency_explicit_support_and_temporal_exclusion():
    data=[observation(dependency_grounded=True),observation('B','B',dependency_grounded=True),observation('T','T',dependency_grounded=True),observation('later','C',date='2014-01-01',dependency_grounded=True)]
    prediction=forecast(data,request(),'dependency')
    assert prediction['findings']['direction']['families']==2
    assert [r['reference'] for r in prediction['exclusions']]==['T','later']

def test_application_rejects_leakage(tmp_path):
    service=SealEmpiricalForecast(PreparedEmpiricalCorpus([observation('T','T')]),FileEmpiricalForecastStore(tmp_path))
    with pytest.raises(ArticleMapError):service.execute(['T'],request().__dict__ | {'excluded_families':['T']},'p'*64)
    assert not list(tmp_path.rglob('sealed.json'))

def test_seal_before_evaluator_and_reproducible(tmp_path):
    training=PreparedEmpiricalCorpus([observation(),observation('B','B')]);store=FileEmpiricalForecastStore(tmp_path)
    raw={**request().__dict__,'excluded_families':['T']}
    sealed=SealEmpiricalForecast(training,store).execute(['A','B'],raw,'p'*64)
    evaluator=PreparedEmpiricalCorpus([observation('T','T',date='2014-01-01')])
    assert evaluator.reads==[]
    first=EvaluateEmpiricalForecast(evaluator,store).execute(sealed['run_id'],['T'])
    second=EvaluateEmpiricalForecast(evaluator,store).execute(sealed['run_id'],['T'])
    assert first==second and not first['scientific_success']
    assert first['scores']['frequency'][0]['categorical_match'] is True

def test_tampered_probability_rejected_before_target_read(tmp_path):
    training=PreparedEmpiricalCorpus([observation(),observation('B','B')]);store=FileEmpiricalForecastStore(tmp_path)
    sealed=SealEmpiricalForecast(training,store).execute(['A','B'],{**request().__dict__,'excluded_families':['T']},'p'*64)
    original=store.read_seal
    def tampered(run_id):
        data=original(run_id);data['modes']['semantic']['findings']['direction']['probabilities']['more_decline']=1;return data
    store.read_seal=tampered
    evaluator=PreparedEmpiricalCorpus([observation('T','T',date='2014-01-01')])
    with pytest.raises(ArticleMapError): EvaluateEmpiricalForecast(evaluator,store).execute(sealed['run_id'],['T'])
    assert evaluator.reads==[]

def test_immutable_error_does_not_damage_seal(tmp_path):
    store=FileEmpiricalForecastStore(tmp_path);rid='f'*64
    store.seal(rid,{'first':True})
    with pytest.raises(ArticleMapError):store.seal(rid,{'first':False})
    assert store.read_seal(rid)=={'first':True}

def test_invalid_output_or_duplicate_reference_rejected():
    with pytest.raises(ArticleMapError):forecast([observation(),observation()],request(),'semantic')
    with pytest.raises(ArticleMapError):forecast([replace(observation(),findings={'direction':'causal','detection':'not_detected'})],request(),'semantic')

def test_retrieval_is_not_forecast():
    prediction=forecast([observation()],request(),'known_union')
    assert prediction['status']=='retrieval_only' and prediction['findings']=={} and len(prediction['known'])==1

def test_evaluation_does_not_select_only_matching_subgroups():
    pred=forecast([observation(),observation('B','B')],request(),'frequency')
    rows=score_prediction(pred,[observation('T1','T',date='2014-01-01'),observation('T2','T','less_decline',date='2014-01-01')])
    assert len(rows)==4 and sum(row.get('categorical_match') is True for row in rows)==3

@pytest.mark.parametrize('name,value,unit,expected',[
    ('beta','-0.13','mmse points/year','more_decline'),
    ('slope difference','0.036','3mse points/visit per sd','less_decline'),
    ('hazard ratio','0.94','dimensionless','less_decline'),
    ('odds ratio','1','dimensionless','zero_point_estimate'),
])
def test_canonical_decimal_strings_and_null_reference(name,value,unit,expected):
    claim=SimpleNamespace(measurements=[{'name':name,'value':value,'unit':unit}],modality='not statistically detected')
    assert findings(claim)=={'direction':expected,'detection':'not_detected'}

@pytest.mark.parametrize('value,unit',[(True,'mmse points/year'),('NaN','mmse points/year'),('-1','dimensionless'),('0.1','tics-m points/year')])
def test_unregistered_units_or_invalid_estimate_rejected(value,unit):
    name='hazard ratio' if unit=='dimensionless' else 'beta'
    with pytest.raises(ArticleMapError): findings(SimpleNamespace(measurements=[{'name':name,'value':value,'unit':unit}],modality='statistically detected'))

def test_all_network_is_denied_during_cli_experiment():
    from tools.run_empirical_question_checkpoint import prohibit_network
    with pytest.raises(RuntimeError): prohibit_network('socket.connect',())
    with pytest.raises(RuntimeError): prohibit_network('socket.getaddrinfo',())
