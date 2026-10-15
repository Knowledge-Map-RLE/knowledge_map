"""Применимость гипотезы о порядке ставок по типизированной семантике."""
from collections import Counter,defaultdict

from domain.article_maps import require,fingerprint
from domain.cohort_transfer import RateObservation,RateQuery,witness_pairs

VERSION='incidence-transfer-scope-1'
VOCABULARY={
    'population':{'general_older_adults','parkinsons_clinical'},
    'residence':{'community','community_and_institutions'},
    'baseline_status':{'no_mci_no_dementia','no_dementia_mci_permitted'},
    'phenotype':{'any_mci','memory_involved_mci','nonmemory_mci','memory_defined_global_preserved'},
    'age_basis':{'baseline','attained'},
    'sex':{'all','female','male'},
    'measure':{'incidence_rate','cumulative_risk','prevalence'},
    'unit':{'per1000personyears'},
    'threshold_rule':{'sd1','sd1_5','clinical_consensus_approx_sd1','sd1_5_or_fcsrt24'},
    'norms':{'age_education','age_clinical_other_factors','age_education_ethnicity_sex'},
    'complaint_rule':{'self','self_or_informant','self_informant_or_examiner'},
    'function_rule':{'independent_basic_adl','sidam_adl_le1_of14','clinical_preserved_function',
                     'physical_but_not_cognitive_disability_allowed','fewer_than3_function_complaints'},
    'direct_dementia_policy':{'assumed_intermediate_mci','not_counted_as_mci'},
    'estimand':{'observed','age_sex_standardized_nonparticipation_weighted','mortality_imputed'},
}
MODERATORS={'country','calendar_period','followup','sample_size'}
POLICY={'version':VERSION,'critical_fields':sorted(VOCABULARY),'moderators':sorted(MODERATORS),
    'minimum_independent_cohorts':2,'unknown_critical':'block even if unknown on both sides',
    'different_critical':'block; no unvalidated bridges','same_age_bounds':'required; no implicit splitting or pooling',
    'decision':'unanimous order across at least two independent admitted cohorts',
    'claim':'conditional empirical hypothesis; not equivalence, deduction or clinical prediction',
    'selection':'all 30 previously registered queries; no replacement or outcome-guided selection'}


def validate_scope(scope):
    require(isinstance(scope,dict) and set(scope)=={'critical','moderators'},'Closed semantic scope required')
    c,m=scope['critical'],scope['moderators']
    require(isinstance(c,dict) and set(c)==set(VOCABULARY),'Missing or extra critical scope field')
    require(isinstance(m,dict) and set(m)==MODERATORS,'Missing or extra moderator field')
    for key,values in VOCABULARY.items():
        require(c[key] is None or isinstance(c[key],str) and c[key] in values,'Unknown categorical value: '+key)
    require(all(v is None or isinstance(v,str) and v.strip() for v in m.values()),'Invalid moderator value')


def compare_scope(source,target):
    validate_scope(source);validate_scope(target)
    matched=[];different=[];unknown=[];moderators=[]
    for field in sorted(VOCABULARY):
        a,b=source['critical'][field],target['critical'][field]
        row={'field':field,'source':a,'target':b}
        if a is None or b is None:unknown.append(row)
        elif a!=b:different.append(row)
        else:matched.append(field)
    for field in sorted(MODERATORS):
        a,b=source['moderators'][field],target['moderators'][field]
        if a is None or b is None or a!=b:
            moderators.append({'field':field,'source':a,'target':b,
                               'status':'unknown' if a is None or b is None else 'different'})
    return {'eligible':not different and not unknown,'matched':matched,'different':different,'unknown':unknown,
            'moderator_warnings':moderators,'equivalence_asserted':False,'empirical_transport_proven':False}


