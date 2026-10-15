"""Пересказ, интерпретация и повтор той же когорты не дают независимых данных."""
from copy import deepcopy
from hashlib import sha256

import pytest

from domain.article_maps import ArticleMapError, fingerprint
from domain.evidence_origin_audit import VERSION, audit_rule_support, validate_origins


def fixture(article='A', family='cohort', document='primary_study', origin='primary_result'):
    text='Methods and results\nReferences'
    unit={'id':'U1','start':0,'end':19,'text':text[:19]}
    knowledge={'knowledge_id':'K1','semantic_frame':{'statements':[
        {'statement_id':'S1','provenance':{'unit_ids':['U1']}},
        {'statement_id':'S2','provenance':{'unit_ids':['U1']}}]}}
    m={'article_id':article,'run_id':'R','source':{'text':text,'sha256':sha256(text.encode()).hexdigest(),
        'content_end':19,'units':[unit]},'graph':{'knowledge':[knowledge]}}
    record={'article_id':article,'run_id':'R','source_sha256':m['source']['sha256'],
        'graph_sha256':fingerprint(m['graph']),'document_kind':document,'dataset_family':family,
        'reason_ru':'Тип документа и источник данных проверены отдельно.',
        'evidence':[{'unit_id':'U1','start':0,'end':19,'text':unit['text'],'sha256':sha256(unit['text'].encode()).hexdigest()}],
        'knowledge':[{'knowledge_id':'K1','knowledge_sha256':fingerprint(knowledge),
            'statements':[{'statement_id':sid,'origin':origin,'reason_ru':'Результат указан в источнике.',
                           'evidence_unit_ids':['U1']} for sid in ('S1','S2')]}]}
    return m,record


def audit(records):
    return {'version':VERSION,'author':'Codex','model_calls':0,'expert_validated':False,'sources':records}


def rule(articles):
    return {'id':'rule','families':articles,'examples':[{'head':[a,'K1'],'body':[]} for a in articles]}


def test_repeated_cohort_and_review_cannot_be_three_independent_observations():
    a,ra=fixture('A');b,rb=fixture('B');c,rc=fixture('C',None,'systematic_review','cited_result')
    index=validate_origins([a,b,c],audit([ra,rb,rc]))
    row=audit_rule_support([rule(['A','B','C'])],index)['rules'][0]
    assert row['declared_primary_dataset_families']==['cohort']
    assert row['secondary_sources']==['C'] and not row['two_primary_families_declared']
    assert not row['logical_entailment_established']


def test_two_declared_datasets_are_counted_but_not_certified_as_logical_proof():
    a,ra=fixture('A','first');b,rb=fixture('B','second')
    row=audit_rule_support([rule(['A','B'])],validate_origins([a,b],audit([ra,rb])))['rules'][0]
    assert row['two_primary_families_declared'] and not row['expert_validated']
    assert not row['logical_entailment_established']


@pytest.mark.parametrize('origin',['primary_interpretation','primary_method','parent_cohort_report',
    'background','definition','research_task','proposed_application','mixed_origin','unresolved_origin'])
def test_nonempirical_conclusions_do_not_vote_as_primary_results(origin):
    m,r=fixture(origin=origin)
    row=audit_rule_support([rule(['A'])],validate_origins([m],audit([r])))['rules'][0]
    assert row['declared_primary_dataset_families']==[]


def test_mixed_compound_frame_not_reduced_to_its_primary_part():
    m,r=fixture();r['knowledge'][0]['statements'][1]['origin']='cited_result'
    row=audit_rule_support([rule(['A'])],validate_origins([m],audit([r])))['rules'][0]
    assert not row['declared_primary_dataset_families'] and row['secondary_sources']==['A']


@pytest.mark.parametrize('case',['unknown_source','stale_run','stale_graph','stale_knowledge','stale_text',
    'missing_statement','reordered_statements','missing_knowledge','missing_source','duplicated_source',
    'duplicated_knowledge','changed_evidence','outside_content','missing_evidence','duplicated_evidence',
    'unknown_origin','no_reason','no_family','review_with_family','review_as_primary','model_calls'])
