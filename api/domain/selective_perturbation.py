"""Источниковая гипотеза селективности; генетическое вмешательство не равно препарату."""
from copy import deepcopy
from itertools import product
from hashlib import sha256
import re

from domain.article_maps import require, fingerprint
from domain.semantic_operator_graph import VERSION as GRAPH_VERSION

VERSION = 'source-bound-selective-perturbation-3'
AUDIT_VERSION = 'selective-perturbation-license-1'
LIMITS = {'search_steps': 200000, 'max_candidates': 20}


def validate_quote(graph, q, statement):
    require(q['unit'] in statement['evidence'], 'Quote outside statement source units')
    u = graph['source_units'][q['unit']]; start, end = q['start'], q['end']
    require(type(start) is int and type(end) is int and u['start'] <= start < end <= u['end'], 'Unicode quote outside source')
    require(u['text'][start-u['start']:end-u['start']] == q['text']
            and sha256(q['text'].encode()).hexdigest() == q['sha256'], 'Quote text or digest changed')


def validate_licenses(graph, audit):
    require(graph['version'] == GRAPH_VERSION and audit['version'] == AUDIT_VERSION,
            'Explicit compatible semantic graph and license required')
    require(audit['graph_sha256'] == fingerprint(graph) and audit['author'] == 'Codex'
            and audit['expert_validated'] is False, 'License graph or authorship differs')
    entries = audit['entries']; seen = set(); result = []
    for entry in entries:
        sid = entry['statement']; require(sid in graph['statements'] and sid not in seen, 'Unknown or repeated licensed statement')
        seen.add(sid); s = graph['statements'][sid]; parent = graph['parents'][s['parent']]
        require(entry['parent_sha256'] == parent['knowledge_sha256'] and entry['statement_sha256'] == fingerprint(s),
                'Source parent or statement changed')
        require(not s['negated'] and s['state_or_action'] == 'state' and s['action_status'] is None
                and s['original_statement']['modality'] is None, 'Qualified or intended statement requires another license')
        require(s['parent_logic'] in {'single', 'conjunction', 'contrast'} and entry['reason_ru'],
                'Independent projection of argument not licensed')
        native_roles = {(r['native_role'], r['target']) for r in s['roles']}
        fields = entry['bindings']; require(set(fields) == {'intervention', 'targets', 'population'}, 'Exact source fields required')
        require(fields['intervention'] and fields['targets'] and len(set(fields['targets'])) == len(fields['targets']),
                'Distinct target bindings required')
        require(('intervention', fields['intervention']) in native_roles, 'Native intervention role differs')
        if fields['population'] is not None:
            require(('population', fields['population']) in native_roles, 'Native population role differs')
        for node in [fields['intervention'], *fields['targets']] + ([] if fields['population'] is None else [fields['population']]):
            require(node in graph['nodes'] and graph['nodes'][node]['kind'] == 'concept'
                    and graph['nodes'][node]['article_id'] == s['article_id'], 'Source-local concept required')
        kind = entry['kind']; require(kind in {'observed_perturbation', 'broad_mechanism'}, 'Unknown selective license kind')
        require(entry['perturbation'] in {'genetic_loss', 'pharmacological_signaling_blockade'}, 'Explicit intervention type required')
        expected = {'observed_perturbation': {'reduced_after_intervention', 'exacerbated_after_intervention'},
                    'broad_mechanism': {'inhibitor_mechanism'}}[kind]
        require(s['original_statement']['predicate'] in expected, 'Native predicate does not license this facet')
        require((kind == 'observed_perturbation') == (entry['perturbation'] == 'genetic_loss'), 'Intervention class differs')
        require((kind == 'observed_perturbation') == bool(fields['population']), 'Observed population missing or invented')
        outcomes = entry['outcomes']
        if kind == 'observed_perturbation':
            require(outcomes and len({o['key'] for o in outcomes}) == len(outcomes), 'Distinct observed outcomes required')
            sign = 'decrease' if s['original_statement']['predicate'] == 'reduced_after_intervention' else 'increase'
            require(all(o['direction'] == sign and o['label_ru'] for o in outcomes), 'Effect direction differs')
        else:
            require(not outcomes and len(fields['targets']) >= 2, 'Broad mechanism cannot invent observed efficacy')
        # Все аналитические значения имеют собственную цитату. Это проверка происхождения,
        # а не независимая экспертная проверка интерпретации цитаты.
        expected_claims = {'intervention', 'targets', 'population', 'perturbation', *('outcome:' + o['key'] for o in outcomes)}
        quotes = entry['quotes']; require({q['claim'] for q in quotes} == expected_claims and len(quotes) == len(expected_claims),
                                          'Every field requires exactly one source quote')
        for q in quotes:
            validate_quote(graph, q, s)
        target_quote = next(q['text'] for q in quotes if q['claim'] == 'targets')
        native_attributes = s['original_statement'].get('qualifiers', {}).get('attributes', [])
        named_mechanism = ' '.join(a['value'] for a in native_attributes if isinstance(a.get('value'), str))
        for target in fields['targets']:
            label = graph['nodes'][target]['label']; pattern = r'(?<!\w)' + re.escape(label) + r'(?!\w)'
            require(re.search(pattern, target_quote if kind == 'observed_perturbation' else named_mechanism, re.IGNORECASE),
                    'Target not named in exact perturbation quote or native mechanism attributes')
        identities = entry['target_identity_proofs']
        require(len(identities) == len(fields['targets']) and {i['target'] for i in identities} == set(fields['targets']),
                'Every target requires named source identity')
        for identity in identities:
            support = graph['statements'].get(identity['statement'])
            require(support is not None and support['article_id'] == s['article_id'], 'Same-source identity statement required')
            validate_quote(graph, identity['quote'], support)
            label = graph['nodes'][identity['target']]['label']
            require(re.search(r'(?<!\w)' + re.escape(label) + r'(?!\w)', identity['quote']['text'], re.IGNORECASE),
                    'Target name missing from licensed identity quote')
            # Разрешение «оба» использует отдельное именованное определение; его
            # отрицание свойства не превращается в отрицание существования сущности.
            if support['id'] != s['id']:
                require(identity['target'] in {r['target'] for r in support['roles']}, 'Identity target lacks native support role')
        require(entry['context_limitations_ru'] and entry['independent_primary_replications_certified'] is False,
                'Unknown detailed context and review provenance must remain explicit')
        result.append({**deepcopy(entry), 'article_id': s['article_id'], 'parent': s['parent'],
                       'scope': deepcopy(s['scope']), 'source_statement': deepcopy(s), 'license_sha256': fingerprint(entry)})
    return result


