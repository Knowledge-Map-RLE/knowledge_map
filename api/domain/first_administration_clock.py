"""Обратимая смена начала отсчёта не создаёт длительность эффекта или эквивалентность опытов."""
from copy import deepcopy
from decimal import Decimal,localcontext
import re
from domain.article_maps import fingerprint,require
from domain.treatment_episode_context import day,text_number,expand_schedule,calendar_difference

VERSION='source-bound-first-administration-clock-2'


def reference(context,first_dose_day):
    # Проверяется тот же тип локальных часов, что и у календарного оператора.
    calendar_difference({'context':context,'day':first_dose_day},{'context':context,'day':first_dose_day})
    r={'source_clock_context':deepcopy(context),'first_dose_day':text_number(day(first_dose_day)),
        'target_anchor':'first_administration_of_this_episode','unit':'day'}
    r['id']=fingerprint(r);return r


def validate_reference(ref):
    require(set(ref)=={'source_clock_context','first_dose_day','target_anchor','unit','id'}
        and ref['id']==fingerprint({k:v for k,v in ref.items()if k!='id'})
        and ref==reference(ref['source_clock_context'],ref['first_dose_day']), 'Relative reference was changed')


def relative_point(point,ref):
    validate_reference(ref)
    require(set(point)=={'context','day'} and point['context']==ref['source_clock_context'],
        'Point and first dose belong to different study, episode or clock')
    with localcontext() as context:
        context.prec=64;value=day(point['day'])-day(ref['first_dose_day'])
    return{'reference_id':ref['id'],'value':text_number(value),'unit':'day'}


def restore_point(point,ref):
    validate_reference(ref)
    require(set(point)=={'reference_id','value','unit'} and point['reference_id']==ref['id']
        and point['unit']=='day' and isinstance(point['value'],str)
        and re.fullmatch(r'-?\d{1,13}(?:\.\d{1,6})?',point['value']), 'Wrong or malformed relative coordinate')
    with localcontext() as context:
        context.prec=64;value=Decimal(point['value'])+day(ref['first_dose_day'])
    require(value>=0,'Restored coordinate precedes the source clock origin')
    restored=text_number(value);day(restored)
    return{'context':deepcopy(ref['source_clock_context']),'day':restored}


def bind_relative_parameter(parameter,ref,allowed_origins):
    """Параметр переносится только внутри собственного эпизода и своей области происхождения."""
    require(set(parameter)=={'point','source_origin'} and parameter['source_origin']in
        {'performed_dose','source_method_endpoint','source_result_plot'}, 'Explicit coordinate origin required')
    require(isinstance(allowed_origins,set) and allowed_origins<=
        {'performed_dose','source_method_endpoint','source_result_plot'},'Explicit caller origin policy required')
    require(parameter['source_origin']in allowed_origins,'A measured response coordinate cannot fill a planned method window')
    return{'point':relative_point(parameter['point'],ref),'source_origin':parameter['source_origin'],
        'coordinate_was_copied_from_its_own_procedure':True,'new_effect_duration_inferred':False}


