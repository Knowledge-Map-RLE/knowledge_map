"""Проверяются допустимые сравнения и отсутствие автоматического разрешения переноса."""
from copy import deepcopy
import pytest
from domain.article_maps import ArticleMapError
from domain.definition_robustness import audit_definition_changes, compare_definitions, validate_series
from application.definition_robustness import AuditDefinitionRobustness
from infrastructure.definition_robustness import FileDefinitionAudit
from pathlib import Path
import json
from hashlib import sha256

ROOT=Path(__file__).resolve().parents[2]/'eval/free_prediction/definition-bridge-audit-v1'


def series():
    return {'id':'mci','source_id':'source','cohort':'cohort','definition':'Isolated memory impairment',
            'context':{'population':'general_population','residence':'community_and_institution',
                       'age_basis':'baseline','measure':'incidence_rate','unit':'per1000personyears',
                       'sex':'all','estimand':'observed','complaint':'required','phenotype':'memory_only'},
            'cells':[{'age':[75,79],'value':'10','interval':['1','30'],'cases':10,'person_years':'1000','evidence_id':'a'},
                     {'age':[80,84],'value':'20','interval':['1','40'],'cases':20,'person_years':'1000','evidence_id':'b'},
                     {'age':[85,None],'value':'15','interval':['1','40'],'cases':15,'person_years':'1000','evidence_id':'c'}],
            'provenance':['methods','table']}


def modified():
    s=series();s['id']='mci-modified';s['context']['complaint']='not_required'
    return s


def test_comparison_never_activates_a_cross_study_bridge():
    result=compare_definitions(series(),modified(),['complaint'])
    assert len(result['rows'])==3 and all(r['point_order_preserved'] for r in result['rows'])
    assert result['independent_cohorts']==1 and result['bridge_activated'] is False
    assert not result['prediction'] and not result['equivalence_asserted'] and not result['statistical_significance_tested']


def test_endpoint_change_can_reverse_order_without_rewriting_either_fact():
    a=series();b=series();b['id']='aacd';b['context']['phenotype']='any_domain'
    b['cells'][2].update(value='25',cases=25)
    original=deepcopy([a,b]);r=compare_definitions(a,b,['phenotype'])
    assert [x['point_order_preserved'] for x in r['rows']]==[True,True,False]
    assert [a,b]==original


@pytest.mark.parametrize('change',[
    lambda s:s.update(cohort='other'),lambda s:s.update(source_id='other'),
    lambda s:s['context'].update(age_basis='attained'),lambda s:s['context'].update(phenotype='other'),
    lambda s:s['context'].update(estimand=None),lambda s:s['cells'][-1].update(age=[85,89]),
])
def test_unknown_or_unregistered_context_and_age_changes_rejected(change):
    b=modified();change(b)
    with pytest.raises(ArticleMapError):compare_definitions(series(),b,['complaint'])


@pytest.mark.parametrize('change',[
    lambda s:s['cells'][0].update(value='NaN'),lambda s:s['cells'][0].update(person_years='0'),
    lambda s:s['cells'][0].update(value='12'),lambda s:s['cells'][0].update(interval=['15','30']),
    lambda s:s['cells'][1].update(age=[79,84]),lambda s:s['cells'][0].update(evidence_id=''),
    lambda s:s['cells'][0].update(expected_order='higher'),lambda s:s['context'].update(age_basis=None),
])
def test_invalid_numeric_or_provenance_input_is_rejected(change):
    a=series();change(a)
    with pytest.raises(ArticleMapError):validate_series(a)


def test_same_cohort_publications_do_not_become_replications():
    a=series();b=modified();r=audit_definition_changes([a,b],[{'id':'complaint','first':'mci','second':'mci-modified','varied_fields':['complaint']}])
    assert r['cohorts']==['cohort'] and r['new_scientific_predictions']==0


def test_equal_point_estimates_are_not_significant_differences():
    a=series();b=modified()
    for s in (a,b):s['cells'][1].update(value='10',cases=10)
    r=compare_definitions(a,b,['complaint'])
    assert r['rows'][0]['orders']=={'mci':'equal','mci-modified':'equal'}


def test_primary_12_cells_and_two_counterexamples_have_verified_provenance(monkeypatch):
    import socket
    def forbidden(*args,**kwargs):raise AssertionError('Network/model calls forbidden')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    port=FileDefinitionAudit(ROOT);inputs=port.read()
    r=AuditDefinitionRobustness().execute(inputs['spec'],inputs['evidence'],inputs['texts'])
    assert len(port.reads)==9 and len(inputs['spec']['series'])==4
    assert sum(len(s['cells']) for s in inputs['spec']['series'])==12
    assert all(all(row['point_order_preserved'] for row in c['rows']) for c in r['comparisons'][:2])
    assert sum(not row['point_order_preserved'] for c in r['comparisons'] for row in c['rows'])==2
    assert r['cohorts']==['LEILA75+'] and r['bridge_activated'] is False


def test_three_repaired_rates_do_not_rewrite_prior_quarantine_or_add_a_cohort():
    inputs=FileDefinitionAudit(ROOT).read();repair=inputs['repairs']
    prior=Path(repair['prior_path'])
    assert sha256(prior.read_bytes()).hexdigest()==repair['prior_sha256']
    assert len(repair['repairs'])==3 and not repair['independent_cohort_added']
    old=json.loads(prior.read_text(encoding='utf-8'))
    assert all(next(x for x in old['rows'] if x['id']==r['old_id'])['status']=='quarantined' for r in repair['repairs'])
    assert all(not r['automatic_training_admission'] for r in repair['repairs'])


@pytest.mark.parametrize('change',[
    lambda i:i['evidence']['table3'].update(start=0),
    lambda i:i['texts'].update({'busse-bjp2003':'changed source'}),
    lambda i:i['spec']['series'][0]['cells'][0].update(evidence_id='unknown'),
    lambda i:i['spec'].update(model_calls=1),
])
def test_corrupted_primary_provenance_or_authorship_rejected(change):
    inputs=FileDefinitionAudit(ROOT).read();change(inputs)
    with pytest.raises(ArticleMapError):AuditDefinitionRobustness().execute(inputs['spec'],inputs['evidence'],inputs['texts'])


def test_manifest_tampering_is_rejected(tmp_path):
    (tmp_path/'inputs.json').write_text(json.dumps({'files':{'../outside.json':'x'}}),encoding='utf-8')
    with pytest.raises(ArticleMapError,match='escapes'):FileDefinitionAudit(tmp_path).read()
