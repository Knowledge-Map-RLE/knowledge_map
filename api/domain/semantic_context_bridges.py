"""Математическая смена представления отдельно от эмпирического переноса."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation, localcontext
from datetime import date
from math import log
from domain.article_maps import require, fingerprint
from domain.empirical_question_forecast import CONTEXT, ForecastRequest, eligibility
from domain.guarded_empirical_transfer import compare_context, canonical_context

VERSION = 'semantic-context-bridges-1'
POLICY = {'version': VERSION, 'quantity_eligibility': {'age_min': '>=60', 'followup_min': '>=2'},
          'identity': 'explicit equal known values; 3MSE/3MS alias only',
          'empirical_license': 'not established by eligibility or representation identity',
          'unknown': 'not equal; no automatic imputation',
          'algebra': ['affine_coordinates_same_analysis', 'reverse_ratio_contrast_same_analysis'],
          'forbidden_automatic_bridges': ['MMSE_to_3MS', 'quartile_to_continuous', 'linear_to_log',
                                        'aggregate_to_MCI_stratum', 'average_to_instantaneous', 'slope_to_event',
                                        'change_adjustment_set', 'significance_across_alpha_or_power']}
POLICY_SHA256 = fingerprint(POLICY)


def audit_context(source, request):
    require(set(source) == {'reference', 'family', 'available_on', 'context', 'binding'}, 'Explicit source context required')
    require(isinstance(request, ForecastRequest), 'Context-only request required')
    require(all(isinstance(source[k], str) and source[k] for k in ['reference', 'family']), 'Source identity required')
    require(date.fromisoformat(source['available_on']).isoformat() == source['available_on'], 'Exact source date required')
    require(set(source['binding']) == {'source_sha256', 'run_id', 'context_sha256', 'frame_sha256', 'provenance'}, 'Explicit source binding required')
    for key in ['source_sha256', 'context_sha256', 'frame_sha256']:
        value = source['binding'][key]
        require(isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value), 'Invalid source binding digest')
    require(source['binding']['run_id'] and source['binding']['provenance'], 'Source provenance required')
    require(source['binding']['context_sha256'] == fingerprint(source['context']), 'Source context changed')
    reasons = eligibility(source['context']) + ['target:' + r for r in eligibility(request.context)]
    if source['family'] in request.excluded_families: reasons.append('heldout_family')
    if source['available_on'] >= request.as_of: reasons.append('not_strictly_earlier')
    left, right = canonical_context(source['context']), canonical_context(request.context)
    rows = []
    for key in sorted(CONTEXT):
        a, b = left[key], right[key]
        if a is None or b is None:
            state = 'unknown'
        elif a == b:
            state = 'identity'
        elif key in ('age_min', 'followup_min') and not eligibility(source['context']) and not eligibility(request.context):
            state = 'eligible_difference'
        else:
            state = 'unlicensed_difference'
        rows.append({'field': key, 'source': source['context'][key], 'target': request.context[key], 'status': state,
                     'representation_blocker': state in ('unknown', 'unlicensed_difference')})
    before = compare_context(source['context'], request.context)
    blockers = [r['field'] for r in rows if r['representation_blocker']]
    return {'version': VERSION, 'reference': source['reference'], 'family': source['family'], 'rows': rows,
            'strict_blocker_count': len(before['different']) + len(before['unknown']),
            'representation_blockers': blockers, 'eligibility_reasons': reasons,
            'representation_compatible': not blockers and not reasons,
            'empirical_transfer_licensed': False, 'knowledge_equivalence': False, 'scientific_prediction': False,
            'policy_sha256': POLICY_SHA256,
            'remaining_assumptions': ['population and followup differences may modify associations; protocol eligibility is not exchangeability']}


def decimal(value):
    require(isinstance(value, str), 'Exact decimal string required')
    try: result = Decimal(value)
    except InvalidOperation: require(False, 'Invalid decimal')
    require(result.is_finite(), 'Finite quantity required')
    return result


def derive_representation(effect, mapping):
    """Результат условен относительно явно заданной смены координат того же анализа."""
    require(set(effect) == {'analysis_id', 'measure', 'estimate', 'ci95', 'unit', 'p', 'test', 'context', 'contrast', 'source_binding'}, 'Closed numerical effect required')
    require(effect['measure'] in {'linear_coefficient', 'ratio'}, 'Supported effect measure required')
    require(isinstance(effect['analysis_id'], str) and effect['analysis_id'], 'Analysis identity required')
    require(isinstance(effect['context'], dict) and effect['context'] and isinstance(effect['unit'], str) and effect['unit'], 'Scope and unit required')
    require(set(effect['contrast']) == {'numerator', 'denominator'} and all(isinstance(v, str) and v for v in effect['contrast'].values()), 'Oriented contrast required')
    require(set(effect['source_binding']) == {'source_sha256', 'run_id', 'frame_sha256', 'provenance'}, 'Bound source frame required')
    require(effect['source_binding']['provenance'] and effect['source_binding']['run_id'], 'Source provenance required')
    for key in ['source_sha256', 'frame_sha256']:
        digest = effect['source_binding'][key]
        require(isinstance(digest, str) and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest), 'Invalid digest')
    require(isinstance(effect['ci95'], list) and len(effect['ci95']) == 2, 'Two CI endpoints required')
    estimate, lower, upper = decimal(effect['estimate']), decimal(effect['ci95'][0]), decimal(effect['ci95'][1])
    require(lower <= estimate <= upper, 'Ordered CI must contain estimate')
    require(0 <= decimal(effect['p']) <= 1, 'Probability outside range')
    require(effect['test'] == {'null_value': '0' if effect['measure'] == 'linear_coefficient' else '1',
                              'policy': 'same_original_test_reparameterized'}, 'Original null and full test must be preserved')
    fields = {'affine_coordinates_same_analysis': {'kind', 'analysis_id', 'a', 'b', 'c', 'd', 'target_unit', 'target_contrast'},
              'reverse_ratio_contrast_same_analysis': {'kind', 'analysis_id'}}
    require(mapping.get('kind') in fields and set(mapping) == fields[mapping['kind']], 'Closed coordinate definition required')
    require(mapping['analysis_id'] == effect['analysis_id'], 'Reparameterization cannot change study or analysis')
    result = deepcopy(effect)
    with localcontext() as ctx:
        ctx.prec = 28
        if mapping['kind'] == 'affine_coordinates_same_analysis':
            require(effect['measure'] == 'linear_coefficient', 'Affine coefficient bridge cannot convert a hazard ratio')
            a, c = decimal(mapping['a']), decimal(mapping['c'])
            decimal(mapping['b']); decimal(mapping['d'])
            require(a > 0 and c > 0, 'Positive coordinate scales required')
            require(isinstance(mapping['target_unit'], str) and mapping['target_unit'], 'Target unit required')
            require(set(mapping['target_contrast']) == {'numerator', 'denominator'} and all(isinstance(v, str) and v for v in mapping['target_contrast'].values()), 'Explicit target contrast required')
            factor = a / c
            result.update(estimate=str(estimate * factor), ci95=[str(lower * factor), str(upper * factor)],
                          unit=mapping['target_unit'], contrast=deepcopy(mapping['target_contrast']))
            equation = 'Y_target = a*Y_source + b; X_target = c*X_source + d; beta_target = (a/c)*beta_source'
        elif mapping['kind'] == 'reverse_ratio_contrast_same_analysis':
            require(effect['measure'] == 'ratio' and effect['unit'] == 'dimensionless', 'Dimensionless ratio required')
            require(0 < lower <= estimate <= upper, 'Positive ratio and interval required')
            result.update(estimate=str(1 / estimate), ci95=[str(1 / upper), str(1 / lower)],
                          contrast={'numerator': effect['contrast']['denominator'], 'denominator': effect['contrast']['numerator']})
            equation = 'ratio_reverse = 1/ratio; CI_reverse = [1/upper, 1/lower]'
        else:
            require(False, 'Unlicensed nonlinear or cross-study mapping')
    output = {'version': VERSION, 'source_effect_sha256': fingerprint(effect), 'mapping_sha256': fingerprint(mapping),
              'status': 'conditional_mathematical_derivation', 'equation': equation, 'result': result,
              'scientific_prediction': False, 'empirical_transport': False, 'source_mapping': 'explicit coordinate definition, not inferred from score ranges',
              'precision': 'arithmetic from reported source values; no extra measurement precision', 'p_invariant': True,
              'analysis_context_unchanged': True, 'source_binding': deepcopy(effect['source_binding'])}
    return {**output, 'derivation_id': fingerprint(output)}


def slope(x, y):
    require(len(x) == len(y) and len(x) >= 2, 'Paired observations required')
    mx, my = sum(x) / len(x), sum(y) / len(y)
    denominator = sum((v - mx) ** 2 for v in x)
    require(denominator > 0, 'Predictor variation required')
    return sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True)) / denominator


def counterexamples():
    """Синтетические контрмодели опровергают безусловные мосты, не научные результаты."""
    rows = [
        {'id': 'quartile_to_continuous', 'input': {'x': [1, 2, 3, 4], 'score_change': [0, -10, 10, -1]},
         'quantities': {'endpoint_high_minus_low': -1, 'continuous_slope': slope([1, 2, 3, 4], [0, -10, 10, -1])},
         'why_ru': 'Контраст крайних групп и линейный наклон могут иметь противоположные знаки.',
         'why_en': 'An extreme-group contrast and a linear slope can have opposite signs.'},
        {'id': 'linear_to_log', 'input': {'x': [1, 2, 100], 'score_change': [0, 10, 4]},
         'quantities': {'raw_slope': slope([1, 2, 100], [0, 10, 4]), 'log_slope': slope([log(1), log(2), log(100)], [0, 10, 4])},
         'why_ru': 'Логарифм сохраняет порядок X, но не гарантирует сохранения знака коэффициента общей линейной регрессии.',
         'why_en': 'Log preserves X ordering but does not guarantee the same sign of a fitted linear coefficient.'},
        {'id': 'aggregate_to_MCI_stratum', 'input': {'stratum_A': {'high_n': 10, 'low_n': 90, 'high_decline': 2, 'low_decline': 3},
                                                 'stratum_B': {'high_n': 90, 'low_n': 10, 'high_decline': 8, 'low_decline': 9}},
         'quantities': {'within_A_high_minus_low': -1, 'within_B_high_minus_low': -1, 'pooled_high_minus_low': (10 * 2 + 90 * 8) / 100 - (90 * 3 + 10 * 9) / 100},
         'why_ru': 'Из общего результата нельзя восстановить результат подгруппы без структуры смеси. Группы A/B синтетические, не измерения MCI.',
         'why_en': 'A pooled result does not identify a subgroup result without mixture information. A/B are synthetic groups, not MCI measurements.'},
        {'id': 'average_to_instantaneous', 'input': {'function': 'f(t)=t*t-6*t', 'observed_interval': [0, 3], 'instant': 3.5},
         'quantities': {'average_rate_0_to_3': -3, 'instantaneous_rate_at_3_5': 1},
         'why_ru': 'Средняя скорость на одном интервале и мгновенная скорость в другой момент могут различаться по знаку. Это контрмодель, не траектория GEMS.',
         'why_en': 'An average rate over one interval and an instantaneous rate at another time can have opposite signs. This is a countermodel, not a GEMS trajectory.'},
        {'id': 'significance_across_alpha_or_power', 'input': {'p': '0.01', 'alpha_source': '0.05', 'alpha_target': '0.0025'},
         'quantities': {'meets_source_strict_alpha': True, 'meets_target_strict_alpha': False},
         'why_ru': 'Одинаковое P при разных критериях даёт разную классификацию значимости; знак или отсутствие эффекта из этого не выводятся.',
         'why_en': 'The same P under different thresholds yields different significance labels; it does not identify effect direction or absence.'},
    ]
    return [{**row, 'synthetic': True, 'unconditional_bridge_refuted': True, 'scientific_article_refuted': False,
             'scientific_prediction': False, 'version': VERSION} for row in rows]
