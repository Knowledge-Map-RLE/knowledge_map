"""Источниковое связывание ролей операций; модели и условия не отождествляются."""
from collections import Counter
from copy import deepcopy
from hashlib import sha256

from domain.article_maps import fingerprint, require
from domain.protocol_parameter_transfer import protocol_frame_identity

VERSION = 'source-bound-operation-role-bindings-1'
ALIASES = {'mog35-55-induced eae': 'mog35-55-induced experimental autoimmune encephalomyelitis'}
ROLE_TYPES = {'intervention': 'intervention', 'comparator': 'comparator', 'population': 'population',
    'challenge': 'biological_challenge', 'outcome': 'measured_attribute', 'specimen': 'specimen',
    'assay': 'assay', 'instrument': 'instrument', 'tissue': 'tissue', 'analyte': 'analyte',
    'analytes': 'analyte', 'markers': 'analyte', 'cohort': 'cohort_context', 'model': 'unresolved_model_kind'}
ADD_ROLES = {'challenge', 'comparator', 'population', 'outcome'}


def profiles(views):
    rows = []
    for key, v in sorted(views.items()):
        rows.append({'part_key': list(key), 'native_key': list(v['native_key']),
            'kind': v['frame']['kind'], 'action_status': v['frame']['action_status'],
            'origin': v['projection_proof']['origin']['origin'],
            'roles': [{'native_role': r['role'], 'type': ROLE_TYPES.get(r['role'], 'unclassified_native_role'),
                       'participant': deepcopy(r['value'])} for s in v['frame']['statements'] for r in s['roles']],
            'unknown_is_not_wildcard': True})
    return rows


