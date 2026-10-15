"""Успех паттерна относительно цели; неподтверждение не равно опровержению."""
from dataclasses import dataclass
from math import isfinite
from collections import defaultdict
from copy import deepcopy
from domain.article_maps import require, fingerprint

VERSION='goal-pattern-experience-1'


@dataclass(frozen=True)
class Goal:
    goal_id: str
    objective: str
    metric: str
    minimum: float
    context: dict
    protocol_sha256: str

    def validate(self):
        require(self.objective in {'engineering_interpretation','clinical_prediction','research_task_reconstruction'},'Explicit objective required')
        require(self.metric in {'agreement','future_effect_match','exact_task_match'},'Explicit metric required')
        require({'engineering_interpretation':'agreement','clinical_prediction':'future_effect_match','research_task_reconstruction':'exact_task_match'}[self.objective]==self.metric,'Objective and metric differ')
        require(isinstance(self.goal_id,str) and bool(self.goal_id) and type(self.minimum) in (int,float) and isfinite(self.minimum) and 0<=self.minimum<=1,'Invalid goal criterion')
        require(isinstance(self.context,dict) and bool(self.context) and all(v is not None for v in self.context.values()),'Known applicability required')
        require(isinstance(self.protocol_sha256,str) and len(self.protocol_sha256)==64 and all(c in '0123456789abcdef' for c in self.protocol_sha256),'Sealed goal protocol required')


def assess(goal,trial):
    goal.validate()
    require(set(trial)=={'pattern_id','family','case_id','metric','value','context','outcome_observed','binding','prospective'},'Closed pattern experience required')
    require(all(isinstance(trial[k],str) and trial[k] for k in ('pattern_id','family','case_id')) and isinstance(trial['binding'],dict) and trial['binding'],'Experience provenance required')
    require(type(trial['outcome_observed']) is bool and type(trial['prospective']) is bool,'Explicit observation status required')
    if trial['metric']!=goal.metric or trial['context']!=goal.context: status='inapplicable'
    elif not trial['outcome_observed'] or trial['value'] is None: status='unknown'
    else:
        require(type(trial['value']) in (int,float) and isfinite(trial['value']) and 0<=trial['value']<=1,'Valid observed metric required')
        status='goal_met' if trial['value']>=goal.minimum else 'goal_not_met'
    data={'goal_id':goal.goal_id,'objective':goal.objective,'metric':goal.metric,'status':status,
          'goal_context':goal.context,'protocol_sha256':goal.protocol_sha256,'trial':trial,
          'scientific_success':False,
          'negative_scientific_result_is_failure':False,'absence_is_refutation':False}
    return deepcopy({'experience_id':fingerprint(data),**data})


def summarize(experiences):
    require(len({e['experience_id'] for e in experiences})==len(experiences),'Repeated experience cannot inflate evidence')
    require(all(e['experience_id']==fingerprint({k:v for k,v in e.items() if k!='experience_id'}) for e in experiences),'Experience content changed')
    episodes={(e['trial']['pattern_id'],e['goal_id'],e['protocol_sha256'],e['trial']['family'],e['trial']['case_id'],fingerprint(e['goal_context'])) for e in experiences}
    require(len(episodes)==len(experiences),'Repeated case cannot inflate evidence within one protocol')
    groups=defaultdict(list)
    for e in experiences:
        key=(e['trial']['pattern_id'],e['goal_id'],fingerprint(e['goal_context']),e['protocol_sha256'])
        groups[key].append(e)
    return [{'pattern_id':key[0],'goal_id':key[1],'applicability_sha256':key[2],'protocol_sha256':key[3],
             'goal_met':sum(e['status']=='goal_met' for e in rows),
             'goal_not_met':sum(e['status']=='goal_not_met' for e in rows),
             'unknown_or_inapplicable':sum(e['status'] in {'unknown','inapplicable'} for e in rows),
             'evaluated_families':sorted({e['trial']['family'] for e in rows if e['status'] in {'goal_met','goal_not_met'}}),
             'empirical_transfer_supported':False,'experience_ids':[e['experience_id'] for e in rows]}
            for key,rows in sorted(groups.items())]
