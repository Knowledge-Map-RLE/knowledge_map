"""Аналогический прогноз вмешательств; граф не превращает гипотезу в доказательство."""
from collections import Counter, defaultdict, deque
from copy import deepcopy
from hashlib import sha256
from itertools import product

from domain.article_maps import fingerprint, require
from domain.development_prediction import validate_visible_dag

VERSION='mechanistic-opportunity-forecast-1'
AUDIT_VERSION='source-bound-mechanistic-facets-1'
LIMITS={'candidate_limit':20,'search_steps':200000}
FACETS={'effect','target_action','delivery','open_application','caution'}
PREDICATES={'effect':{'reduced_after_intervention','exacerbated_after_intervention'},
 'target_action':{'sequesters','inhibitor_mechanism'},'delivery':{'transported_via','pharmacokinetic_result'},
 'open_application':{'investigated_in'},'caution':{'exacerbated_after_intervention','limited_by',
 'requires_confirmation','no_improvement','tested_in','needs_further_study','confirm_efficacy','improved'}}


def validate_audit(maps,audit):
    require(audit['version']==AUDIT_VERSION and audit['author']=='Codex' and audit['model_calls']==0
        and audit['expert_validated'] is False,'Unsupported mechanistic audit')
    sources={m['article_id']:m for m in maps};index={};facets=[];proofs={}
    require(len(sources)==len(maps),'Repeated mechanistic source')
    for entry in audit['entries']:
        key=(entry['article_id'],entry['knowledge_id']);require(key[0] in sources and key not in index,'Unknown or repeated mechanistic parent')
        m=sources[key[0]];source=m['source']
        require(sha256(source['text'].encode()).hexdigest()==source['sha256'],'Mechanistic source changed')
        require(entry['run_id']==m['run_id'] and entry['source_sha256']==source['sha256']
            and entry['graph_sha256']==fingerprint(m['graph']),'Mechanistic source binding differs')
        k=next((k for k in m['graph']['knowledge'] if k['knowledge_id']==key[1]),None)
        require(k is not None and entry['knowledge_sha256']==fingerprint(k),'Mechanistic parent changed')
        native=k['semantic_frame']['statements'];rows=entry['statements']
        require([r['statement_id'] for r in rows]==[s['statement_id'] for s in native],'Complete ordered compound ledger required')
        concepts={c['id'] for c in m['graph']['concepts']};units={u['id']:u for u in source['units']}
        parent_units={u for s in native for u in s['provenance']['unit_ids']};evidence={}
        for quote in entry['evidence']:
            uid=quote['unit_id'];require(uid in parent_units and uid not in evidence,'Unrelated or repeated evidence')
            u=units[uid]
            require(quote['start']==u['start'] and quote['end']==u['end']<=source['content_end']
                and quote['text']==source['text'][u['start']:u['end']]
                and quote['sha256']==sha256(quote['text'].encode()).hexdigest(),'Mechanistic evidence differs')
            evidence[uid]=quote
        require(set(evidence)==parent_units and entry['reason_ru'],'Complete mechanistic parent evidence required')
        for row,s in zip(rows,native):
            require(row['reason_ru'] and isinstance(row['facets'],list),'Explicit facet ledger required')
            for i,facet in enumerate(row['facets']):
                kind=facet['kind'];require(kind in FACETS,'Unknown mechanistic facet')
                require(k['semantic_frame']['logic'] in {'single','conjunction','contrast'},'Argument needs a separate projection license')
                require(s['predicate'] in PREDICATES[kind] and (kind=='caution' or not s['negated']),'Native predicate does not license facet')
                require(kind=='caution' or k['kind']=='state','Intended action is not a completed mechanistic observation')
                if kind=='open_application':
                    require(isinstance(s['modality'],str) and 'ongoing' in s['modality']
                        and 'not yet established' in s['modality'],'Open application status not grounded')
                elif kind!='caution':require(s['modality'] is None,'Qualified result needs a separate mechanism contract')
                links=facet['concept_ids'];require(links and set(links)<=concepts,'Unknown native concept binding')
                require(set(links)&{r['concept_id'] for r in s['roles']},'Facet lacks native participants')
                require(facet['reason_ru'] and facet['context_reason_ru'],'Facet interpretation explanation required')
                values=facet['values'];require(isinstance(values,dict),'Explicit mechanistic values required')
                required={'effect':{'intervention','target','species','disease','compartment','outcomes','route'},
                    'target_action':{'intervention','target','species','compartment','direction'},
                    'delivery':{'intervention','species','compartment','routes'},
                    'open_application':{'intervention','species','disease'},'caution':{'text_ru'}}[kind]
                require(set(values)==required and all(v is not None and v!='' for v in values.values()),'Incomplete facet context')
                if kind=='effect':
                    require(values['outcomes'] and len({v['entity'] for v in values['outcomes']})==len(values['outcomes']),'Distinct source outcomes required')
                    require(all(v['direction'] in {'decrease','increase','not_detected'} and v['text_ru'] for v in values['outcomes']),'Explicit observed outcome direction required')
                    expected='decrease' if s['predicate']=='reduced_after_intervention' else 'increase'
                    require(all(v['direction']==expected for v in values['outcomes']),'Native effect direction differs')
                if kind=='target_action':require(values['direction']=='reduce_activity','Target action must explicitly reduce activity')
                if kind=='delivery':require(values['routes'] and len(set(values['routes']))==len(values['routes']),'Explicit unique delivery routes required')
                proof={'key':list(key),'statement_id':s['statement_id'],'facet_index':i,'facet':deepcopy(facet),
                    'run_id':m['run_id'],'source_sha256':source['sha256'],'parent_knowledge_sha256':fingerprint(k),
                    'complete_parent_frame':deepcopy(k['semantic_frame']),'evidence':list(evidence.values())}
                digest=fingerprint(proof);require(digest not in proofs,'Repeated mechanistic projection')
                proofs[digest]=proof;facets.append({'id':digest,'key':key,'statement_id':s['statement_id'],**deepcopy(facet)})
        index[key]=entry
    return facets,proofs,index


