"""Контроль полного набора вариантов, неизвестных контекстов и изоляции удержанных данных."""
from copy import deepcopy
from dataclasses import replace
import pytest

from domain.article_maps import ArticleMapError, fingerprint
from domain.question_context_modifiers import (
    VARIANTS, ContextModifierEngine, validate_modifier_policy, selected_context, compare_selected, stratified_baseline)
from tests.test_dual_question_outcomes import profiles, transport
from tests.test_qualitative_question_prediction import historical, question, policy, claim


def modifier_policy():
    return {'version': 'question-context-modifiers-1', 'variants': [list(v) for v in VARIANTS],
            'matching': 'exact_normalized_feature_with_unknown_blocking', 'minimum_independent_families': 2,
            'confirmatory': False, 'select_winner': False, 'corpus_expansion': False}


def engine(cs, selected, ps=None):
    return ContextModifierEngine(ps or profiles(cs), transport(), modifier_policy(), selected)


@pytest.mark.parametrize('selected', VARIANTS)
def test_every_predefined_variant_learns_only_with_two_compatible_independent_heads(selected):
    cs, es = historical(); before = fingerprint([c.to_dict() for c in cs.values()])
    r = engine(cs, selected).fit(cs, es, {}, question(), policy())
    d = r['outcome_channels']['reported_direction_exploratory']
    assert len(d['modes']['semantic']) == 1 and d['modes']['semantic'][0]['support'] == 2
    assert d['modes']['semantic'][0]['application_modifiers'].keys() == set(selected)
    assert not d['modes']['dependency'] and d['eligible_modifier_claims'] == 4
    assert before == fingerprint([c.to_dict() for c in cs.values()])


@pytest.mark.parametrize('field', ['variants', 'matching', 'minimum_independent_families', 'confirmatory', 'select_winner', 'corpus_expansion'])
def test_frozen_grid_cannot_drop_variants_select_winner_or_relax_support(field):
    p = modifier_policy(); p[field] = True if field in ('confirmatory', 'select_winner', 'corpus_expansion') else [] if field == 'variants' else 1 if field == 'minimum_independent_families' else 'loose'
    with pytest.raises(ArticleMapError): validate_modifier_policy(p)


@pytest.mark.parametrize('field', ['mci', 'outcome', 'adjustments'])
def test_unknown_selected_trait_is_not_a_shared_stratum(field):
    cs, es = historical(); ps = profiles(cs)
    for p in ps.values(): p['normalized'][field] = {'status': 'not_reported', 'value': None}
    r = engine(cs, (field,), ps).fit(cs, es, {}, question(), policy())
    d = r['outcome_channels']['reported_direction_exploratory']
    assert not d['modes']['semantic'] and not d['modes']['family_frequency_baseline']
    assert d['eligible_modifier_claims'] == 0 and len(d['unknown_modifier_claims']) == 4
    assert engine(cs, (), ps).fit(cs, es, {}, question(), policy())['outcome_channels']['reported_direction_exploratory']['modes']['semantic']


def test_nested_unknown_and_not_applicable_also_block_selected_transport():
    cs, _ = historical(); profile = next(iter(profiles(cs).values()))['normalized']
    profile['outcome']['value']['threshold'] = {'status': 'not_reported', 'value': None}
    assert selected_context(profile, ('outcome',))['unknown'] == ['outcome']
    profile['mci'] = {'status': 'not_applicable', 'value': None}
    assert not selected_context(profile, ('mci',))['eligible']


@pytest.mark.parametrize('field,value', [('mci', {'stratum': 'present'}),
    ('outcome', {'instrument': '3mse', 'estimand': 'time_to_first_decline'}), ('adjustments', ['age'])])
def test_incompatible_mci_scale_estimand_and_covariates_do_not_supply_rule_support(field, value):
    cs, es = historical(); ps = profiles(cs)
    for e in es: ps[tuple(e['conclusion'])]['normalized'][field]['value'] = value
    d = engine(cs, (field,), ps).fit(cs, es, {}, question(), policy())['outcome_channels']['reported_direction_exploratory']
    assert not d['modes']['semantic']
    assert all('feature:' + field in r.get('differences', []) for r in d['diagnostics']['semantic']['rejected'])


def test_stratified_baseline_does_not_count_two_models_as_two_families():
    a, b = claim('a', 'same'), claim('b', 'same')
    views = {(c.evidence.article_id, c.claim_id): replace(c, modality='positive_association') for c in (a, b)}
    contexts = {k: {'values': {'mci': {'status': 'known', 'value': {'stratum': 'absent'}}}} for k in views}
    forecasts, details = stratified_baseline(views, contexts, 2)
    assert not forecasts and len(details[0]['family_votes']) == 1


