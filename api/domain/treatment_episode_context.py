"""Часы и эпизоды процедуры сохраняются отдельно от времени клинического эффекта."""
from copy import deepcopy
from decimal import Decimal,localcontext
from hashlib import sha256
import re
import xml.etree.ElementTree as ET
from domain.article_maps import fingerprint,require

VERSION='source-bound-treatment-episodes-2'
ANCHORS={'post_immunization','manifest_disease_day'}


def day(value):
    require(isinstance(value,str) and re.fullmatch(r'\d{1,12}(?:\.\d{1,6})?',value),'Explicit bounded decimal day required')
    return Decimal(value)


def text_number(value):
    s=format(value,'f');return s.rstrip('0').rstrip('.') if '.' in s else s


def expand_schedule(schedule):
    """Только точный конечный ряд; неоконченный периодический курс не достраивается."""
    if schedule['form']=='explicit':
        require(set(schedule)=={'form','points'} and isinstance(schedule['points'],list)
                and 0<len(schedule['points'])<=64,'Explicit finite dosing points required')
        points=[day(v)for v in schedule['points']]
        require(points==sorted(set(points)),'Repeated or unordered dosing points')
    else:
        require(schedule['form']=='periodic' and set(schedule)=={'form','first','last','step'},'Unknown schedule form')
        first,last,step=[day(schedule[k])for k in ('first','last','step')]
        require(step>0 and last>=first,'Invalid periodic course')
        with localcontext() as context:
            context.prec=64;n=(last-first)/step
            require(n==n.to_integral_value() and n<64,'Last dosing point is not on the declared finite schedule')
            points=[first+step*i for i in range(int(n)+1)]
    return[text_number(v)for v in points]


def calendar_difference(later,earlier):
    """Разность внутри одних часов и эпизода не является длительностью эффекта."""
    fields={'context','day'}
    require(set(later)==set(earlier)==fields and later['context']==earlier['context'],'Different study, episode or clock')
    context=later['context']
    require(set(context)=={'article_id','case_id','procedure','anchor','unit'} and context['anchor']in ANCHORS
            and context['unit']=='day' and all(isinstance(v,str)and v for v in context.values()),'Explicit source-local clock required')
    with localcontext() as precision:
        precision.prec=64;distance=day(later['day'])-day(earlier['day'])
    require(distance>=0,'Measurement precedes the last dose')
    return{'difference_days':text_number(distance),'clock_context':deepcopy(context),
           'effect_duration_inferred':False,'is_new_empirical_prediction':False}


def planned_forecast_window(episode):
    """Будущий вывод не получает время из уже измеренного ответа или края рисунка."""
    end=episode['observation_end']
    if episode['purpose']!='clinical_followup' or end is None or episode['observation_end_origin']!='source_method_endpoint':return None
    points=expand_schedule(episode['schedule']);require(day(end)>=day(points[-1]),'Observation ends before the clinical course')
    return{'anchor':episode['anchor'],'unit':'day','start':points[0],'end':end,
        'time_quantifier':'some_assessed_time','planned_protocol_window_only':True,
        'all_times_effect_inferred':False,'future_duration_copied_from_result':False}


