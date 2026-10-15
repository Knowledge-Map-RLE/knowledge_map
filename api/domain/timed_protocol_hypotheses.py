"""Условные сочетания прошлых компонентов не становятся выполненными опытами или доказанными эффектами."""
from copy import deepcopy
from itertools import product
from domain.article_maps import fingerprint,require
from domain.comparison_normalization import normalize_map
from domain.operation_applicability import compare_features
from domain.first_administration_clock import relative_point
from domain.whole_map_ablation import permuted_groups

VERSION='source-bound-timed-protocol-hypotheses-3'


def structural_groups(maps):
    records={};groups=[]
    for m in maps:
        for k in normalize_map(m):
            key=(m['article_id'],k['id']);records[key]=k
            groups.extend((tuple((key[0],p)for p in g),key)for g in k['premise_groups'])
    return records,groups


def has_group(witness,groups):
    c=witness['full_context']['complete_case']
    body=frozenset(tuple(c[f]['native_key'])for f in ('method','measurement'));head=tuple(c['result']['native_key'])
    return any(body==frozenset(b)and head==h for b,h in groups)


def coherent_semantic_case(w):
    c=w['full_context']['complete_case'];frames={f:c[f]['frame']for f in ('method','measurement','result')}
    if not all(frames[f]['kind']=='action'and frames[f]['action_status']=='performed'for f in ('method','measurement')):return False
    roles={f:{r['role']:r['value']for r in frames[f]['statements'][0]['roles']}for f in frames}
    return (roles['method']['population']==roles['measurement']['population']==roles['result']['population']
        and roles['method']['intervention']==roles['result']['intervention']
        and roles['method']['comparator']==roles['result']['comparator'])


def validate_inputs(review,clock,functional,frozen,maps):
    require(review['version']=='codex-timed-clinical-source-review-1' and review['author']=='Codex'
        and review['expert_validated']is False and review['model_calls']==0 and review['target_read']is False
        and review['clock_sha256']==fingerprint(clock) and clock['version']=='source-bound-first-administration-clock-2',
        'Timed source review binding differs')
    require(frozen['binding']['map_hashes']==[fingerprint(m)for m in maps]
        and functional['binding']['source_sha256']==fingerprint(frozen),'Explicit whole corpus differs')
    witnesses=review['witnesses']
    require(review['pattern']['primary_families']==sorted({w['primary_family'] for w in witnesses})
        and review['pattern']['coordinate']=='17' and review['pattern']['unit']=='source_day_coordinate'
        and review['pattern']['is_pattern_similarity'] is True and review['pattern']['full_fact_equivalence'] is False
        and review['pattern']['is_valid_universal_rule'] is False and review['pattern']['is_future_forecast'] is False
        and review['pattern']['is_automatically_extracted_visual_result'] is False
        and review['new_empirical_forecasts']==0 and review['graph_advantage_demonstrated'] is False,
        'Source review promotes a selected past pattern')
    catalog={m['article_id']:m for m in maps};proofs={p['procedure']:p for p in clock['clock_proofs']}
    certificates={c['id']:c for c in functional['functional_certificates']}
    require(len(witnesses)==len({w['case_id']for w in witnesses}),'Repeated timed source case')
    for w in witnesses:
        p=proofs.get(w['procedure']);require(p is not None and w['full_context']==p['complete_source_case']
            and w['primary_family']==w['full_context']['primary_family']
            and w['source_clock_reference']==p['reference'] and w['relative_time']['reference_id']==p['reference']['id']
            and w['relative_time']['value']==review['pattern']['coordinate']=='17'
            and w['reported_relation']==review['pattern']['relation']=='lower_plotted_group_mean_clinical_score'
            and w['source_features']==review['pattern']['source_features'] and coherent_semantic_case(w),
            'Timed comparison crosses participants, procedure or coordinate')
        c=w['full_context']['complete_case'];m=catalog.get(c['article_id'])
        require(m is not None and m['run_id']==c['run_id'] and m['source']['sha256']==w['full_context']['entry']['source_sha256'],
            'Timed comparison outside explicit corpus')
        require(w['source_features']==c['features'] and compare_features(w['source_features'],w['source_features'])['applicable'],
            'Unknown or forged applicability features')
        require(w['relative_time']==relative_point({'context':p['reference']['source_clock_context'],'day':w['source_day']},p['reference'])
            and w['relative_time']['unit']=='day' and w['read_by']=='Codex' and w['expert_validated']is False
            and review['pattern']['is_valid_universal_rule']is False,'Unlicensed time coordinate or promoted source evidence')
        certificate=certificates.get(w['full_context']['functional_certificate_id'])
        require(certificate is not None and w['case_id']in certificate['case_ids']
            and certificate['structural_target_compatibility_supported']is True,'Missing source functional certificate')
        method_roles={r['role']:r['value']for r in c['method']['frame']['statements'][0]['roles']}
        require(certificate['intervention']==method_roles['intervention'] and certificate['population']==method_roles['population'],
            'Functional evidence belongs to another treatment or population')
        expected=p['source_dose_specifications'];units={a['unit']for a in expected}
        values={v.strip()for a in expected for v in str(a['value']).split(';')}
        require(units and all(d['unit']in units and d['value']in values for d in w['dose_groups']),
            'Dose not licensed by its intervention source')
        require(not w['pointwise_significance_inferred']and not w['clinical_causality_inferred'],
            'Visual point cannot establish significance or clinical causality')
    return proofs,certificates


