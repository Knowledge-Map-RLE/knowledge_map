"""Гипотеза аналогии сохраняет ограничения, составные родители и прошлые источники."""
from copy import deepcopy
from hashlib import sha256
import pytest

from domain.article_maps import ArticleMapError,fingerprint
from domain.mechanistic_opportunities import AUDIT_VERSION,generate,validate_audit
from tests.test_schema6_prediction import graph,ref


def fixture():
    m=graph('one',['Old intervention','Mouse disease model','Outcome','Target','New intervention','Counteracting intervention'])
    template=deepcopy(m['graph']['knowledge'][0]);m['graph']['knowledge']=[]
    predicates=['reduced_after_intervention','sequesters','pharmacokinetic_result','investigated_in','potential_treatment','exacerbated_after_intervention']
    text='Synthetic source: old intervention reduced outcome in mice; new intervention binds target and reaches brain. Its disease application is ongoing. Counteraction may worsen outcome.'
    m['source']={'text':text,'sha256':sha256(text.encode()).hexdigest(),'content_end':len(text),
                 'units':[{'id':'U1','start':0,'end':len(text),'text':text}]}
    for i,predicate in enumerate(predicates,1):
        k=deepcopy(template);k['knowledge_id']='K'+str(i);s=k['semantic_frame']['statements'][0]
        s.update(statement_id='S'+str(i),predicate=predicate,modality='ongoing; efficacy not yet established' if i==4 else 'potential' if i==5 else None)
        s['roles']=[{'role':'intervention','concept_id':'C0' if i==1 else 'C5' if i==6 else 'C4','knowledge_id':None},
                    {'role':'target','concept_id':'C3','knowledge_id':None}]
        m['graph']['knowledge'].append(k)
    # Две части остаются в составном родителе, хотя лицензируется один фактический результат.
    k=m['graph']['knowledge'][0];k['semantic_frame']['logic']='contrast'
    other=deepcopy(k['semantic_frame']['statements'][0]);other.update(statement_id='S1-opaque',predicate='associated_with')
    k['semantic_frame']['statements'].append(other)
    m['graph']['nodes']=[{'id':'B'+str(i),'knowledge_id':'K'+str(i)} for i in range(1,7)]
    m['graph']['transitions']=[{'sources':['B1','B2'],'target':'B5'}]
    m['graph']['edges']=[{'source':v,'target':'B5'} for v in ('B1','B2')]
    values={1:('effect',{'intervention':'old','target':'target','species':'mouse','disease':'disease',
                      'compartment':'brain','route':'intracerebroventricular','outcomes':[
                          {'entity':'target','direction':'decrease','text_ru':'Мишень'},
                          {'entity':'outcome','direction':'decrease','text_ru':'Исход'}]}),
            2:('target_action',{'intervention':'new','target':'target','species':'mouse','compartment':'brain','direction':'reduce_activity'}),
            3:('delivery',{'intervention':'new','species':'mouse','compartment':'brain','routes':['intravenous']}),
            4:('open_application',{'intervention':'new','species':'mouse','disease':'disease'}),
            6:('caution',{'text_ru':'Противодействующий механизм может отменить простой перенос.'})}
    entries=[]
    for i,(kind,value) in values.items():
        k=m['graph']['knowledge'][i-1];rows=[]
        for j,s in enumerate(k['semantic_frame']['statements']):
            rows.append({'statement_id':s['statement_id'],'reason_ru':'Синтетическая источниковая лицензия.',
                'facets':[] if j else [{'kind':kind,'concept_ids':['C3'],'values':value,
                    'reason_ru':'Синтетическое представление.','context_reason_ru':'Контекст синтетического опыта.'}]})
        entries.append({'article_id':'one','knowledge_id':k['knowledge_id'],'run_id':m['run_id'],
            'source_sha256':m['source']['sha256'],'graph_sha256':fingerprint(m['graph']),'knowledge_sha256':fingerprint(k),
            'reason_ru':'Синтетический родитель сохранён.','statements':rows,
            'evidence':[{'unit_id':'U1','start':0,'end':len(text),'text':text,'sha256':m['source']['sha256']}]})
    return m,{'version':AUDIT_VERSION,'author':'Codex','model_calls':0,'expert_validated':False,'entries':entries}


def rebind(m,a):
    for entry in a['entries']:
        entry['graph_sha256']=fingerprint(m['graph'])
        k=next(k for k in m['graph']['knowledge'] if k['knowledge_id']==entry['knowledge_id'])
        entry['knowledge_sha256']=fingerprint(k)


def test_analogy_generates_bounded_hypothesis_with_full_compound_parent_and_cautions():
    m,a=fixture();before=deepcopy(m);r=generate([m],a)
    assert m==before and r['canonical_blocks']==6 and r['statements']==7 and len(r['coverage'])==6
    assert len(r['candidates']['graph'])==len(r['candidates']['without_dependencies'])==1
    c=r['candidates']['graph'][0]
    assert c['conclusion']['expected_direction']=='decrease' and c['conclusion']['species']=='mouse'
    assert not c['logical_entailment'] and not c['causality_established'] and not r['scientific_success']
    assert len(c['premises'])==4 and c['cautions'] and c['conditions_ru']
    assert len(r['facet_proofs'][c['premises'][0]['facet_sha256']]['complete_parent_frame']['statements'])==2
    assert len(c['proof_graph']['nodes'])==6 and len(c['proof_graph']['edges'])==5
    assert r['diagnostics']['rejected']['target_activity_repeats_known_action']==1


