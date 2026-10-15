"""Лицензирование определений не превращает клинический риск в универсальный закон."""
from copy import deepcopy
from hashlib import sha256

import pytest

from domain.article_maps import ArticleMapError,fingerprint
from domain.categorical_licenses import VERSION,validate_licenses,licensed_inference
from domain.whole_map_forecast import project
from tests.test_schema6_prediction import graph


def fixture():
    m=graph('one',['M','S','F']);text='M does not interfere with F, with risk reported separately. S is a subtype of M.'
    m['source']={'text':text,'sha256':sha256(text.encode()).hexdigest(),'content_end':len(text),
                 'units':[{'id':'U1','start':0,'end':len(text),'text':text}]}
    k1,k2,k3=m['graph']['knowledge']
    for k in (k1,k2):k['knowledge_kind']='definition'
    s=k1['semantic_frame']['statements'][0];s.update(predicate='interferes_with',negated=True)
    s['roles']=[{'role':'subject','concept_id':'C0','knowledge_id':None},{'role':'function','concept_id':'C2','knowledge_id':None}]
    risk=deepcopy(s);risk.update(statement_id='S-risk',predicate='associated_with_increased_risk',negated=False)
    k1['semantic_frame']['logic']='conjunction';k1['semantic_frame']['statements'].append(risk)
    s=k2['semantic_frame']['statements'][0];s['predicate']='subtype_of'
    s['roles']=[{'role':'subtype','concept_id':'C1','knowledge_id':None},{'role':'class','concept_id':'C0','knowledge_id':None}]
    scope={'study_group':'one','time':None,'conditions':['definitions as stated in source; not all real patients'],'modality':None}
    def concept(cid):
        return {'id':'one::concept:'+cid,'local_id':'concept:'+cid,'kind':'concept','concept_id':cid,
                'text_en':cid,'text_ru':'Класс '+cid}
    prop={'id':'one::property:interferes_with:C2','local_id':'property:interferes_with:C2',
          'kind':'property','predicate':'interferes_with','object_concept_id':'C2','text_en':'interference with F','text_ru':'Нарушение F'}
    entries=[]
    for k in (k1,k2):
        annotations=[]
        for part in k['semantic_frame']['statements']:
            if part['statement_id']=='S-risk':
                annotations.append({'statement_id':part['statement_id'],'decision':'retain_unconverted','clause':None,'reason_ru':'Риск не является категорическим законом.'});continue
            bindings={'subject':concept('C0' if k is k1 else 'C1'),'object':prop if k is k1 else concept('C0')}
            annotations.append({'statement_id':part['statement_id'],'decision':'license_definition',
                'license_kind':'definition_requirement' if k is k1 else 'subtype_inclusion','bindings':bindings,
                'clause':{'form':'E' if k is k1 else 'A','subject':bindings['subject']['id'],'object':bindings['object']['id'],'scope':scope},
                'reason_ru':'Определение и подтип имеют локальную область источника.'})
        entries.append({'article_id':'one','run_id':m['run_id'],'knowledge_id':k['knowledge_id'],
            'source_sha256':m['source']['sha256'],'graph_sha256':fingerprint(m['graph']),'knowledge_sha256':fingerprint(k),
            'scope':scope,'scope_reason_ru':'Условный класс определения, не наблюдения популяции.','reason_ru':'Синтетическая проверка механизма.',
            'statements':annotations,'evidence':[{'unit_id':'U1','start':0,'end':len(text),'text':text,'sha256':m['source']['sha256']}]})
    return m,{'version':VERSION,'author':'Codex','model_calls':0,'expert_validated':False,'entries':entries}


