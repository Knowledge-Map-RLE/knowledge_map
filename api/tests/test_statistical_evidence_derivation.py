"""Проверяет научные различия и отказы, значимые для семантического вывода."""
from dataclasses import replace
import pytest
from domain.article_maps import ArticleMapError
from domain.statistical_evidence_derivation import StatisticalEvidence, derive_evidence_label

JORDANOVA = StatisticalEvidence('odds_ratio','dimensionless',2.9,(1.1,7.5),0.031,True)
TOOTH = StatisticalEvidence('linear_coefficient','mmse points/year',-0.13,(-0.47,0.21),0.447,False)


def test_real_estimates_do_not_turn_nonsignificance_into_inverse_association():
    assert derive_evidence_label(JORDANOVA)['label'] == 'positive_association'
    actual = derive_evidence_label(TOOTH)
    assert actual['label'] == 'not_statistically_detected'
    assert actual['point_direction'] == 'more_decline'
    assert not actual['causal_effect_established'] and not actual['new_empirical_fact_predicted']


def test_orientation_is_explicit_and_not_inferred_from_beta_sign():
    evidence = replace(TOOTH,estimate=-0.4,ci95=(-0.8,-0.01),p=0.044)
    assert derive_evidence_label(evidence)['label'] == 'positive_association'
    assert derive_evidence_label(replace(evidence,higher_means_more_decline=True))['label'] == 'inverse_association'


def test_missing_interval_or_p_does_not_become_a_negative_result():
    assert derive_evidence_label(replace(JORDANOVA,ci95=None))['label'] == 'insufficient_data'
    assert derive_evidence_label(replace(JORDANOVA,p=None))['label'] == 'insufficient_data'


def test_rounded_or_inconsistent_confidence_interval_needs_review():
    assert derive_evidence_label(replace(JORDANOVA,ci95=(1.0,7.5)))['label'] == 'requires_review'
    assert derive_evidence_label(replace(TOOTH,p=0.01))['label'] == 'requires_review'


def test_exact_alpha_boundary_and_null_estimate_are_retained():
    assert derive_evidence_label(replace(JORDANOVA,p=0.05,ci95=(0.9,7.5)))['label'] == 'not_statistically_detected'
    assert derive_evidence_label(replace(TOOTH,estimate=0))['point_direction'] is None


@pytest.mark.parametrize('changes',[{'estimate':True},{'estimate':float('nan')},{'p':1.1},{'ci95':(3.0,7.5)},
                                   {'ci95':(-1.0,7.5)},{'unit':'mmse points/year'},{'effect':'hazard_ratio'},
                                   {'higher_means_more_decline':None}])
def test_invalid_or_unsupported_evidence_is_rejected(changes):
    with pytest.raises(ArticleMapError):
        derive_evidence_label(replace(JORDANOVA,**changes))


def test_confidence_level_is_not_silently_reinterpreted():
    with pytest.raises(ArticleMapError):
        derive_evidence_label(JORDANOVA,alpha=0.01)
