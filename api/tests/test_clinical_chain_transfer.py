"""Проверки временной доступности, контекста, альтернатив и независимости семей."""
from dataclasses import replace
from copy import deepcopy
import pytest
from domain.article_maps import ArticleMapError
from domain.clinical_chain_transfer import ChainCase, PremiseNode, Support, assess_transfer

CONTEXT = {'age_min': 75, 'dementia_excluded': True, 'specimen': 'plasma',
           'timing': 'single_baseline', 'exposure': 'IL6', 'outcome_scope': 'global_change',
           'followup_min': 3, 'instrument': 'mmse', 'estimand': 'annual_change',
           'contrast': 'high_low', 'mci': 'absent', 'adjustment_class': 'basic_baseline'}


def sample():
    return ChainCase('toy', 'clinical_transfer', 'isolated_IL6',
                     (PremiseNode('a', 'known_before_forecast'), PremiseNode('b', 'known_before_forecast'),
                      PremiseNode('c', 'requires_target_followup')),
                     (('a', 'c'), ('b', 'c')), 'c', (('a', 'b'),),
                     tuple(Support(f, '2010-01-01', True, deepcopy(CONTEXT)) for f in ('A', 'B')))


def assess(case=None, context=None):
    return assess_transfer(case or sample(), context or deepcopy(CONTEXT), '2014-01-01', ('T',))


def test_candidate_is_not_success_or_forecast():
    result = assess()
    assert result['status'] == 'candidate_for_sealed_test'
    assert not result['forecast_generated'] and not result['scientific_success'] and not result['rule_learning_performed']


def test_future_measurement_blocks_joint_group():
    case = sample(); nodes = (replace(case.nodes[0], availability='requires_target_followup'), *case.nodes[1:])
    assert 'no_available_premise_path' in assess(replace(case, nodes=nodes))['reasons']


def test_available_alternative_does_not_require_unavailable_group():
    case = sample(); nodes = (replace(case.nodes[0], availability='requires_target_followup'), *case.nodes[1:])
    result = assess(replace(case, nodes=nodes, premise_groups=(('a',), ('b',))))
    assert result['status'] == 'candidate_for_sealed_test'
    assert [p['available_before_forecast'] for p in result['premise_paths']] == [False, True]


def test_unavailable_ancestor_blocks_known_immediate_premise():
    case = sample()
    case = replace(case, nodes=(*case.nodes, PremiseNode('upstream', 'requires_target_followup')),
                   edges=(*case.edges, ('upstream', 'a')))
    assert 'no_available_premise_path' in assess(case)['reasons']


@pytest.mark.parametrize('operator', ['measurement_to_result', 'method_application', 'limitation_to_task', 'model_validation'])
def test_author_use_is_not_alone_clinical_transfer(operator):
    assert 'operator_is_not_clinical_transfer' in assess(replace(sample(), operator=operator))['reasons']


@pytest.mark.parametrize('scope', ['multi_marker', 'other_exposure', 'method', 'research_task'])
def test_scope_cannot_be_relabelled(scope):
    assert 'scope_is_not_isolated_IL6' in assess(replace(sample(), scope=scope))['reasons']


@pytest.mark.parametrize('change', [dict(family='A'), dict(family='T'), dict(available_on='2014-01-01'), dict(author_use_verified=False)])
def test_independence_time_and_grounding(change):
    case = sample(); supports = (case.supports[0], replace(case.supports[1], **change))
    assert 'fewer_than_two_applicable_independent_families' in assess(replace(case, supports=supports))['reasons']


@pytest.mark.parametrize('key,value', [('specimen', 'serum'), ('estimand', 'concurrent_score'), ('mci', None),
                                      ('contrast', 'log_per_sd'), ('outcome_scope', 'domain_change')])
def test_unknown_and_different_context_never_confirm_applicability(key, value):
    case = sample(); support = replace(case.supports[1], context={**CONTEXT, key: value})
    assert assess(replace(case, supports=(case.supports[0], support)))['status'] == 'not_ready'


@pytest.mark.parametrize('change', [dict(edges=(('a', 'c'), ('c', 'a'))), dict(edges=(('missing', 'c'),)),
                                  dict(premise_groups=(('a',),)), dict(premise_groups=(('a', 'a'),)),
                                  dict(premise_groups=(('a', 'b'), ('a', 'b'))),
                                  dict(premise_groups=(('a', 'b'), ('b', 'a')))])
def test_invalid_graph_or_premise_group_rejected(change):
    with pytest.raises(ArticleMapError): assess(replace(sample(), **change))
