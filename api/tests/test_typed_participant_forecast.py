"""Типизированное обобщение проверяется отдельно от научной успешности прогноза."""
from copy import deepcopy
import pytest
from domain.article_maps import ArticleMapError, fingerprint
from domain.typed_participant_forecast import template, learn, forecast, structural_key, guard_barriers
from domain.whole_map_forecast import template as legacy_template, bind, instantiate
from tests.test_protocol_parameter_transfer import record, reseal
from tests.test_semantic_part_forecast import prepare
from tests.test_whole_map_forecast import corpus, families
from domain.semantic_part_forecast import forecast_parts


def pair(article, intervention):
    body, head = record(article, 'M', '2', 'action'), record(article, 'R', '2')
    for r in (body, head):
        s = r['frame']['statements'][0]
        s['attributes'] = []
        s['roles'] = [role for role in s['roles'] if role['role'] != 'outcome']
        next(role for role in s['roles'] if role['role'] == 'intervention')['value'] = intervention
        reseal(r)
    return body, head


def test_named_digit_participant_binds_whole_concept_without_stripping_digit():
    body, head = pair('training', 'TNFR1 inhibitor')
    actual, _ = pair('receiving', 'TNFR2 inhibitor')
    before = deepcopy((body, head, actual))
    pattern = template([body], head)[1]
    binding = bind(pattern['body'][0], actual['frame'], {})
    assert binding is not None
    output = instantiate(pattern['head'], binding)
    assert next(r['value'] for r in output['statements'][0]['roles'] if r['role'] == 'intervention') == 'TNFR2 inhibitor'
    assert bind(legacy_template([body], head)[1]['body'][0], actual['frame'], {}) is None
    assert (body, head, actual) == before


@pytest.mark.parametrize('literal', ['20', '-2', '2.5', '1e3', '.25'])
def test_pure_numeric_role_literal_is_not_new_variable(literal):
    body, head = pair('training', literal)
    p = template([body], head)[1]['body'][0]
    role = next(r for r in p['statements'][0]['roles'] if r['role'] == 'intervention')
    assert role['value'] == {'constant': literal}


@pytest.mark.parametrize('field', ['negated', 'quantifier', 'modality', 'time', 'conditions', 'unit', 'action_status'])
def test_participant_abstraction_does_not_erase_scientific_guards(field):
    body, head = pair('training', 'TNFR1 inhibitor'); actual, _ = pair('receiving', 'TNFR2 inhibitor')
    for r in (body, head, actual): r['frame']['statements'][0]['attributes'] = [{'name': 'explicit dose', 'value': '20', 'unit': 'mg/kg'}]
    pattern = template([body], head)[1]['body'][0]; s = actual['frame']['statements'][0]
    if field == 'negated': s[field] = True
    elif field == 'unit': s['attributes'][0]['unit'] = 'mg'
    elif field == 'action_status': actual['frame'][field] = 'planned'
    else: s['scope'][field] = ['other group'] if field == 'conditions' else 'different explicit scope'
    assert bind(pattern, actual['frame'], {}) is None


def test_repeated_entity_across_premises_is_same_variable():
    b1, head = pair('training', 'TNFR1 inhibitor'); b2 = deepcopy(b1); b2['key'] = ('training', 'M2')
    b2['frame']['statements'][0]['predicate'] = 'measure effect'
    p = template([b1, b2], head)[1]
    values = [next(r['value'] for r in f['statements'][0]['roles'] if r['role'] == 'intervention') for f in (*p['body'], p['head'])]
    assert values[0] == values[1] == values[2]


def test_unknown_reference_kind_and_semantic_network_never_become_free_variables():
    for value, kind in [('TNFR1 inhibitor', None), ({'cycle': ['binds']}, 'knowledge')]:
        b, h = pair('training', 'TNFR1 inhibitor')
        for r in (b, h):
            role = next(r for r in r['frame']['statements'][0]['roles'] if r['role'] == 'intervention')
            role['reference_kind'], role['value'] = kind, value
        p = template([b], h)[1]
        assert next(r['value'] for r in p['body'][0]['statements'][0]['roles'] if r['role'] == 'intervention') == {'constant': value}


