"""Адресные логические проекции определений сохраняют целый исходный блок."""
from copy import deepcopy
from hashlib import sha256
from itertools import product

from domain.article_maps import fingerprint, require
from domain.categorical_logic import validate as validate_proposition
from domain.whole_map_categorical import infer, LIMITS

VERSION='source-bound-categorical-licenses-3'
SUPPORTED_VERSIONS={VERSION,'source-bound-categorical-licenses-2','source-bound-categorical-licenses-1'}
PROPERTY_PREDICATES={'interferes_with','has_functional_impairment','has_dementia'}
UNARY_PROPERTY_PREDICATES={'has_death_domain'}
EXPLICIT_CLASS_EXCLUSION_PREDICATE='excludes dementia diagnosis'
PREDICATES={'A':('class inclusion','all'),'E':('class disjointness','no')}


def validate_licenses(maps,audit):
    if audit is None:return None
    require(audit['version'] in SUPPORTED_VERSIONS and audit['author']=='Codex' and audit['model_calls']==0
            and audit['expert_validated'] is False,'Unsupported categorical license provenance')
    sources={m['article_id']:m for m in maps};index={};ids=set();classes={}
    for entry in audit['entries']:
        article,kid=entry['article_id'],entry['knowledge_id'];key=(article,kid)
        require(article in sources and key not in index,'Unlisted or repeated categorical parent')
        m=sources[article]
        require(sha256(m['source']['text'].encode()).hexdigest()==m['source']['sha256'],'Categorical source text changed')
        require(entry['run_id']==m['run_id'] and entry['source_sha256']==m['source']['sha256']
                and entry['graph_sha256']==fingerprint(m['graph']),'Categorical source binding differs')
        k=next((k for k in m['graph']['knowledge'] if k['knowledge_id']==kid),None)
        require(k is not None and entry['knowledge_sha256']==fingerprint(k),'Categorical parent changed')
        contrast=k['semantic_frame']['logic']=='contrast'
        require(k['kind']=='state' and k['knowledge_kind']=='definition'
                and k['semantic_frame']['logic'] in {'single','conjunction','partition','contrast'},
                'Only independently asserted definitional parts are licensed')
        if contrast:
            require(audit['version']==VERSION and entry.get('independent_contrast_parts') is True
                    and bool(entry.get('independence_reason_ru')),
                    'Contrast parts need an explicit independent-assertion license')
        native=k['semantic_frame']['statements'];annotations=entry['statements']
        require([a['statement_id'] for a in annotations]==[s['statement_id'] for s in native],
                'Categorical license must account for the entire compound frame in order')
        require(entry['reason_ru'] and entry['scope_reason_ru'],'Categorical scope explanation missing')
        scope=entry['scope'];require(scope['study_group']==article,'Definition scope must remain source-local')
        units={u['id']:u for u in m['source']['units']};evidence={}
        parents={u for s in native for u in s['provenance']['unit_ids']}
        for quote in entry['evidence']:
            uid=quote['unit_id'];require(uid in parents and uid not in evidence,'Unrelated or repeated categorical evidence')
            u=units[uid]
            require(quote['start']==u['start'] and quote['end']==u['end']<=m['source']['content_end']
                    and quote['text']==m['source']['text'][u['start']:u['end']]
                    and quote['sha256']==sha256(quote['text'].encode()).hexdigest(),'Categorical evidence changed')
            evidence[uid]=quote
        require(set(evidence)==parents,'Complete parent evidence required')
        concepts={c['id']:c for c in m['graph']['concepts']};views=[]
        for annotation,s in zip(annotations,native):
            require(annotation['reason_ru'],'Statement license explanation missing')
            if annotation['decision']=='retain_unconverted':
                require(annotation.get('clause') is None,'Unconverted statement cannot publish a clause')
                continue
            require(annotation['decision']=='license_definition' and annotation['license_kind'] in {'subtype_inclusion','definition_requirement','unary_definition_requirement','explicit_class_disjointness'},
                    'Unknown categorical license decision')
            require(s['modality'] is None,'Qualified assertion cannot become an unqualified definition')
            require(s['quantifier'] in (None,'all'),'Partial or negative quantification requires a separate license')
            clause=annotation['clause'];form=clause['form'];require(form in PREDICATES,'Existence cannot be supplied by a definition')
            bindings=annotation['bindings'];require(set(bindings)=={'subject','object'},'Explicit class bindings required')
            roles={r['role']:r['concept_id'] for r in s['roles']}
            require(all(r['knowledge_id'] is None for r in s['roles']),'Unresolved logical participant')
            subject=bindings['subject'];object_=bindings['object']
            for b in (subject,object_):
                require(b['id']==article+'::'+b['local_id'] and b['text_en'] and b['text_ru'],'Source-local bilingual class identity required')
                if b['kind']=='unary_property':
                    require(isinstance(b.get('native_constraints'),dict),'Unary property context is missing')
                expected='concept:'+b['concept_id'] if b['kind']=='concept' else 'property:'+b['predicate']+':'+b['object_concept_id'] if b['kind']=='property' else 'unary_property:'+b['predicate']+':'+fingerprint(b['native_constraints']) if b['kind']=='unary_property' else None
                require(expected is not None and b['local_id']==expected,'Class identity must preserve its native semantic binding')
                previous=classes.setdefault(b['id'],b)
                require(previous==b,'One class identity cannot denote different definitions')
            require(subject['kind']=='concept' and subject['concept_id'] in concepts,'Unknown subject class')
            if annotation['license_kind']=='subtype_inclusion':
                require(s['predicate']=='subtype_of' and not s['negated'] and form=='A',
                        'Native relation is not a positive subtype inclusion')
                require(subject['concept_id']==roles.get('subtype') and object_['kind']=='concept'
                        and object_['concept_id'] in concepts and object_['concept_id']==roles.get('class'),'Subtype class binding differs')
            elif annotation['license_kind']=='explicit_class_disjointness':
                # Явное исключение деменции действует только в проверенной WHICAP-классификации.
                cohort_id=roles.get('cohort')
                require(s['predicate']==EXPLICIT_CLASS_EXCLUSION_PREDICATE and not s['negated']
                        and s['quantifier']=='all' and form=='E'
                        and set(roles)=={'cohort','classification','criterion'}
                        and cohort_id in concepts and concepts[cohort_id]['display_text']=='WHICAP'
                        and subject['kind']=='concept' and subject['concept_id']==roles.get('classification')
                        and object_['kind']=='concept' and object_['concept_id']==roles.get('criterion'),
                        'Native relation is not an explicit WHICAP class exclusion')
                require(s['temporal_context'] and 'WHICAP' in ' '.join(scope['conditions'])
                        and 'consensus' in (' '.join(scope['conditions'])+' '+s['temporal_context']).casefold(),
                        'WHICAP consensus-visit scope is missing')
            elif annotation['license_kind']=='unary_definition_requirement':
                require(audit['version']==VERSION and s['predicate'] in UNARY_PROPERTY_PREDICATES
                        and subject['concept_id']==roles.get('subject'),
                        'Native relation is not a licensed unary definitional property')
                require(object_['kind']=='unary_property' and object_['predicate']==s['predicate']
                        and form==('E' if s['negated'] else 'A'),
                        'Unary property or definitional negation differs')
                # Дополнительные роли и ограничения не исчезают в классовой проекции.
                preserved={'roles':[r for r in s['roles'] if r['role']!='subject'],
                    'attributes':s['qualifiers']['attributes'],'conditions':s['conditions'],
                    'temporal_context':s['temporal_context']}
                require(annotation.get('native_constraints')==preserved
                        and entry.get('shared_native_constraints')==preserved
                        and object_.get('native_constraints')==preserved
                        and 'native_definition_constraints_sha256:'+fingerprint(preserved) in scope['conditions'],
                        'Unary definition constraints must be preserved and shared')
                require(s['quantifier'] is None and not s['conditions'] and s['temporal_context'] is None,
                        'Conditional unary definition needs a separate typed context operator')
            else:
                require(s['predicate'] in PROPERTY_PREDICATES and subject['concept_id']==roles.get('subject'),
                        'Native relation is not a licensed definitional requirement')
                require(object_['kind']=='property' and object_['predicate']==s['predicate']
                        and object_['object_concept_id'] in concepts
                        and object_['object_concept_id'] in {v for role,v in roles.items() if role!='subject'},
                        'Property class does not match the native relation')
                require(form==('E' if s['negated'] else 'A'),'Definitional negation differs')
            require(clause['subject']==subject['id'] and clause['object']==object_['id'] and clause['scope']==scope,
                    'Categorical clause identity or scope differs')
            validate_proposition(clause)
            vid=kid+'@'+s['statement_id'];require((article,vid) not in ids,'Repeated categorical view')
            ids.add((article,vid))
            views.append({'key':(article,vid),'clause':clause,'bindings':bindings,'statement_id':s['statement_id'],
                'native_key':key,'parent_frame_sha256':fingerprint(k['semantic_frame']),
                'parent_knowledge_sha256':fingerprint(k),'license':annotation,'evidence':list(evidence.values()),
                'complete_parent_frame':deepcopy(k['semantic_frame']),'parent_logic':k['semantic_frame']['logic']})
        require(views,'License entry contains no actual definitional projection')
        index[key]={'entry':entry,'views':views}
    return index


