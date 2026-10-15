"""Проверка того, какие скрытые эпизоды определяются наблюдениями на визитах."""
from fractions import Fraction
from domain.article_maps import require

VERSION='observation-identifiability-1'

def number(value):
    require(isinstance(value,str),'Explicit rational time required')
    try:return Fraction(value)
    except (ValueError,ZeroDivisionError):require(False,'Invalid rational time')

def validate_episodes(episodes):
    require(isinstance(episodes,list),'Episode list required')
    previous=None
    for episode in episodes:
        require(set(episode)=={'start','end'},'Episode fields differ')
        start,end=number(episode['start']),number(episode['end'])
        require(start<end,'Positive episode duration required')
        require(previous is None or previous<start,'Episodes must be disjoint and separated')
        previous=end

def observe(episodes,visits):
    validate_episodes(episodes)
    times=[number(t) for t in visits]
    require(times and times==sorted(set(times)),'Unique ordered visits required')
    return ['MCI' if any(number(e['start'])<=t<number(e['end']) for e in episodes) else 'normal' for t in times]

def durations(episodes):
    validate_episodes(episodes)
    return [str(number(e['end'])-number(e['start'])) for e in episodes]

def identifiability_witnesses():
    """Конструктивное опровержение уникальности: одни визиты совместимы с разными историями."""
    visits=['0','2','5']
    short=[{'start':'19/10','end':'21/10'}]
    long=[{'start':'1/10','end':'49/10'}]
    repeated=[{'start':'1/2','end':'3/4'}]+short
    histories=[{'id':i,'episodes':e,'durations':durations(e),'visit_states':observe(e,visits)}
               for i,e in [('short',short),('long',long),('hidden_extra',repeated)]]
    require(all(h['visit_states']==['normal','MCI','normal'] for h in histories),'Witness observations differ')
    worlds=[{'id':'higher_longer','higher_education':'long','lower_education':'short'},
            {'id':'higher_shorter','higher_education':'short','lower_education':'long'}]
    baseline_histories=[{'id':i,'episodes':e,'durations':durations(e),'visit_states':observe(e,visits)} for i,e in [
        ('recent_start',[{'start':'-1','end':'1'}]),('remote_start',[{'start':'-100','end':'1'}])]]
    return {'visits':visits,'histories':histories,'education_worlds':worlds,'baseline_histories':baseline_histories,
            'observed_signature':['normal','MCI','normal'],'episode_duration_identified':False,
            'education_duration_order_identified':False,'single_episode_identified':False,
            'synthetic':True,'clinical_estimates':False,
            'bounds_under_one_perfectly_observed_contiguous_episode':{
                'normal_mci_normal_total_duration':{'lower':'0','lower_inclusive':False,'upper':'5','upper_inclusive':False},
                'baseline_mci_then_normal_total_duration':{'finite_upper_bound':None},
                'baseline_mci_then_normal_remaining_duration':{'lower':'0','lower_inclusive':False,'upper':'2','upper_inclusive':True}},
            'scope':'Constructive non-identifiability under perfect observations; errors and missingness do not restore identification'}

def audit_catalog(catalog):
    require(catalog['protocol']['model_calls']==0 and catalog['protocol']['future_control_access'] is False,'Acquisition policy differs')
    rows=[]
    for source in catalog['sources']:
        require(source['provenance'] and source['expert_validated'] is False,'Source provenance required')
        nominal=source['nominal_times_years']
        spacings=None
        if nominal is not None:
            times=[number(v) for v in nominal]
            require(len(times)>1 and times==sorted(set(times)),'Nominal times differ')
            spacings=[str(b-a) for a,b in zip(times,times[1:])]
        rows.append({'source_id':source['source_id'],'cohort':source['cohort'],
                     'nominal_intervals_years':spacings,'nominal_regular':len(set(spacings))==1 if spacings else None,
                     'actual_regularity_established':False,'duration_order_established':False,
                     'ready_for_empirical_interval_effect_test':False,
                     'reason':'Published schedules and selected visit-state summaries do not establish education-specific episode-duration distributions or a matched interval intervention',
                     'provenance':source['provenance']})
    table=catalog['paquid_table']
    require(table['estimand']=='status_at_next_visit_percent','Cannot relabel visit states as duration')
    require(table['education_stratified'] is False,'Unexpected education duration data')
    return {'version':VERSION,'artifact_kind':'data_sufficiency_audit','sources':rows,
            'witnesses':identifiability_witnesses(),'paquid_table':table,
            'required_next_data':['individual_visit_times_and_states','education_group_definitions',
                                  'onset_and_recovery_intervals','missingness_and_death','diagnostic_error_information',
                                  'predeclared_duration_and_recurrence_assumptions'],
            'empirical_predictions':0,'confirmed_new_scientific_knowledge':0,'scientific_success':False,
            'scope':'Retrospective published-data audit; not an outcome validation or literature novelty test'}