def project_role_bindings(views, by_parent, known, maps, groups, audit):
    require(audit.get('version') == VERSION and audit.get('author') == 'Codex'
            and audit.get('model_calls') == 0 and audit.get('expert_validated') is False,
            'Unsupported operation role binding provenance')
    sources = {m['article_id']: m for m in maps}
    require(len(sources) == len(maps), 'Repeated binding source')
    for m in maps:
        require(m['source']['offset_encoding'] == 'unicode_codepoints'
                and sha256(m['source']['text'].encode('utf8')).hexdigest() == m['source']['sha256'], 'Binding source differs')
    native = {(m['article_id'], k['knowledge_id']): k for m in maps for k in m['graph']['knowledge']}
    group_keys = {(frozenset(body), head) for body, head in groups}
    result, registry, existing = deepcopy(views), deepcopy(by_parent), set(known)
    proofs, seen = [], set()

    for entry in audit['entries']:
        key = tuple(entry['part_key']); require(key in views, 'Unknown binding part')
        v = views[key]; nkey = tuple(v['native_key']); m = sources[nkey[0]]; p = v['projection_proof']
        identity = (key, entry['variant'])
        require(identity not in seen and entry['variant'] and entry['reason_ru'], 'Repeated or unexplained binding variant')
        seen.add(identity)
        require(entry['run_id'] == v['run_id'] == m['run_id'] and entry['source_sha256'] == m['source']['sha256']
                and entry['graph_sha256'] == fingerprint(m['graph']) and entry['frame_sha256'] == fingerprint(v['frame'])
                and p['view_frame_sha256'] == fingerprint(v['frame'])
                and p['complete_native_knowledge'] == native[nkey]
                and entry['knowledge_sha256'] == fingerprint(native[nkey]), 'Operation binding identity differs')
        origin = p['origin']['origin']
        require((v['frame']['kind'] == 'action' and v['frame']['action_status'] == 'performed' and origin == 'primary_method')
                or (v['frame']['kind'] == 'state' and origin == 'primary_result'), 'Only performed methods or own results may be bound')
        require(len(v['frame']['statements']) == 1, 'Binding requires a licensed single part')
        allowed_nodes = {nkey}
        basis = entry.get('binding_group')
        if basis is not None:
            body = frozenset(tuple(x) for x in basis['premises']); head = tuple(basis['head'])
            require((body, head) in group_keys and nkey in (body | {head}), 'Unknown author binding group')
            allowed_nodes |= body | {head}
        require(all(k in native and k[0] == nkey[0] for k in allowed_nodes), 'Binding crosses source scope')
        allowed_units = {uid for k in allowed_nodes for s in native[k]['semantic_frame']['statements'] for uid in s['provenance']['unit_ids']}
        units = {u['id']: u for u in m['source']['units']}

        def evidence(e):
            require(e['unit_id'] in allowed_units and e['unit_id'] in units, 'Binding evidence is unrelated')
            unit = units[e['unit_id']]
            require(unit['start'] <= e['start'] < e['end'] <= unit['end'] <= m['source']['content_end']
                    and e['text'] == m['source']['text'][e['start']:e['end']]
                    and e['sha256'] == sha256(e['text'].encode('utf8')).hexdigest(), 'Binding evidence differs')

        projected = deepcopy(v); statement = projected['frame']['statements'][0]
        require(statement['scope']['modality'] is None, 'Modal statement needs a separate role license')
        require(v['frame']['kind'] != 'action' or not statement['negated'], 'Negated procedure cannot supply performed role context')
        for rename in entry['rename_roles']:
            require(rename['from'] == 'model' and rename['to'] == 'challenge'
                    and rename['biological_induced_disease_model'] is True, 'Unestablished role alias')
            candidates = [r for r in statement['roles'] if r['role'] == rename['from']]
            require(len(candidates) == 1 and not any(r['role'] == rename['to'] for r in statement['roles']), 'Ambiguous role rename')
            require(candidates[0]['value'] in set(ALIASES) | set(ALIASES.values()), 'Biological model alias lacks a registered type')
            evidence(rename['evidence']); candidates[0]['role'] = rename['to']
        for addition in entry['add_roles']:
            role = addition['role']; require(role in ADD_ROLES and addition['source_asserts_role'] is True, 'Unlicensed added role')
            require(not any(r['role'] == role for r in statement['roles']), 'Added role already exists')
            evidence(addition['evidence'])
            if 'copy_from' in addition:
                copy = addition['copy_from']; source_key = tuple(copy['part_key'])
                require(source_key in views, 'Unknown role source')
                source = views[source_key]
                require(tuple(source['native_key']) in allowed_nodes and source_key[0] == nkey[0]
                        and source['run_id'] == v['run_id'] and fingerprint(source['frame']) == copy['frame_sha256']
                        == source['projection_proof']['view_frame_sha256']
                        and source['projection_proof']['complete_native_knowledge'] == native[tuple(source['native_key'])]
                        and source['projection_proof']['origin']['origin'] in {'primary_method', 'primary_result'}, 'Copied role crosses context')
                candidates = [r for s in source['frame']['statements'] for r in s['roles'] if r['role'] == copy['role']]
                require(len(candidates) == 1, 'Ambiguous copied role')
                added = deepcopy(candidates[0]); added['role'] = role
                # Совпадающая популяция — обязательная защита при копировании другого участника.
                target_pop = [r['value'] for r in statement['roles'] if r['role'] == 'population']
                source_pop = [r['value'] for s in source['frame']['statements'] for r in s['roles'] if r['role'] == 'population']
                if target_pop and source_pop:
                    require(target_pop == source_pop, 'Copied role belongs to a different population')
                elif role == 'population':
                    require(addition.get('source_asserts_subprotocol_group') is True and basis is not None,
                            'Unspecified population is not an automatic wildcard')
            else:
                require(isinstance(addition['value'], str) and bool(addition['value'].strip()), 'Explicit source role value required')
                added = {'role': role, 'value': addition['value'], 'reference_kind': 'concept'}
            statement['roles'].append(added)
        require(entry['add_roles'] or entry['rename_roles'], 'Empty binding variant')
        aliases = []
        for role in statement['roles']:
            value = role['value']
            if isinstance(value, str) and value in ALIASES:
                aliases.append({'role': role['role'], 'original': value, 'canonical': ALIASES[value]})
                role['value'] = ALIASES[value]
        statement['roles'] = sorted(statement['roles'], key=lambda r: r['role'])
        require(len({r['role'] for r in statement['roles']}) == len(statement['roles']), 'Duplicate bound role')
        proof = {'version': VERSION, 'audit_sha256': fingerprint(audit), 'entry': deepcopy(entry),
            'source_part_key': list(key), 'source_frame_sha256': fingerprint(v['frame']), 'aliases': aliases,
            'alias_dictionary_sha256': fingerprint(ALIASES), 'complete_parent_retained': True,
            'complete_related_knowledge': [{'native_key': list(k), 'knowledge': deepcopy(native[k]),
                                           'sha256': fingerprint(native[k])} for k in sorted(allowed_nodes)],
            'scope_or_number_changed': False, 'experiments_declared_equivalent': False,
            'participant_groups_merged': False, 'new_empirical_result': False,
            'source_interpretation_requires_expert_review': True}
        proof['id'] = fingerprint(proof)
        pp = projected['projection_proof']; pp.pop('id', None)
        pp['role_binding_proof'] = proof; pp['operator'] = 'source_asserted_operation_role_binding'
        pp['foundation'] = ('Source-linked roles belong to this operation under its unchanged scope. '
            'Source interpretation does not equate different experiments, participant groups, scales or measured results.')
        pp['view_frame_sha256'] = fingerprint(projected['frame']); pp['id'] = fingerprint(pp)
        projected['key'] = (key[0], 'role-view:' + proof['id'])
        require(projected['key'] not in result, 'Repeated role view')
        result[projected['key']] = projected; registry[nkey].append(projected['key'])
        existing.add(protocol_frame_identity(projected['frame'])); proofs.append(proof)
    profile = profiles(views)
    return result, registry, existing, {'version': VERSION, 'audit_sha256': fingerprint(audit),
        'profiles': profile, 'native_role_types': dict(Counter(r['type'] for p in profile for r in p['roles'])),
        'proofs': proofs, 'added_views': len(proofs), 'maps_changed': False, 'new_empirical_observations': 0, 'model_calls': 0,
        'policy_ru': 'Исходные роли и полные родители сохранены. Новые связи ролей привязаны к источнику и группе '
                     'использования знаний; неизвестная группа не становится переменной без явного источникового допуска. '
                     'Совпадение класса измерения не отождествляет шкалы, группы, периоды и эффекты.'}
