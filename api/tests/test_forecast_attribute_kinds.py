"""Служебный номер не является измерением, но величины и условия остаются защищены."""
from copy import deepcopy
import pytest
from domain.article_maps import ArticleMapError, fingerprint
from domain.forecast_attribute_kinds import classify_attribute, project_source_locators
from domain.whole_map_forecast import has_numeric_attributes
from tests.test_whole_map_numeric import statement


def attr(name, value, unit=None):
    return {'name': name, 'value': value, 'unit': unit}


@pytest.mark.parametrize('attribute,kind', [
    (attr('table', 'Table 2'), 'source_locator'),
    (attr('source figure', 'Figure S3'), 'source_locator'),
    (attr('software', 'Stata 12'), 'method_software_version'),
    (attr('software', 'GraphPad Prism version 9.1'), 'method_software_version'),
    (attr('caption panel status', 'prose only; no Figure 6 panel'), 'numeric_or_untyped'),
    (attr('table', 'Table 2; dose 5 mg'), 'numeric_or_untyped'),
    (attr('software', 'Stata 12; p < .05'), 'numeric_or_untyped'),
    (attr('software', 'Stata 12', 'patients'), 'numeric_or_untyped'),
    (attr('dose', '5', 'mg'), 'numeric_or_untyped'),
    (attr('marker', 'IL-6'), 'numeric_or_untyped'),
    (attr('unclear', {'value': 12}), 'untyped'),
])
def test_classification_is_exact_and_unknown_digits_are_not_permitted(attribute, kind):
    assert classify_attribute(attribute) == kind


def fixture(attributes):
    s = statement(); s['attributes'] = attributes
    s['negated'] = True; s['scope']['modality'] = 'may'
    frame = {'kind': 'state', 'action_status': None, 'logic': 'contrast', 'statements': [s, deepcopy(s)]}
    key = ('source', 'K1')
    parent = {'key': key, 'frame': frame, 'run_id': 'run', 'eligible': True,
              'provenance': [{'unit_ids': ['U1']}, {'unit_ids': ['U1']}]}
    text = '🙂 Table 2 reports the measured outcome.'
    evidence = {'unit_id': 'U1', 'text': text, 'start': 0, 'end': len(text)}
    origins = {'knowledge': {key: {}}, 'sources': {'source': {'source_sha256': 'text-hash', 'graph_sha256': 'graph-hash',
                                                          'evidence': [evidence]}}}
    return {key: parent}, origins


def test_only_source_locator_relocated_full_numbers_and_scope_preserved():
    records, origins = fixture([attr('table', 'Table 2'), attr('dose', '5', 'mg'), attr('p', '.04')])
    before = deepcopy((records, origins))
    result, diagnostic = project_source_locators(records, origins)
    assert (records, origins) == before
    projected = result['source', 'K1']['frame']; original = records['source', 'K1']['frame']
    assert projected['logic'] == original['logic'] == 'contrast'
    for s, old in zip(projected['statements'], original['statements']):
        assert s['attributes'] == old['attributes'][1:]
        assert {k: v for k, v in s.items() if k != 'attributes'} == {k: v for k, v in old.items() if k != 'attributes'}
    proof = diagnostic['proofs'][0]
    assert proof['parent_frame'] == original and fingerprint(original) == proof['parent_frame_sha256']
    assert proof['locators'][0]['evidence'] == origins['sources']['source']['evidence']
    assert not proof['scientific_attributes_removed'] and not proof['scope_changed'] and not proof['new_measurement']
    assert has_numeric_attributes(projected)


@pytest.mark.parametrize('case', ['not_in_source', 'unknown_context', 'duplicate', 'typed'])
def test_nonverified_or_ambiguous_locator_is_not_removed(case):
    records, origins = fixture([attr('table', 'Table 2')]); parent = records['source', 'K1']
    if case == 'not_in_source': origins['sources']['source']['evidence'][0]['text'] = 'Another table.'
    elif case == 'unknown_context': parent['eligible'] = False
    elif case == 'duplicate':
        for s in parent['frame']['statements']: s['attributes'].append(attr('table', 'Table 2'))
    else:
        for s in parent['frame']['statements']: s['attribute_types'] = {'table': 'unreviewed'}
    result, diagnostic = project_source_locators(records, origins)
    assert not diagnostic['proofs'] and result == records
    assert has_numeric_attributes(result['source', 'K1']['frame'])


def test_different_units_doses_and_software_versions_are_not_equated():
    from domain.whole_map_forecast import template, bind
    records, origins = fixture([attr('table', 'Table 2'), attr('software', 'Stata 12')])
    projected, _ = project_source_locators(records, origins)
    frame = projected['source', 'K1']['frame']
    assert not has_numeric_attributes(frame)
    pattern = template([{'key': ('source', 'K1'), 'frame': frame}], {'key': ('source', 'K1'), 'frame': frame})[1]['body'][0]
    assert bind(pattern, frame, {}) is not None
    changed = deepcopy(frame)
    changed['statements'][0]['attributes'][0]['value'] = 'Stata 13'
    assert bind(pattern, changed, {}) is None
    changed = deepcopy(frame); changed['statements'][0]['scope']['time'] = 'different duration'
    assert bind(pattern, changed, {}) is None
    for a in [attr('dose', '5', 'mg'), attr('duration', '2', 'years'), attr('p', '.04'), attr('estimate', 2),
              attr('untyped', {'x': 5})]:
        changed = deepcopy(frame); changed['statements'][0]['attributes'].append(a)
        assert has_numeric_attributes(changed)


def test_exact_source_registry_is_required():
    records, origins = fixture([attr('table', 'Table 2')])
    for origin in [None, {**origins, 'knowledge': {}}]:
        with pytest.raises(ArticleMapError): project_source_locators(records, origin)