def compile_episodes(functional,frozen,maps,cases,audit,assets):
    require(functional['run_id']==fingerprint(functional['binding']) and functional['version']=='source-bound-functional-target-guard-2'
        and audit['version']==VERSION and audit['author']=='Codex' and audit['expert_validated']is False
        and audit['model_calls']==0 and audit['functional_sha256']==fingerprint(functional)
        and audit['source_sha256']==fingerprint(frozen) and audit['map_hashes']==[fingerprint(m)for m in maps],
        'Episode corpus binding differs')
    require(set(assets)==set(audit['assets']) and all(sha256(assets[k]).hexdigest()==audit['assets'][k]['sha256']for k in assets),
        'Episode figure or XML bytes differ')
    require(set(assets)=={'atrosimab_figure7','atrosimab_xml'},'Exact published figure registry required')
    figure_asset=audit['assets']['atrosimab_figure7'];xml=ET.fromstring(assets['atrosimab_xml'])
    require(xml.findtext(".//article-id[@pub-id-type='pmcid']")=='PMC8294390'
        and xml.findtext(".//article-id[@pub-id-type='doi']")=='10.3389/fimmu.2021.705485',
        'Figure XML is from another source')
    figures=xml.findall(".//fig[@id='f7']")
    require(len(figures)==1 and any(g.get('{http://www.w3.org/1999/xlink}href')=='fimmu-12-705485-g007.jpg'
        for g in figures[0].findall('.//graphic')) and figure_asset['figure_id']=='f7'
        and figure_asset['source_url']=='https://cdn.ncbi.nlm.nih.gov/pmc/blobs/ddea/8294390/8420d5cfc6a2/fimmu-12-705485-g007.jpg'
        and figure_asset['xml_asset_id']=='atrosimab_xml','Graphical source link differs')
    require(audit['assets']['atrosimab_xml']['sha256']=='62f7a485973785e91c57ff8de3e3890c6569c39732313bd54e301ab9cb3aa420',
        'XML revision differs from the previously acquired complete training source')
    require(figure_asset['sha256']=='fc2cdd3ba1d91c0aac2e780b0f30b4793b9aca2465cca64c239cf7797c6ebd82',
        'Figure differs from the visually inspected published asset')
    require({e['case_id']for e in audit['entries']}==set(functional['guarded_prototype']['certificates'])
        and len(audit['entries'])==len(cases),'Exact prototype case coverage required')
    catalog={m['article_id']:m for m in maps};case_index={c['case_id']:c for c in cases}
    rows=[];consequences=[];conflicts=[];protocol_conflicts=[]
    for e in audit['entries']:
        case=case_index[e['case_id']];m=catalog[case['article_id']];native={k['knowledge_id']:k for k in m['graph']['knowledge']}
        require(e['article_id']==m['article_id'] and e['run_id']==m['run_id'] and e['source_sha256']==m['source']['sha256'],
            'Episode belongs to another article or revision')
        expected_roles={r['role']:r['value']for r in case['method']['frame']['statements'][0]['roles']}
        require(e['participants']==expected_roles,'Episode changes procedure participants')
        extra=e['additional_parent_ids']
        require(len(extra)==len(set(extra)) and all(k in native for k in extra),'Unknown or repeated additional protocol parent')
        full_parents=[p['knowledge']for p in case['complete_basis']]+[native[k]for k in extra]
        allowed={u for p in full_parents for s in p['semantic_frame']['statements']for u in s['provenance']['unit_ids']}
        units={u['id']:u for u in m['source']['units']}
        require(e['evidence'] and len({q['id']for q in e['evidence']})==len(e['evidence']),'Distinct source evidence required')
        for q in e['evidence']:
            u=units.get(q['unit_id']);require(u is not None and q['unit_id']in allowed,'Episode evidence outside original basis')
            require(u['start']<=q['start']<q['end']<=u['end']<=m['source']['content_end']
                and m['source']['text'][q['start']:q['end']]==q['text'] and sha256(q['text'].encode()).hexdigest()==q['sha256'],
                'Episode source fragment changed')
        quotes={q['id']:q['text']for q in e['evidence']}
        episodes=e['episodes'];require(episodes and len({t['id']for t in episodes})==len(episodes),'Distinct source episodes required')
        require(sum(t['purpose']=='clinical_followup'for t in episodes)==1,'Exactly one clinical course per source case')
        for t in episodes:
            require(t['anchor']in ANCHORS and t['unit']=='day' and t['purpose']in {'clinical_followup','tissue_sampling'}
                and t['evidence_ids'] and set(t['evidence_ids'])<=set(quotes),'Episode clock or source license missing')
            points=expand_schedule(t['schedule'])
            require(t['observation_end_origin']in {'source_method_endpoint','unknown'}
                and ((t['observation_end']is None)==(t['observation_end_origin']=='unknown')),'Unlicensed clinical endpoint')
            if t['observation_end']is not None:require(day(t['observation_end'])>=day(points[-1]),'Procedure endpoint precedes dose')
            require(t['source_asserted_effect_duration']is None,'Schedule cannot license an effect duration')
        # Реальные лицензии явных временных записей; другие формулировки требуют новой разметки.
        clinical=next(t for t in episodes if t['purpose']=='clinical_followup')
        if e['case_id']=='tros-prophylactic':
            require(len(episodes)==1 and clinical['anchor']=='post_immunization'
                and expand_schedule(clinical['schedule'])==['3','5','7','9','11','13'] and clinical['observation_end']=='16'
                and 'day 3 post-immunization (PI)'in ' '.join(quotes.values())
                and 'every two days until 13 days PI'in ' '.join(quotes.values())
                and 'cumulative disease score (c,f) was determined 16 days PI'in ' '.join(quotes.values()),
                'Prophylactic course is not the source regimen')
            require('K65'in extra and e['dose_frequency_conflict']is True
                and '150 or 200 µg TROS'in ' '.join(quotes.values())
                and 'every two or three days, respectively'in ' '.join(quotes.values()),'Known dose-frequency conflict was omitted')
            protocol_conflicts.append({'case_id':e['case_id'],'kind':'dose_frequency_source_disagreement',
                'figure_regimen':{'dose':'200','unit':'microgram','interval_days':'2'},
                'methods_wording':{'dose':'200','unit':'microgram','interval_days':'3'},
                'source_was_corrected':False,'source_evidence':deepcopy(e['evidence'])})
        elif e['case_id']=='tros-manifest':
            tissue=next((t for t in episodes if t['purpose']=='tissue_sampling'),None)
            require(len(episodes)==2 and tissue is not None and clinical['anchor']==tissue['anchor']=='post_immunization'
                and expand_schedule(clinical['schedule'])==['8','12','16'] and clinical['observation_end']=='30'
                and expand_schedule(tissue['schedule'])==['8','12'] and tissue['observation_end']=='16'
                and 'day 8 post-immunization (PI)'in ' '.join(quotes.values())
                and 'treatment was repeated on day 12 and 16 PI'in ' '.join(quotes.values())
                and 'treated on day 8 and 12 (clinical scores are not shown)'in ' '.join(quotes.values())
                and 'assessed until 30 days PI'in ' '.join(quotes.values()),'Clinical and tissue episodes are mixed')
        else:
            require(e['case_id']=='atrosimab-manifest' and len(episodes)==1 and clinical['anchor']=='manifest_disease_day'
                and expand_schedule(clinical['schedule'])==['1','4','8','12'] and clinical['observation_end']is None
                and 'days 1, 4, 8 and 12 of manifest disease'in ' '.join(quotes.values()),'Manifest clock or unknown end changed')
        require(e['dose_frequency_conflict']is (e['case_id']=='tros-prophylactic'),'Unlicensed protocol conflict flag')
        for t in episodes:
            context={'article_id':m['article_id'],'case_id':e['case_id'],'procedure':t['id'],'anchor':t['anchor'],'unit':'day'}
            if t['observation_end']is not None:
                relation=calendar_difference({'context':context,'day':t['observation_end']},
                    {'context':context,'day':expand_schedule(t['schedule'])[-1]})
                consequences.append({'case_id':e['case_id'],'procedure':t['id'],**relation,'source_kind':'procedure_calendar'})
        require(e['reported_after_last_dose_days']==('12'if e['case_id']=='tros-manifest'else None),
            'Previously identified calendar disagreement cannot be omitted')
        if e['reported_after_last_dose_days']is not None:
            reported=day(e['reported_after_last_dose_days']);actual=day(clinical['observation_end'])-day(expand_schedule(clinical['schedule'])[-1])
            require(e['case_id']=='tros-manifest' and 'until 12 days after the last treatment'in ' '.join(quotes.values())
                and reported==12,'Unlicensed reported calendar distance')
            if reported!=actual:conflicts.append({'case_id':e['case_id'],'reported_days':text_number(reported),
                'computed_days':text_number(actual),'source_evidence':deepcopy(e['evidence']),
                'source_was_corrected':False,'effect_duration_inferred':False})
        figure=e['figure_assessment']
        require((figure is not None)==(e['case_id']=='atrosimab-manifest'),'Required graphical evidence missing or attached to another case')
        if figure is not None:
            require(e['case_id']=='atrosimab-manifest' and figure['asset_id']in assets
                and figure['caption_evidence_id']in quotes and figure['panel']=='A' and figure['axis_label']=='days of EAE'
                and figure['confirmed_assessment_day']=='18' and figure['axis_upper_tick']=='20'
                and figure['direction']=='lower_reported_group_mean'
                and figure['last_assessment_established']is False and figure['pointwise_significance_inferred']is False
                and figure['expert_validated']is False and figure['author']=='Codex'
                and figure['intervention_labels']==['Atrosimab 30 mg/Kg','Atrosimab 60 mg/Kg']
                and figure['comparator_label']=='FcDeltaab','Unsupported graphical assessment')
            require(day(figure['confirmed_assessment_day'])<day(figure['axis_upper_tick']),'Axis edge is not the assessment point')
            context={'article_id':m['article_id'],'case_id':e['case_id'],'procedure':clinical['id'],
                'anchor':clinical['anchor'],'unit':'day'}
            consequences.append({'case_id':e['case_id'],'procedure':clinical['id'],
                **calendar_difference({'context':context,'day':figure['confirmed_assessment_day']},
                    {'context':context,'day':expand_schedule(clinical['schedule'])[-1]}),
                'source_kind':'confirmed_plot_point','figure_evidence':deepcopy(figure)})
        rows.append({'case_id':e['case_id'],'primary_family':case['primary_family'],'entry':deepcopy(e),
            'complete_case':deepcopy(case),'additional_complete_native_parents':[deepcopy(native[k])for k in extra],
            'functional_certificate_id':functional['guarded_prototype']['certificates'][e['case_id']],
            'planned_forecast_window':planned_forecast_window(clinical),
            'unknown_clinical_observation_end':clinical['observation_end']is None,
            'biological_clock_replaces_report_year_only_in_analysis':e['case_id']=='atrosimab-manifest',
            'doses_and_full_parents_retained':True,'effect_duration_inferred':False})
    families=sorted({r['primary_family']for r in rows if r['planned_forecast_window']is not None
        and not any(c['case_id']==r['case_id']for c in conflicts+protocol_conflicts)})
    return{'version':VERSION,'canonical_blocks':functional['canonical_blocks'],'semantic_statements':functional['semantic_statements'],
        'input_parts':functional['input_parts'],'episodes':rows,'calendar_consequences':consequences,'calendar_conflicts':conflicts,
        'protocol_conflicts':protocol_conflicts,
        'primary_families_with_unconflicted_method_window':families,'eligible_window_families':len(families),
        'guarded_prototype':deepcopy(functional['guarded_prototype']),'assets':deepcopy(audit['assets']),
        'model_calls':0,'target_read':False,'new_empirical_forecasts':0,'graph_advantage_demonstrated':False,
        'scientific_success':False,'source_effect_duration_was_generalized':False}
