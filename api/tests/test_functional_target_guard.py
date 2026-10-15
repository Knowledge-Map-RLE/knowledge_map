"""Связывание не доказывает ингибирование; структурная совместимость не доказывает эффективность."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from domain.article_maps import ArticleMapError,fingerprint
from domain.functional_target_guard import functional_evidence_sufficient,compile_guards,DOMAIN
from infrastructure.functional_target_guard import load_functional_sources


@pytest.mark.parametrize('binding,function,model,target,expected',[
    (True,True,DOMAIN,DOMAIN,True),(True,False,DOMAIN,DOMAIN,False),(False,True,DOMAIN,DOMAIN,False),
    (True,True,'mouse TNFR1',DOMAIN,False),(True,True,None,DOMAIN,False),(True,True,DOMAIN,None,False)])
def test_binding_and_orthology_do_not_fill_missing_function(binding,function,model,target,expected):
    assert functional_evidence_sufficient(binding,function,model,target)==expected


def test_binding_only_has_two_consistent_function_models():
    # Без отдельной посылки обе интерпретации совместимы со связыванием.
    worlds=[{'binds':True,'inhibits':False},{'binds':True,'inhibits':True}]
    assert all(w['binds']for w in worlds) and not all(w['inhibits']for w in worlds)
    assert not functional_evidence_sufficient(True,False,DOMAIN,DOMAIN)


@pytest.fixture(scope='module')
def corpus():
    root=Path(__file__).resolve().parents[2]/'eval'/'whole_map_forecast'
    data=load_functional_sources(root/'measurement-orientation-v1'/'runs'/'63295cef2e45180b2845ee21cdef4b1523c9ad36225b9d312ed403cbc0c7869b')
    audit=json.loads((root/'functional-target-guard-v1'/'prepared-v2'/'audit.json').read_bytes())
    return (*data,audit)


def test_actual_source_certificates_keep_function_context_and_do_not_claim_in_vivo_effect(corpus):
    before=fingerprint(corpus);r=compile_guards(*corpus)
    assert fingerprint(corpus)==before and len(r['functional_certificates'])==2
    assert len(r['guarded_prototype']['body'])==3 and len(r['guarded_prototype']['certificates'])==3
    assert len(r['guarded_prototype']['primary_families'])==2
    assert not r['guarded_prototype']['is_executable_rule'] and not r['guarded_prototype']['clinical_conclusion_deductively_entailed']
    for p in r['functional_certificates']:
        assert p['structural_target_compatibility_supported'] and p['source_binding_and_inhibition_are_distinct']
        assert not p['in_vivo_target_engagement_established'] and not p['pure_antagonism_all_doses_established']
        assert not p['tnfr2_functional_preservation_established'] and not p['clinical_efficacy_inferred']
        assert p['extra_primary_clinical_replications']==0 and p['full_native_parents']
        assert p['functional_frame']['statements'][0]['scope']['conditions'] and p['original_functional_source_attributes']
    assert r['new_empirical_forecasts']==0 and not r['scientific_success'] and not r['graph_advantage_demonstrated']


@pytest.mark.parametrize('kind',['binding_only','wrong_function','alias','domain','model_missing','quote','origin','duplicate_case'])
def test_incomplete_or_forged_biological_guard_rejected(corpus,kind):
    orientation,frozen,maps,cases,base=corpus;audit=deepcopy(base);e=audit['entries'][0]
    if kind=='binding_only':e['evidence']=[x for x in e['evidence']if x['kind']!='inhibition']
    elif kind=='wrong_function':
        f=next(x for x in e['evidence']if x['kind']=='inhibition');f['quote']=deepcopy(next(x['quote']for x in e['evidence']if x['kind']=='binding'))
    elif kind=='alias':e['agent_alias']='Atrosimab'
    elif kind=='domain':e['model_target_domain']='mouse TNFR1'
    elif kind=='model_missing':e['evidence']=[x for x in e['evidence']if x['kind']!='model_domain']
    elif kind=='quote':e['evidence'][0]['quote']['text']+='!'
    elif kind=='origin':e['functional_origin']='own_report_with_unread_supplement'
    else:e['case_ids'].append(e['case_ids'][0])
    with pytest.raises(ArticleMapError):compile_guards(orientation,frozen,maps,cases,audit)


def test_compiled_target_is_fixed_and_agent_population_are_bound_to_the_same_prototype(corpus):
    r=compile_guards(*corpus);p=r['guarded_prototype'];state=p['body'][0]['statements'][0]
    roles={x['role']:x['value']for x in state['roles']};head={x['role']:x['value']for x in p['head']['statements'][0]['roles']}
    assert roles['required target domain']=={'constant':DOMAIN}
    assert roles['intervention']==head['intervention'] and roles['population']==head['population']
    assert not p['author_asserted_this_three_part_group'] and p['guard_was_added_by_compiler']


def test_assayed_release_inhibition_does_not_become_direct_receptor_inhibition(corpus):
    r=compile_guards(*corpus);p=next(p for p in r['functional_certificates']if 'pmc8294390'in p['article_id'])
    s=p['functional_frame']['statements'][0];roles={r['role']:r['value']for r in s['roles']}
    assert roles['outcome']=='interleukin 8 release' and roles['stimulus']=='tumor necrosis factor alpha'
    assert roles['assay population']=='HT1080 cells' and 'target' not in roles
    assert not p['in_vivo_target_engagement_established']


@pytest.mark.parametrize('change',['conditions','time','quantifier','causal_target','extra_participant','numeric_claim'])
def test_functional_frame_cannot_extend_its_source_claim(corpus,change):
    orientation,frozen,maps,cases,base=corpus;audit=deepcopy(base)
    e=next(e for e in audit['entries']if e['agent_alias']=='Atrosimab');s=e['functional_frame']['statements'][0]
    if change=='conditions':s['scope']['conditions']=['Clinical benefit demonstrates receptor blockade']
    elif change=='time':s['scope']['time']='Throughout all clinical follow-up'
    elif change=='quantifier':s['scope']['quantifier']='all mice at all doses'
    elif change=='causal_target':s['roles'].append({'role':'target','value':'human TNFR1','reference_kind':'concept'})
    elif change=='extra_participant':s['roles'].append({'role':'population','value':'all treated mice','reference_kind':'concept'})
    else:s['attributes'].append({'name':'in vivo receptor occupancy','value':'100','unit':'%'})
    with pytest.raises(ArticleMapError):compile_guards(orientation,frozen,maps,cases,audit)


def test_invalid_input_does_not_replace_sealed_result_and_identical_run_is_reused(corpus,tmp_path):
    from application.functional_target_guard import SealFunctionalTargetGuard
    from infrastructure.development_prediction_store import FilePredictionStore
    class Inputs:
        def __init__(self,data):self.data=data
        def load(self):return self.data
    inputs=Inputs(corpus);store=FilePredictionStore(tmp_path/'runs');service=SealFunctionalTargetGuard(inputs,store)
    first=service.execute({});path=store.path(first['run_id'])/'predictions.json';original=path.read_bytes()
    assert service.execute({})==first and path.read_bytes()==original
    bad=list(corpus);bad[-1]=deepcopy(bad[-1]);bad[-1]['entries'][0]['model_target_domain']='mouse TNFR1'
    inputs.data=tuple(bad)
    with pytest.raises(ArticleMapError):service.execute({})
    assert path.read_bytes()==original and len(list((tmp_path/'runs').glob('*/seal.json')))==1