def test_source_definition_produces_conditional_consequence_with_entire_parent_and_native_references():
    m,a=fixture();before=deepcopy(m);records,groups,_=project([m])
    result=licensed_inference([m],records,groups,a)
    assert m==before and result['original_canonical_blocks']==3 and result['licensed_parent_blocks']==2
    assert result['licensed_views']==2 and len(result['license_proofs'][0]['complete_parent_frame']['statements'])==2
    candidates=result['consequences']['without_dependencies'];assert len(candidates)==1
    c=candidates[0];assert c['conclusion']['form']=='E' and not c['novel_empirical_prediction']
    assert c['proof']['entailed'] and not c['proof']['existence_conditions']
    assert {p['knowledge_id'] for p in c['premises']}=={'K1','K2'}
    assert all(p['statement_id'] and p['view_id'] and p['license_proof_sha256'] for p in c['premises'])
    assert all(n['knowledge_id'] in {'K1','K2'} for n in c['proof_graph']['nodes'][:2])
    assert result['consequences']['graph']==candidates and not result['graph_advantage_demonstrated']


@pytest.mark.parametrize('case',['target','run','source','source_text','graph','knowledge','quote','coordinates',
    'references','partial_ledger','reorder','unrelated_evidence','duplicate_entry','scope','class_id','class_meaning',
    'concept','property','subtype','negation','modality','partial_quantifier','existence','association','model_calls','action'])
def test_tampered_or_unlicensed_definitions_fail_closed(case):
    m,a=fixture();e=a['entries'][0];s=e['statements'][0]
    if case=='target':e['article_id']='target'
    elif case=='run':e['run_id']='other'
    elif case=='source':e['source_sha256']='changed'
    elif case=='source_text':m['source']['text']='changed'
    elif case=='graph':e['graph_sha256']='changed'
    elif case=='knowledge':e['knowledge_sha256']='changed'
    elif case=='quote':e['evidence'][0]['text']='changed'
    elif case=='coordinates':e['evidence'][0]['start']=1
    elif case=='references':m['source']['content_end']=3
    elif case=='partial_ledger':e['statements'].pop()
    elif case=='reorder':e['statements'].reverse()
    elif case=='unrelated_evidence':e['evidence'][0]['unit_id']='References'
    elif case=='duplicate_entry':a['entries'].append(deepcopy(e))
    elif case=='scope':e['scope']['study_group']='different-study'
    elif case=='class_id':s['bindings']['subject']['id']='global-M'
    elif case=='class_meaning':a['entries'][1]['statements'][0]['bindings']['object']['text_en']='another definition'
    elif case=='concept':s['bindings']['subject']['concept_id']='missing'
    elif case=='property':s['bindings']['object']['object_concept_id']='C1'
    elif case=='subtype':a['entries'][1]['statements'][0]['bindings']['subject']['concept_id']='C0'
    elif case=='negation':s['clause']['form']='A'
    elif case=='existence':s['clause']['form']='I'
    elif case=='model_calls':a['model_calls']=1
    else:
        k=m['graph']['knowledge'][0];native=k['semantic_frame']['statements'][0]
        if case=='modality':native['modality']='may'
        elif case=='partial_quantifier':native['quantifier']='most'
        elif case=='association':native['predicate']='associated_with'
        elif case=='action':k['kind']='action'
        for entry in a['entries']:entry['graph_sha256']=fingerprint(m['graph'])
        e['knowledge_sha256']=fingerprint(k)
    with pytest.raises(ArticleMapError):validate_licenses([m],a)


def test_opaque_parts_cannot_be_smuggled_into_a_published_clause():
    m,a=fixture();a['entries'][0]['statements'][1]['clause']=deepcopy(a['entries'][0]['statements'][0]['clause'])
    with pytest.raises(ArticleMapError):validate_licenses([m],a)


def test_unknown_original_context_and_view_collision_are_not_overridden():
    m,a=fixture();records,groups,_=project([m]);records['one','K1']['eligible']=False
    with pytest.raises(ArticleMapError):licensed_inference([m],records,groups,a)
    records,groups,_=project([m]);records['one','K1@S1']=deepcopy(records['one','K1'])
    with pytest.raises(ArticleMapError):licensed_inference([m],records,groups,a)


def test_missing_license_is_explicit_and_does_not_create_an_ai_client():
    assert licensed_inference([],{},[],None)['status']=='not_supplied'


