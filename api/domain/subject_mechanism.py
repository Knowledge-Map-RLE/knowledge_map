"""Условные механистические гипотезы и проверки границ переноса."""
from fractions import Fraction
from itertools import product
from datetime import date
from domain.article_maps import fingerprint, require
from domain.knowledge_foundation import validate_dag

VERSION = 'subject-window-mechanism-1'
CONDITIONS = ['fixed_positive_group_durations', 'longer_group_window', 'regular_assessment_grid',
              'uniform_onset_phase', 'complete_followup_window', 'perfect_state_detection',
              'one_contiguous_episode', 'otherwise_unchanged_protocol']


def rational(value):
    require(isinstance(value, str), 'Explicit rational string required')
    try: result = Fraction(value)
    except (ValueError, ZeroDivisionError): require(False, 'Invalid rational')
    require(result > 0, 'Positive duration required')
    return result


def capture(duration, interval):
    """Вероятность пересечения фиксированного окна регулярной сеткой при равномерной фазе."""
    return min(Fraction(1), rational(duration)/rational(interval))


def relative_capture(high, low, interval):
    require(rational(high) >= rational(low), 'Ordered group windows required')
    return capture(high, interval)/capture(low, interval)


def fixed_window_comparison(high, low, shorter, longer):
    require(rational(shorter) < rational(longer), 'Assessment interval must decrease')
    before = relative_capture(high, low, longer); after = relative_capture(high, low, shorter)
    require(after <= before, 'Fixed-window theorem failed')
    return {'before': str(before), 'after': str(after), 'attenuation': after < before,
            'nonincrease': True, 'estimand': 'relative_ascertainment_probability', 'clinical_measurement': False}


def mixture_capture(distribution, interval):
    require(isinstance(distribution, list) and distribution, 'Distribution required')
    weights = []; total = Fraction(0)
    for point in distribution:
        require(set(point) == {'duration', 'probability'}, 'Distribution fields differ')
        weight = rational(point['probability']); rational(point['duration']); weights.append(weight)
        total += weight*capture(point['duration'], interval)
    require(sum(weights) == 1, 'Probabilities must sum to one')
    return total


def mixture_counterexample():
    """Иллюстративные длительности, не оценки когорт: даже стохастический порядок недостаточен."""
    low = [{'duration':'1/10','probability':'1/2'}, {'duration':'100','probability':'1/2'}]
    high = [{'duration':'1','probability':'1/2'}, {'duration':'100','probability':'1/2'}]
    before = mixture_capture(high,'50')/mixture_capture(low,'50')
    after = mixture_capture(high,'2')/mixture_capture(low,'2')
    require(after > before, 'Counterexample must violate fixed-window monotonicity')
    return {'low':low,'high':high,'longer_interval':'50','shorter_interval':'2',
            'before':str(before),'after':str(after),'expected_universal_attenuation':False,
            'higher_group_first_order_dominates':True,'synthetic':True,'clinical_estimate':False}


def validate_knowledge(blocks):
    require(isinstance(blocks, list), 'Knowledge list required')
    ids = {b['knowledge_id'] for b in blocks}
    require(len(ids) == len(blocks), 'Duplicate canonical knowledge')
    for b in blocks:
        require(set(b) == {'knowledge_id','text','text_ru','kind','knowledge_kind','frame','provenance','available_on'}, 'Knowledge fields differ')
        require(b['text'] and b['text_ru'] and b['provenance'], 'Labels or provenance missing')
        require(b['kind'] == 'state', 'Source premises must be states')
        try: available = date.fromisoformat(b['available_on'])
        except (TypeError, ValueError): require(False, 'ISO source date required')
        require(available <= date(2023,12,31), 'Training cutoff exceeded')
        frame = b['frame']
        require(set(frame) == {'predicate','roles','modality','quantifier','negated','context','conditions','status'}, 'Frame fields differ')
        require(type(frame['negated']) is bool and isinstance(frame['roles'], dict), 'Semantic flags differ')
        require(frame['modality'] in {'reported','hypothesized','definition','assumed'}, 'Unknown modality')
        require(frame['quantifier'] in {'study_specific','conditional','general_background'}, 'Unknown quantifier')
        require(isinstance(frame['context'],dict) and isinstance(frame['conditions'],list), 'Explicit context required')


def proof_graph(premises, target):
    nodes = [{'id':i,'knowledge_id':i,'role':'premise'} for i in sorted(premises)]
    nodes.append({'id':target,'knowledge_id':target,'role':'hypothesis'})
    edges = [{'source':i,'target':target} for i in sorted(premises)]
    return {'occurrences':nodes,'edges':edges,'joint_premises':sorted(premises),
            'ranks':dict(sorted(validate_dag(nodes,edges).items()))}


