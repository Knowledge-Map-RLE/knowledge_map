"""Эмпирическая гипотеза по вопросу: знак оценки и обнаружимость разделены."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from collections import defaultdict
from datetime import date
from math import isfinite
from domain.article_maps import require, fingerprint

VERSION = 'empirical-question-forecast-1'
QUESTION = 'baseline-plasma-il6-global-decline-2y-1'
CORE = ('age_min', 'dementia_excluded', 'specimen', 'timing', 'exposure', 'outcome_scope', 'followup_min')
FACETS = ('instrument', 'estimand', 'contrast', 'mci', 'adjustment_class')
CONTEXT = set(CORE + FACETS)
LABELS = {
    'direction': ('more_decline', 'less_decline', 'zero_point_estimate'),
    'detection': ('detected_more_decline', 'detected_less_decline', 'not_detected'),
}


def validate_context(raw):
    require(isinstance(raw, dict) and set(raw) == CONTEXT, 'Explicit question context fields required')
    for key, value in raw.items():
        if key in ('age_min', 'followup_min'):
            require(value is None or type(value) in (int, float) and isfinite(value) and value >= 0, 'Invalid core quantity')
        elif key == 'dementia_excluded':
            require(value is None or type(value) is bool, 'Dementia exclusion must be explicit')
        else:
            require(value is None or isinstance(value, str) and bool(value.strip()), 'Invalid categorical context')


def eligibility(context):
    validate_context(context)
    reasons = ['unknown:' + key for key in CORE if context[key] is None]
    checks = {'age_min': lambda v: v >= 60, 'followup_min': lambda v: v >= 2,
              'dementia_excluded': lambda v: v is True, 'specimen': lambda v: v == 'plasma',
              'timing': lambda v: v == 'single_baseline', 'exposure': lambda v: v == 'IL6', 'outcome_scope': lambda v: v == 'global_change'}
    reasons += ['mismatch:' + key for key in CORE if context[key] is not None and not checks[key](context[key])]
    return reasons


@dataclass(frozen=True)
class Observation:
    reference: str
    family: str
    available_on: str
    context: dict
    findings: dict
    binding: dict
    dependency_grounded: bool = False

    def validate(self):
        require(isinstance(self.reference, str) and bool(self.reference) and isinstance(self.family, str) and bool(self.family), 'Observation identity required')
        require(date.fromisoformat(self.available_on).isoformat() == self.available_on, 'Exact historical publication date required')
        validate_context(self.context)
        require(set(self.findings) == set(LABELS) and all(v is None or v in LABELS[k] for k, v in self.findings.items()), 'Unknown empirical finding')
        require(type(self.dependency_grounded) is bool, 'Explicit author-use grounding required')
        require(set(self.binding) == {'source_sha256', 'run_id', 'claim_sha256'}, 'Exact observation binding required')
        require(all(isinstance(v,str) and bool(v) for v in self.binding.values()), 'Empty observation binding')
        for key in ('source_sha256', 'claim_sha256'):
            require(len(self.binding[key]) == 64 and all(c in '0123456789abcdef' for c in self.binding[key]), 'Invalid content digest')


@dataclass(frozen=True)
class ForecastRequest:
    question_id: str
    as_of: str
    excluded_families: tuple[str, ...]
    context: dict

    @classmethod
    def parse(cls, raw):
        require(set(raw) == {'question_id', 'as_of', 'excluded_families', 'context'}, 'Request cannot contain heldout outcomes or undeclared fields')
        require(raw['question_id'] == QUESTION, 'Unsupported question; no automatic relaxation')
        require(date.fromisoformat(raw['as_of']).isoformat() == raw['as_of'], 'Exact prediction date required')
        families = raw['excluded_families']
        require(isinstance(families, list) and families and all(isinstance(v,str) and v for v in families) and len(set(families)) == len(families), 'Explicit complete-family exclusion required')
        validate_context(raw['context'])
        return cls(raw['question_id'],raw['as_of'],tuple(families),dict(raw['context']))


def context_agreement(left, right):
    """Неизвестность не считается совпадением; различия не доказывают эквивалентность."""
    unknown = [key for key in FACETS if left[key] is None or right[key] is None]
    matched = [key for key in FACETS if key not in unknown and left[key] == right[key]]
    differences = [key for key in FACETS if key not in unknown and left[key] != right[key]]
    return {'similarity': len(matched)/len(FACETS), 'matched':matched, 'unknown':unknown, 'differences':differences,
            'knowledge_equivalence':False}


def forecast(observations, request, mode, minimum_families=2):
    require(mode in ('known_union','frequency','semantic','dependency'), 'Unknown forecast mode')
    require(type(minimum_families) is int and minimum_families >= 2, 'Two independent training families required')
    require(len({o.reference for o in observations}) == len(observations), 'Duplicated observation')
    for observation in observations: observation.validate()
    base = {'version':VERSION,'mode':mode,'request':{**asdict(request),'excluded_families':list(request.excluded_families)},'confirmed_scientific_forecast':False,
            'knowledge_equivalence':False,'probabilities_calibrated':False,'causal_effect_established':False,
            'predicts_numeric_effect':False,'findings':{},'exclusions':[]}
    target_reasons = eligibility(request.context)
    if target_reasons:
        return {**base,'status':'abstained','reasons':target_reasons,'known':[]}
    accepted=[]
    for observation in sorted(observations,key=lambda o:o.reference):
        reasons=eligibility(observation.context)
        if observation.family in request.excluded_families: reasons.append('heldout_family')
        if observation.available_on >= request.as_of: reasons.append('not_strictly_earlier')
        if mode == 'dependency' and not observation.dependency_grounded: reasons.append('author_use_not_grounded')
        if reasons:
            base['exclusions'].append({'reference':observation.reference,'reasons':reasons}); continue
        accepted.append(observation)
    if mode == 'known_union':
        return {**base,'status':'retrieval_only','known':[asdict(o) for o in accepted], 'reasons':['known_source_results_are_not_new_predictions']}
    for channel, labels in LABELS.items():
        families=defaultdict(list)
        for observation in accepted:
            if observation.findings[channel] is not None: families[observation.family].append(observation)
        if len(families) < minimum_families:
            base['findings'][channel]={'status':'abstained','families':len(families),'reason':'insufficient_independent_families'}; continue
        totals={label:1.0 for label in labels}
        evidence=[]
        for family, members in sorted(families.items()):
            # Публикации и подгруппы одной семьи в сумме дают не более одного голоса.
            weighted=[(o,1.0 if mode=='frequency' else .25+.75*context_agreement(o.context,request.context)['similarity']) for o in members]
            family_weight=max(w for _,w in weighted)
            denominator=sum(w for _,w in weighted)
            votes={label:sum(w for o,w in weighted if o.findings[channel]==label)/denominator for label in labels}
            for label in labels: totals[label]+=family_weight*votes[label]
            evidence.append({'family':family,'weight':family_weight,'votes':votes,
                             'observations':[{'reference':o.reference,'agreement':context_agreement(o.context,request.context),'binding':o.binding} for o,_ in weighted]})
        probabilities={label:totals[label]/sum(totals.values()) for label in labels}
        best=max(probabilities.values()); leaders=[label for label in labels if abs(probabilities[label]-best)<1e-12]
        base['findings'][channel]={'status':'hypothesis','families':len(families),'probabilities':probabilities,
                                  'top_label':leaders[0] if len(leaders)==1 else None,'tie':len(leaders)>1,
                                  'evidence':evidence,'confidence_kind':'uncalibrated_family_balanced_predictive_distribution'}
    base['status']='hypothesis' if any(c['status']=='hypothesis' for c in base['findings'].values()) else 'abstained'
    return base


def score_prediction(prediction, targets):
    """Оценка вызывается отдельно после запечатывания прогноза; все подгруппы сохранены."""
    results=[]
    request=ForecastRequest.parse({**prediction['request'],'excluded_families':list(prediction['request']['excluded_families'])})
    for target in sorted(targets,key=lambda o:o.reference):
        target.validate()
        require(target.family in request.excluded_families and target.available_on == request.as_of, 'Evaluator target is outside sealed fold')
        require(target.context==request.context,'Evaluator applicability differs from sealed request')
        require(not eligibility(target.context),'Ineligible target cannot be scored')
        for channel,labels in LABELS.items():
            finding=prediction['findings'].get(channel,{})
            truth=target.findings[channel]
            row={'reference':target.reference,'family':target.family,'channel':channel,'observed_label':truth,
                 'forecast_status':finding.get('status',prediction['status'])}
            if finding.get('status')=='hypothesis' and truth is not None:
                probabilities=finding['probabilities']
                require(set(probabilities)==set(labels) and all(type(v) in (int,float) and isfinite(v) and 0<=v<=1 for v in probabilities.values())
                        and abs(sum(probabilities.values())-1)<1e-9,'Invalid sealed probabilities')
                row.update(brier=sum((probabilities[label]-(1 if label==truth else 0))**2 for label in labels),
                           categorical_match=None if finding['top_label'] is None else finding['top_label']==truth,
                           point_sign_not_biological_effect=channel=='direction')
            results.append(row)
    return results
