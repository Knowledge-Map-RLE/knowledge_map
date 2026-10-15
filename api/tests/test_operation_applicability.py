"""Контракты не склеивают режимы, неизвестности и независимость источников."""
from copy import deepcopy
from hashlib import sha256

import pytest

from domain.article_maps import fingerprint, ArticleMapError
from domain.operation_applicability import AXES, VERSION, analyze, compare_features
from domain.semantic_part_forecast import forecast_parts
from tests.test_schema6_prediction import graph, ref
from tests.test_semantic_part_forecast import prepare


def inputs():
    maps = [graph(a, ['drug '+a, 'mice '+a, 'unused']) for a in ['one','two','three']]
    for m in maps:
        m['graph']['concepts'].extend([{'id':'C3','display_text':'mog35-55-induced experimental autoimmune encephalomyelitis','aliases':[]},
            {'id':'C4','display_text':'eae clinical score','aliases':[]},
            {'id':'C5','display_text':'eae clinical progression','aliases':[]}])
        for i,k in enumerate(m['graph']['knowledge']):
            k['kind'] = 'action' if i < 2 else 'state';k['action_status'] = 'performed' if i < 2 else None
            s=k['semantic_frame']['statements'][0]
            s['predicate'] = ['administer treatment','measure clinical course','reduced after intervention'][i]
            ids=[('population','C1'),('challenge','C3')]
            if i!=1:ids.append(('intervention','C0'))
            if i:ids.append(('outcome','C4' if i==1 else 'C5'))
            s['roles']=[{'role':role,'concept_id':cid,'knowledge_id':None} for role,cid in ids]
            if i==0:s['qualifiers']['attributes']=[{'name':'dose','value':str(100+len(m['article_id'])),'unit':'microgram'}]
    maps,origin=prepare(maps)
    for source in origin['sources']:
        for k in source['knowledge']:
            if k['knowledge_id'] in {'K1','K2'}:
                for s in k['statements']:s['origin']='primary_method'
    result=forecast_parts(maps,{m['article_id']:m['article_id'] for m in maps},None,None,origin)
    binding={'references':[ref(m['article_id']) for m in maps]};result['binding']=binding;result['run_id']=fingerprint(binding)
    cases=[]
    for i,m in enumerate(maps):
        def v(kid):return next(v for v in result['part_views'] if v['native_key']==(m['article_id'],kid))
        u=m['source']['units'][0];e={'unit_id':'U1','start':u['start'],'end':u['end'],'text':u['text'],
            'sha256':sha256(u['text'].encode()).hexdigest(),'source_asserts_feature':True}
        features=dict(zip(AXES,['mouse','mog35_55_induced_eae','human_tnfr1','selective_inhibition','ip',
                               'manifest_disease' if i<2 else 'prophylactic','clinical_score']))
        cases.append({'id':m['article_id'],'method':v('K1')['key'],'measurement':v('K2')['key'],'result':v('K3')['key'],
            'basis':[[m['article_id'],k['knowledge_id']] for k in m['graph']['knowledge']],
            'source_sha256':m['source']['sha256'],'graph_sha256':fingerprint(m['graph']),
            'features':features,'feature_evidence':{axis:[deepcopy(e)] for axis in AXES},
            'outcome_class':'clinical_eae_burden','qualitative_direction':'lower_clinical_burden','direction_evidence':[deepcopy(e)],
            'reason_ru':'Синтетический контракт проверки, не научные данные.'})
    audit={'version':VERSION,'author':'Codex','model_calls':0,'expert_validated':False,
        'input_run_id':result['run_id'],'input_sha256':fingerprint(result),'cases':cases}
    return result,maps,origin,audit


def test_separates_phase_and_preserves_every_full_part_and_native_parent():
    values=inputs();before=deepcopy(values);r=analyze(*values)
    assert values==before and r['new_predictions']==0 and not r['scientific_success']
    supported=[s for s in r['schemata'] if s['minimum_primary_support']]
    assert len(supported)==1 and len(supported[0]['primary_families'])==2
    assert supported[0]['case_ids']==['one','two']
    assert not supported[0]['valid_universal_rule'] and not supported[0]['new_prediction']
    assert not r['graph_advantage_demonstrated']
    for c in r['cases']:
        for field in ('method','measurement','result'):
            original=next(v for v in values[0]['part_views'] if v['key']==c[field]['key'])
            assert original==c[field]
        assert c['scope_and_numbers_retained'] and not c['claims_experimental_equivalence']
    assert r['coverage']['contract_views']==9
    assert [c['different'] for c in r['comparisons']]==[[],['phase'],['phase']]


@pytest.mark.parametrize('axis',AXES)
def test_unknown_is_not_a_wildcard_and_known_difference_blocks_merge(axis):
    features=inputs()[-1]['cases'][0]['features']
    unknown=deepcopy(features);unknown[axis]=None
    assert compare_features(unknown,unknown)['unknown']==[axis]
    assert not compare_features(features,unknown)['applicable']
    different=deepcopy(features);different[axis]='different'
    assert compare_features(features,different)['different']==[axis]


