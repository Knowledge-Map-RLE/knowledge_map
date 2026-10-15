"""Качественные направления и статистические выводы сравниваются раздельно."""
from collections import defaultdict,Counter
from domain.article_maps import require,fingerprint

VERSION='qualitative-relation-transfer-1'
POLICY={'max_candidates':20,'minimum_cohorts':2,'question':None,
        'scope':'Retrospective source-only transfer of known qualitative patterns',
        'novel_scientific_predictions':False,'forecast_significance':False,'forecast_causality':False}
DIRECTIONS={'higher','lower','equal','mixed','no_clear_pattern','unspecified'}
FINDINGS={'detected','not_detected','not_reported'}
FIELDS={'id','source_id','family_id','knowledge_id','kind','knowledge_kind','phenotype','factor','contrast','estimand',
        'context','result','semantic_frame','provenance','author','expert_validated'}


def validate_claim(c):
    require(isinstance(c,dict) and set(c)==FIELDS,'Unexpected qualitative claim fields')
    require(all(isinstance(c[k],str) and c[k] for k in ('id','source_id','family_id','knowledge_id','phenotype','contrast','estimand')),'Claim identity missing')
    require(c['factor'] in {'age','sex','education'} and c['kind']=='state' and c['knowledge_kind']=='observation','Unsupported qualitative observation')
    require(set(c['result'])=={'direction','statistical_finding','causal_status'},'Unexpected result fields')
    require(c['result']['direction'] in DIRECTIONS and c['result']['statistical_finding'] in FINDINGS,'Unknown qualitative label')
    require(c['result']['causal_status']=='observational','Causality must not be asserted')
    require(set(c['context'])=={'critical','moderators','analysis'} and all(isinstance(v,dict) for v in c['context'].values()),'Missing typed context')
    require(c['context']['analysis']['causal_identification'] is False,'Unestablished causal identification')
    frame=c['semantic_frame'];require(frame['logic']=='conjunction' and len(frame['statements'])==2,'Both result layers must be retained')
    for statement,(predicate,value) in zip(frame['statements'],[('reported_association_direction',c['result']['direction']),('reported_statistical_finding',c['result']['statistical_finding'])]):
        require(statement=={'predicate':predicate,'roles':{'exposure':c['factor'],'outcome':c['phenotype']},'value':value,'modality':'reported','negated':False},'Semantic frame differs from result')
    require(isinstance(c['provenance'],list) and c['provenance'] and all(isinstance(v,str) and v for v in c['provenance']),'Source provenance missing')
    require(c['expert_validated'] is False and c['author']=='Codex','Unexpected annotation status')


def signature(c):
    return tuple(c[k] for k in ('factor','contrast','phenotype','estimand'))


def compare_claims(a,b):
    validate_claim(a);validate_claim(b)
    differences={k:{'left':a[k],'right':b[k]} for k in ('factor','contrast','phenotype','estimand') if a[k]!=b[k]}
    contexts={section:{key:{'left':a['context'][section].get(key),'right':b['context'][section].get(key)}
              for key in sorted(set(a['context'][section])|set(b['context'][section]))
              if a['context'][section].get(key)!=b['context'][section].get(key)}
              for section in ('critical','moderators','analysis')}
    unknown={section:sorted(k for c in (a,b) for k,v in c['context'][section].items() if v is None)
             for section in ('critical','moderators','analysis')}
    da,db=a['result']['direction'],b['result']['direction'];sa,sb=a['result']['statistical_finding'],b['result']['statistical_finding']
    if 'factor' in differences or 'contrast' in differences:relation='different_relation'
    elif 'phenotype' in differences:relation='different_phenotype'
    elif 'estimand' in differences:relation='different_estimand'
    elif da!='unspecified' and db!='unspecified' and da!=db:relation='direction_disagreement'
    elif sa!=sb and 'not_reported' not in {sa,sb}:relation='statistical_disagreement'
    elif da=='unspecified' or db=='unspecified' or sa!=sb:relation='partial_pattern'
    else:relation='same_pattern'
    # Равные исходы разных когорт означают сходство паттерна, а не тождество фактов.
    equivalent=bool(a['family_id']==b['family_id'] and a['source_id']==b['source_id'] and a['context']==b['context']
                    and not any(unknown.values()) and signature(a)==signature(b) and a['result']==b['result'])
    return {'relation':relation,'direction_agreement':da==db if 'unspecified' not in {da,db} else None,
            'statistical_agreement':sa==sb if 'not_reported' not in {sa,sb} else None,
            'identity_differences':differences,'context_differences':contexts,'unknown_context':unknown,
            'scientific_fact_equivalence':equivalent,'logical_contradiction':False,
            'independent_cohorts':len({a['family_id'],b['family_id']}),'numeric_effect_compared':False}


