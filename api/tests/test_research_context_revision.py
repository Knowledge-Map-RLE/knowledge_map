"""Контроль происхождения ручных уточнений и ограничения sensitivity-ветки."""
from copy import deepcopy

import pytest

from domain.article_maps import digest, fingerprint, ArticleMapError
from domain.research_semantics import context_value as cv
from domain.research_context_revision import apply_context_revision, VERSION
from tests.test_qualitative_question_prediction import claim, policy_raw, question
from domain.qualitative_question_prediction import finding_label, QualitativePolicy, qualitative_projection
from dataclasses import replace


def context_case():
    text = 'Older adults were described as nondemented. 🧠 Table | 3.8 pg/ml'
    graph = {'synthetic': True}
    raw = {'claim_id': 'K1S1', 'context': {'population': cv(None, 'not_reported')}, 'measurements': []}
    annotation = {'run_id': 'run', 'source_sha256': digest(text), 'graph_sha256': fingerprint(graph), 'claims': [raw]}
    bundle = {'map': {'article_id': 'a', 'run_id': 'run', 'source': {'text': text, 'sha256': digest(text)}, 'graph': graph},
              'annotation': annotation, 'registry': {'available_on': '2015-01-01'}}
    evidence = {'source_id': 'a', 'sha256': digest(text), 'start': 0, 'end': len(text), 'text': text, 'offset_encoding': 'unicode_code_points'}
    patch = {'claim_id': 'K1S1', 'original_claim_sha256': fingerprint(raw), 'quality': 'author_reported_nondemented',
             'context': {'population': cv('older adults without dementia')}, 'measurements_append': [],
             'evidence': [evidence], 'table_ids': [], 'rationale_ru': 'Авторское описание; клинический протокол не подтверждён.'}
    audit = {'version': VERSION, 'scope': 'sensitivity', 'author': 'Codex', 'expert_validated': False, 'sources': [], 'tables': [], 'patches': [patch]}
    return bundle, audit


def test_exact_provenance_does_not_mutate_source_or_map():
    bundle, audit = context_case()
    before = deepcopy(bundle)
    revised = apply_context_revision(bundle, audit)
    assert bundle == before
    assert revised['claims'][0]['context']['population']['status'] == 'known'
    assert revised['context_revision']['audit_sha256'] == fingerprint(audit)
    assert revised['context_revision']['scope'] == 'sensitivity'


@pytest.mark.parametrize('damage', ['source_hash', 'offset', 'quote', 'original_claim', 'clinical_promotion', 'unknown_source', 'duplicate', 'role_change'])
def test_forged_or_unsupported_context_revision_is_rejected(damage):
    bundle, audit = context_case()
    patch = audit['patches'][0]
    if damage == 'source_hash': patch['evidence'][0]['sha256'] = '0' * 64
    elif damage == 'offset': patch['evidence'][0]['end'] -= 1
    elif damage == 'quote': patch['evidence'][0]['text'] += ' invented'
    elif damage == 'original_claim': patch['original_claim_sha256'] = '0' * 64
    elif damage == 'clinical_promotion': audit['scope'] = 'primary'
    elif damage == 'unknown_source': patch['evidence'][0]['source_id'] = 'new-target'
    elif damage == 'duplicate': audit['patches'].append(deepcopy(patch))
    elif damage == 'role_change': patch['context']['outcome'] = cv('dementia')
    with pytest.raises(ArticleMapError): apply_context_revision(bundle, audit)


def add_cohort_source(bundle, audit, date='2001-01-01'):
    text = 'The explicitly cited recruitment cohort was aged 70 to 79.'
    audit['scope'] = 'primary'
    audit['sources'] = [{'id': 'methods', 'text': text, 'sha256': digest(text), 'kind': 'primary_methods_abstract',
                         'available_on': date, 'url': 'https://pubmed.ncbi.nlm.nih.gov/11584038/', 'training': False}]
    patch = audit['patches'][0]
    patch['quality'] = 'operational_screen_with_explicit_cohort_link'
    patch['evidence'].append({'source_id': 'methods', 'sha256': digest(text), 'start': 0, 'end': len(text), 'text': text, 'offset_encoding': 'unicode_code_points'})


