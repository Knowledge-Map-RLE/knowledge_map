"""Роли разрешаются по источнику, а неизвестный контекст не становится общим."""
from copy import deepcopy
from hashlib import sha256

import pytest

from domain.article_maps import fingerprint
from domain.operation_role_bindings import VERSION, project_role_bindings


def inputs():
    text = '🐁 Mice were scored daily. Treatment mice received MOG and PBS control.'
    source = {'text': text, 'sha256': sha256(text.encode()).hexdigest(), 'offset_encoding': 'unicode_codepoints',
              'content_end': len(text), 'units': [{'id': 'U1', 'text': text, 'start': 0, 'end': len(text)}]}
    frames = [
        {'kind': 'action', 'action_status': 'performed', 'logic': 'single', 'statements': [{
            'predicate': 'measure clinical course', 'roles': [{'role': 'model',
                'value': 'mog35-55-induced eae', 'reference_kind': 'concept'}], 'negated': False,
            'scope': {'modality': None, 'quantifier': None, 'time': 'daily', 'conditions': ['specific protocol']},
            'attributes': [{'name': 'maximum score', 'value': '6', 'unit': 'score'}]}]},
        {'kind': 'action', 'action_status': 'performed', 'logic': 'single', 'statements': [{
            'predicate': 'administer treatment', 'roles': [
                {'role': 'population', 'value': 'treatment mice', 'reference_kind': 'concept'},
                {'role': 'challenge', 'value': 'mog35-55-induced eae', 'reference_kind': 'concept'}], 'negated': False,
            'scope': {'modality': None, 'quantifier': None, 'time': 'day 3 PI', 'conditions': ['specific protocol']},
            'attributes': [{'name': 'dose', 'value': '200', 'unit': 'ug'}]}]},
    ]
    native = [{'knowledge_id': 'K' + str(i + 1), 'semantic_frame': {'statements': [
        {'provenance': {'unit_ids': ['U1']}}]}} for i in range(2)]
    m = {'article_id': 'article', 'run_id': 'run', 'source': source, 'graph': {'knowledge': native}}
    views = {}
    for i, frame in enumerate(frames):
        key = ('article', 'part' + str(i + 1))
        proof = {'origin': {'origin': 'primary_method'}, 'complete_native_knowledge': native[i],
                 'view_frame_sha256': fingerprint(frame), 'id': 'proof' + str(i)}
        views[key] = {'key': key, 'native_key': ('article', native[i]['knowledge_id']), 'run_id': 'run',
                      'frame': frame, 'projection_proof': proof}
    quoted = 'Treatment mice received MOG and PBS control.'
    start = text.index(quoted)
    evidence = {'unit_id': 'U1', 'start': start, 'end': start + len(quoted), 'text': quoted,
                'sha256': sha256(quoted.encode()).hexdigest()}
    entry = {'part_key': ['article', 'part1'], 'variant': 'source_context', 'reason_ru': 'Явная группа и модель.',
             'run_id': 'run', 'source_sha256': source['sha256'], 'graph_sha256': fingerprint(m['graph']),
             'frame_sha256': fingerprint(frames[0]), 'knowledge_sha256': fingerprint(native[0]),
             'binding_group': {'premises': [['article', 'K1']], 'head': ['article', 'K2']},
             'rename_roles': [{'from': 'model', 'to': 'challenge', 'biological_induced_disease_model': True,
                               'evidence': evidence}],
             'add_roles': [{'role': 'population', 'source_asserts_role': True, 'source_asserts_subprotocol_group': True,
                            'evidence': evidence, 'copy_from': {'part_key': ['article', 'part2'],
                                'role': 'population', 'frame_sha256': fingerprint(frames[1])}}]}
    return (views, {v['native_key']: [k] for k, v in views.items()}, set(), [m],
            [(tuple([('article', 'K1')]), ('article', 'K2'))],
            {'version': VERSION, 'author': 'Codex', 'model_calls': 0, 'expert_validated': False, 'entries': [entry]})


def test_bound_roles_keep_source_frame_scope_numbers_and_originals():
    values = inputs(); before = deepcopy(values)
    views, parents, known, summary = project_role_bindings(*values)
    assert values == before
    assert len(views) == 3 and summary['added_views'] == 1 and len(summary['profiles']) == 2
    assert not summary['maps_changed'] and summary['new_empirical_observations'] == 0
    for key, v in values[0].items(): assert views[key] == v
    extra = next(v for key, v in views.items() if key not in values[0])
    original = values[0]['article', 'part1']['frame']['statements'][0]
    s = extra['frame']['statements'][0]
    for field in ('predicate', 'negated', 'scope', 'attributes'): assert s[field] == original[field]
    assert {r['role']: r['value'] for r in s['roles']} == {
        'challenge': 'mog35-55-induced experimental autoimmune encephalomyelitis', 'population': 'treatment mice'}
    p = extra['projection_proof']['role_binding_proof']
    assert len(p['complete_related_knowledge']) == 2
    assert not p['experiments_declared_equivalent'] and not p['participant_groups_merged']
    assert p['source_interpretation_requires_expert_review']
    assert len(parents['article', 'K1']) == 2 and len(known) == 1


