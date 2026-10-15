"""Семейство оператора не превращает разные модели или факты в эквивалентные."""
from copy import deepcopy
import pytest

from domain.article_maps import ArticleMapError
from domain.semantic_operator_graph import build_graph, match_pattern
from domain.operator_frame_routing import route_graph, family_motifs
from tests.test_semantic_operator_graph import fixture, pattern


def test_unregistered_predicate_stays_explicit_without_guessed_semantics():
    g = build_graph([fixture()]); r = route_graph(g)
    assert len(r['rows']) == g['statement_count'] == r['counts']['unregistered']
    assert all(not x['forecast_licensed'] and not x['semantic_equivalence_established'] for x in r['rows'])


def test_different_models_keep_exact_predicates_units_and_scopes():
    m = fixture(); names = ['estimated hazard ratio', 'estimated cognitive level difference', 'estimated instantaneous rate difference']
    for k, name in zip(m['graph']['knowledge'], names): k['semantic_frame']['statements'][0]['predicate'] = name
    g = build_graph([m]); before = deepcopy(g); r = route_graph(g)
    assert g == before and r['counts']['reported_model_parameter'] == 3
    assert {s['predicate'] for s in g['statements'].values()} == set(names)
    assert not match_pattern(g, pattern())['matches']


def test_frequency_family_does_not_convert_rate_to_prevalence_or_probability():
    m = fixture()
    for k, name, unit in zip(m['graph']['knowledge'], ['reported cohort prevalence', 'mci incidence', 'dementia conversion'],
                              ['percent', 'per1000personyear', 'percent']):
        s = k['semantic_frame']['statements'][0]; s['predicate'] = name
        s['qualifiers']['attributes'] = [{'name': 'estimate', 'value': '10', 'unit': unit}]
    g = build_graph([m]); r = route_graph(g)
    assert r['counts']['reported_frequency'] == 3
    assert {s['attributes'][0]['unit'] for s in g['statements'].values()} == {'percent', 'per1000personyear'}
    assert all(not s['independent_premise_licensed'] for s in g['statements'].values())


def test_family_motifs_preserve_negative_statements_and_original_graph():
    one, two = fixture(), fixture('two')
    for m in (one, two):
        for k in m['graph']['knowledge']: k['semantic_frame']['statements'][0]['predicate'] = 'group comparison'
    two['graph']['knowledge'][0]['semantic_frame']['statements'][0]['negated'] = True
    g = build_graph([one, two]); before = deepcopy(g); routing = route_graph(g)
    motifs = family_motifs(g, routing, {'one': 'f1', 'two': 'f2'})
    assert before == g and any(any(x['negated'] for x in p['shape']['statements']) for p in motifs['patterns'])
    assert all(not p['inference_licensed'] for p in motifs['patterns']) and not motifs['predictions']


def test_changed_routing_ledger_rejected():
    g = build_graph([fixture()]); r = route_graph(g); r['rows'][0]['operator_family'] = 'reported_model_parameter'
    with pytest.raises(ArticleMapError): family_motifs(g, r, {'one': 'f1'})


def test_undetected_effect_is_distinct_from_detected_benefit():
    m = fixture()
    for k, predicate in zip(m['graph']['knowledge'], ['memory performance improved',
                            'improvement not statistically detected', 'possible explanation']):
        k['semantic_frame']['statements'][0]['predicate'] = predicate
    graph = build_graph([m]); before = deepcopy(graph); routed = route_graph(graph)
    assert graph == before
    assert routed['counts']['reported_intervention_effect'] == 1
    assert routed['counts']['reported_undetected_or_unestablished_effect'] == 1
    assert routed['counts']['proposed_mechanism'] == 1
    assert all(not row['forecast_licensed'] for row in routed['rows'])


def test_new_primary_categories_do_not_normalize_fact_semantics():
    m = fixture()
    names = ['performed method', 'investigate unresolved', 'upstream activity inferred']
    for k, name in zip(m['graph']['knowledge'], names):
        k['semantic_frame']['statements'][0]['predicate'] = name
    graph = build_graph([m]); before = deepcopy(graph); routed = route_graph(graph)
    assert graph == before and {s['predicate'] for s in graph['statements'].values()} == set(names)
    assert set(routed['counts']) == {'experimental_procedure', 'research_task', 'reported_inferred_network_activity'}
    assert not any(row['semantic_equivalence_established'] for row in routed['rows'])


def test_cohort_operations_route_by_explicit_method_family_without_licensing_transfer():
    m = fixture()
    predicates = ['estimate incidence rate', 'calculate person-time', 'fit Cox proportional-hazards model']
    for item, predicate in zip(m['graph']['knowledge'], predicates):
        item['kind'] = 'action'
        item['knowledge_kind'] = 'operation'
        item['action_status'] = 'performed'
        item['semantic_frame']['statements'][0]['predicate'] = predicate
    graph = build_graph([m]); before = deepcopy(graph); routed = route_graph(graph)
    assert graph == before
    assert routed['counts'] == {'incidence_estimation': 1, 'person_time_calculation': 1,
                                'survival_model_fitting': 1}
    assert all(not row['forecast_licensed'] and not row['semantic_equivalence_established']
               for row in routed['rows'])


def test_hypothesis_modality_and_target_negation_survive_routing():
    m = fixture()
    first, second = [k['semantic_frame']['statements'][0] for k in m['graph']['knowledge'][:2]]
    first['predicate'] = 'possible feedback'; first['modality'] = 'may'
    second['predicate'] = 'cross reacts with'; second['negated'] = True
    graph = build_graph([m]); before = deepcopy(graph); routed = route_graph(graph)
    assert graph == before and routed['counts']['proposed_mechanism'] == 1
    assert routed['counts']['reported_target_mechanism'] == 1
    actual = list(graph['statements'].values())
    assert actual[0]['original_statement']['modality'] == 'may'
    assert actual[1]['original_statement']['negated'] is True


def test_unregistered_terms_remain_unregistered_after_expansion():
    m = fixture()
    for k in m['graph']['knowledge']:
        k['semantic_frame']['statements'][0]['predicate'] = 'Unknown brand new claim'
    routed = route_graph(build_graph([m]))
    assert routed['counts'] == {'unregistered': 3}
    assert all(row['operator_family'] is None for row in routed['rows'])


def test_native_underscore_and_uppercase_do_not_lose_rna_result():
    m = fixture()
    m['graph']['knowledge'][0]['semantic_frame']['statements'][0]['predicate'] = 'RNA_change_not_detected'
    routed = route_graph(build_graph([m]))
    assert routed['counts']['reported_undetected_or_unestablished_effect'] == 1
    row = next(r for r in routed['rows'] if r['native_predicate'] == 'RNA_change_not_detected')
    assert row['normalized_predicate'] == 'rna change not detected' and not row['forecast_licensed']
