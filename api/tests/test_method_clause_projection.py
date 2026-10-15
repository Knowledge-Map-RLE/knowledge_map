"""Операции метода не меняют научные условия и не добавляют измеренных результатов."""
from copy import deepcopy
from hashlib import sha256

import pytest

from domain.article_maps import fingerprint
from domain.method_clause_projection import project_method_clauses, VERSION


def inputs():
    text = 'Mice were immunized. Mice were scored daily.'
    source = {'text': text, 'sha256': sha256(text.encode()).hexdigest(), 'offset_encoding': 'unicode_codepoints',
        'content_end': len(text), 'units': [{'id': 'U1', 'text': text, 'start': 0, 'end': len(text)}]}
    native = {'knowledge_id': 'K1', 'kind': 'action'}
    frame = {'kind': 'action', 'action_status': 'performed', 'logic': 'single', 'statements': [{
        'predicate': 'perform experimental procedure', 'roles': [{'role': 'population', 'value': 'female mice'}],
        'negated': False, 'scope': {'modality': None, 'quantifier': None, 'time': 'day 16', 'conditions': ['MOG model']},
        'attributes': [{'name': 'dose', 'value': '30', 'unit': 'mg/kg'}]}]}
    key = ('article', 'part')
    proof = {'parent_key': ['article', 'K1'], 'run_id': 'run', 'origin': {'origin': 'primary_method'},
        'selected_provenance': {'unit_ids': ['U1']}, 'complete_native_knowledge': native,
        'parent_knowledge_sha256': fingerprint(native), 'view_frame_sha256': fingerprint(frame), 'id': 'parent-proof'}
    view = {'key': key, 'native_key': ('article', 'K1'), 'run_id': 'run', 'frame': frame, 'projection_proof': proof}
    m = {'article_id': 'article', 'run_id': 'run', 'source': source, 'graph': {'knowledge': [native]}}
    entry = {'part_key': list(key), 'run_id': 'run', 'source_sha256': source['sha256'], 'graph_sha256': fingerprint(m['graph']),
        'knowledge_sha256': fingerprint(native), 'view_frame_sha256': fingerprint(frame), 'decision': 'source_asserted_clauses',
        'reason_ru': 'Две явно выполненные операции.', 'operations': []}
    for predicate, quote in [('induce disease', 'Mice were immunized.'), ('measure clinical course', 'Mice were scored daily.')]:
        start = text.index(quote)
        entry['operations'].append({'predicate': predicate, 'source_asserts_performed_operation': True, 'reason_ru': 'Явная операция.',
            'evidence': {'unit_id': 'U1', 'start': start, 'end': start+len(quote), 'text': quote, 'sha256': sha256(quote.encode()).hexdigest()}})
    return {key: view}, {view['native_key']: [key]}, set(), [m], {'version': VERSION, 'author': 'Codex',
        'model_calls': 0, 'expert_validated': False, 'entries': [entry]}


def test_clauses_preserve_full_parent_roles_scope_and_numbers():
    values = inputs(); before = deepcopy(values)
    views, parents, known, summary = project_method_clauses(*values)
    assert len(views) == 3 and len(parents['article', 'K1']) == 3
    assert summary['added_views'] == 2 and summary['new_empirical_observations'] == 0
    original = values[0]['article', 'part']
    assert views['article', 'part'] == original
    for k, v in views.items():
        if k == ('article', 'part'): continue
        expected = deepcopy(v['frame']); expected['statements'][0]['predicate'] = 'perform experimental procedure'
        assert expected == original['frame']
        proof = v['projection_proof']['method_clause_proof']
        assert proof['complete_parent_retained'] and not proof['operation_is_complete_parent_equivalent']
        assert not proof['participant_or_constraint_removed'] and not proof['new_empirical_result']
        assert proof['constraints_inherited_from_complete_parent_not_reassigned']
        assert 'not an identity' in v['projection_proof']['foundation']
    assert values == before and len(known) == 2


def test_retain_complex_regimes_explicitly():
    values = inputs(); entry = values[-1]['entries'][0]
    entry['decision'], entry['operations'] = 'retain_native', []
    result = project_method_clauses(*values)
    assert result[0] == values[0] and result[-1]['counts']['retain_native'] == 1


@pytest.mark.parametrize('case', ['missing', 'duplicate', 'source', 'offset', 'graph', 'run', 'native', 'quote',
    'unit', 'outside', 'unknown_operation', 'not_asserted', 'duplicate_operation', 'modal', 'negative', 'model_calls', 'cited', 'planned'])
def test_invalid_or_unlicensed_clauses_refused(case):
    values = inputs(); views, _, _, maps, audit = values
    entry = audit['entries'][0]; op = entry['operations'][0]; v = views['article', 'part']
    if case == 'missing': audit['entries'] = []
    elif case == 'duplicate': audit['entries'].append(deepcopy(entry))
    elif case == 'source': maps[0]['source']['text'] += 'changed'
    elif case == 'offset': maps[0]['source']['offset_encoding'] = 'utf16'
    elif case == 'graph': entry['graph_sha256'] = 'changed'
    elif case == 'run': entry['run_id'] = 'other'
    elif case == 'native': v['projection_proof']['complete_native_knowledge']['kind'] = 'state'
    elif case == 'quote': op['evidence']['text'] = 'No operation was performed.'
    elif case == 'unit': op['evidence']['unit_id'] = 'U2'
    elif case == 'outside': op['evidence']['end'] += 100
    elif case == 'unknown_operation': op['predicate'] = 'produce favorable outcome'
    elif case == 'not_asserted': op['source_asserts_performed_operation'] = False
    elif case == 'duplicate_operation': entry['operations'].append(deepcopy(op))
    elif case in {'modal', 'negative'}:
        if case == 'modal': v['frame']['statements'][0]['scope']['modality'] = 'possible'
        else: v['frame']['statements'][0]['negated'] = True
        entry['view_frame_sha256'] = v['projection_proof']['view_frame_sha256'] = fingerprint(v['frame'])
    elif case == 'model_calls': audit['model_calls'] = 1
    elif case == 'cited': v['projection_proof']['origin']['origin'] = 'cited_method'
    else: v['frame']['action_status'] = 'planned'
    with pytest.raises(ValueError): project_method_clauses(*values)


def test_specific_native_method_retained_without_alias_guessing():
    values = inputs(); v = values[0]['article', 'part']
    v['frame']['statements'][0]['predicate'] = 'fit longitudinal linear regression'
    values[-1]['entries'] = []
    result = project_method_clauses(*values)
    assert result[0] == values[0] and result[-1]['counts']['specific_native_predicate_retained'] == 1
