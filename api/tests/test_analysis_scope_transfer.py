"""Перенос фильтров между моделями и допустимое наследование свойств популяции."""
import copy
import pytest
from domain.article_maps import digest
from domain.analysis_scope_transfer import audit_scope_transfer
from application.audit_analysis_scope import AuditAnalysisScope
from infrastructure.research_artifacts import FileResearchArtifacts

@pytest.fixture
def inputs():
    text = 'All baseline participants were aged at least 60. The analysis excludes diagnosed baseline dementia.'
    source = {'paper': {'text': text, 'sha256': digest(text)}}
    binding = {'article_id': 'paper', 'source_sha256': digest(text), 'evidence': [
        {'start': 0, 'end': len(text), 'text': text, 'offset_encoding': 'unicode_code_points'}]}
    scope = {'family': 'family-a', 'analysis_id': 'model-a', 'population_id': 'selected-a', 'visit_id': 'blood-baseline', 'level': 'analysis'}
    fact = {'id': 'clinical-exclusion', 'field': 'dementia_excluded', 'value': True, 'scope': scope,
            'universal_population_fact': False, 'binding': binding}
    return fact, copy.deepcopy(scope), source

def test_same_analysis_scope_preserves_known_condition(inputs):
    fact, target, sources = inputs
    result = audit_scope_transfer(fact, target, None, sources)
    assert result['context_inheritance_allowed'] and result['resolved_context_value'] is True
    assert not result['empirical_effect_transfer_allowed'] and not result['clinical_prediction']

@pytest.mark.parametrize(('key', 'value', 'reason'), [
    ('analysis_id', 'model-b', 'different_analysis_or_population'),
    ('population_id', 'selected-b', 'different_analysis_or_population'),
    ('family', 'family-b', 'different_family'),
    ('visit_id', 'year-four', 'different_origin_visit'),
    ('population_id', None, 'unknown_population_or_origin'),
    ('analysis_id', None, 'unknown_analysis_identity')])
def test_cohort_name_is_not_sufficient(inputs, key, value, reason):
    fact, target, sources = inputs; target[key] = value
    result = audit_scope_transfer(fact, target, None, sources)
    assert not result['context_inheritance_allowed'] and reason in result['blockers']
    assert result['resolved_context_value'] is None

def test_unknown_clinical_exclusion_not_resolved(inputs):
    fact, target, sources = inputs; fact['value'] = None
    assert 'unknown_fact_value' in audit_scope_transfer(fact, target, None, sources)['blockers']

def universal(inputs):
    fact, target, sources = inputs
    fact.update(field='minimum_age', value=60, universal_population_fact=True)
    fact['scope'].update(level='cohort', analysis_id=None, population_id='original')
    membership = {'family': 'family-a', 'visit_id': 'blood-baseline', 'parent_population_id': 'original',
                  'child_population_id': 'selected-a', 'binding': copy.deepcopy(fact['binding'])}
    return fact, target, membership, sources

def test_universal_baseline_age_inherits_to_proven_subset(inputs):
    fact, target, membership, sources = universal(inputs)
    result = audit_scope_transfer(fact, target, membership, sources)
    assert result['context_inheritance_allowed'] and result['resolved_context_value'] == 60

def test_subset_proof_required_even_for_universal_fact(inputs):
    fact, target, membership, sources = universal(inputs)
    assert 'subset_membership_not_proven' in audit_scope_transfer(fact, target, None, sources)['blockers']

@pytest.mark.parametrize('key', ['parent_population_id', 'child_population_id', 'visit_id', 'family'])
def test_unrelated_membership_cannot_license_inheritance(inputs, key):
    fact, target, membership, sources = universal(inputs); membership[key] = 'other'
    assert 'subset_membership_scope_differs' in audit_scope_transfer(fact, target, membership, sources)['blockers']

def test_followup_horizon_not_inherited_as_population_property(inputs):
    fact, target, membership, sources = universal(inputs); fact.update(field='followup_years', value=8)
    assert 'not_universal_population_property' in audit_scope_transfer(fact, target, membership, sources)['blockers']

def test_analysis_local_fact_cannot_be_marked_universal(inputs):
    fact, target, sources = inputs; fact['universal_population_fact'] = True
    with pytest.raises(ValueError, match='Analysis-local'):
        audit_scope_transfer(fact, target, None, sources)

@pytest.mark.parametrize('location', ['fact', 'membership'])
def test_modified_primary_evidence_rejected(inputs, location):
    fact, target, membership, sources = universal(inputs)
    binding = fact['binding'] if location == 'fact' else membership['binding']
    binding['evidence'][0]['text'] += 'invented'
    with pytest.raises(ValueError, match='evidence differs'):
        audit_scope_transfer(fact, target, membership, sources)

@pytest.mark.parametrize('value', ['true', 1, [], {}])
def test_boolean_fact_is_not_inferred_from_truthy_value(inputs, value):
    fact, target, sources = inputs; fact['value'] = value
    with pytest.raises(ValueError, match='boolean'):
        audit_scope_transfer(fact, target, None, sources)

def test_immutable_scenario_replay(inputs, tmp_path):
    fact, target, sources = inputs
    cases = [{'id': 'check', 'fact': fact, 'target_scope': target, 'membership': None, 'note_ru': 'Контроль', 'note_en': 'Check'}]
    app = AuditAnalysisScope(FileResearchArtifacts(tmp_path))
    first = app.execute(cases, sources); assert app.execute(cases, sources) == first
    assert len(list(tmp_path.glob('*.json'))) == 1

def test_duplicate_case_is_rejected(inputs, tmp_path):
    fact, target, sources = inputs
    case = {'id': 'check', 'fact': fact, 'target_scope': target, 'membership': None, 'note_ru': 'Контроль', 'note_en': 'Check'}
    with pytest.raises(ValueError, match='Unique'):
        AuditAnalysisScope(FileResearchArtifacts(tmp_path)).execute([case, case], sources)
