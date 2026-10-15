"""Консервативный отбор прямых наблюдений; происхождение не выводится из имени статьи."""
from collections import Counter

VERSION = 'empirical-origin-eligibility-2'


def classify(item, concepts):
    reasons = set()
    if item['kind'] != 'state':
        reasons.add('action_or_task')
    if item['knowledge_kind'] not in {'observation', 'result', 'comparison'}:
        reasons.add('not_observed_result')
    for statement in item['semantic_frame']['statements']:
        if not statement.get('temporal_context') or not statement.get('conditions'):
            reasons.add('context_not_explicit')
        if statement['modality'] is not None:
            reasons.add('qualified_modality')
        origins = [concepts.get(r.get('concept_id'), '') for r in statement['roles'] if r['role'] == 'evidence_origin']
        if not origins:
            reasons.add('origin_not_explicit')
        elif any(origin != 'direct observation in this primary study' for origin in origins):
            reasons.add('not_direct_primary_observation')
    return {'knowledge_id': item['knowledge_id'], 'eligible_direct_observation': not reasons,
            'reasons': sorted(reasons)}


def audit(graph):
    concepts = {c['id']: c['display_text'] for c in graph['concepts']}
    rows = [classify(item, concepts) for item in graph['knowledge']]
    return {'version': VERSION, 'scope': 'direct empirical support only; other knowledge remains available for reasoning',
            'eligible_blocks': sum(r['eligible_direct_observation'] for r in rows),
            'reason_counts': dict(Counter(reason for r in rows for reason in r['reasons'])),
            'rows': rows, 'scientific_accuracy_verified': False}