@pytest.mark.parametrize('slot,field,value',[(0,'target','different'),(0,'species','human'),(0,'disease','different'),
    (0,'compartment','periphery'),(1,'intervention','different'),(2,'species','human'),(2,'compartment','periphery'),
    (2,'routes',['intracerebroventricular']),(3,'species','human'),(3,'disease','different')])
def test_incompatible_context_or_unestablished_delivery_abstains(slot,field,value):
    m,a=fixture();a['entries'][slot]['statements'][0]['facets'][0]['values'][field]=value
    assert not generate([m],a)['candidates']['without_dependencies']


def test_removing_graph_does_not_remove_semantic_hypothesis_or_assert_advantage():
    m,a=fixture();m['graph']['transitions']=[];m['graph']['edges']=[];rebind(m,a)
    r=generate([m],a);assert not r['candidates']['graph'] and len(r['candidates']['without_dependencies'])==1
    assert not r['graph_advantage_demonstrated']


def test_alternative_paths_do_not_become_a_joint_author_argument():
    m,a=fixture();m['graph']['transitions']=[{'sources':['B1'],'target':'B5'},{'sources':['B2'],'target':'B5'}];rebind(m,a)
    r=generate([m],a)
    assert len(r['candidates']['without_dependencies'])==1 and not r['candidates']['graph']


@pytest.mark.parametrize('case',['unknown_article','run','source','graph','parent','quote','coordinates','references',
    'partial_ledger','unknown_concept','unbound_concept','modal_result','negated_effect','performed_open',
    'unknown_field','unknown_kind','empty_context','argument','cycle','unknown_edge','model_call'])
def test_invalid_licenses_and_graphs_reject_entire_run(case):
    m,a=fixture();e=a['entries'][0];f=e['statements'][0]['facets'][0]
    if case=='unknown_article':e['article_id']='future-target'
    elif case=='run':e['run_id']='other'
    elif case=='source':e['source_sha256']='other'
    elif case=='graph':e['graph_sha256']='other'
    elif case=='parent':e['knowledge_sha256']='other'
    elif case=='quote':e['evidence'][0]['text']='other'
    elif case=='coordinates':e['evidence'][0]['start']=1
    elif case=='references':e['evidence'][0]['unit_id']='References'
    elif case=='partial_ledger':e['statements'].pop()
    elif case=='unknown_concept':f['concept_ids']=['missing']
    elif case=='unbound_concept':f['concept_ids']=['C2']
    elif case=='unknown_field':f['values']['imagined_context']='wrong'
    elif case=='unknown_kind':f['kind']='deductive_proof'
    elif case=='empty_context':f['values']['species']=''
    elif case=='model_call':a['model_calls']=1
    else:
        s=m['graph']['knowledge'][0]['semantic_frame']['statements'][0]
        if case=='modal_result':s['modality']='may'
        elif case=='negated_effect':s['negated']=True
        elif case=='performed_open':m['graph']['knowledge'][3]['semantic_frame']['statements'][0]['modality']=None
        elif case=='argument':m['graph']['knowledge'][0]['semantic_frame']['logic']='argument'
        elif case=='cycle':m['graph']['edges'].append({'source':'B5','target':'B1'})
        elif case=='unknown_edge':m['graph']['edges'].append({'source':'unknown','target':'B1'})
        rebind(m,a)
    with pytest.raises(ArticleMapError):generate([m],a)


def test_application_cannot_read_future_sources_and_preserves_immutable_run_on_error(tmp_path,monkeypatch):
    import socket
    from application.mechanistic_opportunities import SealMechanisticOpportunities
    from infrastructure.development_prediction_store import FilePredictionStore
    monkeypatch.setattr(socket,'create_connection',lambda *a,**k:(_ for _ in ()).throw(AssertionError('No network/model')))
    m,a=fixture();other=deepcopy(m);other.update(article_id='two',run_id='run-two')
    other['source']['text']+=' Independent synthetic source.';other['source']['sha256']=sha256(other['source']['text'].encode()).hexdigest()
    maps=[m,other];reads=[]
    class Port:
        def get(self,article,pipeline,owner,run):
            assert article!='future' and owner=='owner';reads.append(article)
            return next(m for m in maps if m['article_id']==article)
    app=SealMechanisticOpportunities(Port(),FilePredictionStore(tmp_path));refs=[ref('one'),ref('two')]
    metadata={'question':None,'training_cutoff':'2017-05-15','source_dates':{'one':'2016-01-01','two':'2016-02-01'}}
    r=app.execute(refs,{'one':'a','two':'b'},'owner',metadata,{'synthetic':'fixed'},a)
    assert r==app.execute(refs,{'one':'a','two':'b'},'owner',metadata,{'synthetic':'fixed'},a)
    broken=deepcopy(a);broken['entries'][0]['article_id']='future'
    with pytest.raises(ArticleMapError):app.execute(refs,{'one':'a','two':'b'},'owner',metadata,{'synthetic':'fixed'},broken)
    count=len(reads);future=deepcopy(metadata);future['source_dates']['two']='2018-01-01'
    with pytest.raises(ArticleMapError):app.execute(refs,{'one':'a','two':'b'},'owner',future,{'synthetic':'fixed'},a)
    assert len(reads)==count and len(list(tmp_path.glob('*/seal.json')))==1
