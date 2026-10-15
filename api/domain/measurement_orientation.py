"""Источниковая абстракция измеряемого свойства не отождествляет инструменты и эффекты."""
from copy import deepcopy
from hashlib import sha256

from domain.article_maps import fingerprint, require
from domain.evidence_origin_audit import validate_origins
from domain.interval_knowledge import _learn_modes, decimal
from domain.protocol_parameter_transfer import protocol_frame_identity
from domain.typed_participant_forecast import guard_barriers

VERSION='source-bound-measurement-orientation-1'


def ordered_direction(effect, orientation):
    """Необнаруженность не означает нулевую величину; неизвестная ориентация не угадывается."""
    require(effect in {'improved','worsened','not_detected','unknown'},'Unknown effect category')
    require(orientation in {'higher_is_worse','higher_is_better','unknown'},'Unknown measurement orientation')
    if effect in {'not_detected','unknown'} or orientation=='unknown': return None
    return 'lower' if (effect=='improved') == (orientation=='higher_is_worse') else 'higher'


def _quote(e, source, allowed):
    unit=next((u for u in source['units'] if u['id']==e['unit_id']),None)
    require(unit is not None and e['unit_id'] in allowed,'Orientation quote outside source basis')
    require(unit['start']<=e['start']<e['end']<=unit['end']<=source['content_end']
            and source['text'][e['start']:e['end']]==e['text'] and sha256(e['text'].encode()).hexdigest()==e['sha256'],
            'Orientation quote changed')


def project(frozen, maps, cases, origins, audit):
    """Добавляет типовые свойства отдельно от всех исходных фактов и их полных родителей."""
    require(audit['version']==VERSION and audit['author']=='Codex' and audit['expert_validated'] is False
            and audit['model_calls']==0 and audit['source_sha256']==fingerprint(frozen)
            and audit['map_hashes']==[fingerprint(m) for m in maps],'Orientation audit binding differs')
    views={tuple(v['key']):deepcopy(v) for v in frozen['part_views']}
    native={(m['article_id'],k['knowledge_id']):k for m in maps for k in m['graph']['knowledge']}
    catalog={m['article_id']:m for m in maps}; case_index={c['case_id']:c for c in cases}
    require(len(case_index)==len(cases),'Repeated orientation case')
    outputs, proofs, seen={},[],set()
    for entry in audit['entries']:
        cid=entry['case_id']; require(cid in case_index and cid not in seen,'Unknown or repeated orientation case');seen.add(cid)
        case=case_index[cid]; m=catalog[case['article_id']]
        require(entry['case_sha256']==fingerprint(case) and entry['source_sha256']==m['source']['sha256'],'Orientation case changed')
        selected=[views[tuple(case[f]['key'])] for f in ('method','measurement','result')]
        method,measurement,result=selected
        for field,v,origin in zip(('method','measurement','result'),selected,('primary_method','primary_method','primary_result')):
            require(fingerprint(v)==fingerprint(case[field]) and v['key'][0]==case['article_id']
                    and v['run_id']==m['run_id'] and case['primary_family']==origins['sources'][case['article_id']]['dataset_family'],
                    'Orientation case does not match the exact sealed part')
            p=v['projection_proof']; key=tuple(v['native_key'])
            require(p['complete_native_knowledge']==native[key] and p['view_frame_sha256']==fingerprint(v['frame'])
                    and p['origin']['origin']==origin and p['origin'] in origins['knowledge'][key]['statements'],
                    'Orientation part lost its source or origin')
            require(v['frame']['logic']=='single' and len(v['frame']['statements'])==1,'Orientation needs licensed single parts')
            s=v['frame']['statements'][0]
            require(not s['negated'] and s['scope']['modality'] is None and s['scope']['quantifier'] is None,'Negation/modality needs another orientation operator')
        require(all(v['frame']['kind']=='action' and v['frame']['action_status']=='performed' for v in selected[:2])
                and result['frame']['kind']=='state' and result['frame']['action_status'] is None,'Wrong action/result status')
        mr={r['role']:r['value'] for r in method['frame']['statements'][0]['roles']}
        qr={r['role']:r['value'] for r in measurement['frame']['statements'][0]['roles']}
        rr={r['role']:r['value'] for r in result['frame']['statements'][0]['roles']}
        require(all(mr.get(r)==rr.get(r) and mr.get(r) is not None for r in ('population','intervention','challenge','comparator'))
                and all(mr.get(r)==qr.get(r) for r in ('population','challenge')),'Orientation crosses participants or comparisons')
        require(entry['source_outcome']==rr['outcome'] and entry['source_measure']==qr['outcome']
                and entry['property_label'] and entry['orientation']=='higher_is_worse' and entry['effect']=='improved',
                'Unlicensed outcome-property bridge')
        allowed={uid for v in selected for s in native[tuple(v['native_key'])]['semantic_frame']['statements'] for uid in s['provenance']['unit_ids']}
        for e in (*entry['order_evidence'],*entry['bridge_evidence'],*entry['scale_caveat_evidence']): _quote(e,m['source'],allowed)
        require(entry['order_evidence'] and entry['bridge_evidence'],'Orientation needs instrument and outcome evidence')
        # Числа используются только для порядка якорей; пропорциональность баллов не утверждается.
        points=entry['anchors']; require(len(points)>=2,'At least two ordered source anchors required')
        values=[decimal(p['value']) for p in points]
        require(all(v.is_finite() for v in values) and values==sorted(set(values)),'Invalid or unordered measurement anchors')
        for p in points:
            require(isinstance(p['value'],str) and p['source_fragment'].startswith(p['value']+',')
                    and p['meaning_ru'] and any(p['source_fragment'] in e['text'] for e in entry['order_evidence']), 'Anchor lacks exact source fragment')
        direction=ordered_direction(entry['effect'],entry['orientation']); require(direction=='lower','This source bridge has no lower-burden direction')
        require(result['frame']['statements'][0]['predicate'] in {'reduced after intervention','improved after intervention'},'Effect predicate not licensed')
        proof={'case_id':cid,'source_case':deepcopy(case),'entry':deepcopy(entry),
            'direction':direction,'property_label':entry['property_label'],'method_preserved':deepcopy(method),
            'complete_measurement_frame':deepcopy(measurement['frame']),'complete_result_frame':deepcopy(result['frame']),
            'participants_or_context_changed':False,'numerical_attributes_changed':False,
            'scale_equivalence_asserted':False,'complete_fact_equivalence':False,'effect_size_converted':False,
            'all_times_or_animals_asserted':False,'new_observation':False,'expert_validated':False,
            'status':'source_bound_coarse_property_abstraction'}
        proof['id']=fingerprint(proof); proofs.append(proof)
        for kind,v in (('measurement',measurement),('result',result)):
            projected=deepcopy(v); s=projected['frame']['statements'][0]
            for r in s['roles']:
                if r['role']=='outcome': r['value']=entry['property_label']
            if kind=='result': s['predicate']='reduced after intervention'
            # Одинаковое определение измерения в двух режимах не порождает двух одинаковых вхождений.
            identity=fingerprint({'version':VERSION,'native_key':v['native_key'],'kind':kind,'frame':projected['frame']})
            key=(v['key'][0],'orientation-view:'+identity)
            if key in outputs:
                outputs[key]['projection_proof']['orientation_evidence_ids'].append(proof['id'])
                outputs[key]['projection_proof']['source_part_keys'].append(list(v['key']))
                outputs[key]['projection_proof']['id']=fingerprint({k:x for k,x in outputs[key]['projection_proof'].items() if k!='id'})
                continue
            p=projected['projection_proof'];p.pop('id',None)
            p['measurement_orientation']={'version':VERSION,'kind':kind,'source_key':list(v['key']),
                'source_frame_sha256':fingerprint(v['frame']),'complete_input_frame':deepcopy(v['frame']),
                'property_label':entry['property_label'],'full_fact_equivalence':False,'scale_equivalence':False}
            p['orientation_evidence_ids']=[proof['id']];p['source_part_keys']=[list(v['key'])]
            p['view_frame_sha256']=fingerprint(projected['frame']);p['id']=fingerprint(p)
            projected['key']=key;outputs[key]=projected
    return outputs,proofs


