"""Предлагает нерешённые исследовательские задачи из документированных ограничений.

Это заданные вручную методологические операции, а не обученные законы природы.
Они предлагают один из возможных планов и никогда не предсказывают его результат.
"""
from domain.article_maps import require, fingerprint

VERSION = 'limitation-task-proposals-1'
KINDS = {
    'population_coverage': {'scope', 'restriction_dimensions'},
    'relationship_design': {'design'},
    'longitudinal_assessment': {'assessment'},
    'exposure_sampling': {'sampling'},
    'exposure_construct': {'construct'},
}


def validate_request(request):
    require(isinstance(request,dict) and set(request) == {'question', 'facts', 'joint_groups'} and request['question'] == 'address_documented_limitations', 'Unexpected task question or hidden target')
    require(isinstance(request['facts'], list) and isinstance(request['joint_groups'], list), 'Invalid input lists')
    ids = set()
    for f in request['facts']:
        require(isinstance(f,dict) and set(f) == {'id','kind','context','roles','negated','data','origin','grounding'}
                and isinstance(f['kind'],str) and f['kind'] in KINDS, 'Unknown limitation contract')
        require(isinstance(f['id'], str) and f['id'] and f['id'] not in ids, 'Duplicate premise'); ids.add(f['id'])
        require(isinstance(f['context'], str) and f['context'] and type(f['negated']) is bool, 'Explicit context and polarity required')
        require(f['grounding'] in {'own_study_description','attributed_literature_gap'}, 'Unknown grounding')
        require(isinstance(f['roles'], dict) and f['roles'] and all(isinstance(k, str) and isinstance(v, str) and v for k,v in f['roles'].items()), 'Invalid roles')
        require(isinstance(f['origin'],dict) and set(f['origin']) == {'knowledge_id','statement_ids'} and isinstance(f['origin']['knowledge_id'], str)
                and f['origin']['knowledge_id'] and isinstance(f['origin']['statement_ids'], list) and f['origin']['statement_ids']
                and all(isinstance(x,str) and x for x in f['origin']['statement_ids']), 'Origin must contain only references')
        require(isinstance(f['data'],dict) and set(f['data']) == KINDS[f['kind']], 'Unknown semantic data field')
        d = f['data']
        if f['kind'] == 'population_coverage':
            require(d['scope'] in {'restricted','broad','unknown'} and isinstance(d['restriction_dimensions'], list)
                    and all(isinstance(x,str) and x in {'education','ethnicity','geography','health','cohort_identity'} for x in d['restriction_dimensions'])
                    and len(d['restriction_dimensions']) == len(set(d['restriction_dimensions'])), 'Invalid recruitment restrictions')
            require(set(f['roles']) == {'population'}, 'Population referent required')
        if f['kind'] == 'relationship_design':
            require(d['design'] in {'cross_sectional','longitudinal','unknown'} and set(f['roles']) == {'exposure','outcome'}, 'Unknown relationship design')
        if f['kind'] == 'longitudinal_assessment':
            require(d['assessment'] in {'unassessed','assessed_nondetection','assessed_detection','unknown'}
                    and set(f['roles']) == {'exposure','outcome'}, 'Unknown longitudinal availability')
        if f['kind'] == 'exposure_sampling':
            require(d['sampling'] in {'single_occasion','repeated','unknown'} and set(f['roles']) == {'exposure'}, 'Unknown sampling')
        if f['kind'] == 'exposure_construct':
            require(d['construct'] in {'chronic','dynamic','snapshot','unknown'} and set(f['roles']) == {'exposure'}, 'Unknown target construct')
    for g in request['joint_groups']:
        require(isinstance(g,list) and g and len(g) == len(set(g)) and set(g) <= ids, 'Invalid joint group')


def propose_tasks(request):
    validate_request(request)
    facts = {f['id']: f for f in request['facts']}; tasks = []; reasons = set()
    for ids in request['joint_groups']:
        group = [facts[i] for i in ids]
        if len({f['context'] for f in group}) != 1:
            reasons.add('context_mismatch'); continue
        if any(f['negated'] for f in group):
            reasons.add('negated_premise'); continue
        if len({f['grounding'] for f in group}) != 1:
            reasons.add('mixed_grounding'); continue
        by_kind = {f['kind']: f for f in group}; kinds = set(by_kind)
        if len(by_kind) != len(group):
            reasons.add('ambiguous_joint_group'); continue
        predicate = None; conditions = []; limits = ['one_possible_design_not_a_unique_necessary_plan', 'not_a_prediction_of_results']
        if len(group) == 1 and kinds == {'population_coverage'}:
            f = group[0]
            if f['data']['scope'] != 'restricted' or not f['data']['restriction_dimensions']:
                reasons.add('documented_population_restriction_missing'); continue
            predicate = 'evaluate_transportability_beyond_recruitment_frame'
            bound_roles = f['roles']; conditions = ['cover_documented_restrictions:' + ','.join(sorted(f['data']['restriction_dimensions']))]
            limits.append('no_assumed_replication_success')
        elif kinds == {'relationship_design','longitudinal_assessment'}:
            design, assessment = by_kind['relationship_design'], by_kind['longitudinal_assessment']
            if design['roles'] != assessment['roles']:
                reasons.add('role_mismatch'); continue
            if design['data']['design'] != 'cross_sectional' or assessment['data']['assessment'] != 'unassessed':
                reasons.add('documented_longitudinal_gap_missing'); continue
            predicate = 'assess_relationship_with_prospective_repeated_outcome_measurements'
            bound_roles = design['roles']; conditions = ['observe_outcome_over_time']
            limits += ['longitudinal_observation_does_not_identify_causality', 'no_followup_length_or_sample_size_inferred']
        elif kinds == {'exposure_sampling','exposure_construct'}:
            sampling, construct = by_kind['exposure_sampling'], by_kind['exposure_construct']
            if sampling['roles'] != construct['roles']:
                reasons.add('role_mismatch'); continue
            if sampling['data']['sampling'] != 'single_occasion' or construct['data']['construct'] not in {'dynamic','chronic'}:
                reasons.add('documented_sampling_construct_gap_missing'); continue
            predicate = 'characterize_exposure_with_repeated_measurements'
            bound_roles = sampling['roles']; conditions = ['target_construct:' + construct['data']['construct']]
            limits += ['repeated_sampling_does_not_guarantee_chronic_exposure_identification','no_sampling_interval_or_number_inferred']
        else:
            reasons.add('required_joint_limitation_facts_missing'); continue
        task = {'predicate': predicate, 'kind': 'action', 'action_status': 'unresolved', 'modality': 'candidate_research_task',
                'negated': False, 'roles': bound_roles, 'context': group[0]['context'], 'conditions': conditions,
                'grounding': group[0]['grounding'], 'premises': ids, 'limitations': limits}
        if task not in tasks: tasks.append(task)
    if not tasks and not reasons: reasons.add('required_joint_limitation_facts_missing')
    return {'version': VERSION, 'request_sha256': fingerprint(request), 'status': 'generated' if tasks else 'abstained',
            'tasks': tasks, 'reasons': sorted(reasons) if not tasks else [], 'blocked_groups': sorted(reasons),
            'handcrafted': True, 'learned_rules': False, 'clinical_forecast': False, 'causal_identification': False}
