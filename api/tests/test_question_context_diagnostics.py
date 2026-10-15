"""Различия контрактов не превращаются в прогноз или научное опровержение."""
from dataclasses import replace

import pytest

from domain.article_maps import ArticleMapError
from domain.question_context_diagnostics import diagnose_context
from domain.qualitative_question_prediction import fit_qualitative_forecast
from domain.research_semantics import context_value as cv
from tests.test_qualitative_question_prediction import claim, policy, question


def forecast(a, b):
    result = fit_qualitative_forecast({(c.evidence.article_id, c.claim_id): c for c in [a, b]}, [], {}, question(), policy())
    result['run_id'] = 'synthetic'
    return result


def test_identity_and_statistical_estimate_are_not_applicability_differences():
    a, b = claim('a', 'one'), claim('b', 'two', value='3')
    result = diagnose_context(forecast(a, b))
    assert result['cross_family_pairs'] == result['applicability_equal_pairs'] == 1
    assert not result['pairs'][0]['differences']
    assert result['status'].startswith('contract_diagnostic_not_forecast')


def test_report_preserves_context_and_finding_differences_and_does_not_duplicate_families():
    a, b = claim('a', 'one'), claim('b', 'two', value='-1', modality='statistically detected')
    b = replace(b, context={**b.context, 'stratum': cv('different age and mci status')})
    result = diagnose_context(forecast(a, b))
    assert result['applicability_equal_pairs'] == 0
    assert result['difference_counts'] == {'context:stratum': 1}
    assert not result['pairs'][0]['same_finding_label']
    assert result['pairs'][0]['differences'][0]['right'] == b.context['stratum']
    assert diagnose_context(forecast(a, replace(b, evidence=replace(b.evidence, family='one'))))['pairs'] == []


def test_unresolved_context_not_admitted_and_row_order_is_irrelevant():
    a, b = claim('a', 'one'), claim('b', 'two')
    result = forecast(a, b)
    reference = diagnose_context(result)
    result['observations'].reverse()
    assert diagnose_context(result) == reference
    unresolved = replace(b, context={**b.context, 'stratum': cv(None, 'not_reported')})
    assert diagnose_context(forecast(a, unresolved))['cross_family_pairs'] == 0
    result['observations'].append(result['observations'][0])
    with pytest.raises(ArticleMapError, match='Duplicate'): diagnose_context(result)
