"""Контекст, временные смыслы, независимые семьи и разделение прогноза с оценкой."""
import copy
import json
from pathlib import Path
import pytest

from domain.article_maps import fingerprint
from domain.structured_question_forecast import validate_context, eligibility, forecast, evaluate
from application.structured_question_forecast import SealStructuredForecast, EvaluateStructuredForecast
from infrastructure.structured_prediction_artifacts import FileStructuredForecastArtifacts
from infrastructure.structured_prediction_corpus import PreparedStructuredTrainingCorpus
from infrastructure.structured_schema6_findings import structured_findings

def context(instrument='3ms'):
    return {'schema_version': 2, 'age_min': 70, 'specimen': 'plasma', 'timing': 'single_baseline', 'exposure': 'IL6',
        'outcome_scope': 'global_change', 'instrument': instrument, 'estimand': 'slope', 'contrast': 'high_low',
        'mci': None, 'adjustment_class': None,
        'time': {'study_horizon_years': 7, 'study_horizon_basis': 'upper_horizon', 'minimum_individual_years': None,
                 'assessment_span_min_years': None, 'modeled_time_years': 3.5, 'time_origin': 'baseline_exposure'},
        'baseline_dementia': {'operationally_excluded': True, 'method': 'authors_report_dementia_free', 'adjudication_status': 'unknown'}}

def observation(name, family, detection, instrument='3ms', direction=None):
    c = context(instrument)
    return {'reference': name, 'family': family, 'available_on': '2010-01-01', 'context': c,
        'findings': {'reported_detection': detection, 'point_direction': direction},
        'binding': {'source_sha256': 'a'*64, 'map_run_id': 'run', 'knowledge_id': name,
                    'frame_sha256': 'b'*64, 'context_sha256': fingerprint(c), 'annotation_sha256': 'c'*64}}

def request(): return {'reference': 'target', 'family': 'target-family', 'available_on': '2016-01-01', 'context': context()}

def training(): return [observation('a','family-a','detected'), observation('b','family-b','not_detected','mmse')]

def test_horizon_does_not_resolve_individual_minimum():
    c = context()
    assert eligibility(c,'reported_study_horizon') == []
    assert eligibility(c,'verified_individual_minimum') == ['unknown:minimum_individual_years']
    assert c['time']['minimum_individual_years'] is None

@pytest.mark.parametrize('key,value', [('age_min',False),('time',{'followup_min':7}),('schema_version',True),('specimen',3)])
def test_incorrect_context_rejected(key,value):
    c=context();c[key]=value
    with pytest.raises(ValueError): validate_context(c)

def test_legacy_boolean_duration_contract_not_accepted():
    with pytest.raises(ValueError): validate_context({'dementia_excluded':True,'followup_min':7})

def test_screening_cannot_be_adjudication():
    c=context();c['baseline_dementia'].update(method='clinical_adjudication',adjudication_status='not_documented')
    with pytest.raises(ValueError,match='Adjudication'): validate_context(c)

@pytest.mark.parametrize('field,value', [('specimen','serum'),('age_min',59),('timing','repeated'),('exposure','CRP'),('outcome_scope','domain_change')])
def test_question_conditions_preserved(field,value):
    c=context();c[field]=value
    assert 'mismatch:'+field in eligibility(c,'reported_study_horizon')

def test_model_learns_training_categorical_counts():
    t=training();r=request()
    nb=forecast(t,r,'categorical_naive_bayes','reported_study_horizon')['findings']['reported_detection']
    base=forecast(t,r,'family_frequency','reported_study_horizon')['findings']['reported_detection']
    assert nb['probabilities']['detected'] > base['probabilities']['detected']
    changed=request();changed['context']['instrument']='mmse'
    assert forecast(t,changed,'categorical_naive_bayes','reported_study_horizon')['findings']['reported_detection']['top_label']=='not_detected'
    assert base['top_label'] is None

def test_unknowns_are_marginalized_and_not_counted_as_equal():
    result=forecast(training(),request(),'categorical_naive_bayes','reported_study_horizon')
    trace=result['findings']['reported_detection']['feature_trace']
    assert next(r for r in trace if r['field']=='mci')['status']=='unknown_query'
    changed=request();changed['context']['instrument']='unseen-test'
    result=forecast(training(),changed,'categorical_naive_bayes','reported_study_horizon')
    assert result['findings']['reported_detection']['top_label'] is None
    assert next(r for r in result['findings']['reported_detection']['feature_trace'] if r['field']=='instrument')['status']=='unseen_query'

