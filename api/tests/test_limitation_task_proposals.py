"""Проверяет задачи из ограничений, неизвестность контекста и запрет подстановки цели."""
import copy
import socket

import pytest

from application.limitation_task_proposals import run_task_proposals
from domain.article_maps import ArticleMapError
from domain.limitation_task_proposals import propose_tasks


def fact(fid, kind, data, roles=None):
    return {'id':fid,'kind':kind,'context':'local-study','roles': roles or {'exposure':'marker','outcome':'tau'},
            'negated':False,'data':data,'grounding':'own_study_description',
            'origin':{'knowledge_id':'K'+fid,'statement_ids':['S'+fid]}}


def request(facts, groups): return {'question':'address_documented_limitations','facts':facts,'joint_groups':groups}


def temporal():
    return request([fact('d','relationship_design',{'design':'cross_sectional'}),
                    fact('a','longitudinal_assessment',{'assessment':'unassessed'})],[['d','a']])


def test_temporal_gap_proposes_an_unresolved_task_not_a_result():
    r=propose_tasks(temporal());t=r['tasks'][0]
    assert t['predicate']=='assess_relationship_with_prospective_repeated_outcome_measurements'
    assert t['action_status']=='unresolved' and t['roles']=={'exposure':'marker','outcome':'tau'}
    assert not r['clinical_forecast'] and not r['causal_identification'] and not r['learned_rules']
    assert 'no_followup_length_or_sample_size_inferred' in t['limitations']


@pytest.mark.parametrize('assessment',['assessed_nondetection','assessed_detection','unknown'])
def test_nondetection_and_unknown_do_not_mean_unassessed(assessment):
    q=temporal();q['facts'][1]['data']['assessment']=assessment
    assert propose_tasks(q)['status']=='abstained'


@pytest.mark.parametrize('fid',['d','a'])
def test_both_temporal_inputs_are_necessary(fid):
    q=temporal();q['facts']=[f for f in q['facts'] if f['id']!=fid];q['joint_groups']=[[f['id'] for f in q['facts']]]
    assert propose_tasks(q)['status']=='abstained'


@pytest.mark.parametrize('change',['context','roles','grounding','negated'])
def test_incompatible_joint_premises_abstain(change):
    q=temporal()
    q['facts'][1][change]={'context':'other-study','roles':{'exposure':'marker','outcome':'volume'},
                          'grounding':'attributed_literature_gap','negated':True}[change]
    assert propose_tasks(q)['status']=='abstained'


def test_alternative_paths_are_not_combined_into_one_joint_group():
    q=temporal();q['joint_groups']=[['d'],['a']]
    assert propose_tasks(q)['status']=='abstained'
    q=temporal();f=fact('p','population_coverage',{'scope':'broad','restriction_dimensions':[]},{'population':'cohort'})
    q['facts'].append(f);q['joint_groups'].append(['p'])
    assert len(propose_tasks(q)['tasks'])==1


def test_population_task_preserves_dimensions_without_claiming_generalization():
    q=request([fact('p','population_coverage',{'scope':'restricted','restriction_dimensions':['ethnicity','education']}, {'population':'cohort'})],[['p']])
    t=propose_tasks(q)['tasks'][0]
    assert t['conditions']==['cover_documented_restrictions:education,ethnicity']
    assert 'no_assumed_replication_success' in t['limitations'] and t['action_status']=='unresolved'


@pytest.mark.parametrize('scope',['broad','unknown'])
def test_population_scope_not_invented(scope):
    q=request([fact('p','population_coverage',{'scope':scope,'restriction_dimensions':[]},{'population':'cohort'})],[['p']])
    assert propose_tasks(q)['status']=='abstained'


@pytest.mark.parametrize('sampling',['repeated','unknown'])
def test_existing_repeated_sampling_or_unknown_not_called_missing(sampling):
    q=request([fact('s','exposure_sampling',{'sampling':sampling},{'exposure':'marker'}),
               fact('c','exposure_construct',{'construct':'dynamic'},{'exposure':'marker'})],[['s','c']])
    assert propose_tasks(q)['status']=='abstained'


def test_single_snapshot_with_chronic_construct_proposes_measurements():
    q=request([fact('s','exposure_sampling',{'sampling':'single_occasion'},{'exposure':'marker'}),
               fact('c','exposure_construct',{'construct':'chronic'},{'exposure':'marker'})],[['s','c']])
    t=propose_tasks(q)['tasks'][0]
    assert t['predicate']=='characterize_exposure_with_repeated_measurements'
    assert 'no_sampling_interval_or_number_inferred' in t['limitations']


@pytest.mark.parametrize('payload',[None,{},'hidden answer'])
def test_malformed_input_rejected(payload):
    with pytest.raises(ArticleMapError): propose_tasks(payload)


def test_source_text_and_task_requirements_cannot_be_passed():
    q=temporal();q['target']='Longer follow-up';
    with pytest.raises(ArticleMapError): propose_tasks(q)
    q=temporal();q['facts'][0]['kind']='validation_requirement'
    with pytest.raises(ArticleMapError): propose_tasks(q)


def test_application_seals_before_evaluation_without_network(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Network forbidden')
    monkeypatch.setattr(socket,'socket',forbidden)
    records=[]
    class Store:
        def seal(self,key,value):records.append((key,copy.deepcopy(value)))
    r=run_task_proposals({'case':temporal()},Store())
    assert [k for k,_ in records]==['requests.json','sealed-output.json']
    assert records[1][1]==r and r['clinical_forecasts']==r['model_calls']==0
