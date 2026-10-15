"""Отделяет новый вывод от повторения явно доступного требования."""
from domain.article_maps import require, fingerprint

VERSION = 'argument-transfer-audit-1'


def classify_transfer(request, response):
    require(response['operator'] == request['operator'] and response['request_sha256'] == fingerprint(request), 'Request binding differs')
    if response['status'] == 'abstained':
        return {'classification': 'abstained', 'novel_conclusion': False, 'clinical_forecast': False}
    require(response['status'] == 'generated' and bool(response['conclusions']), 'Invalid reconstruction response')
    known = []
    for c in response['conclusions']:
        repeated_requirement = any(
            f['type'] == 'validation_requirement' and f['status'] == 'explicit_requirement' and not f['negated']
            and f['context'] == c['context'] and f['roles'] == c['roles']
            and f['data']['scope'] == 'independent_populations' and f['data']['before_generalization']
            and c['predicate'] == 'validate_in_independent_populations'
            and c['action_status'] == 'unresolved' and c['conditions'] == ['before_generalization']
            for f in request['facts'] if f['id'] in c['premises'])
        known.append(repeated_requirement)
    return {'classification': 'known_requirement_restatement' if all(known) else 'candidate_interpretation',
            'novel_conclusion': not all(known), 'clinical_forecast': False,
            'novelty_scope': 'relative_to_explicit_input_only_not_a_truth_or_generalization_test'}
