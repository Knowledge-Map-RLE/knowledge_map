"""Составляет ретроспективные разбиения из проверенных первичных знаний."""
from collections import defaultdict
from dataclasses import fields

from domain.article_maps import fingerprint, require
from domain.cohort_transfer import RateContext, RateObservation, RateQuery
from domain.primary_pdf_rates import normalize_rate, audit_review, VERSION


def prepare_primary_transfer(annotation, evidence, legacy, source_bindings):
    profiles=annotation['profiles']; rates=annotation['rates']
    require(len({r['id'] for r in rates})==len(rates), 'Duplicate source measurement')
    observations=[];series=defaultdict(list);labels={};frames={}
    for rate in rates:
        normalized=normalize_rate(rate)
        require(rate['source_id'] in profiles, 'Unknown primary source')
        if rate['selection']!='repair':continue
        profile=profiles[rate['source_id']];study=profile['study'];family=profile['cohort']
        context={f.name:None for f in fields(RateContext)}
        context.update(study_id=study,family_id=family,endpoint=rate['endpoint'],
            measure='incidence_rate',unit='per1000personyears',design='longitudinal',
            criteria=profile['criteria']+'; phenotype: '+rate['phenotype']+'; age basis: '+profile['age_basis'],
            threshold_sd=profile['threshold_sd'],dementia_exclusion='dementia excluded at baseline',
            norms=profile['norms'],followup_years=profile['followup'],followup_kind='source-specific description',
            country=profile['country'],attrition_adjustment=profile['estimand'],sample_n=profile['riskset'])
        obs={'id':rate['id'],'context':context,'age':rate['age'],
             'value':normalized['value'],'interval':normalized['interval'],
             'evidence_ids':[rate['source_id']+':table']}
        RateObservation.parse(obs);observations.append(obs);series[(rate['source_id'],rate['endpoint'])].append(obs)
        frames[rate['id']]={**{k:profile[k] for k in ('age_basis','riskset','criteria','threshold_sd','norms','followup','country')},
                           'phenotype':rate['phenotype'],'estimand':rate['estimand']}
    audit=audit_review(rates,legacy,annotation['quarantined_review_ids'])
    controls={};folds=[]
    for index,family in enumerate(sorted({o['context']['family_id'] for o in observations}),1):
        training=[o for o in observations if o['context']['family_id']!=family];queries=[]
        for (source,endpoint),items in sorted(series.items()):
            if profiles[source]['cohort']!=family:continue
            items=sorted(items,key=lambda o:o['age'][0])
            for left,right in zip(items,items[1:]):
                qid='Q:'+profiles[source]['study'].replace(' ','-')+':'+endpoint+f":{left['age'][0]}-{right['age'][0]}"
                query={'id':qid,'context':left['context'],'ages':[left['age'],right['age']],
                       'evidence_ids':[source+':title']}
                RateQuery.parse(query);queries.append(query)
                labels[qid]={'ru':profiles[source]['study']+f" · {endpoint} · {query['ages']}",
                             'en':profiles[source]['study']+f" · {endpoint} · {query['ages']}"}
                controls[qid]={'values':[left['value'],right['value']],
                    'intervals':[left['interval'],right['interval']],
                    'evidence_ids':left['evidence_ids'], 'family_id':family,
                    'ages':query['ages'],'context':query['context'],'label':labels[qid]}
        used={p for item in training+queries for p in item['evidence_ids']}
        # Входы удержанной когорты содержат только точные заголовки, без аннотаций и таблиц.
        require(all(evidence[p]['kind']=='title' for p in used if evidence[p]['cohort']==family), 'Hidden table leaked')
        fold={'fold_id':f'F{index}','withheld_family':family,'training':training,'queries':queries,
              'evidence':{p:evidence[p] for p in sorted(used)},'labels':{q['id']:labels[q['id']] for q in queries}}
        folds.append(fold)
    manifest={'contract_version':1,'folds':[{'path':f'fold-{i}.json','sha256':fingerprint(f),
        'withheld_family':f['withheld_family']} for i,f in enumerate(folds,1)],'source_bindings':source_bindings,
        'metadata':{'version':VERSION,'annotation_sha256':fingerprint(annotation),'author':'Codex','model_calls':0,
         'primary_tables_verified_by_Codex':True,'expert_validated':False,'known_sources_retrospective':True,
         'scientific_success':False,'selection':'Same review cells except three unverified Busse cells; supplemental rates excluded',
         'legacy_endpoint_aliases_are_not_equivalence':'MCI memory-specific and all-domain; aMCI inclusive memory versus single-domain retained in frames',
         'no_future_control_access':True,'LEILA_shared_cohort_confirmed':True}}
    hidden={'manifest_sha256':fingerprint(manifest),'controls':controls,
            'evidence':{k:v for k,v in evidence.items() if v['kind']=='table'},'author':'Codex','expert_validated':False}
    return {'folds':folds,'manifest':manifest,'hidden':hidden,'audit':audit,'frames':frames,
            'observations':observations,'query_count':len(controls)}