def contrast_fixture():
    m, old = fixture(); k = m['graph']['knowledge'][0]
    first, second = k['semantic_frame']['statements']
    for statement, cid, negated in ((first, 'C0', False), (second, 'C1', True)):
        statement.update(predicate='has_death_domain', negated=negated, conditions=[], temporal_context=None)
        statement['roles'] = [{'role': 'subject', 'concept_id': cid, 'knowledge_id': None}]
        statement['qualifiers'] = {'attributes': []}
    k['semantic_frame']['logic'] = 'contrast'
    constraints = {'roles': [], 'attributes': [], 'conditions': [], 'temporal_context': None}
    scope = deepcopy(old['entries'][0]['scope'])
    scope['conditions'].append('native_definition_constraints_sha256:' + fingerprint(constraints))
    property_ = {'kind': 'unary_property', 'predicate': 'has_death_domain', 'native_constraints': constraints,
        'local_id': 'unary_property:has_death_domain:' + fingerprint(constraints),
        'text_en': 'Structures with domain', 'text_ru': 'Структуры с доменом'}
    property_['id'] = 'one::' + property_['local_id']
    entry = deepcopy(old['entries'][0]); entry.update(scope=scope, independent_contrast_parts=True,
        independence_reason_ru='Два самостоятельных синтетических структурных описания.', shared_native_constraints=constraints,
        graph_sha256=fingerprint(m['graph']), knowledge_sha256=fingerprint(k))
    entry['statements'] = []
    for statement in k['semantic_frame']['statements']:
        cid = statement['roles'][0]['concept_id']
        subject = {'kind': 'concept', 'concept_id': cid, 'id': 'one::concept:' + cid,
            'local_id': 'concept:' + cid, 'text_en': cid, 'text_ru': 'Класс ' + cid}
        entry['statements'].append({'statement_id': statement['statement_id'], 'decision': 'license_definition',
            'license_kind': 'unary_definition_requirement', 'native_constraints': deepcopy(constraints),
            'bindings': {'subject': subject, 'object': deepcopy(property_)},
            'clause': {'form': 'E' if statement['negated'] else 'A', 'subject': subject['id'],
                'object': property_['id'], 'scope': deepcopy(scope)}, 'reason_ru': 'Проверка типа и отрицания.'})
    return m, {**old, 'version': VERSION, 'entries': [entry]}


def test_independently_asserted_contrast_preserves_parent_and_yields_disjointness():
    m, audit = contrast_fixture(); before = deepcopy(m)
    records, groups, _ = project([m]); result = licensed_inference([m], records, groups, audit)
    assert m == before and result['licensed_views'] == 2 and result['licensed_parent_blocks'] == 1
    conclusions = result['consequences']['without_dependencies']; assert len(conclusions) == 1
    head = conclusions[0]['conclusion']
    assert head['form'] == 'E' and {head['subject'], head['object']} == {'one::concept:C0', 'one::concept:C1'}
    assert conclusions[0]['proof']['entailed'] and not conclusions[0]['novel_empirical_prediction']
    assert {p['knowledge_id'] for p in conclusions[0]['premises']} == {'K1'}
    assert len(result['license_proofs'][0]['complete_parent_frame']['statements']) == 2
    assert result['license_proofs'][0]['parent_logic'] == 'contrast'