def licensed_inference(maps,records,groups,audit):
    index=validate_licenses(maps,audit)
    if index is None:return {'version':VERSION,'status':'not_supplied','model_calls':0}
    expanded=deepcopy(records);proofs=[];view_keys={}
    for native_key,value in index.items():
        require(native_key in records and records[native_key]['eligible'],'Unresolved parent cannot be licensed')
        for view in value['views']:
            require(view['key'] not in expanded,'Categorical view collides with native knowledge')
            clause=view['clause'];predicate,quantifier=PREDICATES[clause['form']]
            r=deepcopy(records[native_key]);r['key']=view['key'];r['native_key']=native_key
            r['frame']={'kind':'state','action_status':None,'logic':'single','statements':[{
                'predicate':predicate,'roles':[{'role':'subject','value':clause['subject']},
                                              {'role':'class','value':clause['object']}],
                'scope':{**deepcopy(clause['scope']),'quantifier':quantifier},'negated':False,'attributes':[]}]}
            r['license_proof']=view;expanded[view['key']]=r;proofs.append(view)
            view_keys.setdefault(native_key,[]).append(view['key'])
    expanded_groups=[]
    for body,head in groups:
        if len(body)>LIMITS['max_premise_blocks']:
            expanded_groups.append((body,head));continue
        choices=[view_keys.get(p,[p]) for p in body]
        head_choices=view_keys.get(head,[head])
        for selected in product(*choices):
            for selected_head in head_choices:
                require(len(expanded_groups)<LIMITS['search_steps'],'Categorical license expansion budget exceeded')
                expanded_groups.append((tuple(selected),selected_head))
    result=infer(expanded,expanded_groups)
    for candidates in result['consequences'].values():
        for candidate in candidates:
            for p in candidate['premises']:
                key=(p['article_id'],p['knowledge_id'])
                if key in expanded and 'license_proof' in expanded[key]:
                    view=expanded[key]['license_proof'];p['view_id']=p['knowledge_id']
                    p['knowledge_id']=view['native_key'][1];p['statement_id']=view['statement_id']
                    p['license_proof_sha256']=fingerprint(view)
            for node,p in zip(candidate['proof_graph']['nodes'],candidate['premises']):
                if 'view_id' in p:
                    node['view_id']=p['view_id'];node['knowledge_id']=p['knowledge_id'];node['statement_id']=p['statement_id']
    result.update(version=VERSION,status='source_definitions_licensed',audit_sha256=fingerprint(audit),
        original_canonical_blocks=len(records),licensed_parent_blocks=len(index),licensed_views=len(proofs),
        license_proofs=proofs,expert_validated=False)
    result['policy']='Definitional parts are licensed independently with their full compound parent retained; opaque parts remain unconverted, not discarded. No population law or empirical forecast is asserted.'
    return result