def infer_with_scope(query,witnesses,scopes):
    target_key=query.context.study_id+':'+query.context.endpoint
    require(target_key in scopes,'Query semantic scope missing')
    target=scopes[target_key]['scope'];validate_scope(target)
    audits=[];admitted=[]
    for w in witnesses:
        # Проверяем все серии, не выбирая по наблюдённому направлению результата.
        source_key=w['context'].study_id+':'+w['context'].endpoint
        require(source_key in scopes,'Training semantic scope missing')
        source=scopes[source_key]['scope'];comparison=compare_scope(source,target);reasons=[]
        if w['context'].family_id==query.context.family_id:reasons.append('same_cohort')
        if w['ages']!=query.ages:reasons.append('different_age_bounds')
        if comparison['different']:reasons.append('incompatible_critical_scope')
        if comparison['unknown']:reasons.append('unknown_critical_scope')
        a={'source_key':source_key,'cohort':w['context'].family_id,'observation_ids':w['observation_ids'],
           'ages':w['ages'],'eligible':not reasons,'reasons':reasons,'comparison':comparison,
           'source_provenance':scopes[source_key]['provenance'],
           'query_provenance':scopes[target_key]['provenance']}
        audits.append(a)
        if not reasons:
            admitted.append({**a,'order':w['order'],'evidence_ids':w['evidence_ids']})
    votes=defaultdict(list)
    for w in admitted:votes[w['cohort']].append(w['order'])
    family_votes={k:v[0] if len(set(v))==1 else 'mixed' for k,v in sorted(votes.items())}
    decision=None;reason='insufficient_independent_compatible_cohorts'
    if len(family_votes)>=POLICY['minimum_independent_cohorts']:
        if len(set(family_votes.values()))==1 and 'mixed' not in family_votes.values():
            decision=next(iter(family_votes.values()));reason=None
        else:reason='conflicting_admitted_orders'
    # Частотная база использует тот же допуск и минимум независимых когорт.
    frequency=None
    clear_votes=[v for v in family_votes.values() if v!='mixed']
    if len(clear_votes)>=POLICY['minimum_independent_cohorts']:
        ranks=Counter(clear_votes).most_common()
        if ranks and (len(ranks)==1 or ranks[0][1]>ranks[1][1]):frequency=ranks[0][0]
    return {'query_id':query.id,'ages':query.ages,'semantic_scope':target,'mode':'typed_guard',
        'order':decision,'status':'conditional_hypothesis' if decision else 'abstain','reason':reason,
        'family_votes':family_votes,'admitted':admitted,'candidate_audits':audits,
        'scope_frequency':{'query_id':query.id,'mode':'scope_frequency','order':frequency,
          'status':'frequency_hypothesis' if frequency else 'abstain'},
        'numeric_prediction':None,'causal':False,'statistical_significance_claimed':False,
        'equivalence_asserted':False,'model_calls':0}


def forecast_scoped_fold(fold,scopes):
    training=[RateObservation.parse(o) for o in fold['training']]
    queries=[RateQuery.parse(q) for q in fold['queries']]
    require(all(o.context.family_id!=fold['withheld_family'] for o in training),'Held-out cohort leaked')
    require(all(q.context.family_id==fold['withheld_family'] for q in queries),'Query outside withheld cohort')
    require(all((x.context.measure,x.context.unit,x.context.design)==
                ('incidence_rate','per1000personyears','longitudinal') for x in [*training,*queries]),
            'This operator supports longitudinal person-time incidence only')
    witnesses=witness_pairs(training)
    predictions=[infer_with_scope(q,witnesses,scopes) for q in queries]
    return {'fold_id':fold['fold_id'],'withheld_family':fold['withheld_family'],
            'predictions':predictions,'model_calls':0}


def evaluate_scoped(folds,controls):
    from domain.cohort_transfer import order
    ids={p['query_id'] for f in folds for p in f['predictions']}
    require(ids==set(controls),'Scope evaluation identities differ')
    result={}
    for mode in ['typed_guard','scope_frequency']:
        rows=[]
        for fold in folds:
            for item in fold['predictions']:
                p=item if mode=='typed_guard' else item['scope_frequency'];c=controls[p['query_id']]
                actual=order(*c['values']);issued=p['order'] is not None
                rows.append({'query_id':p['query_id'],'issued':issued,'predicted_order':p['order'],
                    'reported_order':actual,'matched':p['order']==actual if issued else None})
        issued=sum(r['issued'] for r in rows);matched=sum(r['matched'] is True for r in rows)
        result[mode]={'queries':len(rows),'issued':issued,'matched':matched,'wrong_order':issued-matched,
                     'abstained':len(rows)-issued,'accuracy_among_issued':matched/issued if issued else None,'rows':rows}
    return {'modes':result,'independent_success':False,'new_scientific_predictions':0,
            'warning':'Retrospective context diagnostic; abstention is not scientific predictive success'}