def adjacency(maps):
    edges=set();groups=[]
    for m in maps:
        validate_visible_dag(m['graph']);nodes={n['id']:n['knowledge_id'] for n in m['graph']['nodes']};article=m['article_id']
        knowledge={k['knowledge_id'] for k in m['graph']['knowledge']};visible=set()
        require(len(nodes)==len(m['graph']['nodes']) and set(nodes.values())<=knowledge,'Unknown or repeated visible knowledge')
        for t in m['graph']['transitions']:
            require(t['target'] in nodes and t['sources'] and len(set(t['sources']))==len(t['sources'])
                and all(n in nodes and n!=t['target'] for n in t['sources']),'Unknown or repeated transition participant')
            body=tuple((article,nodes[n]) for n in t['sources']);head=(article,nodes[t['target']])
            groups.append((body,head));edges.update((p,head) for p in body)
            visible.update((n,t['target']) for n in t['sources'])
        require(visible=={(e['source'],e['target']) for e in m['graph']['edges']},'Visible edges and premise groups differ')
    return edges,groups


def path_to(start,target,edges):
    if start==target:return [start]
    outgoing=defaultdict(list)
    for a,b in sorted(edges):outgoing[a].append(b)
    queue=deque([(start,[start])]);seen={start}
    while queue:
        node,path=queue.popleft()
        for nxt in outgoing[node]:
            if nxt==target:return path+[nxt]
            if nxt not in seen:seen.add(nxt);queue.append((nxt,path+[nxt]))
    return None


def shared_argument(effect,action,records,edges,groups):
    # Общий авторский аргумент только организует основания гипотезы, не доказывает её.
    choices=[]
    for body,key in groups:
        record=records[key]
        if key[0]!=effect['key'][0] or record['kind']!='state':continue
        if not any(s['modality'] is not None for s in record['semantic_frame']['statements']):continue
        for first,second in product(body,body):
            if first==second:continue
            left=path_to(effect['key'],first,edges);right=path_to(action['key'],second,edges)
            if left and right:choices.append((len(left)+len(right),key,body,left+[key],right+[key]))
    return min(choices) if choices else None