def test_explicit_whicap_exclusion_and_subtype_use_single_edge_as_eae_premises():
    m,a=fixture();k1,k2=m['graph']['knowledge'][:2]
    source_text='At the WHICAP consensus visit, MCI requires no dementia diagnosis. S is a WHICAP MCI subtype.'
    m['source']['text']=source_text;m['source']['sha256']=sha256(source_text.encode()).hexdigest()
    m['source']['content_end']=len(source_text)
    m['source']['units']=[{'id':'U1','start':0,'end':len(source_text),'text':source_text}]
    m['graph']['concepts'].append({'id':'C3','display_text':'WHICAP','aliases':[],'provenance':{'unit_ids':['U1'],'source_spans':[]}})
    exclusion=k1['semantic_frame']['statements'][0]
    exclusion.update(predicate='excludes dementia diagnosis',negated=False,quantifier='all',
                     temporal_context='WHICAP consensus visit')
    exclusion['roles']=[{'role':'cohort','concept_id':'C3','knowledge_id':None},
                        {'role':'classification','concept_id':'C0','knowledge_id':None},
                        {'role':'criterion','concept_id':'C2','knowledge_id':None}]
    inclusion=k2['semantic_frame']['statements'][0]
    inclusion['predicate']='subtype_of';inclusion['quantifier']='all';inclusion['temporal_context']='WHICAP consensus visit'
    inclusion['roles']=[{'role':'subtype','concept_id':'C1','knowledge_id':None},
                        {'role':'subject','concept_id':'C1','knowledge_id':None},
                        {'role':'class','concept_id':'C0','knowledge_id':None}]
    k1['knowledge_kind']=k2['knowledge_kind']='definition'
    m['graph']['transitions']=[{'sources':['B1'],'target':'B2'}]
    scope={'study_group':'one','time':'WHICAP consensus visit','conditions':['WHICAP operational MCI definition at the same consensus visit'],'modality':None}
    def concept(cid,text):
        return {'id':'one::concept:'+cid,'local_id':'concept:'+cid,'kind':'concept','concept_id':cid,
                'text_en':text,'text_ru':'Локальный класс '+cid}
    bindings1={'subject':concept('C0','WHICAP MCI'),
               'object':concept('C2','Participants diagnosed with dementia at the WHICAP consensus visit')}
    bindings2={'subject':concept('C1','WHICAP MCI subtype S'),'object':concept('C0','WHICAP MCI')}
    def quote():
        return {'unit_id':'U1','start':0,'end':len(source_text),'text':source_text,'sha256':m['source']['sha256']}
    a={'version':VERSION,'author':'Codex','model_calls':0,'expert_validated':False,'entries':[
        {'article_id':'one','run_id':m['run_id'],'source_sha256':m['source']['sha256'],'graph_sha256':fingerprint(m['graph']),
         'knowledge_id':'K1','knowledge_sha256':fingerprint(k1),'scope':scope,
         'scope_reason_ru':'Только операционное определение WHICAP на той же согласительной диагностической оценке.',
         'reason_ru':'Проверено точное исключение диагноза деменции из WHICAP MCI.', 'evidence':[quote()],
         'statements':[{'statement_id':exclusion['statement_id'],'decision':'license_definition',
             'license_kind':'explicit_class_disjointness','reason_ru':'Явное исключение в источнике задаёт дизъюнктность классов.',
             'bindings':bindings1,'clause':{'form':'E','subject':bindings1['subject']['id'],'object':bindings1['object']['id'],'scope':scope}},
             {'statement_id':k1['semantic_frame']['statements'][1]['statement_id'],'decision':'retain_unconverted',
              'reason_ru':'Вторая часть составного исходного знания не является категорическим условием.','clause':None}]},
        {'article_id':'one','run_id':m['run_id'],'source_sha256':m['source']['sha256'],'graph_sha256':fingerprint(m['graph']),
         'knowledge_id':'K2','knowledge_sha256':fingerprint(k2),'scope':scope,
         'scope_reason_ru':'Тот же WHICAP-контекст и диагностическая оценка.',
         'reason_ru':'Подтип прямо задан как часть локальной классификации MCI.', 'evidence':[quote()],
         'statements':[{'statement_id':inclusion['statement_id'],'decision':'license_definition',
             'license_kind':'subtype_inclusion','reason_ru':'Явное включение подтипа в MCI.',
             'bindings':bindings2,'clause':{'form':'A','subject':bindings2['subject']['id'],'object':bindings2['object']['id'],'scope':scope}}]}]}
    records,groups,_=project([m]);result=licensed_inference([m],records,groups,a)
    assert result['consequences']['graph']==result['consequences']['without_dependencies']
    assert len(result['consequences']['graph'])==1
    c=result['consequences']['graph'][0]
    assert c['conclusion']['form']=='E' and c['proof']['entailed'] and not c['novel_empirical_prediction']
    assert {p['knowledge_id'] for p in c['premises']}=={'K1','K2'}


