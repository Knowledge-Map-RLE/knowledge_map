"""Ручные контракты модели привязаны к точной карте и фрагментам её источника."""
from hashlib import sha256
from domain.article_maps import require,fingerprint

VERSION='statistical-context-audit-1'
KINDS={'category_coefficient','continuous_coefficient','reference_coefficient','time_slope'}
FIELDS={'statement_index','kind','model','unit','contrast','estimand','threshold','reference','bounds','evidence_unit_ids'}


def audit_models(maps,audit):
    if audit is None:return {}
    require(audit['version']==VERSION and audit['author']=='Codex' and audit['expert_validated'] is False
            and audit['model_calls']==0,'Unsupported model audit provenance')
    sources={m['article_id']:m for m in maps};index={}
    for entry in audit['entries']:
        require(entry['article_id'] in sources,'Model audit references unlisted source')
        m=sources[entry['article_id']];source=m['source']
        require(entry['run_id']==m['run_id'] and entry['source_sha256']==source['sha256']
                and entry['graph_sha256']==fingerprint(m['graph']),'Model audit binding differs')
        k=next((k for k in m['graph']['knowledge'] if k['knowledge_id']==entry['knowledge_id']),None)
        require(k is not None and entry['knowledge_sha256']==fingerprint(k),'Model audit knowledge changed')
        key=(m['article_id'],k['knowledge_id']);require(key not in index,'Duplicate model audit')
        require(k['kind']=='state' and entry['reason_ru'],'Model audit requires observed state and reason')
        units={u['id']:u for u in source['units']};evidence={}
        parent_units={u for s in k['semantic_frame']['statements'] for u in s['provenance']['unit_ids']}
        for e in entry['evidence']:
            require(e['unit_id'] in units and e['unit_id'] not in evidence,'Unknown or repeated model evidence')
            u=units[e['unit_id']]
            require(e['start']==u['start'] and e['end']==u['end']<=source['content_end']
                    and e['text']==source['text'][u['start']:u['end']]
                    and e['sha256']==sha256(e['text'].encode()).hexdigest(),'Model evidence differs')
            evidence[e['unit_id']]=e
        require(parent_units & evidence.keys(),'Model audit lacks table evidence')
        annotations=entry['statements']
        require([a['statement_index'] for a in annotations]==list(range(len(k['semantic_frame']['statements']))),
                'Model audit must cover complete compound frame in order')
        for a in annotations:
            require(set(a)==FIELDS and a['kind'] in KINDS,'Unexpected model annotation fields')
            require(a['model'] in {'Tobit regression','linear regression'} and isinstance(a['unit'],str) and a['unit'],
                    'Unsupported audited model or units')
            require(all(isinstance(a[n],str) and a[n] for n in ('contrast','estimand')),'Model axes missing')
            require(a['threshold'] is None or isinstance(a['threshold'],str),'Model threshold must be explicit')
            require(a['evidence_unit_ids'] and set(a['evidence_unit_ids'])<=evidence.keys(),'Model contract evidence missing')
            require(isinstance(a['bounds'],list) and (a['reference'] is None or isinstance(a['reference'],str)),
                    'Invalid model bounds or reference')
        index[key]=entry
    return index
