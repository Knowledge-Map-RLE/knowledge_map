"""Проекция готовой схемы 6; не извлекает исходный текст и не создаёт AI-клиента."""
from domain.article_maps import fingerprint, require
from domain.comparison_normalization import normalize_map, VERSION as NORMALIZER_VERSION, DICTIONARY_SHA256
from domain.development_prediction import validate_visible_dag
from domain.semantic_operator_learning import Knowledge, Example

VERSION = 'schema6-operator-projection-1'


def project(result, family, published_on, annotations):
    validate_visible_dag(result['graph'])
    normalized = normalize_map(result)
    by_id = {k['id']: k for k in normalized}
    require(set(annotations) == {'availability', 'transitions', 'question_context'}, 'Explicit availability, contexts and operator annotations required')
    require(set(annotations['availability']) == set(by_id), 'Availability must cover every canonical knowledge')
    require(set(annotations['question_context']) == set(by_id), 'Question context must cover every canonical knowledge')
    units, by_knowledge = [], {}
    source_id = result['article_id']
    for k in normalized:
        # Только конъюнкция допускает независимое рассмотрение частей; аргумент и контраст остаются едиными.
        groups = [[s] for s in k['statements']] if k['logic'] == 'conjunction' else [k['statements']]
        by_knowledge[k['id']] = []
        for i, statements in enumerate(groups):
            frame = {'kind': k['kind'], 'action_status': k['action_status'],
                     'logic': 'single' if k['logic'] == 'conjunction' else k['logic'],
                     'statements': []}
            for s in statements:
                frame['statements'].append({key: s[key] for key in ('predicate', 'scope', 'attributes', 'negated', 'unknown_context')}
                                          | {'scope': {key: s['scope'][key] for key in ('quantifier', 'modality', 'time', 'conditions')},
                                             'roles': [{'role': r['role'], 'value': r['value'] if isinstance(r['value'], str)
                                                        else 'knowledge:' + fingerprint(r['value'])} for r in s['roles']]})
            claim_id = source_id + '/' + k['id'] + '/' + str(i)
            unit = Knowledge(claim_id, source_id, family, published_on, frame, annotations['availability'][k['id']],
                             {'source_sha256': result['source']['sha256'], 'run_id': result['run_id'],
                              'frame_sha256': fingerprint(frame), 'provenance': [s['provenance'] | {'knowledge_id': k['id'], 'statement_id': s['id']} for s in statements]},
                             annotations['question_context'][k['id']])
            unit.validate(); units.append(unit); by_knowledge[k['id']].append(claim_id)
    nodes = {n['id']: n['knowledge_id'] for n in result['graph']['nodes']}
    transitions = {t['id']: t for t in result['graph']['transitions']}
    require(set(annotations['transitions']) == set(transitions), 'Operator annotation must cover each transition')
    examples, rejected = [], []
    for tid, t in transitions.items():
        annotation = annotations['transitions'][tid]
        require(set(annotation) == {'operator', 'author_grounded'}, 'Exact transition annotation required')
        premises = tuple(p for node in t['sources'] for p in by_knowledge[nodes[node]])
        if len(premises) > 3:
            rejected.append({'transition_id': tid, 'reason': 'more_than_three_joint_semantic_premises'}); continue
        for conclusion in by_knowledge[nodes[t['target']]]:
            examples.append(Example(source_id + '/' + tid + '/' + conclusion, annotation['operator'], premises,
                                    conclusion, annotation['author_grounded']))
    return {'knowledge': units, 'examples': examples, 'rejected': rejected,
            'binding': {'article_id': source_id, 'run_id': result['run_id'], 'family': family, 'published_on': published_on,
                        'source_sha256': result['source']['sha256'], 'graph_sha256': fingerprint(result['graph']),
                        'annotations_sha256': fingerprint(annotations), 'projection_version': VERSION,
                        'normalizer_version': NORMALIZER_VERSION, 'dictionary_sha256': DICTIONARY_SHA256}}
