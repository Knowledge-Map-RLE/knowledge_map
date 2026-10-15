"""Подготовка ручной исследовательской карты через общий контракт без генераторов."""
import json
from hashlib import sha256
from uuid import uuid5, NAMESPACE_URL
from domain.article_maps import prepare_source, digest, require, fingerprint
from domain.knowledge_development import validate_development_map, initialize_occurrences, apply_development_review, model_contract, identity
from application.text_to_development_map import extraction_input, dependency_input, prompt_binding, registered_prompt_paths
from application.publish_article_map import russian_translation
from domain.whole_map_input_audit import audit_source_coverage


def prepare_manual_map(article_id, text, expected_sha256, authored, extraction_prompt, dependency_prompt,
                       prompt_binding_value=None):
    require(digest(text) == expected_sha256, 'Manual source hash differs')
    require(authored['complete_source_reviewed'] is True, 'Explicit complete source review required')
    source = prepare_source(article_id, text)
    require(source['references_excluded'] is True, 'Manual scientific source requires an explicit References boundary')
    keys = {k['key']: f'K{i+1}' for i,k in enumerate(authored['knowledge'])}
    require(len(keys) == len(authored['knowledge']), 'Duplicate manual key')
    units = {u['id']:u for u in source['units']}
    concepts, concepts_by_text, knowledge = [], {}, []
    def roles(values, uids):
        output=[]
        for role,value in values.items():
            if value.startswith('@'):
                require(value[1:] in keys, 'Unknown manual knowledge role')
                output.append({'role':role,'concept_id':None,'knowledge_id':keys[value[1:]]})
                continue
            name=identity(value)
            if name not in concepts_by_text:
                c={'id':f'C{len(concepts)+1}','display_text':value,
                   'aliases':authored.get('concept_aliases',{}).get(value,[]),'provenance':{'unit_ids':[]}}
                concepts.append(c);concepts_by_text[name]=c
            c=concepts_by_text[name]
            c['provenance']['unit_ids']=list(dict.fromkeys(c['provenance']['unit_ids']+uids))
            output.append({'role':role,'concept_id':c['id'],'knowledge_id':None})
        return output
    for item in authored['knowledge']:
        kid=keys[item['key']];uids=item['units'];require(all(u in units for u in uids),'Unknown manual source unit')
        statements=[]
        for i,claim in enumerate(item.get('claims',[{}])):
            cu=claim.get('units',uids);require(all(u in units for u in cu),'Unknown statement source unit')
            attrs=item.get('attrs',{}) | claim.get('attrs',{})
            statements.append({'statement_id':f'{kid}S{i+1}','predicate':claim.get('predicate',item['predicate']),
                'roles':roles(item['roles'] | claim.get('roles',{}),cu),
                'quantifier':claim.get('quantifier',item.get('quantifier')),
                'modality':claim.get('modality',item.get('modality')),
                'negated':claim.get('negated',item.get('negated',False)),
                'conditions':item.get('conditions',[])+claim.get('conditions',[]),
                'temporal_context':claim.get('time',item.get('time')),
                'qualifiers':{'attributes':[{'name':n,'value':v['value'],'unit':v.get('unit')} for n,v in attrs.items()]},
                'provenance':{'unit_ids':cu}})
        kind=item.get('kind','state')
        knowledge.append({'knowledge_id':kid,'kind':kind,'knowledge_kind':item.get('type','operation' if kind=='action' else 'observation'),
            'display_text':item['en'],'aliases':item.get('aliases',[]),'action_status':item.get('status','performed') if kind=='action' else None,
            'grounding':item.get('grounding','source_explicit'),'semantic_frame':{'logic':item.get('logic','single'),'statements':statements},
            'provenance':{'unit_ids':uids}})
    extraction={'schema_version':6,'concepts':concepts,'knowledge':knowledge,'nodes':[],'edges':[],'transitions':[]}
    graph=initialize_occurrences(validate_development_map(extraction,source,extraction=True),source)
    nodes={n['knowledge_id']:n['id'] for n in graph['nodes']}
    transitions=[{'id':f'T{i+1}','sources':[nodes[keys[k]] for k in t['sources']], 'target':nodes[keys[t['target']]],
        'usage':t['usage'],'reason':t['reason'],'unit_ids':t['units'],'conditions':t.get('conditions',[])} for i,t in enumerate(authored['transitions'])]
    artifacts={'source.en.md':text,'source.json':source,'authored.json':authored,'extraction.response.json':extraction,
        'prompt.extraction.en.md':extraction_prompt,'prompt.dependencies.en.md':dependency_prompt,
        'extraction.request.json':{'system':extraction_prompt,'user':extraction_input(article_id,text,source)}}
    completed=[];groups=[]
    for offset in range(0,len(knowledge),40):
        targets=[k['knowledge_id'] for k in knowledge[offset:offset+40]]
        selected={nodes[k] for k in targets};answer={'occurrences':[],'transitions':[t for t in transitions if t['target'] in selected]}
        prefix=f'dependencies.{offset//40+1}'
        artifacts[prefix+'.request.json']={'system':dependency_prompt,'user':dependency_input(article_id,text,source,graph,targets,completed,extraction_prompt)}
        artifacts[prefix+'.response.json']=answer
        graph=apply_development_review(json.dumps(answer,ensure_ascii=False),graph,source,target_keys=targets)
        groups.append({'targets':targets,'request':prefix+'.request.json','response':prefix+'.response.json'});completed+=targets
    graph=validate_development_map(model_contract(graph),source)
    generation={'kind':'codex_manual','author':'Codex','external_llm_calls':0,'local_llm_calls':0,'translation_llm_calls':0,'embedding_calls':0,'token_usage':None}
    binding=prompt_binding_value or prompt_binding()
    if prompt_binding_value is not None:
        registered_extraction, registered_dependencies = registered_prompt_paths(binding)
        require(extraction_prompt == registered_extraction.read_text(encoding='utf-8'), 'Manual extraction prompt differs from its registered version')
        require(dependency_prompt == registered_dependencies.read_text(encoding='utf-8'), 'Manual dependency prompt differs from its registered version')
    require(sha256(extraction_prompt.encode()).hexdigest()==binding['prompt']['sha256'] and sha256(dependency_prompt.encode()).hexdigest()==binding['dependency_prompt']['sha256'], 'Prepared prompt binding differs')
    run_id=str(uuid5(NAMESPACE_URL,fingerprint({'source_sha256':expected_sha256,'authored':authored,'graph':graph,'prompt_binding':binding})))
    labels={keys[k['key']]:k['ru'] for k in authored['knowledge']}
    result={'article_id':article_id,'article_title':source['units'][0]['text'].lstrip('# '),'pipeline_id':'text_reified','run_id':run_id,
        'graph_schema_version':6,'builder_version':'codex-complete-research-map-1','source':source,'graph':graph,**binding,
        'generation':generation,'expert_validated':False,'needs_expert_review':True,
        'translations':{'ru':russian_translation(graph,labels,run_id,generation)}}
    rows=[]
    for u in source['units']:
        ids=[k['knowledge_id'] for k in knowledge if u['id'] in k['provenance']['unit_ids']]
        reason=authored.get('excluded_units',{}).get(u['id'])
        require(bool(ids)!=bool(reason), f'Missing or ambiguous source coverage: {u["id"]}')
        rows.append({'unit_id':u['id'],'start':u['start'],'end':u['end'],'knowledge_ids':ids,
            'status':'represented' if ids else 'excluded','reason_ru':None if ids else reason})
    coverage={'complete_source_reviewed':True,'complete_semantic_coverage':authored['complete_semantic_coverage'],
        'table_cells_exhaustively_formalized':authored['table_cells_exhaustively_formalized'],'references_excluded':True,
        'source_limitations':authored.get('source_limitations',[]),'units':rows}
    audit_source_coverage(result,coverage,fingerprint(coverage))
    artifacts.update({'map.json':result,'translation.ru.json':labels,'coverage.json':coverage,'key-to-id.json':keys,
        'validation.json':{'contract':'passed','dag':'passed','provenance':'passed','coverage_units':len(rows),'analysis':graph['analysis'],
            'complete_semantic_coverage_declared':coverage['complete_semantic_coverage'],'expert_validated':False,'model_calls':0},
        'dependency-groups.json':groups})
    return artifacts