def rebind(values):
    views, _, _, maps, _, audit = values
    v = views['article', 'part1']; entry = audit['entries'][0]
    entry['frame_sha256'] = v['projection_proof']['view_frame_sha256'] = fingerprint(v['frame'])
    entry['graph_sha256'] = fingerprint(maps[0]['graph'])
    entry['knowledge_sha256'] = fingerprint(maps[0]['graph']['knowledge'][0])


@pytest.mark.parametrize('case', ['run', 'source', 'graph', 'native', 'frame', 'unicode', 'quote', 'offset',
    'evidence_hash', 'unit', 'references', 'group', 'different_population', 'subgroup_not_asserted',
    'unknown_part', 'copy_run', 'copy_frame', 'copy_native', 'copy_origin', 'copy_role', 'repeated_variant',
    'empty', 'not_asserted', 'unregistered_role', 'model_calls', 'expert_claim', 'author', 'modal',
    'negative_method', 'planned', 'cited_method', 'unknown_model_type'])
def test_invalid_binding_rejects_entire_result(case):
    values = inputs(); views, _, _, maps, groups, audit = values
    e = audit['entries'][0]; a = e['add_roles'][0]; v = views['article', 'part1']; src = views['article', 'part2']
    if case == 'run': e['run_id'] = 'other'
    elif case == 'source': maps[0]['source']['text'] += 'changed'
    elif case == 'graph': e['graph_sha256'] = 'changed'
    elif case == 'native': v['projection_proof']['complete_native_knowledge'] = {}
    elif case == 'frame': e['frame_sha256'] = 'changed'
    elif case == 'unicode': maps[0]['source']['offset_encoding'] = 'utf16'
    elif case == 'quote': a['evidence']['text'] = 'guess'
    elif case == 'offset': a['evidence']['end'] += 1
    elif case == 'evidence_hash': a['evidence']['sha256'] = 'changed'
    elif case == 'unit': a['evidence']['unit_id'] = 'other'
    elif case == 'references': maps[0]['source']['content_end'] = 1
    elif case == 'group': groups.clear()
    elif case == 'different_population':
        v['frame']['statements'][0]['roles'].append({'role': 'population', 'value': 'other mice'})
        a['role'] = 'challenge'; a['copy_from']['role'] = 'challenge'; e['rename_roles'] = []; rebind(values)
    elif case == 'subgroup_not_asserted': a['source_asserts_subprotocol_group'] = False
    elif case == 'unknown_part': a['copy_from']['part_key'][1] = 'missing'
    elif case == 'copy_run': src['run_id'] = 'other'
    elif case == 'copy_frame': a['copy_from']['frame_sha256'] = 'changed'
    elif case == 'copy_native': src['projection_proof']['complete_native_knowledge'] = {}
    elif case == 'copy_origin': src['projection_proof']['origin']['origin'] = 'cited_method'
    elif case == 'copy_role': a['copy_from']['role'] = 'missing'
    elif case == 'repeated_variant': audit['entries'].append(deepcopy(e))
    elif case == 'empty': e['add_roles'] = []; e['rename_roles'] = []
    elif case == 'not_asserted': a['source_asserts_role'] = False
    elif case == 'unregistered_role': a['role'] = 'produced_effect'
    elif case == 'model_calls': audit['model_calls'] = 1
    elif case == 'expert_claim': audit['expert_validated'] = True
    elif case == 'author': audit['author'] = 'model'
    elif case == 'modal': v['frame']['statements'][0]['scope']['modality'] = 'may'; rebind(values)
    elif case == 'negative_method': v['frame']['statements'][0]['negated'] = True; rebind(values)
    elif case == 'planned': v['frame']['action_status'] = 'planned'; rebind(values)
    elif case == 'cited_method': v['projection_proof']['origin']['origin'] = 'cited_method'
    elif case == 'unknown_model_type': v['frame']['statements'][0]['roles'][0]['value'] = 'statistical model'; rebind(values)
    with pytest.raises(ValueError): project_role_bindings(*values)


def test_literal_comparator_and_negative_result_are_preserved():
    values = inputs(); v = values[0]['article', 'part1']; entry = values[-1]['entries'][0]
    v['frame']['kind'] = 'state'; v['frame']['action_status'] = None
    v['frame']['statements'][0]['negated'] = True
    v['projection_proof']['origin']['origin'] = 'primary_result'
    evidence = entry['add_roles'][0]['evidence']
    entry['rename_roles'] = []; entry['add_roles'] = [{'role': 'comparator', 'value': 'PBS control',
        'source_asserts_role': True, 'evidence': evidence}]; rebind(values)
    result = project_role_bindings(*values)
    added = next(v for k, v in result[0].items() if k not in values[0])
    assert added['frame']['statements'][0]['negated']
    assert any(r['role'] == 'comparator' for r in added['frame']['statements'][0]['roles'])


def test_empty_audit_profiles_all_parts_without_guessing_types():
    values = inputs(); values[-1]['entries'] = []
    v = values[0]['article', 'part1']; v['frame']['statements'][0]['roles'].append({'role': 'unknown', 'value': 'x'})
    result = project_role_bindings(*values)
    assert result[0] == values[0]
    assert result[-1]['native_role_types']['unresolved_model_kind'] == 1
    assert result[-1]['native_role_types']['unclassified_native_role'] == 1
    assert all(p['unknown_is_not_wildcard'] for p in result[-1]['profiles'])