def generate(inputs):
    require(set(inputs) == {'protocol','knowledge','foundation_binding'}, 'Generator inputs differ')
    validate_knowledge(inputs['knowledge']); protocol = inputs['protocol']
    require(protocol['future_control_access'] is False and protocol['model_calls'] == 0, 'Acquisition policy differs')
    require(protocol['candidate_budget'] == 20, 'Frozen budget differs')
    by_predicate = {}
    for b in inputs['knowledge']: by_predicate.setdefault(b['frame']['predicate'],[]).append(b)
    candidates = []; diagnostics = []
    required = {'longer_mci_window_hypothesis','intervisit_mci_may_be_missed','fixed_window_capture_model','fixed_window_relative_order'}
    present = set(by_predicate)
    if not required <= present:
        return {'candidates':[], 'diagnostics':[{'reason':'missing_mechanistic_premise','missing':sorted(required-present)}]}
    for selected in product(*(by_predicate[p] for p in sorted(required))):
        bundle = {b['frame']['predicate']:b for b in selected}
        window = bundle['longer_mci_window_hypothesis']; missed = bundle['intervisit_mci_may_be_missed']
        model = bundle['fixed_window_capture_model']; order = bundle['fixed_window_relative_order']
        a,b = window['frame'],missed['frame']
        context_fields={'cohort','phenotype','diagnostic_scope','population'}
        if (a['negated'] or b['negated'] or a['context'] != b['context'] or
            not context_fields <= set(a['context']) or not all(a['context'][k] for k in context_fields)):
            diagnostics.append({'reason':'incompatible_source_context','premises':[window['knowledge_id'],missed['knowledge_id']]});continue
        require(model['frame']['modality']=='assumed' and model['frame']['quantifier']=='conditional' and set(model['frame']['conditions'])==set(CONDITIONS), 'Sampling assumptions changed')
        require(not model['frame']['negated'] and not order['frame']['negated'], 'Negated mathematical premise')
        require(order['frame']['status']=='conditional_mathematical_result' and order['frame']['quantifier']=='conditional' and set(order['frame']['conditions'])==set(CONDITIONS), 'Unknown mathematical operator')
        require(a['modality']=='hypothesized', 'Unmeasured duration ordering must remain hypothetical')
        roles = a['roles']; require(set(roles)=={'factor','higher_group','lower_group','state'}, 'Window roles differ')
        require(roles=={'factor':'education','higher_group':'higher_education','lower_group':'lower_education','state':'isolated_memory_mci'}, 'Operator participant scope differs')
        require(a['context']['phenotype']==roles['state'], 'Phenotype and state differ')
        require(b['roles']['state']==roles['state'], 'State identity differs')
        frame = {'predicate':'assessment_interval_interacts_with_relative_state_ascertainment',
                 'roles':roles,'modality':'hypothesized','quantifier':'conditional','negated':False,
                 'context':a['context'],'conditions':CONDITIONS,'status':'requires_duration_and_protocol_validation'}
        identifier = fingerprint(frame); premises = [v['knowledge_id'] for v in bundle.values()]
        candidates.append({'id':identifier,'kind':'state','knowledge_kind':'hypothesis','frame':frame,
            'text':'Under fixed longer MCI windows in the higher-education group and a regular ideal assessment model, shortening visit intervals cannot increase the relative probability of capturing its MCI episodes; it may attenuate that ratio.',
            'text_ru':'Если окно MCI фиксировано и длиннее в группе с более высоким образованием, то в идеальной модели регулярных осмотров сокращение интервала визитов не увеличивает относительную вероятность обнаружить её эпизоды MCI; отношение может уменьшиться.',
            'premises':sorted(premises),'graph':proof_graph(premises,'hypothesis:'+identifier),
            'status':'conditional_mechanistic_candidate','empirical_prediction_released':False,
            'new_scientific_knowledge_confirmed':False,'target_question_supplied':False,
            'source_support_families':sorted({x['frame']['context'].get('cohort') for x in [window,missed]}),
            'novelty':'A generated conditional interaction; membership in known corpus must be audited separately',
            'measurement_task':{'kind':'action','action_status':'unresolved',
                 'text':'Measure education-stratified MCI episode duration distributions and validate the visit/detection process before testing interval effects.',
                 'text_ru':'Оценить распределения длительности эпизодов MCI по образованию и проверить процесс визитов и обнаружения до проверки эффекта интервала.'}})
    distinct = {c['id']:c for c in candidates}
    return {'candidates':[distinct[i] for i in sorted(distinct)][:20],'diagnostics':diagnostics,
            'background_not_automatically_composed':[b['knowledge_id'] for b in inputs['knowledge'] if b['frame']['predicate'] not in required]}


def evaluate_eligibility(candidate, profiles):
    require(candidate['empirical_prediction_released'] is False, 'Candidate already promoted without validation')
    rows = []
    for p in profiles:
        require(set(p) == {'source_id','context','regular_grid','uniform_phase','fixed_group_durations','perfect_detection','complete_followup','education_duration_order_measured','matched_protocol_interval_comparison','provenance'}, 'Profile fields differ')
        require(p['provenance'], 'Profile provenance missing')
        reasons = []
        if p['context']['phenotype'] != candidate['frame']['context']['phenotype']: reasons.append('different_phenotype')
        for field in ('regular_grid','uniform_phase','fixed_group_durations','perfect_detection','complete_followup','education_duration_order_measured','matched_protocol_interval_comparison'):
            require(p[field] is None or type(p[field]) is bool, 'Missingness must be explicit')
            if p[field] is not True: reasons.append(('unknown_' if p[field] is None else 'violated_')+field)
        rows.append({'source_id':p['source_id'],'status':'eligible_for_separate_test' if not reasons else 'not_testable_from_selected_data',
                     'reasons':reasons,'provenance':p['provenance'],'agreement':None,'scientific_success':False})
    return rows
