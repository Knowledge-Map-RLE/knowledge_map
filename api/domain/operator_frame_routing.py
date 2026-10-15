"""Явный выбор семейства операторов; классификация не устанавливает эквивалентность."""
from collections import Counter
from copy import deepcopy

from domain.article_maps import fingerprint, require

VERSION = 'explicit-operator-frame-routing-3'
DICTIONARY = {
    'reported_model_parameter': [
        'estimated association', 'estimated cognitive level difference', 'estimated instantaneous rate difference',
        'estimated hazard ratio', 'estimated cognitive slope', 'regression coefficient',
        'stratified estimated cmv association', 'meta regression coefficient',
        'abstract-reported validation slope', 'estimated baseline cognition'],
    'reported_sample_summary': ['reported baseline summary', 'sample profile', 'reported group summary',
                                'cohort profile', 'sample proportion', 'reference sample profile'],
    'reported_group_comparison': ['group comparison', 'reported attrition comparison', 'group difference',
                                  'memory performance difference', 'some induction greater in acute model'],
    'reported_adjusted_group_mean': ['reported adjusted mmse mean'],
    'reported_frequency': ['reported cohort prevalence', 'subgroup mci prevalence', 'mci incidence',
                           'reported cohort incidence', 'dementia conversion'],
    'reported_correlation': ['partial correlation', 'stratified correlation', 'correlation coefficient'],
    'reported_association': ['associated with', 'risk factor association', 'reported lower cognition association',
                             'reported faster decline association', 'cited faster decline association'],
    'definition_or_characterization': ['characterized by', 'subtype of', 'intermediate between', 'barrier definition'],
    'reported_intervention_effect': ['reduced after intervention', 'exacerbated after intervention',
                                    'improved after intervention', 'no improvement',
                                    'memory performance improved', 'plaque burden reduced after intervention',
                                    'plaque count reduced after intervention', 'concentration reduced after intervention',
                                    'cell count reduced after intervention', 'morphology preserved after intervention',
                                    'downregulation prevented', 'apical localization preserved'],
    'measurement': ['measure biomarkers', 'measured using', 'measure subjective sleep', 'measure physical activity'],
    'review_procedure': ['conduct review', 'search literature', 'extract study data', 'assessed risk of bias'],
    'reported_limit': ['limited by', 'inconsistent association findings', 'unknown episode duration',
                       'interpretation limited by', 'model scope limitation'],
    'reported_strength': ['strengthened by'],
    'reported_expression_response': ['expression increased', 'expression reduced after intervention',
                                     'induction attenuated', 'induction abrogated', 'induction prevented'],
    'reported_undetected_or_unestablished_effect': [
        'differential expression not detected', 'change not detected', 'not induced in this model',
        'severe microvillus loss not observed', 'induced permeability increase not observed',
        'rna change not detected', 'count decrease not statistically established', 'count decrease not detected',
        'decrease not statistically established', 'improvement not statistically detected',
        'inflammatory response change not detected'],
    'reported_barrier_response': ['permeability increased'],
    'reported_inferred_network_activity': ['upstream activity inferred'],
    'reported_target_mechanism': ['inhibitor mechanism', 'cross reacts with'],
    'source_background': ['reported background', 'motivates selective inhibition'],
    'proposed_mechanism': ['possible explanation', 'possible interaction', 'possible feedback', 'proposed mechanistic chain'],
    'research_task': ['investigate', 'investigate unresolved'],
    'experimental_procedure': ['performed method'],
    'incidence_estimation': ['estimate incidence rate'],
    'person_time_calculation': ['calculate person-time'],
    'survival_model_fitting': ['fit cox proportional-hazards model'],
    'reported_data_access': ['data deposited'],
}
DICTIONARY_SHA256 = fingerprint(DICTIONARY)
PREDICATES = {predicate: family for family, values in DICTIONARY.items() for predicate in values}
require(len(PREDICATES) == sum(len(v) for v in DICTIONARY.values()), 'Ambiguous routing dictionary')


def route_graph(graph):
    rows = []
    for statement in graph['statements'].values():
        family = PREDICATES.get(statement['predicate'])
        rows.append({'statement_id': statement['id'], 'parent': statement['parent'],
            'native_predicate': statement['original_statement']['predicate'],
            'normalized_predicate': statement['predicate'], 'operator_family': family,
            'status': 'explicit_routing_category' if family else 'no_registered_operator_family',
            'reason_ru': 'Категория выбирает проверку; исходный предикат и все ограничения сохраняются.' if family else
                         'Для этого предиката ещё нет явного семейства операторов; смысл не угадывается.',
            'semantic_equivalence_established': False, 'forecast_licensed': False})
    return {'version': VERSION, 'dictionary': deepcopy(DICTIONARY), 'dictionary_sha256': DICTIONARY_SHA256,
            'rows': rows, 'counts': dict(Counter(r['operator_family'] or 'unregistered' for r in rows)),
            'all_statements_routed_or_explicitly_unregistered': len(rows) == graph['statement_count'],
            'scientific_success': False}


def family_motifs(graph, routing, families):
    from domain.semantic_operator_graph import inventory_patterns
    require(routing['version'] == VERSION and routing['dictionary_sha256'] == DICTIONARY_SHA256
            and routing['rows'] == route_graph(graph)['rows'], 'Routing binding changed')
    # Временное представление служит только инвентаризации форм, не сопоставлению фактов или выводу.
    shadow = dict(graph); shadow['statements'] = {}
    for statement in graph['statements'].values():
        family = PREDICATES.get(statement['predicate'])
        if family is not None:
            shadow['statements'][statement['id']] = {**statement, 'predicate': 'operator-family:' + family}
    result = inventory_patterns(shadow, families)
    for pattern in result['patterns']:
        pattern['status'] = 'operator_family_motif_only; different predicates and estimands retained'
        pattern['semantic_equivalence_established'] = False
        pattern['inference_licensed'] = False
    return {**result, 'routing_version': VERSION, 'routing_dictionary_sha256': DICTIONARY_SHA256,
            'interpretation_ru': 'Общие семьи операций, а не одинаковые факты, модели или логические законы.'}