def test_conflicting_family_abstains_within_stratum_but_strata_are_not_pooled():
    views = {}; contexts = {}
    for article, family, label, mci in [('a', 'one', 'positive_association', 'absent'),
                                      ('b', 'one', 'inverse_association', 'absent'),
                                      ('c', 'two', 'positive_association', 'absent'),
                                      ('d', 'three', 'positive_association', 'present')]:
        c = replace(claim(article, family), modality=label); key = (article, c.claim_id)
        views[key] = c; contexts[key] = {'values': {'mci': {'status': 'known', 'value': {'stratum': mci}}}}
    forecasts, strata = stratified_baseline(views, contexts, 2)
    assert not forecasts and any(s['ambiguous_families_excluded'] == ['one'] for s in strata)


def test_target_modifier_changes_do_not_change_fit_or_training_binding():
    cs, es = historical(); target = claim('target', 'heldout', '2024-01-01')
    ps = profiles({**cs, ('target', target.claim_id): target}); first = engine(cs, ('mci',), ps)
    ps['target', target.claim_id]['normalized']['mci']['value']['stratum'] = 'present'
    second = engine(cs, ('mci',), ps)
    assert first.binding_for(cs) == second.binding_for(cs)
    assert first.fit(cs, es, {}, question(), policy()) == second.fit(cs, es, {}, question(), policy())


@pytest.mark.parametrize('target_mci,scorable', [('absent', 1), ('present', 0), (None, 0)])
def test_evaluation_preserves_every_target_and_blocks_unknown_or_different_mci(target_mci, scorable):
    cs, es = historical(); target = claim('target', 'heldout', '2024-01-01', value='.2')
    ps = profiles({**cs, ('target', target.claim_id): target})
    ps['target', target.claim_id]['normalized']['mci'] = {'status': 'known', 'value': {'stratum': target_mci}} if target_mci else {'status': 'not_reported', 'value': None}
    e = engine(cs, ('mci',), ps); r = e.fit(cs, es, {}, question(), policy()); r['binding'] = {'training_families': []}
    result = e.evaluate(r, [target])['outcome_channels']['reported_direction_exploratory']
    assert len(result['targets']) == 1
    score = result['modes']['semantic']
    assert score['claim_comparisons'] == 1 and score['scorable_comparisons'] == scorable
    assert score['supported_target_comparisons'] == 0


def test_comparison_preserves_exact_estimand_threshold_and_covariate_normalization():
    from tests.test_structured_question_context import features
    from domain.structured_question_context import normalized_features
    a = features(); b = deepcopy(a); b['adjustments']['value'] = ['sex', 'education', 'age']
    left, right = normalized_features(a), normalized_features(b)
    assert compare_selected(left, right, ('adjustments',))['eligible']
    right['outcome']['value']['threshold'] = {'value': '5', 'unit': '3ms_point'}
    assert compare_selected(left, right, ('outcome',))['differences'] == ['outcome']


def test_modifier_grid_does_not_change_the_strict_statistical_channel():
    cs, es = historical()
    reference = engine(cs, ()).fit(cs, es, {}, question(), policy())
    for selected in VARIANTS[1:]:
        result = engine(cs, selected).fit(cs, es, {}, question(), policy())
        assert result['outcome_channels']['statistical_detection_strict'] == reference['outcome_channels']['statistical_detection_strict']
        assert result['modes'] == reference['modes']


def test_modifier_scenario_seals_before_evaluation_and_rejects_unauthorized_owner(tmp_path, monkeypatch):
    from dataclasses import asdict
    from application.qualitative_question_prediction import SealQualitativeQuestionExperiment
    from infrastructure.development_prediction_store import FilePredictionStore
    from domain.article_maps import ArticleMapAccessDenied, digest
    from tests.test_question_prediction import Maps, map_fixture, registry, reference
    from tests.test_qualitative_question_prediction import policy_raw
    import httpx
    monkeypatch.setattr(httpx.Client, 'send', lambda *a, **k: pytest.fail('Network/model calls forbidden'))
    a, b = map_fixture('a'), map_fixture('b')
    for m in (a, b):
        m['source']['text'] += m['article_id']; m['source']['sha256'] = digest(m['source']['text'])
    rs = {m['article_id']: {**registry(m, '2010-01-01' if m is a else '2015-01-01'),
                           'family': 'family-' + m['article_id']} for m in (a, b)}
    store = FilePredictionStore(tmp_path)
    class CheckedEngine(ContextModifierEngine):
        def evaluate(self, sealed, targets):
            assert store.read_seal(sealed['run_id']) == sealed
            return super().evaluate(sealed, targets)
    scenario = SealQualitativeQuestionExperiment(Maps(a, b), store, CheckedEngine({}, transport(), modifier_policy(), ('mci',)))
    args = ([reference(a), reference(b)], rs, {}, [], asdict(question()), policy_raw())
    result = scenario.execute(*args, 'owner')
    assert not result['readiness']['target_reading_allowed']
    assert scenario.execute(*args, 'owner') == result
    with pytest.raises(ArticleMapAccessDenied): scenario.execute(*args, 'other')