def test_family_repeated_observations_do_not_add_independence():
    t=training();original=forecast(t,request(),'categorical_naive_bayes','reported_study_horizon')
    copies=[dict(copy.deepcopy(t[0]),reference='a-copy-'+str(i)) for i in range(20)]
    result=forecast(t+copies,request(),'categorical_naive_bayes','reported_study_horizon')
    assert result['findings']['reported_detection']['families']==2
    assert result['findings']['reported_detection']['probabilities']==pytest.approx(original['findings']['reported_detection']['probabilities'])

def test_missing_directions_never_turn_into_zero_effect():
    result=forecast(training(),request(),'family_frequency','reported_study_horizon')
    assert result['findings']['point_direction']['status']=='abstained'
    assert result['findings']['point_direction']['families']==0

@pytest.mark.parametrize('corruption',['family','date','context_digest','duplicate'])
def test_target_leak_future_training_and_modified_context_rejected(corruption):
    t=training()
    if corruption=='family': t[0]['family']='target-family'
    elif corruption=='date': t[0]['available_on']='2016-01-01'
    elif corruption=='context_digest': t[0]['context']['instrument']='different'
    else: t.append(t[0])
    with pytest.raises(ValueError): forecast(t,request(),'categorical_naive_bayes','reported_study_horizon')

def test_holdout_outcome_not_accepted_in_request():
    r=request();r['findings']={'reported_detection':'not_detected'}
    with pytest.raises(ValueError,match='cannot contain'): forecast(training(),r,'family_frequency','reported_study_horizon')

def test_brier_exposes_worse_context_forecast():
    target=observation('target','target-family','not_detected');target['available_on']='2016-01-01'
    scores={}
    for model in ('family_frequency','categorical_naive_bayes'):
        pred=forecast(training(),request(),model,'reported_study_horizon')
        scores[model]=evaluate(pred,target)[0]['brier']
    assert scores['categorical_naive_bayes']>scores['family_frequency']

def test_known_lower_bound_enables_sensitivity_without_imputation():
    c=context();c['time']['minimum_individual_years']=2
    assert eligibility(c,'verified_individual_minimum')==[]
    c['time']['minimum_individual_years']=1
    assert 'mismatch:minimum_individual_years' in eligibility(c,'verified_individual_minimum')

def test_source_adapters_do_not_create_missing_sign():
    k={'semantic_frame':{'logic':'single','statements':[{'negated':False,'predicate':'associated with','qualifiers':{'attributes':[
        {'name':'evidence_presentation','value':'own_result','unit':None}, {'name':'detection','value':'statistically significant','unit':None}]}}]}}
    assert structured_findings(k,None)=={'reported_detection':'detected','point_direction':None}

@pytest.mark.parametrize('unit',['mg/L','unknown points/year','person_years'])
def test_unregistered_orientation_rejected(unit):
    k={'semantic_frame':{'logic':'single','statements':[{'negated':False,'predicate':'estimated association','qualifiers':{'attributes':[
        {'name':'evidence_presentation','value':'own_result','unit':None}, {'name':'estimate','value':-1,'unit':unit}]}}]}}
    with pytest.raises(ValueError,match='orientation'): structured_findings(k,None)

def test_seal_before_evaluator_and_immutable_replay(tmp_path):
    class Corpus:
        def context(self,reference): return request()
        def earlier_other_families(self,family,before): return training()
    class Target:
        reads=0
        def outcome(self,reference):
            self.reads+=1;r=observation('target','target-family','not_detected');r['available_on']='2016-01-01';return r
    store=FileStructuredForecastArtifacts(tmp_path);target=Target()
    app=SealStructuredForecast(Corpus(),store)
    meta={'already_outcome_exposed':True,'blind_scientific_test':False}
    run=app.execute(['target'],meta)
    assert target.reads==0 and app.execute(['target'],meta)==run
    eid,result=EvaluateStructuredForecast(target,store).execute(run)
    assert target.reads==4 and result['new_clinical_predictions']==0
    assert (tmp_path/run/'evaluations'/f'{eid}.json').exists()

def test_sealed_tamper_is_rejected(tmp_path):
    store=FileStructuredForecastArtifacts(tmp_path);store.seal('a'*64,{'predictions':[]})
    with pytest.raises(ValueError,match='changed'): EvaluateStructuredForecast(object(),store).execute('a'*64)

def test_artifact_path_traversal_rejected(tmp_path):
    with pytest.raises(ValueError): FileStructuredForecastArtifacts(tmp_path).read_seal('../escape')