def generate(graph, audit):
    facets = validate_licenses(graph, audit)
    observations = [e for e in facets if e['kind'] == 'observed_perturbation']
    mechanisms = [e for e in facets if e['kind'] == 'broad_mechanism']
    pool = {}; steps = 0; rejected = {}
    for good, bad, broad in product(observations, observations, mechanisms):
        steps += 1; require(steps <= LIMITS['search_steps'], 'Selective search budget exceeded; no partial publication')
        reason = None
        g, b, m = [v['bindings'] for v in (good, bad, broad)]
        if len({v['article_id'] for v in (good, bad, broad)}) != 1: reason = 'cross_source_identity_not_licensed'
        elif len(g['targets']) != 1 or not all(o['direction'] == 'decrease' for o in good['outcomes']): reason = 'not_selective_favorable_perturbation'
        elif not all(o['direction'] == 'increase' for o in bad['outcomes']): reason = 'not_unfavorable_perturbation'
        elif g['population'] != b['population']: reason = 'different_source_population'
        elif not (set(g['targets']) | set(b['targets'])) <= set(m['targets']) or not set(b['targets']) - set(g['targets']): reason = 'no_distinct_opposing_branch'
        if reason:
            rejected[reason] = rejected.get(reason, 0) + 1; continue
        # Общее понятие модели не удостоверяет равенство возраста, генотипа и режима.
        # Поэтому вывод остаётся условной возможностью, а не сравнением эффективности.
        for outcome in good['outcomes']:
            conclusion = {'action': 'selective_pharmacological_signaling_blockade', 'target': g['targets'][0],
                          'preserve_targets': sorted(set(m['targets']) - set(g['targets'])), 'population': g['population'],
                          'outcome': outcome['key'], 'expected_direction': outcome['direction'],
                          'modality': 'may; genetic-to-pharmacological transfer unestablished'}
            identity = fingerprint(conclusion)
            evidence = [good, bad, broad]
            candidate = {'id': identity, 'conclusion': conclusion, 'outcome_ru': outcome['label_ru'],
                'premise_statements': [v['statement'] for v in evidence], 'premise_parents': [v['parent'] for v in evidence],
                'licenses': [v['license_sha256'] for v in evidence], 'status': 'unverified_selective_intervention_hypothesis',
                'proof_kind': 'source-bound-opposing-perturbation-analogy', 'logical_entailment': False,
                'causality_established': False, 'comparative_efficacy_predicted': False, 'human_efficacy_predicted': False,
                'independent_primary_replications_certified': False, 'expert_validated': False,
                'parent_frames': [deepcopy(graph['parents'][v['parent']]['complete_parent']['semantic_frame']) for v in evidence],
                'source_quotes': [deepcopy(q) for v in evidence for q in v['quotes']],
                'target_identity_proofs': [deepcopy(i) for v in evidence for i in v['target_identity_proofs']],
                'identity_parent_frames': {graph['statements'][i['statement']]['parent']:
                    deepcopy(graph['parents'][graph['statements'][i['statement']]['parent']]['complete_parent']['semantic_frame'])
                    for v in evidence for i in v['target_identity_proofs']},
                'contexts': [deepcopy(v['scope']) for v in evidence],
                'limitations_ru': list(dict.fromkeys([x for v in evidence for x in v['context_limitations_ru']])) + [
                    'Удаление гена не удостоверяет эффект фармакологического ингибирования.',
                    'Сохранение второй ветви — условие конструкции; её фактическая активность должна измеряться.',
                    'Сравнительная эффективность против неселективного препарата не предсказывается.',
                    'Модель, возраст, доза, доставка, длительность и стадия болезни требуют отдельной проверки.'],
                'role_join': {'shared_population': g['population'], 'beneficial_target': g['targets'][0],
                              'opposing_targets': sorted(set(b['targets']) - set(g['targets'])),
                              'broad_targets': sorted(m['targets'])},
                'scientific_novelty_certified': False}
            if identity not in pool or fingerprint(candidate) < fingerprint(pool[identity]): pool[identity] = candidate
    ranked = sorted(pool.values(), key=lambda c: c['id'])[:LIMITS['max_candidates']]
    # Один блок может служить всеми основаниями только если действительно содержит все
    # лицензированные части; заранее не приписываем этому контролю нулевой результат.
    single_parent = [c for c in ranked if len(set(c['premise_parents'])) == 1]
    coverage = [{'parent': p, 'knowledge_id': v['knowledge_id'], 'article_id': v['article_id'],
                 'status': 'source_licensed' if p in {f['parent'] for f in facets} else 'no_selective_license',
                 'full_parent_retained': True} for p, v in graph['parents'].items()]
    return {'version': VERSION, 'question': None, 'model_calls': 0, 'target_read': False,
        'canonical_blocks': graph['canonical_blocks'], 'statement_count': graph['statement_count'], 'coverage': coverage,
        'licensed_statement_count': len(facets), 'license_proofs': facets,
        'candidates': {'semantic_role_join': ranked, 'single_parent': single_parent},
        'diagnostics': {'search_steps': steps, 'rejected': rejected},
        'interpretation_ru': 'Оператор механистической аналогии; число кандидатов не доказывает научную точность или преимущество.',
        'scientific_success': False, 'graph_advantage_demonstrated': False}
