"""Материал после обработки и возраст при измерении не подменяются общим описанием когорты."""
from copy import deepcopy
import pytest
from domain.article_maps import ArticleMapError, digest
from domain.prospective_question_screening import screen_continuous_mmse, validate_screening_record


def record():
    proof = [{'start': 0, 'end': 1, 'text': '🙂', 'offset_encoding': 'unicode_code_points'}]
    visit = {'axis': 'age_years', 'value': '85'}
    values = {'matrix': 'plasma', 'processing': 'direct_plasma_assay', 'exposure_visit': visit,
              'outcome_start_visit': visit, 'dementia_excluded': True, 'dementia_visit': visit,
              'minimum_age_at_exposure': 85, 'outcome': {'instrument': 'mmse', 'estimand': 'two_assessment_annual_change'},
              'followup_years': {'basis': 'planned', 'value': 3}}
    return {'id': 'example', 'family': 'independent', 'source_sha256': digest('🙂 source'),
            'features': {name: {'status': 'known', 'value': value, 'evidence': deepcopy(proof)} for name, value in values.items()},
            'note_ru': 'Синтетический контроль', 'note_en': 'Synthetic control'}


def test_aligned_direct_plasma_can_pass_without_claiming_context_equivalence_or_two_years_for_everyone():
    r = screen_continuous_mmse(record())
    assert r['eligible_for_subquestion'] and not r['comparison_context_equivalence_confirmed']
    assert not r['every_participant_followed_two_years'] and not r['training_support_added']


@pytest.mark.parametrize('matrix,processing', [('serum', 'direct_plasma_assay'), ('whole_blood_supernatant', 'ex_vivo_incubation'),
                                            ('plasma', 'ex_vivo_incubation')])
def test_unstimulated_whole_blood_production_is_not_automatically_plasma(matrix, processing):
    r = record(); r['features']['matrix']['value'] = matrix; r['features']['processing']['value'] = processing
    assert not screen_continuous_mmse(r)['eligible_for_subquestion']


def test_later_blood_draw_cannot_inherit_the_old_dementia_screen_or_cognitive_baseline():
    r = record(); r['features']['exposure_visit']['value'] = {'axis': 'age_years', 'value': '86'}
    result = screen_continuous_mmse(r)
    assert {b['reason'] for b in result['blockers']} == {'common_baseline_not_established', 'dementia_exclusion_at_exposure_not_established'}
    assert all(b['kind'] == 'unknown' for b in result['blockers'])


@pytest.mark.parametrize('field', ['matrix', 'processing', 'exposure_visit', 'outcome_start_visit', 'dementia_excluded',
                                  'dementia_visit', 'minimum_age_at_exposure', 'outcome', 'followup_years'])
def test_missing_required_anchor_blocks_admission(field):
    r = record(); r['features'][field].update(status='not_reported', value=None)
    assert not screen_continuous_mmse(r)['eligible_for_subquestion']


@pytest.mark.parametrize('instrument,estimand', [('3mse', 'two_assessment_annual_change'), ('mmse', 'binary_decline'),
                                              ('composite', 'last_available_annual_change')])
def test_global_scale_label_cannot_replace_exact_continuous_mmse(instrument, estimand):
    r = record(); r['features']['outcome']['value'] = {'instrument': instrument, 'estimand': estimand}
    assert not screen_continuous_mmse(r)['eligible_for_subquestion']


def test_mean_followup_does_not_satisfy_protocol_median_requirement():
    r = record(); r['features']['followup_years']['value']['basis'] = 'mean'
    with pytest.raises(ArticleMapError): screen_continuous_mmse(r)


def test_mean_age_or_late_age_is_not_the_minimum_age_at_exposure():
    r = record(); r['features']['minimum_age_at_exposure']['value'] = 55
    result = screen_continuous_mmse(r)
    assert result['blockers'][0]['reason'] == 'age_at_least_60_not_established'


def test_unicode_source_and_proof_are_bound_without_rewriting_source():
    r = record(); s = {'text': '🙂 source', 'sha256': digest('🙂 source')}
    assert validate_screening_record(r, s) == r
    r['features']['matrix']['evidence'][0]['end'] = 2
    with pytest.raises(ArticleMapError): validate_screening_record(r, s)


def test_bibliography_cannot_establish_own_sample_or_exposure_methods():
    r = record(); text = '🙂 source\nReferences\nplasma'
    s = {'text': text, 'sha256': digest(text)}; r['source_sha256'] = s['sha256']
    r['features']['matrix']['evidence'] = [{'start': text.index('plasma'), 'end': len(text), 'text': 'plasma', 'offset_encoding': 'unicode_code_points'}]
    with pytest.raises(ArticleMapError): validate_screening_record(r, s)


@pytest.mark.parametrize('field', ['minimum_age_at_exposure', 'followup_years'])
def test_nan_boolean_and_infinity_are_not_scientific_quantities(field):
    for value in ['nan', 'inf', True]:
        r = record()
        if field == 'followup_years': r['features'][field]['value']['value'] = value
        else: r['features'][field]['value'] = value
        with pytest.raises(ArticleMapError): screen_continuous_mmse(r)


def test_application_rejects_abstract_only_future_and_implicit_sources_and_preserves_repeated_audit(tmp_path, monkeypatch):
    import httpx
    from application.prospective_question_screening import ScreenProspectiveQuestionSources
    from infrastructure.research_artifacts import FileResearchArtifacts
    monkeypatch.setattr(httpx.Client, 'send', lambda *a, **k: pytest.fail('Model calls forbidden'))
    source = {'text': '🙂 source', 'sha256': digest('🙂 source'), 'publication_year': 2016, 'kind': 'full_primary_article'}
    sources = {source['sha256']: source}; selection = {'cutoff': '2022-12-31', 'purpose': 'historical_training_feasibility_only'}
    scenario = ScreenProspectiveQuestionSources(FileResearchArtifacts(tmp_path))
    a = scenario.execute(sources, [record()], selection)
    assert a == scenario.execute(sources, [record()], selection) and a['eligible_records'] == 1
    assert a['new_training_sources'] == 0 and not a['forecast_issued']
    for field, value in [('publication_year', 2024), ('publication_year', True), ('kind', 'abstract')]:
        bad = deepcopy(source); bad[field] = value
        with pytest.raises(ArticleMapError): scenario.execute({source['sha256']: bad}, [record()], selection)
    with pytest.raises(ArticleMapError): scenario.execute({**sources, 'implicit': source}, [record()], selection)