def combine(witnesses,proofs,certificates,mode,limit=20):
    """Перебор зависит только от прошлого материала; вопрос или будущая цель отсутствуют."""
    families=sorted({w['primary_family']for w in witnesses})
    if len(families)<2:return[]
    proposals={}
    for donor,recipient in product(witnesses,repeat=2):
        if donor['case_id']==recipient['case_id']:continue
        compatibility=compare_features(donor['source_features'],recipient['source_features'])
        if not compatibility['applicable']:continue
        dp=proofs[donor['procedure']];rp=proofs[recipient['procedure']]
        donor_cert=certificates[donor['full_context']['functional_certificate_id']]
        recipient_cert=certificates[recipient['full_context']['functional_certificate_id']]
        if donor_cert['required_target_domain']!=recipient_cert['required_target_domain']:continue
        for dose in donor['dose_groups']:
            scenario={'intervention_source_case':donor['case_id'],'population_class_source_case':recipient['case_id'],
                'treatment_schedule_source_case':donor['case_id'],'measurement_source_case':recipient['case_id'],
                'comparator_source_case':donor['case_id'],
                'dose':deepcopy(dose),'relative_dosing_days':[p['point']['value']for p in dp['relative_doses']],
                'assessed_coordinate':donor['relative_time']['value'],'clock_type':'first_administration_of_this_proposed_episode',
                'unit':'source_day_coordinate','source_features':deepcopy(donor['source_features']),
                'required_target_domain':donor_cert['required_target_domain']}
            method_roles={r['role']:r['value'] for r in donor['full_context']['complete_case']['method']['frame']['statements'][0]['roles']}
            scenario['comparator']=method_roles['comparator']
            scenario['comparator_label']=donor['comparator_label']
            scenario_id=fingerprint(scenario)
            body=[{'kind':'state','action_status':None,'meaning':'source reports functional activity and receptor-domain compatibility',
                    'source_functional_certificate':donor_cert['id'],'source_model_certificate':recipient_cert['id'],
                    'in_vivo_function_in_proposed_model_established':False},
                {'kind':'action','action_status':'planned','meaning':'administer the selected source dose and relative schedule to a proposed new group',
                    'dose':deepcopy(dose),'relative_dosing_days':scenario['relative_dosing_days'],
                    'source_treatment_context':deepcopy(donor['full_context']),
                    'population_definition_context':deepcopy(recipient['full_context']),
                    'population_is_original_study_group':False},
                {'kind':'action','action_status':'planned','meaning':'establish a matched control group using the comparator specified by the intervention source',
                    'comparator':scenario['comparator'],'comparator_label':scenario['comparator_label'],
                    'source_comparator_context':deepcopy(donor['full_context']),
                    'population_is_original_study_group':False},
                {'kind':'action','action_status':'planned','meaning':'assess the proposed treatment and matched control groups at the relative time coordinate',
                    'assessed_coordinate':scenario['assessed_coordinate'],'relative_time_anchor':'first_administration_of_this_proposed_episode',
                    'source_day_coordinate':True,
                    'source_measurement_context':deepcopy(recipient['full_context']),
                    'design_origin':'proposed_design_derived_from_past_timed_pattern','future_observation_read':False}]
            proposal={'id':scenario_id,'scenario':scenario,'body':body,
                'head':{'kind':'state','action_status':None,'predicate':'hypothesized lower group mean clinical EAE score than matched control',
                    'modality':'hypothesis_if_the_planned_experiment_is_performed','negated':False,
                    'time_quantifier':'specified_relative_time_from_first_administration','assessed_coordinate':scenario['assessed_coordinate'],
                    'assessment_time':{'anchor':'first_administration_of_this_proposed_episode',
                        'value':scenario['assessed_coordinate'],'unit':'source_day_coordinate'},
                    'population_scope':'proposed_new_group_defined_by_source_model_context','source_data_was_not_relabelled_as_future_result':True,
                    'effect_size':None,'statistical_significance':None,'continuous_effect_asserted':False,
                    'dose_equivalence_asserted':False,'clinical_causality_proven':False},
                'support_primary_families':sorted({donor['primary_family'],recipient['primary_family']}),
                'support_witness_ids':sorted({donor['id'],recipient['id']}),
                'full_functional_contexts':[deepcopy(donor_cert),deepcopy(recipient_cert)],
                'status':'exploratory_counterfactual_candidate','valid_universal_rule':False,'deductively_entailed':False,
                'expert_validated':False,'source_population_identity_reused':False,
                'novelty':{'pair_absent_from_licensed_case_registry':True,'absence_from_all_source_texts_established':False,
                    'new_scientific_knowledge_confirmed':False},
                'unverified_changes_ru':['Препарат переносится на другой генетический, половой и возрастной контекст.',
                    'Совместимость внеклеточной мишени не доказывает ингибирование в новом организме.',
                    'Используется метод оценивания принимающего контекста; направление средних не инвариантно к произвольной перекодировке.',
                    'Численность групп, распределение по группам и остальные детали нового опыта должны быть явно зафиксированы до проверки.',
                    'Момент 17 выбран по двум вручную прочитанным прошлым рисункам; вероятностная калибровка и независимая новизна не установлены.'],
                'mode':mode}
            proposals[scenario_id]=proposal
    return[proposals[k]for k in sorted(proposals)[:limit]]


