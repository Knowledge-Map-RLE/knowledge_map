"""Применимость определяется контекстом до оценки совпадений с ответами."""
import copy
import json
from pathlib import Path

import pytest

from domain.article_maps import ArticleMapError,fingerprint
from domain.incidence_transfer_scope import VOCABULARY,compare_scope,forecast_scoped_fold,validate_scope
from application.incidence_transfer_scope import SealIncidenceScope,EvaluateIncidenceScope
from infrastructure.incidence_transfer_scope import FileIncidenceScopeInputs
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.empirical_inference_files import FileEmpiricalControls

ROOT=Path(__file__).resolve().parents[2]/'eval/free_prediction/incidence-scope-audit-v1'
PRIMARY=ROOT.parent/'primary-pdf-cohort-v1'


def scope():
    registry=json.loads((ROOT/'prepared/typed-contexts.json').read_text(encoding='utf-8'))
    return copy.deepcopy(registry['scopes']['Roberts 2012:aMCI']['scope'])


def fold():
    from tests.test_cohort_transfer import context
    training=[];scopes={}
    for study,family,country in [('a','A','France'),('b','B','Sweden'),('c','C','USA')]:
        c=context(study,family);c['endpoint']='aMCI';s=scope();s['moderators'].update(country=country,sample_size=family)
        scopes[study+':aMCI']={'scope':s,'provenance':[]}
        if family=='C':query={'id':'q','context':c,'ages':[[75,79],[80,84]],'evidence_ids':['metadata']}
        else:
            for age,value in [(75,10),(80,20)]:
                training.append({'id':study+str(age),'context':c,'age':[age,age+4],'value':str(value),
                                 'interval':['0','30'],'evidence_ids':['proof']})
    return {'fold_id':'synthetic','withheld_family':'C','training':training,'queries':[query],'evidence':{},'labels':{}},scopes


def test_compatible_scope_permits_hypothesis_despite_moderator_differences():
    f,s=fold();r=forecast_scoped_fold(f,s)['predictions'][0]
    assert r['order']=='higher' and len(r['family_votes'])==2
    assert r['scope_frequency']['order']=='higher'
    assert r['numeric_prediction'] is None and r['causal'] is False and r['equivalence_asserted'] is False
    assert all(w['comparison']['moderator_warnings'] for w in r['admitted'])


@pytest.mark.parametrize('field',sorted(VOCABULARY))
def test_unknown_critical_value_blocks_even_when_both_unknown(field):
    a=scope();a['critical'][field]=None
    r=compare_scope(a,a)
    assert r['eligible'] is False and [v['field'] for v in r['unknown']]==[field]


@pytest.mark.parametrize('field',[k for k,v in VOCABULARY.items() if len(v)>1])
def test_every_critical_difference_is_an_explicit_blocker(field):
    a=scope();b=copy.deepcopy(a)
    b['critical'][field]=next(v for v in sorted(VOCABULARY[field]) if v!=a['critical'][field])
    r=compare_scope(a,b)
    assert r['eligible'] is False and [v['field'] for v in r['different']]==[field]


def test_unknown_moderator_does_not_become_an_unknown_critical_block():
    a=scope();b=copy.deepcopy(a);b['moderators']['country']=None
    r=compare_scope(a,b)
    assert r['eligible'] and not r['unknown'] and any(w['field']=='country' for w in r['moderator_warnings'])


def test_one_family_with_two_publications_does_not_create_two_supports():
    f,s=fold()
    for o in f['training']:o['context']['family_id']='A'
    r=forecast_scoped_fold(f,s)['predictions'][0]
    assert r['order'] is None and len(r['family_votes'])==1 and r['scope_frequency']['order'] is None


def test_conflicting_orders_abstain_and_frequency_tie_abstains():
    f,s=fold();f['training'][3]['value']='5'
    r=forecast_scoped_fold(f,s)['predictions'][0]
    assert r['order'] is None and r['reason']=='conflicting_admitted_orders' and r['scope_frequency']['order'] is None


def test_rejection_does_not_depend_on_training_outcome_direction():
    f,s=fold();s['a:aMCI']['scope']['critical']['age_basis']='attained'
    a=forecast_scoped_fold(f,s)['predictions'][0]
    for o in f['training']:o['value']='1'
    b=forecast_scoped_fold(f,s)['predictions'][0]
    assert a['candidate_audits']==b['candidate_audits']