def candidate(key,direction,records,mode):
    return {'id':fingerprint({'signature':key,'direction':direction,'mode':mode}),
            'signature':dict(zip(('factor','contrast','phenotype','estimand'),key)),
            'expected_direction':direction,'expected_significance':None,'causal':False,
            'status':'transfer_hypothesis_of_known_pattern' if mode=='semantic' else 'known_pattern_baseline',
            'novel_claim':False,'cohorts':sorted({r['family_id'] for r in records}),
            'premise_ids':[r['id'] for r in sorted(records,key=lambda r:r['id'])],
            'premises':sorted(records,key=lambda r:r['id'])}


def forecast_fold(fold):
    require(set(fold)=={'fold_id','withheld_family','training'},'Unexpected forecast input fields')
    records=fold['training'];require(len({c['id'] for c in records})==len(records),'Duplicate claim')
    for c in records:
        validate_claim(c);require(c['family_id']!=fold['withheld_family'],'Withheld cohort leaked')
    grouped=defaultdict(list)
    for c in records:grouped[signature(c)].append(c)
    semantic=[];known=[];frequency=[];diagnostics=[]
    for key,group in sorted(grouped.items()):
        eligible=[c for c in group if c['result']['statistical_finding']=='detected' and c['result']['direction'] in {'higher','lower'}]
        votes=defaultdict(set)
        for c in eligible:votes[c['family_id']].add(c['result']['direction'])
        signs={direction for v in votes.values() for direction in v}
        admitted=len(votes)>=POLICY['minimum_cohorts'] and len(signs)==1
        if admitted:semantic.append(candidate(key,next(iter(signs)),eligible,'semantic'))
        diagnostics.append({'signature':dict(zip(('factor','contrast','phenotype','estimand'),key)),
                            'detected_cohort_votes':dict(votes),'admitted':admitted,
                            'reason':'admitted' if admitted else 'opposing_detected_directions' if len(signs)>1 else 'insufficient_independent_detected_support',
                            'nondetections':[c['id'] for c in group if c['result']['statistical_finding']=='not_detected']})
        all_votes=defaultdict(set)
        for c in group:
            if c['result']['direction']!='unspecified':all_votes[c['result']['direction']].add(c['family_id'])
        for direction,families in sorted(all_votes.items()):
            known.append(candidate(key,direction,[c for c in group if c['result']['direction']==direction],'known_union'))
        ranking=sorted(all_votes,key=lambda d:(-len(all_votes[d]),d))
        if ranking and (len(ranking)==1 or len(all_votes[ranking[0]])>len(all_votes[ranking[1]])):
            direction=ranking[0];frequency.append(candidate(key,direction,[c for c in group if c['result']['direction']==direction],'frequency'))
    def rank(items):return sorted(items,key=lambda c:(-len(c['cohorts']),c['id']))[:POLICY['max_candidates']]
    for d in diagnostics:d['detected_cohort_votes']={k:sorted(v) for k,v in d['detected_cohort_votes'].items()}
    return {'fold_id':fold['fold_id'],'withheld_family':fold['withheld_family'],
            'predictions':{'semantic':rank(semantic),'known_union':rank(known),'frequency':rank(frequency)},
            'diagnostics':diagnostics,'training_records':len(records)}


def evaluate_fold(fold,controls):
    for c in controls:validate_claim(c);require(c['family_id']==fold['withheld_family'],'Wrong held-out cohort')
    modes={}
    for mode,patterns in fold['predictions'].items():
        rows=[]
        for c in controls:
            matches=[p for p in patterns if p['signature']==dict(zip(('factor','contrast','phenotype','estimand'),signature(c)))]
            directions={p['expected_direction'] for p in matches}
            if not matches:status='not_addressed'
            elif len(directions)!=1:status='ambiguous_known_patterns'
            elif c['result']['statistical_finding']!='detected' or c['result']['direction']=='unspecified':status='uncertain'
            elif c['result']['direction']==next(iter(directions)):status='qualitative_pattern_match'
            else:status='inconsistent_transfer'
            rows.append({'id':c['id'],'status':status,'pattern_ids':[p['id'] for p in matches],
                         'expected_directions':sorted(directions),'observed_result':c['result'],
                         'scientific_fact_equivalence':False,'future_prediction':False,
                         'context_audits':[{'source_id':r['source_id'],'comparison':compare_claims(r,c)} for p in matches for r in p['premises']]})
        # Полные контексты источников остаются в зафиксированных гипотезах, контекст цели — в контролях.
        modes[mode]={'rows':rows,'counts':dict(Counter(r['status'] for r in rows)),'candidate_count':len(patterns)}
    return {'fold_id':fold['fold_id'],'modes':modes}