def test_unknown_case_remains_visible_but_does_not_supply_support():
    values=inputs();c=values[-1]['cases'][1];c['features']['target']=None;c['feature_evidence']['target']=[]
    r=analyze(*values)
    assert not any(s['minimum_primary_support'] for s in r['schemata'])
    assert r['coverage']['unknown_contract_axes']==1 and len(r['cases'])==3


def test_same_dataset_does_not_become_two_independent_supports():
    values=inputs()
    for s in values[2]['sources']:s['dataset_family']='one dataset'
    assert not any(s['minimum_primary_support'] for s in analyze(*values)['schemata'])


@pytest.mark.parametrize('case',['input_run','input_sha','model','source','graph','quote','quote_hash','unit','outside',
    'not_asserted','missing_evidence','basis','repeated','phase','modal','negative','planned','origin','family',
    'measurement','intervention','outcome','group','direction','direction_quote','repeated_role'])
def test_unlicensed_contract_rejects_entire_analysis(case):
    values=inputs();forecast,maps,origin,audit=values;c=audit['cases'][0]
    method=next(v for v in forecast['part_views'] if v['key']==c['method'])
    measurement=next(v for v in forecast['part_views'] if v['key']==c['measurement'])
    result=next(v for v in forecast['part_views'] if v['key']==c['result'])
    if case=='input_run':audit['input_run_id']='other'
    elif case=='input_sha':audit['input_sha256']='other'
    elif case=='model':audit['model_calls']=1
    elif case=='source':c['source_sha256']='other'
    elif case=='graph':c['graph_sha256']='other'
    elif case=='quote':c['feature_evidence']['phase'][0]['text']='invented'
    elif case=='quote_hash':c['feature_evidence']['phase'][0]['sha256']='other'
    elif case=='unit':c['feature_evidence']['phase'][0]['unit_id']='missing'
    elif case=='outside':c['feature_evidence']['phase'][0]['end']+=1
    elif case=='not_asserted':c['feature_evidence']['phase'][0]['source_asserts_feature']=False
    elif case=='missing_evidence':c['feature_evidence']['phase']=[]
    elif case=='basis':c['basis'][0][0]='two'
    elif case=='repeated':audit['cases'].append(deepcopy(c))
    elif case=='phase':c['features']['phase']='at some time'
    elif case=='modal':method['frame']['statements'][0]['scope']['modality']='may'
    elif case=='negative':method['frame']['statements'][0]['negated']=True
    elif case=='planned':method['frame']['action_status']='planned'
    elif case=='origin':method['projection_proof']['origin']['origin']='cited_method'
    elif case=='family':origin['sources'][0]['dataset_family']=None
    elif case=='measurement':next(r for r in measurement['frame']['statements'][0]['roles'] if r['role']=='population')['value']='unrelated group'
    elif case=='intervention':next(r for r in result['frame']['statements'][0]['roles'] if r['role']=='intervention')['value']='another drug'
    elif case=='outcome':c['outcome_class']='all biomarker outcomes'
    elif case=='group':c['measurement']=c['method']
    elif case=='direction':c['qualitative_direction']='lower p value'
    elif case=='direction_quote':c['direction_evidence']=[]
    elif case=='repeated_role':measurement['frame']['statements'][0]['roles'].append(deepcopy(measurement['frame']['statements'][0]['roles'][0]))
    for v in [method,measurement,result]:v['projection_proof']['view_frame_sha256']=fingerprint(v['frame'])
    if case not in {'input_sha','input_run','model'}:audit['input_sha256']=fingerprint(forecast)
    with pytest.raises((ArticleMapError,KeyError)):analyze(*values)


def test_application_seals_replay_and_error_without_models(tmp_path,monkeypatch):
    import socket
    import httpx
    from application.operation_applicability import SealOperationApplicability
    from infrastructure.development_prediction_store import FilePredictionStore
    monkeypatch.setattr(socket,'create_connection',lambda *a,**k:pytest.fail('No network'))
    monkeypatch.setattr(httpx.Client,'send',lambda *a,**k:pytest.fail('No model calls'))
    forecast,maps,origin,audit=inputs()
    class Port:
        def load(self):return forecast,maps,origin
    app=SealOperationApplicability(Port(),FilePredictionStore(tmp_path))
    a=app.execute(audit,{'code':'fixed'});assert a==app.execute(audit,{'code':'fixed'})
    b=deepcopy(audit);b['cases'][0]['features']['target']=None;b['cases'][0]['feature_evidence']['target']=[]
    assert app.execute(b,{'code':'fixed'})['run_id']!=a['run_id']
    assert len(list(tmp_path.glob('*/seal.json')))==2
    bad=deepcopy(audit);bad['cases'][0]['direction_evidence']=[]
    with pytest.raises(ArticleMapError):app.execute(bad,{'code':'fixed'})
    assert len(list(tmp_path.glob('*/seal.json')))==2