def test_unknown_context_prevents_prediction_without_implicit_bridge():
    f,s=fold();s['c:aMCI']['scope']['critical']['age_basis']=None
    r=forecast_scoped_fold(f,s)['predictions'][0]
    assert r['order'] is None and not r['admitted']
    assert all('unknown_critical_scope' in a['reasons'] for a in r['candidate_audits'])


def test_85plus_is_not_85to89():
    f,s=fold();f['queries'][0]['ages']=[[75,79],[80,None]]
    r=forecast_scoped_fold(f,s)['predictions'][0]
    assert r['order'] is None and all('different_age_bounds' in a['reasons'] for a in r['candidate_audits'])


def test_no_target_cohort_in_training():
    f,s=fold();f['training'][0]['context']['family_id']='C'
    with pytest.raises(ArticleMapError,match='leaked'):forecast_scoped_fold(f,s)


def test_unknown_scope_schema_or_extra_result_field_rejected():
    a=scope();a['expected_order']='higher'
    with pytest.raises(ArticleMapError):validate_scope(a)


def test_primary_scope_input_reads_only_explicit_contexts_and_folds():
    port=FileIncidenceScopeInputs(ROOT/'prepared/manifest.json');data=port.read_inputs()
    assert len(data['registry']['scopes'])==12 and len(data['folds'])==6
    assert len(port.reads)==9
    assert all(not any(word in p for word in ['hidden-controls','article.layout','article.pdf']) for p in port.reads)


def test_primary_results_are_not_silently_reclassified_as_predictions():
    data=FileIncidenceScopeInputs(ROOT/'prepared/manifest.json').read_inputs()
    results=[forecast_scoped_fold(f,data['registry']['scopes']) for f in data['folds']]
    assert sum(len(f['predictions']) for f in results)==30
    assert all(p['order'] is None for f in results for p in f['predictions'])
    assert sum(not any(v is None for v in p['semantic_scope']['critical'].values()) for f in results for p in f['predictions'])==9


def test_seal_precedes_controls_and_repeats_immutably(tmp_path,monkeypatch):
    import socket
    monkeypatch.setattr(socket,'socket',lambda *a,**k:pytest.fail('network attempted'))
    port=FileIncidenceScopeInputs(ROOT/'prepared/manifest.json');store=FilePredictionStore(tmp_path)
    controls=FileEmpiricalControls(PRIMARY/'prepared/hidden-controls.json')
    with pytest.raises(ArticleMapError,match='Seal required'):EvaluateIncidenceScope(controls,store).execute('0'*64,{'synthetic':'1'})
    assert controls.reads==[]
    r=SealIncidenceScope(port,store).execute({'synthetic':'1'});assert controls.reads==[]
    same=SealIncidenceScope(port,store).execute({'synthetic':'1'});assert fingerprint(r)==fingerprint(same)
    e=EvaluateIncidenceScope(controls,store).execute(r['run_id'],{'synthetic':'1'})
    assert e['modes']['typed_guard']['issued']==0 and e['independent_success'] is False
    with pytest.raises(ArticleMapError,match='implementation changed'):
        EvaluateIncidenceScope(controls,store).execute(r['run_id'],{'changed':'2'})


@pytest.mark.parametrize('change',['cohort','scope_field','proof_hash','extra_answer'])
def test_context_tampering_rejected_with_rebound_outer_hash(tmp_path,change):
    m=json.loads((ROOT/'prepared/manifest.json').read_text(encoding='utf-8'))
    r=json.loads((ROOT/'prepared/typed-contexts.json').read_text(encoding='utf-8'))
    record=r['scopes']['Katz 2012:aMCI']
    if change=='cohort':record['cohort_id']='other'
    if change=='scope_field':record['scope']['critical']['threshold_rule']='desired conclusion'
    if change=='proof_hash':record['provenance'][0]['source_sha256']='0'*64
    if change=='extra_answer':record['expected_order']='higher'
    m['registry_sha256']=fingerprint(r)
    (tmp_path/'manifest.json').write_text(json.dumps(m),encoding='utf-8')
    (tmp_path/'typed-contexts.json').write_text(json.dumps(r),encoding='utf-8')
    with pytest.raises(ArticleMapError):FileIncidenceScopeInputs(tmp_path/'manifest.json').read_inputs()
