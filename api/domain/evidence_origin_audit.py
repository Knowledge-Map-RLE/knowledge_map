"""Происхождение утверждений отделяется от числа публикаций и логической истинности."""
from hashlib import sha256
from collections import Counter
from domain.article_maps import require,fingerprint

VERSION='whole-map-evidence-origin-1'
ORIGINS={'primary_result','primary_method','primary_interpretation','parent_cohort_report',
    'review_result','review_method','review_interpretation','cited_result','cited_method','background',
    'definition','research_task','proposed_application','mixed_origin','unresolved_origin'}
DOCUMENTS={'primary_study','systematic_review','narrative_review'}


def validate_origins(maps,audit):
    if audit is None:return None
    require(audit['version']==VERSION and audit['author']=='Codex' and audit['model_calls']==0
            and audit['expert_validated'] is False,'Unsupported origin audit provenance')
    sources={m['article_id']:m for m in maps};registry={};index={}
    require(len(sources)==len(maps),'Repeated origin map')
    for record in audit['sources']:
        article=record['article_id'];require(article in sources and article not in registry,'Unknown or repeated origin source')
        m=sources[article]
        require(sha256(m['source']['text'].encode()).hexdigest()==m['source']['sha256'],'Origin source text hash differs')
        require(record['run_id']==m['run_id'] and record['source_sha256']==m['source']['sha256']
                and record['graph_sha256']==fingerprint(m['graph']),'Origin source binding differs')
        require(record['document_kind'] in DOCUMENTS and record['reason_ru'],'Source kind not reviewed')
        family=record['dataset_family']
        require((isinstance(family,str) and bool(family.strip())) if record['document_kind']=='primary_study' else family is None,
                'Primary dataset family must be explicit; review is not a new cohort')
        units={u['id']:u for u in m['source']['units']};catalog={}
        for evidence in record['evidence']:
            uid=evidence['unit_id'];require(uid in units and uid not in catalog,'Unknown or repeated origin evidence')
            unit=units[uid]
            require(evidence['start']==unit['start'] and evidence['end']==unit['end']<=m['source']['content_end']
                    and evidence['text']==m['source']['text'][unit['start']:unit['end']]
                    and evidence['sha256']==sha256(evidence['text'].encode()).hexdigest(),'Origin evidence differs')
            catalog[uid]=evidence
        registry[article]=record
        knowledge={k['knowledge_id']:k for k in m['graph']['knowledge']};seen=set()
        for entry in record['knowledge']:
            kid=entry['knowledge_id'];require(kid in knowledge and kid not in seen,'Unknown or repeated origin knowledge')
            seen.add(kid);k=knowledge[kid]
            require(entry['knowledge_sha256']==fingerprint(k),'Origin knowledge changed')
            annotations=entry['statements'];statements=k['semantic_frame']['statements']
            require([a['statement_id'] for a in annotations]==[s['statement_id'] for s in statements],
                    'Origin audit must cover complete compound frame in order')
            for a,s in zip(annotations,statements):
                require(a['origin'] in ORIGINS and a['reason_ru'],'Unknown or unexplained origin')
                require(len(a['evidence_unit_ids'])==len(set(a['evidence_unit_ids'])),'Repeated origin statement evidence')
                require(set(a['evidence_unit_ids'])==set(s['provenance']['unit_ids'])
                        and set(a['evidence_unit_ids'])<=catalog.keys(),'Origin statement evidence missing')
                if a['origin'].startswith('primary_') or a['origin']=='parent_cohort_report':
                    require(record['document_kind']=='primary_study','Review cannot declare a new primary result')
                if a['origin'].startswith('review_'):
                    require(record['document_kind']!='primary_study','Primary study cannot be a review synthesis')
            index[article,kid]=entry
        require(seen==set(knowledge),'Origin audit does not cover entire source map')
    require(set(registry)==set(sources),'Origin audit does not cover explicit corpus')
    return {'sources':registry,'knowledge':index,'audit_sha256':fingerprint(audit)}


def audit_rule_support(rules,index):
    if index is None:return {'version':VERSION,'status':'not_audited','rules':[]}
    rows=[]
    for rule in rules:
        primary=set();secondary=set();other=set();heads=set()
        for example in rule['examples']:
            article,kid=example['head'];entry=index['knowledge'][article,kid];record=index['sources'][article]
            origins={a['origin'] for a in entry['statements']};heads.add((article,kid))
            if origins=={'primary_result'} and record['document_kind']=='primary_study':
                primary.add(record['dataset_family'])
            elif record['document_kind']!='primary_study' or origins & {'cited_result','cited_method','parent_cohort_report'}:
                secondary.add(article)
            else:other.add(article)
        rows.append({'rule_id':rule['id'],'publication_families':rule['families'],
            'declared_primary_dataset_families':sorted(primary),'secondary_sources':sorted(secondary),
            'nonempirical_or_mixed_sources':sorted(other),'heads':[list(h) for h in sorted(heads)],
            'two_primary_families_declared':len(primary)>=2,'logical_entailment_established':False,
            'expert_validated':False})
    return {'version':VERSION,'status':'source_origins_declared','audit_sha256':index['audit_sha256'],
        'rules':rows,'counts':dict(Counter(len(r['declared_primary_dataset_families']) for r in rows)),
        'note':'Origin accounting does not validate inference, context compatibility or independence of participants.'}