def test_single_family_and_measured_numeric_head_do_not_license_new_rule():
    records, groups = {}, []
    for article, name in [('a', 'TNFR1 inhibitor'), ('b', 'TNFR2 inhibitor')]:
        b, h = pair(article, name); records[b['key']], records[h['key']] = b, h
        groups.append(((b['key'],), h['key']))
    rules, _ = learn(records, groups, {'a': 'shared', 'b': 'shared'}); assert not rules
    rules, _ = learn(records, groups, {'a': 'first', 'b': 'second'}); assert len(rules) == 1
    for _, head in groups:
        records[head]['frame']['statements'][0]['attributes'] = [{'name': 'measured response', 'value': '3.2', 'unit': 'score'}]
        reseal(records[head])
    rules, diagnostic = learn(records, groups, {'a': 'first', 'b': 'second'})
    assert not rules and diagnostic['rejected']['unmodelled_numeric_conclusion'] == 2


def synthetic():
    maps, audit = prepare(corpus())
    source = forecast_parts(maps, families(maps), None, None, audit)
    source['binding'] = {'map_hashes': [fingerprint(m) for m in maps], 'families': families(maps)}
    source['run_id'] = fingerprint(source['binding'])
    return source, maps, audit


def test_whole_corpus_identical_parents_retained_and_no_ai_or_target_access(monkeypatch):
    import socket
    def forbidden(*a, **k): raise AssertionError('Network/model access forbidden')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    source, maps, audit = synthetic(); before = deepcopy((source, maps, audit))
    result = forecast(source, maps, audit)
    assert result['canonical_blocks'] == result['licensed_parts'] == 8
    assert len(result['parent_coverage']) == 8
    assert result['model_calls'] == 0 and not result['target_read'] and not result['future_outcomes_read']
    assert not result['scientific_success'] and not result['graph_advantage_demonstrated']
    assert (source, maps, audit) == before
    assert result['policies']['typed_concept_participants']['graph']['predictions']


@pytest.mark.parametrize('change', ['source', 'parent', 'origin', 'part'])
def test_modified_input_or_provenance_rejected(change):
    source, maps, audit = synthetic()
    if change == 'source': maps[0]['source']['text'] += '!'
    elif change == 'parent': source['part_views'][0]['projection_proof']['complete_native_knowledge']['display_text'] += '!'
    elif change == 'origin': source['part_views'][0]['projection_proof']['origin']['origin'] = 'cited_result'
    else: source['part_views'][0]['frame']['statements'][0]['predicate'] = 'invented'
    with pytest.raises(ArticleMapError): forecast(source, maps, audit)


def test_application_is_idempotent_and_changed_implementation_has_new_seal(tmp_path):
    from application.typed_participant_forecast import SealTypedParticipantForecast
    from infrastructure.development_prediction_store import FilePredictionStore
    source, maps, audit = synthetic()
    class Port:
        def load(self): return source, maps, audit
    app = SealTypedParticipantForecast(Port(), FilePredictionStore(tmp_path))
    a = app.execute({'test': 'first'}); assert a == app.execute({'test': 'first'})
    b = app.execute({'test': 'second'}); assert a['run_id'] != b['run_id']
    assert len(list(tmp_path.glob('*/seal.json'))) == 2


def test_different_guards_are_only_diagnostic_similarity_not_a_supported_rule():
    records, groups = {}, []
    for article, day in [('a', 'early'), ('b', 'late')]:
        b, h = pair(article, 'TNFR1 inhibitor')
        for r in (b, h): r['frame']['statements'][0]['scope']['time'] = day; reseal(r)
        records[b['key']], records[h['key']] = b, h; groups.append(((b['key'],), h['key']))
    rules, diagnostic = learn(records, groups, {'a': 'first', 'b': 'second'})
    assert rules == [] and diagnostic['unsupported_templates'] == 2
    origins = {'sources': {a: {'document_kind': 'primary_study', 'dataset_family': a} for a in ('a', 'b')}}
    barriers = guard_barriers(diagnostic['unsupported_rules'], records, origins)
    assert len(barriers) == 1 and len(barriers[0]['variants']) == 2
    assert not barriers[0]['valid_rule'] and not barriers[0]['prediction_created']
    assert {v['head']['statements'][0]['scope']['time'] for v in barriers[0]['variants']} == {'early', 'late'}


def test_diagnostic_structure_keeps_direction_negation_and_participant_equalities():
    b, h = pair('a', 'TNFR1 inhibitor'); shape = template([b], h)[1]; shape['internal_edges'] = []
    different = deepcopy(shape); different['head']['statements'][0]['negated'] = True
    assert structural_key(shape)[0] != structural_key(different)[0]
    different = deepcopy(shape); different['head']['statements'][0]['predicate'] = 'increased'
    assert structural_key(shape)[0] != structural_key(different)[0]
    different = deepcopy(shape); different['head']['statements'][0]['roles'][0]['value'] = {'variable': '$new'}
    assert structural_key(shape)[0] != structural_key(different)[0]
