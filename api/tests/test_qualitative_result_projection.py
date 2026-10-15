"""Качественный перенос не переносит значимость, дозу или новые научные наблюдения."""
from copy import deepcopy
import pytest

from domain.article_maps import ArticleMapError, fingerprint
from domain.qualitative_result_projection import project_qualitative_results, summary_kind, INTERPRETATION
from domain.whole_map_forecast import has_numeric_attributes, template, bind
from tests.test_whole_map_numeric import statement


def attr(name, value, unit=None):
    return {'name': name, 'value': value, 'unit': unit}


def fixture(attributes=None):
    key = ('source', 'K1')
    s = statement(predicate='expression increased')
    s['attributes'] = attributes or []
    s['roles'] = [{'role': 'gene', 'value': 'tnf', 'reference_kind': 'concept'},
                  {'role': 'population', 'value': 'mice', 'reference_kind': 'concept'}]
    s['scope']['modality'] = None
    s['scope']['conditions'] = ['dose 5 mg', 'protocol kept']
    frame = {'kind': 'state', 'action_status': None, 'logic': 'single', 'statements': [s]}
    parent = {'key': key, 'frame': frame, 'run_id': 'run', 'eligible': True,
        'provenance': [{'unit_ids': ['U1']}]}
    text = '🙂 Tnf expression increased sixfold after the intervention.'
    evidence = {'unit_id': 'U1', 'start': 0, 'end': len(text), 'text': text}
    origins = {'knowledge': {key: {'statements': [{'statement_id': 'S1', 'origin': 'primary_result',
        'evidence_unit_ids': ['U1']}]}}, 'sources': {'source': {'document_kind': 'primary_study',
        'source_sha256': 'source-hash', 'graph_sha256': 'graph-hash', 'evidence': [evidence]}}}
    return {key: parent}, origins


def test_qualitative_projection_retains_all_numbers_in_proof_and_all_conditions_in_view():
    records, origins = fixture([attr('n per group', '4-5'), attr('approximate fold change', '6', 'fold'),
        attr('p', '.001', 'dimensionless'), attr('statistical status', 'significant increase'),
        attr('dose', '5', 'mg')])
    original = deepcopy((records, origins))
    output, diagnostic = project_qualitative_results(records, origins)
    assert (records, origins) == original
    before, after = records['source', 'K1']['frame'], output['source', 'K1']['frame']
    a, b = before['statements'][0], after['statements'][0]
    assert {k: v for k, v in a.items() if k != 'attributes'} == {k: v for k, v in b.items() if k != 'attributes'}
    assert b['attributes'] == [attr('dose', '5', 'mg'), INTERPRETATION]
    assert has_numeric_attributes(after)
    proof = diagnostic['proofs'][0]
    assert proof['parent_frame'] == before and proof['parent_frame_sha256'] == fingerprint(before)
    assert len(proof['statements'][0]['summaries']) == 4
    assert proof['statements'][0]['evidence'] == origins['sources']['source']['evidence']
    assert not proof['scope_changed'] and not proof['participants_changed']
    assert not proof['significance_predicted'] and not proof['direction_inferred_from_numbers']
    assert not proof['new_measurement'] and not diagnostic['new_measurements']


@pytest.mark.parametrize('attribute', [attr('dose', '5', 'mg'), attr('duration', '2', 'years'),
    attr('mean', '6', 'score'), attr('sample count unknown', '7'), attr('n per group', '4; dose 5 mg'),
    attr('n per group', '0'), attr('n per group', '8-3'), attr('n per group', '4', 'days'),
    attr('p', '2'), attr('p', '.01; subgroup only'), attr('p', 0.01),
    attr('approximate fold change', '0.5', 'fold'), attr('estimate', '-2'),
    attr('p', '.01', 'mg'), attr('statistical status', 'trend only')])
def test_unknown_or_contextual_number_is_never_removed(attribute):
    assert summary_kind(attribute, 'expression increased') is None
    records, origins = fixture([attribute])
    output, _ = project_qualitative_results(records, origins)
    assert attribute in output['source', 'K1']['frame']['statements'][0]['attributes']


@pytest.mark.parametrize('case', ['unknown', 'review', 'cited', 'negated', 'modal', 'action',
    'duplicate', 'typed', 'missing_evidence', 'different_evidence', 'no_directed_predicate'])
def test_unlicensed_direction_or_evidence_fails_closed(case):
    records, origins = fixture([attr('p', '.01')]); parent = records['source', 'K1']; s = parent['frame']['statements'][0]
    if case == 'unknown': parent['eligible'] = False
    elif case == 'review': origins['sources']['source']['document_kind'] = 'review'
    elif case == 'cited': origins['knowledge']['source', 'K1']['statements'][0]['origin'] = 'cited_result'
    elif case == 'negated': s['negated'] = True
    elif case == 'modal': s['scope']['modality'] = 'may'
    elif case == 'action': parent['frame']['kind'] = 'action'; parent['frame']['action_status'] = 'planned'
    elif case == 'duplicate': s['attributes'].append(attr('p', '.02'))
    elif case == 'typed': s['attribute_types'] = {'p': 'unreviewed'}
    elif case == 'missing_evidence': origins['sources']['source']['evidence'] = []
    elif case == 'different_evidence': parent['provenance'][0]['unit_ids'] = ['U2']
    else: s['predicate'] = 'difference not statistically detected'
    output, diagnostic = project_qualitative_results(records, origins)
    assert output == records and not diagnostic['proofs']


def test_qualitative_match_ignores_effect_size_but_never_dose_time_or_roles():
    records, origins = fixture([attr('approximate fold change', '6', 'fold'), attr('p', '.01')])
    output, _ = project_qualitative_results(records, origins); frame = output['source', 'K1']['frame']
    pattern = template([{'key': ('source', 'K1'), 'frame': frame}], {'key': ('source', 'K1'), 'frame': frame})[1]['body'][0]
    other = deepcopy(records); other['source', 'K1']['frame']['statements'][0]['attributes'][0]['value'] = '30'
    equivalent, _ = project_qualitative_results(other, origins)
    assert bind(pattern, equivalent['source', 'K1']['frame'], {}) is not None
    for change in ['dose', 'time', 'negation', 'modality', 'quantifier']:
        changed = deepcopy(frame); s = changed['statements'][0]
        if change == 'dose': s['scope']['conditions'] = ['dose 50 mg', 'protocol kept']
        elif change == 'time': s['scope']['time'] = 'different phase'
        elif change == 'negation': s['negated'] = True
        elif change == 'modality': s['scope']['modality'] = 'hypothesis'
        else: s['scope']['quantifier'] = 'some'
        assert bind(pattern, changed, {}) is None


def test_no_new_knowledge_from_mean_or_nonsignificance():
    records, origins = fixture([attr('mean', '6'), attr('p', '.1')])
    records['source', 'K1']['frame']['statements'][0]['predicate'] = 'reported mean'
    output, diagnostic = project_qualitative_results(records, origins)
    assert output == records and not diagnostic['proofs']


def test_complete_origin_registry_required():
    records, origins = fixture()
    for invalid in [None, {**origins, 'knowledge': {}}]:
        with pytest.raises(ArticleMapError): project_qualitative_results(records, invalid)
    origins['knowledge']['source', 'K1']['statements'] = []
    with pytest.raises(ArticleMapError): project_qualitative_results(records, origins)