@pytest.mark.parametrize('case', ['old_version', 'independence', 'explanation', 'polarity', 'predicate',
    'property', 'shared_constraints', 'property_constraints', 'scope_context', 'condition', 'time', 'partial_quantifier'])
def test_unlicensed_or_context_stripped_contrast_is_rejected(case):
    m, audit = contrast_fixture(); entry = audit['entries'][0]; annotation = entry['statements'][0]
    statement = m['graph']['knowledge'][0]['semantic_frame']['statements'][0]
    if case == 'old_version': audit['version'] = 'source-bound-categorical-licenses-1'
    elif case == 'independence': entry['independent_contrast_parts'] = False
    elif case == 'explanation': entry['independence_reason_ru'] = ''
    elif case == 'polarity': annotation['clause']['form'] = 'E'
    elif case == 'predicate': statement['predicate'] = 'associated_with'
    elif case == 'property': annotation['bindings']['object']['predicate'] = 'has_dementia'
    elif case == 'shared_constraints': entry['shared_native_constraints'] = {}
    elif case == 'property_constraints': annotation['bindings']['object'].pop('native_constraints')
    elif case == 'scope_context': entry['scope']['conditions'] = ['Снята привязка контекста.']
    elif case == 'condition': statement['conditions'] = ['under treatment']
    elif case == 'time': statement['temporal_context'] = 'after treatment'
    elif case == 'partial_quantifier': statement['quantifier'] = 'most'
    entry['graph_sha256'] = fingerprint(m['graph'])
    entry['knowledge_sha256'] = fingerprint(m['graph']['knowledge'][0])
    with pytest.raises(ArticleMapError): validate_licenses([m], audit)


def test_previous_source_license_contract_remains_readable():
    m, audit = fixture(); audit['version'] = 'source-bound-categorical-licenses-1'
    assert len(validate_licenses([m], audit)) == 2


def test_application_binds_license_revision_and_preserves_seals_on_invalid_import(tmp_path,monkeypatch):
    import socket
    from application.whole_map_forecast import SealWholeMapForecast
    from infrastructure.development_prediction_store import FilePredictionStore
    from tests.test_schema6_prediction import ref
    def forbidden(*args,**kwargs):raise AssertionError('No network or model transport')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    m,a=fixture();other=deepcopy(m);other.update(article_id='two',run_id='run-two')
    other['source']['text']+=' Independent synthetic source.'
    other['source']['sha256']=sha256(other['source']['text'].encode()).hexdigest()
    maps=[m,other];before=deepcopy(maps);reads=[]
    class Port:
        def get(self,article,pipeline,owner,run):
            assert article!='target' and owner=='owner';reads.append(article)
            return next(m for m in maps if m['article_id']==article)
    app=SealWholeMapForecast(Port(),FilePredictionStore(tmp_path))
    args=([ref(m['article_id']) for m in maps],{'one':'first','two':'second'},'owner',
        {'question':None,'training_cutoff':'2023-12-31','source_dates':{'one':'2022-01-01','two':'2022-01-01'}},
        {'synthetic_implementation':'fixed'})
    base=app.execute(*args);licensed=app.execute(*args,categorical_licenses=a)
    assert licensed['run_id']!=base['run_id'] and licensed['binding']['categorical_licenses_sha256']==fingerprint(a)
    assert licensed['predictions']==base['predictions'] and maps==before
    assert licensed==app.execute(*args,categorical_licenses=a)
    broken=deepcopy(a);broken['entries'][0]['article_id']='target'
    with pytest.raises(ArticleMapError):app.execute(*args,categorical_licenses=broken)
    assert len(list(tmp_path.glob('*/seal.json')))==2 and set(reads)=={'one','two'}
