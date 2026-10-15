"""Чувствительность не стирает отрицания и не превращается в разрешение прогнозировать."""
from copy import deepcopy

import pytest

from application.rule_support_diagnostic import SealRuleSupportDiagnostic
from domain.article_maps import ArticleMapError, fingerprint
from domain.rule_support_diagnostic import diagnose_support, diagnostic_shape
from domain.whole_map_forecast import forecast
from infrastructure.development_prediction_store import FilePredictionStore
from tests.test_whole_map_forecast import corpus, families


def fixture(*, change=None, primary=True):
    maps = corpus()
    if change:
        change(maps[0]['graph']['knowledge'][-1]['semantic_frame']['statements'][0],
               maps[1]['graph']['knowledge'][-1]['semantic_frame']['statements'][0])
    f = forecast(maps, families(maps))
    f['run_id'] = 'a' * 64; f['binding'] = {'synthetic_test': True}
    def origins(rules):
        return {'status': 'source_origins_declared', 'rules': [
            {'rule_id': r['id'], 'declared_primary_dataset_families': r['families'] if primary else [],
             'secondary_sources': [] if primary else r['families']} for r in rules]}
    f['evidence_origin_support'] = {'supported_rules': origins(f['rules']),
        'unsupported_rules': origins(f['learning']['unsupported_rules'])}
    return f


def alter(field, first, second):
    def change(left, right):
        left[field] = first; right[field] = second
    return change


def test_exact_agrees_and_joint_gate_is_not_blamed_when_rules_exist():
    f = fixture(); before = deepcopy(f); result = diagnose_support(f)
    assert f == before
    assert result['supported_exact_rules'] == len(f['rules']) > 0
    assert not result['joint_gate_removal_cannot_help_with_no_rules']
    assert result['observed_same_rules_candidates_without_gate'] > 0
    assert result['observed_same_rules_candidates_with_gate'] == 0
    assert result['predictions'] == [] and not result['scientific_success']


def test_different_context_can_look_alike_but_is_not_licensed():
    f = fixture(change=alter('conditions', ['young sample'], ['old sample']))
    d = diagnose_support(f)
    assert d['supported_exact_rules'] == 0 and d['joint_gate_removal_cannot_help_with_no_rules']
    assert d['modes']['context_details_hidden']['multi_publication_shape_count'] == 1
    assert all(not r['inference_licensed'] and not r['context_equivalence_established']
               for r in d['modes']['context_details_hidden']['groups'])
    assert d['predictions'] == []


@pytest.mark.parametrize('field,first,second', [('modality', 'may', 'must'), ('quantifier', 'some', 'all')])
def test_modality_and_quantifier_survive_context_blinding(field, first, second):
    d = diagnose_support(fixture(change=alter(field, first, second)))
    assert all(m['multi_publication_shape_count'] == 0 for m in d['modes'].values())


def test_negated_and_positive_heads_never_collapse():
    def change(a, b): a['negated'] = True
    d = diagnose_support(fixture(change=change))
    assert all(m['multi_publication_shape_count'] == 0 for m in d['modes'].values())


def test_attribute_unit_is_retained_when_value_hidden():
    def change(a, b):
        a['qualifiers']['attributes'] = [{'name': 'measurement', 'value': 'alpha', 'unit': 'mg'}]
        b['qualifiers']['attributes'] = [{'name': 'measurement', 'value': 'beta', 'unit': 'ml'}]
    d = diagnose_support(fixture(change=change))
    assert d['modes']['attribute_values_hidden']['multi_publication_shape_count'] == 0
    assert d['modes']['attributes_and_context_hidden']['multi_publication_shape_count'] == 0


def test_same_unit_different_nonnumeric_values_show_only_diagnostic_similarity():
    def change(a, b):
        a['qualifiers']['attributes'] = [{'name': 'measurement', 'value': 'alpha', 'unit': 'mg'}]
        b['qualifiers']['attributes'] = [{'name': 'measurement', 'value': 'beta', 'unit': 'mg'}]
    d = diagnose_support(fixture(change=change))
    assert d['supported_exact_rules'] == 0
    assert d['modes']['attribute_values_hidden']['multi_publication_shape_count'] == 1
    assert d['predictions'] == []


def test_two_reviews_do_not_turn_into_two_primary_replications():
    d = diagnose_support(fixture(primary=False))
    assert d['modes']['exact']['multi_publication_shape_count'] > 0
    assert d['modes']['exact']['multi_primary_shape_count'] == 0


def test_unknown_predicates_are_not_lumped_into_generic_family():
    def change(a, b): a['predicate'] = 'unknown alpha'; b['predicate'] = 'unknown beta'
    d = diagnose_support(fixture(change=change))
    assert d['modes']['predicate_family_only']['multi_publication_shape_count'] == 0


def test_body_permutation_and_variable_names_do_not_create_false_differences():
    r = fixture()['rules'][0]; changed = deepcopy(r)
    changed['body'].reverse()
    changed['internal_edges'] = [[1 - a, 1 - b] for a, b in changed['internal_edges']]
    for frame in [*changed['body'], changed['head']]:
        for s in frame['statements']:
            for role in s['roles']:
                if 'variable' in role['value']: role['value']['variable'] += '-renamed'
    assert diagnostic_shape(r, 'attribute_values_hidden') == diagnostic_shape(changed, 'attribute_values_hidden')


def test_unmodelled_numeric_heads_stay_rejected_not_diagnostic_rules():
    def change(a, b):
        a['qualifiers']['attributes'] = [{'name': 'measurement', 'value': '12', 'unit': 'mg'}]
        b['qualifiers']['attributes'] = [{'name': 'measurement', 'value': '13', 'unit': 'mg'}]
    f = fixture(change=change); d = diagnose_support(f)
    assert d['template_count'] == 0 and d['learning_rejections']['unmodelled_numeric_conclusion'] == 2
    assert d['learning_rejected_groups'] == f['learning']['rejected_groups']


def test_corrupt_template_rejected():
    f = fixture(); f['rules'][0]['head']['logic'] = 'argument'
    with pytest.raises(ArticleMapError, match='Template binding'): diagnose_support(f)


def test_seal_replay_no_source_or_network_read_and_change_gets_new_run(tmp_path, monkeypatch):
    import socket
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('Network forbidden'))
    f = fixture(); source = FilePredictionStore(tmp_path / 'input'); source.seal(f['run_id'], f)
    store = FilePredictionStore(tmp_path / 'output'); app = SealRuleSupportDiagnostic(source, store)
    first = app.execute(f['run_id'], {'test': 'fixed'})
    assert first == app.execute(f['run_id'], {'test': 'fixed'})
    assert not first['target_read'] and first['model_calls'] == 0
    second = app.execute(f['run_id'], {'test': 'changed'})
    assert first['run_id'] != second['run_id'] and len(list(store.root.glob('*/seal.json'))) == 2
    assert first['binding']['forecast_sha256'] == fingerprint(f)