def analyze(previous,frozen,maps,origin_audit,cases,audit):
    require(previous['version']=='source-bound-interval-knowledge-2' and previous['run_id']==fingerprint(previous['binding'])
            and previous['binding']['source_sha256']==fingerprint(frozen),'Orientation upstream differs')
    origins=validate_origins(maps,origin_audit);require(origins is not None,'Complete orientation origin audit required')
    additions,proofs=project(frozen,maps,cases,origins,audit)
    base={tuple(v['key']):deepcopy(v) for v in frozen['part_views']}
    base.update({tuple(v['key']):deepcopy(v) for v in previous['projected_views']})
    enhanced={**base,**additions}
    known={protocol_frame_identity(v['frame']) for v in (*base.values(),*enhanced.values())}
    # Известные части неразобранных родителей также не считаются новыми выводами.
    from domain.comparison_normalization import normalize_map
    for m in maps:
        for k in normalize_map(m):
            for s in k['statements']:
                atom={n:deepcopy(s[n]) for n in ('predicate','roles','scope','attributes','negated')}
                known.add(protocol_frame_identity({'kind':k['kind'],'action_status':k['action_status'],'logic':'single','statements':[atom]}))
    policies={}
    for name,views in (('before_measurement_orientation',base),('source_bound_measurement_orientation',enhanced)):
        modes=_learn_modes(views,maps,origins,frozen['binding']['families'],known)
        for mode,row in modes.items():
            if 'learning' not in row: continue
            # Диагностическая структура не разрешает удалять ограничения при выводе.
            row['guard_barriers']=guard_barriers([*row['rules'],*row['learning']['unsupported_rules']],
                {k:{**v,'key':k,'native_key':tuple(v['native_key'])} for k,v in views.items()},origins)
        policies[name]=modes
    for mode,row in previous['policies']['source_bound_interval_summary'].items():
        if 'learning' in row:require(fingerprint(row['learning'])==fingerprint(policies['before_measurement_orientation'][mode]['learning']),
                                   'Orientation baseline learning changed')
    return {'version':VERSION,'question':None,'canonical_blocks':previous['canonical_blocks'],
        'semantic_statements':previous['semantic_statements'],'input_parts':len(base),'oriented_parts':len(enhanced),
        'orientation_views':list(additions.values()),'orientation_proofs':proofs,'policies':policies,
        'input_coverage':deepcopy(previous['coverage']),'baseline_learning_reproduced':True,
        'model_calls':0,'target_read':False,'independent_future_validation':False,'scientific_success':False,
        'graph_advantage_demonstrated':False,'expert_validated':False}