def test_cohort_context_needs_historical_link_and_cannot_add_training_source():
    bundle, audit = context_case()
    add_cohort_source(bundle, audit)
    assert apply_context_revision(bundle, audit)['context_revision']['scope'] == 'primary'
    audit['sources'][0]['training'] = True
    with pytest.raises(ArticleMapError, match='training article'): apply_context_revision(bundle, audit)
    bundle, audit = context_case()
    add_cohort_source(bundle, audit, '2024-01-01')
    with pytest.raises(ArticleMapError, match='later'): apply_context_revision(bundle, audit)
    bundle, audit = context_case()
    audit['scope'] = 'primary'; audit['patches'][0]['quality'] = 'operational_screen_with_explicit_cohort_link'
    with pytest.raises(ArticleMapError, match='cohort link'): apply_context_revision(bundle, audit)


def symbolic_policy():
    raw = policy_raw()
    raw['statistical_fields'].append('association direction')
    raw['symbolic_directions'] = {'association direction': {'more decline with higher exposure': 'positive_association',
                                                           'less decline with higher exposure': 'inverse_association'}}
    return QualitativePolicy.parse(raw, question())


@pytest.mark.parametrize('value,label', [('more decline with higher exposure', 'positive_association'),
                                         ('less decline with higher exposure', 'inverse_association'),
                                         ('unclear', 'insufficient_data')])
def test_explicit_symbolic_direction_without_fabricated_coefficient(value, label):
    c = replace(claim(modality='statistically detected'), measurements=({'name': 'association direction', 'value': value, 'unit': 'categorical'},))
    assert finding_label(c, symbolic_policy())[0] == label
    if label != 'insufficient_data':
        projected, diagnostic = qualitative_projection(c, symbolic_policy())
        assert projected.measurements == ()
        assert diagnostic['source_measurements'] == c.measurements


def test_conflicting_symbolic_numeric_direction_and_index_weight_are_rejected():
    direction = {'name': 'association direction', 'value': 'more decline with higher exposure', 'unit': 'categorical'}
    c = replace(claim(modality='statistically detected', value='0.5'), measurements=claim(value='0.5').measurements + (direction,))
    assert finding_label(c, symbolic_policy())[0] == 'insufficient_data'
    weight = replace(c, measurements=({'name': 'primary index weight', 'value': '0.31', 'unit': 'dimensionless'},))
    assert finding_label(weight, symbolic_policy())[0] == 'insufficient_data'
    assert qualitative_projection(weight, symbolic_policy())[0] is None
    unknown = replace(c, measurements=({'name': 'association direction', 'value': 'more decline with higher exposure', 'unit': 'pg/ml'},))
    assert finding_label(unknown, symbolic_policy())[0] == 'insufficient_data'


def test_sensitivity_cannot_authorize_future_target_or_enter_primary(tmp_path):
    from dataclasses import asdict
    from application.qualitative_question_prediction import SealQualitativeQuestionExperiment
    from infrastructure.development_prediction_store import FilePredictionStore
    from tests.test_question_prediction import Maps, map_fixture, registry, reference
    m = map_fixture('a')
    refs = [reference(m)]
    metadata = {'a': {**registry(m, '2010-01-01'), 'family': 'family-a'}}
    scenario = SealQualitativeQuestionExperiment(Maps(m), FilePredictionStore(tmp_path))
    result = scenario.execute(refs, metadata, {}, [], asdict(question()), policy_raw(), 'owner', 'sensitivity')
    assert not result['readiness']['checks']['primary_confirmatory_scope']
    assert not result['readiness']['target_reading_allowed']
    with pytest.raises(ArticleMapError, match='scope differs'):
        scenario.execute(refs, metadata, {'a': {'context_revision': {'scope': 'sensitivity'}}}, [], asdict(question()), policy_raw(), 'owner', 'primary')