def generate(maps,audit):
    facets,proofs,index=validate_audit(maps,audit);edges,groups=adjacency(maps)
    records={(m['article_id'],k['knowledge_id']):k for m in maps for k in m['graph']['knowledge']}
    by_kind={kind:[f for f in facets if f['kind']==kind] for kind in FACETS}
    coverage=[{'article_id':key[0],'knowledge_id':key[1],'statements':len(k['semantic_frame']['statements']),
        'status':'source_facets_licensed' if key in index else 'no_licensed_mechanistic_projection',
        'reason_ru':'Есть отдельная привязанная к источнику проекция.' if key in index else
        'Этот оператор требует явного вмешательства, доставки, целевого действия или незавершённого применения; исходный блок сохранён.'}
        for key,k in records.items()]
    modes={m:[] for m in ('graph','without_dependencies','source_neighborhood','permuted_dependencies')}
    diagnostics=Counter();steps=0;pool={}
    # Все явно лицензированные темы обрабатываются; заданного вопроса и списка факторов нет.
    for effect,action,delivery,opening in product(by_kind['effect'],by_kind['target_action'],by_kind['delivery'],by_kind['open_application']):
        steps+=1;require(steps<=LIMITS['search_steps'],'Mechanistic search budget exceeded; no partial publication')
        e,a,d,o=[f['values'] for f in (effect,action,delivery,opening)]
        if len({f['key'][0] for f in (effect,action,delivery,opening)})!=1:
            diagnostics['cross_source_identity_not_licensed']+=1;continue
        if not (a['intervention']==d['intervention']==o['intervention']) or e['intervention']==a['intervention']:
            diagnostics['intervention_identity_mismatch_or_known_application']+=1;continue
        if e['target']!=a['target'] or e['disease']!=o['disease'] or len({v['species'] for v in (e,a,d,o)})!=1 or len({v['compartment'] for v in (e,a,d)})!=1:
            diagnostics['target_species_disease_or_compartment_mismatch']+=1;continue
        if not any(route in {'systemic','intravenous','subcutaneous','intraperitoneal'} for route in d['routes']):
            diagnostics['systemic_delivery_not_established']+=1;continue
        argument=shared_argument(effect,action,records,edges,groups)
        context={'species':o['species'],'disease':o['disease'],'compartment':a['compartment'],
            'intervention':a['intervention'],'target':a['target'],'routes':sorted(d['routes'])}
        cautions=[f for f in by_kind['caution'] if f['key'][0]==opening['key'][0]]
        for outcome in e['outcomes']:
            if outcome['entity']==a['target']:
                diagnostics['target_activity_repeats_known_action']+=1;continue
            known=[f for f in by_kind['effect'] if f['values']['intervention']==a['intervention']
                and f['values']['species']==o['species'] and f['values']['disease']==o['disease']
                and any(v['entity']==outcome['entity'] for v in f['values']['outcomes'])]
            if known:diagnostics['application_outcome_already_reported']+=1;continue
            conclusion={**context,'outcome':outcome['entity'],'expected_direction':outcome['direction'],
                'modality':'may; mechanistic analogy, efficacy unestablished'}
            identity=fingerprint(conclusion);premises=[effect,action,delivery,opening]
            nodes=[{'id':'premise:'+str(i),'article_id':f['key'][0],'knowledge_id':f['key'][1],
                'statement_id':f['statement_id'],'facet_sha256':f['id']} for i,f in enumerate(premises)]
            nodes+=[{'id':'operator','knowledge_id':VERSION},{'id':'conclusion','knowledge_id':'hypothesis:'+identity}]
            candidate={'id':identity,'conclusion':conclusion,'outcome_ru':outcome['text_ru'],
                'premises':[{'key':list(f['key']),'statement_id':f['statement_id'],'facet_sha256':f['id']} for f in premises],
                'status':'untested_mechanistic_opportunity','logical_entailment':False,'causality_established':False,
                'clinical_efficacy_established':False,'expert_validated':False,'independent_replications_certified':False,
                'novel_relative_to_licensed_application_outcomes':True,'novel_scientific_idea_certified':False,
                'conditions_ru':['Перенос эффекта между разными вмешательствами — гипотеза, а не закон.',
                    'Доставка и связывание не доказывают достаточного подавления патологической активности.',
                    'Рецепторный баланс, доза, длительность и стадия заболевания могут изменить результат.',
                    'Величина эффекта, статистическая значимость и эффективность у человека не предсказываются.'],
                'cautions':[{'facet_sha256':f['id'],'text_ru':f['values']['text_ru']} for f in cautions],
                'source_families':[opening['key'][0]],'evidence_type':'reviewed_preclinical_results_and_delivery; not two independent primary families',
                'author_argument':None if argument is None else {'key':list(argument[1]),
                    'joint_group':[list(k) for k in argument[2]],'effect_path':[list(k) for k in argument[3]],
                    'action_path':[list(k) for k in argument[4]],
                    'complete_argument_frame':deepcopy(records[argument[1]]['semantic_frame'])},
                'proof_graph':{'nodes':nodes,'edges':[{'source':n['id'],'target':'conclusion'} for n in nodes[:-1]],
                    'visible_dag':True,'interpretation':'hypothesis rationale, not deductive proof'}}
            prior=pool.get(identity)
            if prior is None or fingerprint(candidate)<fingerprint(prior):pool[identity]=candidate
    ranked=sorted(pool.values(),key=lambda c:c['id'])[:LIMITS['candidate_limit']]
    modes['without_dependencies']=ranked
    modes['graph']=[c for c in ranked if c['author_argument'] is not None]
    # Контроли используют тот же поиск; меняется лишь организация авторских оснований.
    from domain.whole_map_ablation import permuted_groups
    permutation_records={key:{'key':key,'provenance':[s['provenance'] for s in k['semantic_frame']['statements']]} for key,k in records.items()}
    permuted=permuted_groups(permutation_records,groups);permuted_edges={(p,h) for body,h in permuted for p in body}
    lookup={f['id']:f for f in facets}
    for candidate in ranked:
        effect=lookup[candidate['premises'][0]['facet_sha256']];action=lookup[candidate['premises'][1]['facet_sha256']]
        control=shared_argument(effect,action,records,permuted_edges,permuted)
        if control is not None:
            alternative=deepcopy(candidate)
            alternative['permuted_control_argument']={'key':list(control[1]),'joint_group':[list(k) for k in control[2]],
                'effect_path':[list(k) for k in control[3]],'action_path':[list(k) for k in control[4]],
                'interpretation':'negative control; permuted links are not author evidence'}
            modes['permuted_dependencies'].append(alternative)
        parents=[records[tuple(p['key'])] for p in candidate['premises']]
        units=[{u for s in k['semantic_frame']['statements'] for u in s['provenance']['unit_ids']} for k in parents]
        if set.intersection(*units):modes['source_neighborhood'].append(candidate)
    return {'version':VERSION,'question':None,'factor_whitelist':None,'predicate_topic_whitelist':None,'limits':LIMITS,
        'canonical_blocks':len(records),'statements':sum(v['statements'] for v in coverage),'coverage':coverage,
        'licensed_parent_blocks':len(index),'facet_count':len(facets),'facet_proofs':proofs,'candidates':modes,
        'diagnostics':{'search_steps':steps,'rejected':dict(diagnostics),'candidate_pool':len(pool)},
        'policy':'Pre-specified analogical opportunity operator; not an empirically learned law, not a certified forecast. Entire selected maps scanned; only source-licensed facets can generate.',
        'scientific_success':False,'graph_advantage_demonstrated':False,'model_calls':0,'target_read':False}
