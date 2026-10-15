"""Проверки научных ограничений черновика WHICAP."""
import json
from pathlib import Path

import pytest

from tools.author_manly_prose_stage import build


@pytest.fixture
def records():
    root = Path(__file__).resolve().parents[2]
    source = json.loads((root / 'eval/whole_map_forecast/manly-complete-map-v1/source-v1/source.json').read_text(encoding='utf-8'))
    return {k['key']: k for k in build(source)['knowledge_draft']}


def test_nonsignificance_is_not_zero(records):
    nulls = [k for key, k in records.items()
             if key.startswith(('mci-null-', 'ad-null-'))
             and k['predicate'] == 'association not statistically detected']
    assert len(nulls) == 12
    assert all('relative_estimate' not in k['attrs'] for k in nulls)
    assert all(k['attrs']['causal_identification']['value'] == 'not established' for k in nulls)
    assert records['diagnostic-instability-null']['predicate'] == 'association not statistically detected'


def test_ambiguous_endpoint_remains_unresolved(records):
    uncertain = [k for key, k in records.items() if key.startswith('ambiguous-ad-section-age-')]
    assert len(uncertain) == 3
    assert all(k['time'] is None and k['conditions'] == [] for k in uncertain)
    assert all('endpoint unresolved' in k['roles']['outcome'] for k in uncertain)


def test_subtypes_have_shared_criteria_and_membership(records):
    subtypes = [records['subtype-' + name] for name in ['amnestic','executive','language','visuospatial','mcdm','mcdn']]
    assert len(subtypes) == 6
    for k in subtypes:
        assert k['logic'] == 'conjunction'
        assert k['claims'][0]['predicate'] == 'subtype_of'
        assert k['claims'][1]['roles']['shared_criteria'] == '@mci-core-criteria'


def test_model_and_phenotype_are_distinct(records):
    memory = records['memory-mci-heart']
    nonmemory = records['nonmemory-mci-education']
    assert memory['roles']['outcome'] != nonmemory['roles']['outcome']
    assert memory['roles']['analysis_model'] != nonmemory['roles']['analysis_model']
    assert memory['attrs']['relative_estimate']['value'] == '0.70'
    assert nonmemory['attrs']['relative_estimate']['value'] == '1.4'


def test_methods_have_explicit_operation_predicates(records):
    assert records['calculate-incidence']['kind'] == 'action'
    assert records['calculate-incidence']['predicate'] == 'estimate incidence rate'
    assert records['fit-mci-cox']['predicate'] == 'fit Cox proportional-hazards model'
    assert records['calculate-ad-incidence']['predicate'] == 'estimate incidence rate'
    assert records['fit-ad-cox']['predicate'] == 'fit Cox proportional-hazards model'


def test_selection_denominators_and_discrepancy_survive(records):
    assert records['selection-age-education']['attrs']['included_age']['value'] == '75.8'
    assert records['results-sample-profile']['attrs']['age']['value'] == '76.1'
    assert records['results-duration-and-genotype']['attrs']['genotyped']['value'] == '2067'
    assert records['genotype-subset-contrast']['attrs']['sample_n']['value'] == '1572'
    assert records['death-autopsy-selection']['roles']['autopsy_denominator'] == 'participants who died'


def test_observed_reevaluations_account_for_final_sample(records):
    values = records['reevaluation-distribution']['attrs']
    assert sum(int(v['value']) for v in values.values()) == 2364
    assert 'visits_5' not in values


def test_reversion_phases_and_overlapping_denominators(records):
    assert records['reversion-all-visits']['attrs']['normal_n']['value'] == '170'
    assert records['first-followup-course']['attrs']['normal_n']['value'] == '255'
    first = records['first-followup-course']['attrs']
    assert sum(int(first[k]['value']) for k in ['normal_n','mci_n','ad_n','other_dementia_n']) == 564
    assert 'overlapping' in records['reversion-overlapping-criteria']['predicate']


def test_validation_endpoint_and_unresolved_tasks(records):
    ad = records['autopsy-marker-stable-cognition-ad']
    any_path = records['autopsy-marker-stable-cognition-any']
    assert ad['roles']['reference_outcome'] != any_path['roles']['reference_outcome']
    assert ad['attrs']['specificity']['value'] == '59'
    assert any_path['attrs']['specificity']['value'] == '100'
    assert records['continued-followup-task']['status'] == 'unresolved'
    assert records['larger-autopsy-task']['status'] == 'unresolved'


def test_author_hypotheses_are_not_observed_biomarkers(records):
    hypothesis = records['subtype-biomarker-hypothesis']
    assert hypothesis['modality'] == 'possible'
    assert hypothesis['type'] == 'assertion'
    assert hypothesis['attrs'] == {}
    assert 'MCDN' in hypothesis['roles']['population']
    assert records['subtype-underlying-pathology-hypothesis']['modality'] == 'possible'
    assert records['cutoff-fluctuation-hypothesis']['modality'] == 'possible'


def test_arguments_use_existing_distinct_knowledge(records):
    from tools.manly_clinical_course_records import clinical_argument_transitions
    for t in clinical_argument_transitions():
        assert t['target'] in records
        assert all(s in records and s != t['target'] for s in t['sources'])
        assert t['units'] and t['reason']
    joint = next(t for t in clinical_argument_transitions() if t['target'] == 'weight-objective-criteria-proposal')
    assert len(joint['sources']) == 2


def test_background_is_not_primary_cohort_evidence(records):
    assert records['background-progression-context']['roles']['evidence_origin'] == 'studies cited by WHICAP introduction'
    incident = records['memory-nonmemory-incidence']['attrs']
    assert int(incident['memory_cases']['value']) + int(incident['nonmemory_cases']['value']) == int(incident['total_cases']['value'])
    assert incident['memory_rate']['unit'] == 'per 100 person-years'
    assert records['amnestic-mcdm-rate-difference']['attrs']['difference']['unit'] == 'per 100 person-years'
