"""Ручная полная карта проверяется общим контрактом без сетевой генерации."""
from copy import deepcopy
import json
import pytest
import httpx
from domain.article_maps import digest, prepare_source, ArticleMapError
from application.prepare_manual_research_map import prepare_manual_map
from application.text_to_development_map import PROMPT_PATH,DEPENDENCY_PROMPT_PATH

TEXT='# Source title\n\nAlpha may not change under every stated condition.\n\nApply the alpha method to check the unresolved outcome.\n\n## References\n\n1. Reference preserved only in source.\n'

def authored():
    return {'complete_source_reviewed':True,'complete_semantic_coverage':True,'table_cells_exhaustively_formalized':False,
        'excluded_units':{'U1':'Заголовок источника.'},'transitions':[],
        'knowledge':[{'key':'first','units':['U2'],'en':'Alpha may not change under every stated condition.',
            'ru':'Альфа может не изменяться при каждом заданном условии.','predicate':'changes','roles':{'subject':'Alpha'},
            'modality':'may','quantifier':'every','negated':True,'time':'stated condition'},
            {'key':'second','units':['U3'],'en':'Apply the alpha method to check the unresolved outcome.',
             'ru':'Применить метод альфа для проверки нерешённого исхода.','predicate':'apply method','roles':{'method':'alpha'},
             'kind':'action','status':'unresolved','time':'future test'}]}

def prepare(a=None,text=TEXT,sha=None):
    return prepare_manual_map('test-source',text,sha or digest(text),a or authored(),
        PROMPT_PATH.read_text(encoding='utf-8'),DEPENDENCY_PROMPT_PATH.read_text(encoding='utf-8'))

def test_manual_map_has_no_model_transport_and_is_reproducible(monkeypatch):
    def forbidden(*args,**kwargs): raise AssertionError('Transport forbidden')
    monkeypatch.setattr(httpx.Client,'request',forbidden)
    monkeypatch.setattr(httpx.AsyncClient,'request',forbidden)
    a=authored();before=deepcopy(a);artifacts=prepare(a)
    assert a==before and artifacts==prepare(a)
    result=artifacts['map.json'];assert result['generation']['external_llm_calls']==0
    assert result['generation']['local_llm_calls']==0 and result['generation']['translation_llm_calls']==0
    assert len(result['graph']['concepts'])==1
    first,second=result['graph']['knowledge']
    assert first['semantic_frame']['statements'][0]['negated'] is True
    assert first['semantic_frame']['statements'][0]['quantifier']=='every'
    assert second['action_status']=='unresolved' and not result['graph']['edges']
    assert artifacts['coverage.json']['complete_semantic_coverage']
    assert result['translations']['ru']['run_id']==result['run_id']

def test_source_hash_checked_before_preparation():
    with pytest.raises(ArticleMapError,match='hash'):prepare(sha='incorrect')

def test_incomplete_or_ambiguous_coverage_is_rejected():
    a=authored();a['knowledge'].pop()
    with pytest.raises(ArticleMapError,match='coverage'):prepare(a)
    a=authored();a['excluded_units']['U2']='Исключено одновременно с представленным.'
    with pytest.raises(ArticleMapError,match='coverage'):prepare(a)

def test_unknown_role_reference_is_rejected():
    a=authored();a['knowledge'][0]['roles']['object']='@absent'
    with pytest.raises(ArticleMapError,match='Unknown manual'):prepare(a)

def test_hidden_cycle_does_not_create_visible_edges():
    a=authored();a['knowledge'][0]['roles']['other']='@second';a['knowledge'][1]['roles']['other']='@first'
    graph=prepare(a)['map.json']['graph']
    assert graph['edges']==[] and len(graph['knowledge'])==2

def test_visible_cycle_rejected_before_artifacts_returned():
    a=authored();a['transitions']=[{'sources':['first'],'target':'second','usage':'premise','reason':'Source stated use.','units':['U3']},
        {'sources':['second'],'target':'first','usage':'premise','reason':'Source stated use.','units':['U2']}]
    with pytest.raises(ArticleMapError,match='cycle|DAG'):prepare(a)

def test_dependency_requests_cover_every_target_and_preserve_full_source():
    a=authored();a['transitions']=[{'sources':['first'],'target':'second','usage':'premise','reason':'The source uses the stated condition for the action.','units':['U3']}]
    artifacts=prepare(a)
    assert artifacts['dependency-groups.json'][0]['targets']==['K1','K2']
    request=artifacts['dependencies.1.request.json']['user']
    payload=json.loads(request)
    source=artifacts['map.json']['source']
    assert payload['article_text']==TEXT[:source['content_end']]
    assert payload['source_units']==source['units']
    assert 'Reference preserved' not in payload['article_text']
    assert len(artifacts['map.json']['graph']['transitions'])==1
    assert artifacts['map.json']['source']['text']==TEXT


def test_missing_references_boundary_is_rejected_explicitly():
    with pytest.raises(ArticleMapError,match='References boundary'):
        prepare(text=TEXT.split('## References')[0])