def forecast(review,clock,functional,frozen,maps):
    proofs,certificates=validate_inputs(review,clock,functional,frozen,maps)
    records,groups=structural_groups(maps);scrambled=permuted_groups(records,groups)
    output={};eligibility={}
    for mode in ('graph','same_facts_without_dependencies','permuted_dependencies'):
        witnesses=[w for w in review['witnesses']if coherent_semantic_case(w)
            and (mode=='same_facts_without_dependencies'or has_group(w,groups if mode=='graph'else scrambled))]
        eligibility[mode]={'source_cases':[w['case_id']for w in witnesses],
            'primary_families':sorted({w['primary_family']for w in witnesses})}
        output[mode]=combine(witnesses,proofs,certificates,mode)
    inventory=[{'article_id':m['article_id'],'run_id':m['run_id'],'knowledge_id':k['knowledge_id'],
        'statement_count':len(k['semantic_frame']['statements'])}for m in maps for k in m['graph']['knowledge']]
    return{'version':VERSION,'question':None,'canonical_blocks':len(inventory),
        'semantic_statements':sum(p['statement_count']for p in inventory),'input_inventory':inventory,
        'licensed_source_cases':len(review['witnesses']),'operator_coverage_is_whole_corpus':False,
        'modes':output,'eligibility':eligibility,'candidate_count':len(output['graph']),
        'all_operator_conditions_shared_with_semantic_control':True,'clinical_template_is_statistical_hypothesis':True,
        'first_three_part_guard_was_author_asserted':False,'new_independent_outcomes_read':False,
        'qualified_new_scientific_forecasts':0,'scientific_success':False,'graph_advantage_demonstrated':False,
        'model_calls':0,'target_read':False}
