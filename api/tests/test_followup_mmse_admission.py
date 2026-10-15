"""Последующий уровень MMSE и снижение среднего не заменяют индивидуальный годовой исход."""
import pytest
from domain.prospective_question_screening import screen_continuous_mmse


def record(estimand):
    baseline = {'axis': 'study_visit', 'value': 'baseline'}
    values = {'matrix': 'plasma', 'processing': 'direct_plasma_assay', 'exposure_visit': baseline,
              'outcome_start_visit': baseline, 'dementia_excluded': True, 'dementia_visit': baseline,
              'minimum_age_at_exposure': 65, 'outcome': {'instrument': 'mmse', 'estimand': estimand},
              'followup_years': {'basis': 'planned', 'value': 3}}
    return {'id': 'model-outcome-control', 'family': 'synthetic-kurogawa',
            'features': {key: {'status': 'known', 'value': value, 'evidence': []} for key, value in values.items()}}


@pytest.mark.parametrize('estimand', ['followup_score', 'baseline_score', 'followup_score_conditioned_on_baseline',
                                     'aggregate_mean_change'])
def test_decline_wording_and_two_measurements_do_not_change_the_model_dependent_variable(estimand):
    result = screen_continuous_mmse(record(estimand))
    assert not result['eligible_for_subquestion']
    assert result['blockers'] == [{'field': 'outcome', 'reason': 'not_continuous_annual_mmse_change', 'kind': 'mismatch'}]
    assert result['features']['outcome']['value']['estimand'] == estimand


def test_specimen_conflict_stays_unknown_not_a_serum_or_negative_effect_assumption():
    r = record('followup_score')
    r['features']['matrix'].update(status='not_reported', value=None)
    result = screen_continuous_mmse(r)
    assert {'field': 'matrix', 'reason': 'not_established', 'kind': 'unknown'} in result['blockers']
    assert not any(b['reason'] == 'not_plasma' for b in result['blockers'])
    assert not result['training_support_added']


def test_resolving_specimen_alone_does_not_admit_followup_score():
    r = record('followup_score')
    assert not screen_continuous_mmse(r)['eligible_for_subquestion']
    r['features']['outcome']['value']['estimand'] = 'two_assessment_annual_change'
    assert screen_continuous_mmse(r)['eligible_for_subquestion']
