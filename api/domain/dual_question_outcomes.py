"""Два исхода опыта: знак наблюдаемой оценки и отдельно статистическая обнаружимость."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal,InvalidOperation

from domain.article_maps import fingerprint,require
from domain.qualitative_question_prediction import (
    IDENTITY,eligible,question_matches,learn_rules,qualitative_projection,prepare_observations,
)
from domain.question_prediction import generate_question_candidates,ForecastQuestion
from domain.research_semantics import context_value
from domain.structured_question_context import StructuredQualitativeEngine,compare_features,structured_projection

VERSION='dual-question-outcomes-1'
TRANSPORT_FIELDS={'version','kind','minimum_age_years','minimum_protocol_years','min_families',
                  'transported_features','confirmatory','scope_ru','scope_en'}
TRANSPORTED=['age','dementia_entry','mci','baseline_score','exposure','outcome','followup','adjustments','model','alpha','sample_size']


def validate_transport(raw):
    require(set(raw)==TRANSPORT_FIELDS,'Transport policy fields differ')
    require(raw['version']=='il6-point-direction-transport-1' and raw['kind']=='unvalidated_cross_study_hypothesis'
            and raw['confirmatory'] is False,'Exploratory transport cannot claim confirmation')
    require(type(raw['minimum_age_years']) is int and raw['minimum_age_years']==60
            and type(raw['minimum_protocol_years']) is int and raw['minimum_protocol_years']==2
            and type(raw['min_families']) is int and raw['min_families']>=2,'Explicit bounded question scope required')
    require(raw['transported_features']==TRANSPORTED and bool(raw['scope_ru']) and bool(raw['scope_en']),
            'All transported context dimensions must be disclosed')
    return deepcopy(raw)


def point_direction(claim,policy):
    """Знак оценки не зависит от p и не становится доказательством истинного направления эффекта."""
    if claim.negated or claim.unresolved or claim.action_status not in (None,'performed') or claim.logic!='single':
        return {'label':None,'reason':'unsupported_negation_action_or_logic','supported_direction':False}
    rules={(r['name'],r['unit']):r for r in policy.measurement_rules}
    directions=set();interval_support=[];details=[]
    for m in claim.measurements:
        if m['name'] in policy.symbolic_directions:
            label=policy.symbolic_directions[m['name']].get(str(m['value'])) if m['unit']=='categorical' else None
            if not label:return {'label':None,'reason':'invalid_symbolic_direction','supported_direction':False}
            directions.add(label)
            details.append({'measurement':m,'reference':None,'ci':None,'basis':'explicit_author_direction'})
            interval_support.append(claim.modality=='statistically detected')
            continue
        rule=rules.get((m['name'],m['unit']))
        if not rule:continue
        try:value=Decimal(str(m['value']))
        except InvalidOperation:continue
        if not value.is_finite():continue
        reference=Decimal(1) if m['name'] in {'hazard ratio','odds ratio','risk ratio'} else Decimal(0)
        if reference==1 and value<=0:continue
        label='zero_point_estimate' if value==reference else 'positive_association' if (value>reference)==rule['higher_means_decline'] else 'inverse_association'
        directions.add(label)
        ci=next((v for v in claim.measurements if v['name']==m['name']+' ci' and v['unit']==m['unit']),None)
        supported=False;ci_status='not_reported'
        if ci:
            try:
                require(isinstance(ci['value'],list) and len(ci['value'])==2,'Direction CI must have two endpoints')
                lo,hi=map(lambda x:Decimal(str(x)),ci['value'])
                require(lo.is_finite() and hi.is_finite() and lo<=value<=hi,'Invalid direction interval')
                require(reference!=1 or lo>0,'Ratio CI must be positive')
                supported=hi<reference if value<reference else lo>reference
                ci_status='excludes_reference' if supported else 'includes_reference'
            except (InvalidOperation,TypeError):return {'label':None,'reason':'invalid_direction_interval','supported_direction':False}
        details.append({'measurement':m,'reference':str(reference),'ci':ci,'ci_status':ci_status})
        interval_support.append(supported)
    if len(directions)!=1:
        return {'label':None,'reason':'direction_missing_or_conflicting','supported_direction':False,'details':details}
    # ДИ может не учитывать более строгую авторскую поправку на множественные проверки.
    return {'label':directions.pop(),'reason':'reported_estimate_direction',
            'supported_direction':all(interval_support) and claim.modality=='statistically detected',
            'details':details,'statistical_modality':claim.modality,'biological_direction_proved':False}


def transport_scope(profile,transport):
    """Неизвестные модификаторы видны как риск гипотезы; обязательные якоря нельзя додумывать."""
    blockers=[]
    age=profile['age'];entry=profile['dementia_entry'];exposure=profile['exposure'];followup=profile['followup']
    if age['status']!='known' or Decimal(age['value']['minimum']['value'])<transport['minimum_age_years']:
        blockers.append('age_outside_bounded_question')
    if entry['status']!='known' or entry['value'].get('excluded') is not True:blockers.append('baseline_dementia_exclusion_unknown')
    if exposure['status']!='known' or exposure['value'].get('specimen')!='plasma' or exposure['value'].get('timing')!='single_baseline':
        blockers.append('single_baseline_plasma_not_established')
    durations=[]
    if followup['status']=='known':
        for key in ('protocol','nominal','maximum_protocol'):
            q=followup['value'].get(key)
            if isinstance(q,dict) and q.get('unit')=='year':durations.append(Decimal(q['value']))
    if not durations or max(durations)<transport['minimum_protocol_years']:blockers.append('followup_protocol_not_established')
    return {'eligible':not blockers,'blockers':blockers,'unknown_features':compare_features(profile,profile)['unknown'],
            'individual_minimum_followup_guaranteed':False,'context_equivalence_confirmed':False,
            'assumption':'protocol_duration_and_broad_question_scope_only'}


def directional_views(claims,profiles,question,policy,transport):
    views={};rows=[]
    for key,c in sorted(claims.items()):
        require(c.evidence.available_on<=question.cutoff,'Training direction leaks future date')
        if c.evidence.presentation!='own_result' or not c.evidence.family or not question_matches(c.proposition,question):continue
        prior,_=qualitative_projection(c,policy)
        # Состав ранее проверенных результатов фиксирован: новый опыт не расширяет корпус или извлечение.
        if prior is None:continue
        require(key in profiles,'Missing direction context; no fallback')
        direction=point_direction(c,policy);scope=transport_scope(profiles[key]['normalized'],transport)
        row={'reference':list(key),'original':c.to_dict(),'direction':direction,'transport_scope':scope}
        rows.append(row)
        if direction['label'] is None or not scope['eligible'] or not eligible(c):continue
        context=dict(c.context)
        context['measure']=context_value('global cognitive decline under exploratory estimand transport')
        for field in ('stratum','conditions'):context[field]=context_value('exploratory_transport:'+fingerprint(transport))
        # Числа не объявляются эквивалентными: они целиком остаются в original и профиле применения.
        views[key]=replace(c,modality=direction['label'],context=context,measurements=())
    return views,rows


class DualOutcomeEngine(StructuredQualitativeEngine):
    def __init__(self,profiles,transport):
        super().__init__(profiles)
        self.transport=validate_transport(transport)
        self.analysis_binding={**self.analysis_binding,'workflow_version':'dual-question-workflow-1',
                               'outcomes_version':VERSION,'transport_sha256':fingerprint(self.transport)}

    def fit(self,claims,episodes,maps,question,policy):
        require(policy.min_families==self.transport['min_families'],'Support policies differ')
        base=super().fit(claims,episodes,maps,question,policy)
        statistical_modes,statistical_rules=deepcopy(base['modes']),deepcopy(base['rules'])
        raw_views,_=prepare_observations(claims,question,policy)
        binary_views={k:replace(structured_projection(v,self.profiles[k]['normalized']),
                         modality='statistically_detected' if claims[k].modality=='statistically detected' else 'not_statistically_detected')
                      for k,v in raw_views.items()}
        def exact_context(a,b):
            result=compare_features(self.profiles[a.evidence.article_id,a.claim_id]['normalized'],self.profiles[b.evidence.article_id,b.claim_id]['normalized'])
            return ['unknown:'+k for k in result['unknown']]+['feature:'+d['feature'] for d in result['differences']]
        for mode in ('semantic','dependency'):
            learned,_=learn_rules(claims,binary_views,episodes,maps,question,policy,mode=='dependency',context_check=exact_context)
            candidates,_=generate_question_candidates(binary_views,learned,question)
            candidates=[c for c in candidates if not set(c['abstracted_context_fields'])-IDENTITY]
            for c in candidates:
                c.update(finding=c['proposition']['modality'],status='strict_statistical_detection_hypothesis',
                         application_features=deepcopy(self.profiles[c['premises'][0]['evidence']['article_id'],c['premises'][0]['claim_id']]['normalized']))
            statistical_modes[mode]=candidates;statistical_rules[mode]=learned
        views,rows=directional_views(claims,self.profiles,question,policy,self.transport)
        modes={};rules={};diagnostics={}
        for mode in ('semantic','dependency'):
            learned,stats=learn_rules(claims,views,episodes,maps,question,policy,mode=='dependency')
            candidates,bounded=generate_question_candidates(views,learned,question)
            candidates=[c for c in candidates if not set(c['abstracted_context_fields'])-IDENTITY]
            for c in candidates:
                c.update(status='exploratory_reported_direction_hypothesis',finding=c['proposition']['modality'],
                         numerical_evidence=[claims[p['evidence']['article_id'],p['claim_id']].to_dict() for p in c['premises']],
                         transport_policy=deepcopy(self.transport),confirmation_eligible=False,
                         source_profiles=[deepcopy(self.profiles[p['evidence']['article_id'],p['claim_id']]) for p in c['premises']])
            modes[mode]=candidates;rules[mode]=learned;diagnostics[mode]={**stats,'bounded_searches':bounded}
        # Новая гипотеза и частотная база имеют разные происхождение и результаты.
        frequencies={}
        for row in rows:
            label=row['direction']['label']
            if not label or not row['transport_scope']['eligible']:continue
            f=frequencies.setdefault(label,{'finding':label,'families':set(),'evidence':[]})
            f['families'].add(row['original']['evidence']['family']);f['evidence'].append(row['reference'])
        family_labels={}
        for key,view in views.items():family_labels.setdefault(view.evidence.family,set()).add(view.modality)
        votes={};ambiguous=[]
        for family,labels in sorted(family_labels.items()):
            if len(labels)==1:votes[family]=next(iter(labels))
            else:ambiguous.append(family)
        counts={label:sum(v==label for v in votes.values()) for label in sorted(set(votes.values()))}
        best=max(counts.values(),default=0);winners=[label for label,count in counts.items() if count==best]
        modes['family_frequency_baseline']=[]
        if len(winners)==1 and len(votes)>=policy.min_families:
            label=winners[0];anchor=next(iter(views.values()));prop=anchor.proposition
            prop={**prop,'context':{k:v for k,v in prop['context'].items() if k not in IDENTITY},'modality':label}
            modes['family_frequency_baseline']=[{'id':fingerprint(prop),'status':'family_majority_baseline',
                'finding':label,'proposition':prop,'family_votes':votes,'ambiguous_families_excluded':ambiguous,
                'confirmation_eligible':False,'support':len(votes),'ranking_score':best/len(votes)}]
        base['outcome_channels']={'statistical_detection_strict':{'modes':statistical_modes,'rules':statistical_rules,
                                  'finding_semantics':'source_statistical_detection_with_exact_context'},
            'reported_direction_exploratory':{'modes':modes,'rules':rules,'diagnostics':diagnostics,'observations':rows,
             'frequency_baseline':[{'status':'descriptive_family_frequency',**r,'families':sorted(r['families'])} for _,r in sorted(frequencies.items())],
             'family_votes':votes,'ambiguous_families_excluded':ambiguous,
             'transport_policy':deepcopy(self.transport),'min_independent_support':policy.min_families,
             'confirmation_eligible':False,'point_sign_is_not_biological_truth':True}}
        return base

    def evaluate(self,sealed,targets):
        # Общая оценка сначала проверяет даты, семейства и строгий статистический канал.
        result=super().evaluate(sealed,targets)
        from domain.qualitative_question_prediction import QualitativePolicy
        q=ForecastQuestion.parse(sealed['question']);policy=QualitativePolicy.parse(sealed['policy'],q)
        target_rows=[]
        for c in sorted(targets,key=lambda c:(c.evidence.article_id,c.claim_id)):
            if c.evidence.presentation!='own_result' or not question_matches(c.proposition,q):continue
            p,_=qualitative_projection(c,policy)
            if not p:continue
            key=(c.evidence.article_id,c.claim_id);require(key in self.profiles,'Missing heldout direction context')
            target_rows.append({'reference':list(key),'original':c.to_dict(),'direction':point_direction(c,policy),
                                'transport_scope':transport_scope(self.profiles[key]['normalized'],self.transport)})
        evaluated={}
        for mode,candidates in sealed['outcome_channels']['reported_direction_exploratory']['modes'].items():
            rows=[]
            for candidate in candidates:
                for target in target_rows:
                    c=target['original'];p=candidate['proposition'];d=target['direction']
                    same_logic=all(c[k]==p[k] for k in ('predicate','roles','negated','quantifier','action_status','logic'))
                    scorable=bool(d['label']) and target['transport_scope']['eligible'] and same_logic
                    status='point_sign_agreement' if scorable and d['label']==candidate['finding'] else 'different_point_sign' if scorable else 'unscorable'
                    rows.append({'prediction_id':candidate['id'],'target':target['reference'],'status':status,
                                 'predicted':candidate['finding'],'observed':d['label'],'supported_target_direction':d['supported_direction'],
                                 'direction_evidence':d,'transport_scope':target['transport_scope'],
                                 'true_biological_direction_confirmed':False})
            scored=[r for r in rows if r['status']!='unscorable'];correct=sum(r['status']=='point_sign_agreement' for r in scored)
            families=sorted({t['original']['evidence']['family'] for t in target_rows if t['direction']['label']})
            evaluated[mode]={'issued_answers':len(candidates),'claim_comparisons':len(rows),'scorable_comparisons':len(scored),
                             'agreements':correct,'different_signs':sum(r['status']=='different_point_sign' for r in scored),
                             'point_sign_agreement_rate':correct/len(scored) if scored else None,'target_families':families,
                             'supported_target_comparisons':sum(r['supported_target_direction'] for r in scored),'results':rows,
                             'multiple_estimates_are_not_independent_trials':True,'confirmation_eligible':False}
        binary_evaluations=deepcopy(result['modes'])
        for mode in ('semantic','dependency'):
            answers=[]
            for prediction in sealed['outcome_channels']['statistical_detection_strict']['modes'][mode]:
                matches=[]
                for target in target_rows:
                    c=target['original'];p=prediction['proposition'];profile=self.profiles[tuple(target['reference'])]['normalized']
                    same_logic=all(c[k]==p[k] for k in ('predicate','roles','negated','quantifier','action_status','logic'))
                    compatible=compare_features(prediction['application_features'],profile)['transfer_authorized'] and same_logic
                    observed='statistically_detected' if c['modality']=='statistically detected' else 'not_statistically_detected'
                    matches.append({'target':target['reference'],'status':'context_mismatch' if not compatible else
                                    'qualitative_agreement' if observed==prediction['finding'] else 'different_statistical_finding'})
                agree=any(m['status']=='qualitative_agreement' for m in matches);differ=any(m['status']=='different_statistical_finding' for m in matches)
                answers.append({'id':prediction['id'],'status':'mixed' if agree and differ else 'agreement' if agree else 'different_finding' if differ else 'abstain_or_incompatible','matches':matches})
            scored=lambda rows:[r for r in rows if r['status'] in {'agreement','different_finding','mixed'}]
            binary_evaluations[mode]={'issued_answers':len(answers),'agreements':sum(a['status']=='agreement' for a in answers),
                'different_findings':sum(a['status']=='different_finding' for a in answers),'results':answers,'scorable_answers':len(scored(answers)),
                'agreement_at_k':{str(k):sum(a['status']=='agreement' for a in answers[:k])/len(scored(answers[:k])) if scored(answers[:k]) else None for k in (1,5,10)}}
        result['outcome_channels']={'reported_direction_exploratory':{'modes':evaluated,'targets':target_rows},
                                   'statistical_detection_strict':{'modes':binary_evaluations}}
        return result