def test_bad_bindings_and_partial_coverage_fail_closed(case):
    m,r=fixture();a=audit([r]);k=r['knowledge'][0]
    if case=='unknown_source':r['article_id']='target'
    elif case=='stale_run':r['run_id']='other'
    elif case=='stale_graph':r['graph_sha256']='changed'
    elif case=='stale_knowledge':k['knowledge_sha256']='changed'
    elif case=='stale_text':m['source']['text']='different'
    elif case=='missing_statement':k['statements'].pop()
    elif case=='reordered_statements':k['statements'].reverse()
    elif case=='missing_knowledge':r['knowledge']=[]
    elif case=='missing_source':a['sources']=[]
    elif case=='duplicated_source':a['sources'].append(deepcopy(r))
    elif case=='duplicated_knowledge':r['knowledge'].append(deepcopy(k))
    elif case=='changed_evidence':r['evidence'][0]['text']='different'
    elif case=='outside_content':m['source']['content_end']=5
    elif case=='missing_evidence':r['evidence']=[]
    elif case=='duplicated_evidence':k['statements'][0]['evidence_unit_ids'].append('U1')
    elif case=='unknown_origin':k['statements'][0]['origin']='invented'
    elif case=='no_reason':k['statements'][0]['reason_ru']=''
    elif case=='no_family':r['dataset_family']=None
    elif case=='review_with_family':r['document_kind']='systematic_review'
    elif case=='review_as_primary':r.update(document_kind='systematic_review',dataset_family=None)
    elif case=='model_calls':a['model_calls']=1
    with pytest.raises(ArticleMapError):validate_origins([m],a)


def test_optional_audit_is_explicitly_unaudited():
    assert validate_origins([],None) is None
    assert audit_rule_support([],None)['status']=='not_audited'


def test_application_seals_audit_version_separately_and_rejects_invalid_before_publish(tmp_path,monkeypatch):
    import socket
    from application.whole_map_forecast import SealWholeMapForecast
    from infrastructure.development_prediction_store import FilePredictionStore
    from tests.test_whole_map_forecast import corpus,families
    from tests.test_schema6_prediction import ref

    def forbidden(*args,**kwargs):raise AssertionError('Network or model transport forbidden')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    maps=corpus();records=[]
    for m in maps:
        text='Synthetic source '+m['article_id'];digest=sha256(text.encode()).hexdigest()
        m['source']={'text':text,'sha256':digest,'content_end':len(text),
                     'units':[{'id':'U1','start':0,'end':len(text),'text':text}]}
        records.append({'article_id':m['article_id'],'run_id':m['run_id'],'source_sha256':digest,
            'graph_sha256':fingerprint(m['graph']),'document_kind':'primary_study',
            'dataset_family':'one-shared-cohort','reason_ru':'Синтетическая проверка учёта источников.',
            'evidence':[{'unit_id':'U1','start':0,'end':len(text),'text':text,'sha256':digest}],
            'knowledge':[{'knowledge_id':k['knowledge_id'],'knowledge_sha256':fingerprint(k),
                'statements':[{'statement_id':s['statement_id'],'origin':'primary_result',
                    'reason_ru':'Синтетическая проверка, не научный результат.', 'evidence_unit_ids':['U1']}
                    for s in k['semantic_frame']['statements']]} for k in m['graph']['knowledge']]})
    origin=audit(records);reads=[]
    class Port:
        def get(self,article,pipeline,owner,run):
            assert owner=='owner' and article!='target';reads.append(article)
            return next(m for m in maps if m['article_id']==article)
    app=SealWholeMapForecast(Port(),FilePredictionStore(tmp_path))
    arguments=([ref(m['article_id']) for m in maps],families(maps),'owner',
        {'question':None,'training_cutoff':'2023-12-31','source_dates':{m['article_id']:'2022-01-01' for m in maps}},
        {'synthetic_implementation':'fixed'})
    before=deepcopy(maps)
    base=app.execute(*arguments);checked=app.execute(*arguments,origin_audit=origin)
    assert base['run_id']!=checked['run_id'] and base['predictions']==checked['predictions']
    assert checked==app.execute(*arguments,origin_audit=origin) and maps==before
    rows=checked['evidence_origin_support']['supported_rules']['rules']
    assert rows and all(r['declared_primary_dataset_families']==['one-shared-cohort'] for r in rows)
    assert not any(r['two_primary_families_declared'] for r in rows)
    broken=deepcopy(origin);broken['sources'][0]['article_id']='target'
    with pytest.raises(ArticleMapError):app.execute(*arguments,origin_audit=broken)
    assert len(list(tmp_path.glob('*/seal.json')))==2 and set(reads)=={'one','two','three'}