def analyze_clocks(previous):
    require(previous['run_id']==fingerprint(previous['binding']) and previous['version']=='source-bound-treatment-episodes-2'
        and previous['model_calls']==0 and previous['target_read']is False, 'Explicit source episode run required')
    rows=[];all_references=set();before_relations=[];after_relations=[]
    for parent in previous['episodes']:
        entry=parent['entry']
        require(all(parent['complete_case'][field]['frame']['kind']=='action'
            and parent['complete_case'][field]['frame']['action_status']=='performed'
            for field in ('method','measurement')), 'Only source-reported performed procedures license these coordinates')
        for e in entry['episodes']:
            source_points=expand_schedule(e['schedule'])
            context={'article_id':entry['article_id'],'case_id':entry['case_id'],'procedure':e['id'],
                'anchor':e['anchor'],'unit':e['unit']}
            ref=reference(context,source_points[0]);require(ref['id']not in all_references,'Repeated relative episode');all_references.add(ref['id'])
            doses=[bind_relative_parameter({'point':{'context':context,'day':p},'source_origin':'performed_dose'},
                ref,{'performed_dose'})for p in source_points]
            endpoint=None if e['observation_end']is None else bind_relative_parameter(
                {'point':{'context':context,'day':e['observation_end']},'source_origin':'source_method_endpoint'},ref,{'source_method_endpoint'})
            graphical=[]
            if e['purpose']=='clinical_followup' and entry['figure_assessment']is not None:
                graphical.append(bind_relative_parameter({'point':{'context':context,
                    'day':entry['figure_assessment']['confirmed_assessment_day']},'source_origin':'source_result_plot'},
                    ref,{'source_result_plot'}))
            for source,shifted in zip(source_points,doses):
                require(restore_point(shifted['point'],ref)=={'context':context,'day':source},'Dosing shift is not reversible')
            if endpoint is not None:require(restore_point(endpoint['point'],ref)['day']==e['observation_end'],'Endpoint shift is not reversible')
            for p in graphical:require(restore_point(p['point'],ref)['day']==entry['figure_assessment']['confirmed_assessment_day'],
                'Graphical point shift is not reversible')
            gaps=[text_number(day(b)-day(a))for a,b in zip(source_points,source_points[1:])]
            relative=[p['point']['value']for p in doses]
            require(gaps==[text_number(day(b)-day(a))for a,b in zip(relative,relative[1:])], 'Change of origin alters dosing intervals')
            measured_day=e['observation_end']if endpoint is not None else(
                entry['figure_assessment']['confirmed_assessment_day']if graphical else None)
            if measured_day is not None:
                before=day(measured_day)>day(source_points[-1]);after=Decimal((endpoint or graphical[0])['point']['value'])>day(relative[-1])
                require(before==after,'Temporal ordering changed after normalization')
                relation={'case_id':entry['case_id'],'procedure':e['id'],'assessment_after_last_dose':before,
                    'measurement_origin':'source_method_endpoint'if endpoint is not None else'source_result_plot'}
                before_relations.append(relation);after_relations.append({**relation,'assessment_after_last_dose':after})
            method_window=None
            if e['purpose']=='clinical_followup' and parent['planned_forecast_window']is not None:
                require(endpoint is not None and endpoint['source_origin']=='source_method_endpoint','Method window was filled from outcome')
                window=parent['planned_forecast_window'];require(window['start']==source_points[0] and window['end']==e['observation_end'],
                    'Method window belongs to another dose course')
                method_window={'reference_id':ref['id'],'start':'0','end':endpoint['point']['value'],'unit':'day',
                    'time_quantifier':window['time_quantifier'],'new_effect_duration_inferred':False}
            r={'case_id':entry['case_id'],'procedure':e['id'],'purpose':e['purpose'],'primary_family':parent['primary_family'],
                'phase':parent['complete_case']['features']['phase'],'reference':ref,'relative_doses':doses,'relative_endpoint':endpoint,
                'relative_graphical_points':graphical,'relative_method_window':method_window,'unchanged_interval_days':gaps,
                'complete_source_case':deepcopy(parent),'source_numbers_and_clock_retained':True,
                'biological_onset_equivalence_inferred':False,'doses_or_scales_converted':False,
                'effect_duration_inferred':False,'new_empirical_prediction':False}
            r['source_dose_specifications']=[deepcopy(a)for a in parent['complete_case']['method']['frame']['statements'][0]['attributes']
                if a['name']in {'dose','doses'}]
            r['id']=fingerprint(r);rows.append(r)
    comparisons=[]
    for i,a in enumerate(rows):
        for b in rows[i+1:]:
            if a['purpose']!=b['purpose']:continue
            comparisons.append({'left':a['id'],'right':b['id'],'same_reference_type':True,
                'same_source_clock_identity':a['reference']['id']==b['reference']['id'],
                'same_phase':a['phase']==b['phase'],
                'same_relative_dosing_schedule':[x['point']['value']for x in a['relative_doses']]==[x['point']['value']for x in b['relative_doses']],
                'same_dose_specifications':a['source_dose_specifications']==b['source_dose_specifications'],
                'both_method_endpoints_known':a['relative_endpoint']is not None and b['relative_endpoint']is not None,
                'experimental_equivalence':False,'transfer_of_effect_established':False})
    require(before_relations==after_relations,'Coordinate change added temporal evidence')
    return{'version':VERSION,'canonical_blocks':previous['canonical_blocks'],'semantic_statements':previous['semantic_statements'],
        'input_parts':previous['input_parts'],'clock_proofs':rows,'comparisons':comparisons,
        'source_temporal_relations':before_relations,'normalized_temporal_relations':after_relations,
        'source_calendar_consequences':deepcopy(previous['calendar_consequences']),
        'source_calendar_conflicts':deepcopy(previous['calendar_conflicts']),
        'source_protocol_conflicts':deepcopy(previous['protocol_conflicts']),
        'source_guarded_prototype':deepcopy(previous['guarded_prototype']),
        'relative_reference_equates_experiments':False,'new_empirical_forecasts':0,'graph_advantage_demonstrated':False,
        'model_calls':0,'target_read':False,'scientific_success':False,'empirical_generator_run':False}
