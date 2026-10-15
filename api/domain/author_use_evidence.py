"""Проверяет первичное основание ручной разметки переноса метода или аргумента."""
from domain.article_maps import digest, require, fingerprint
from domain.research_semantics import valid_date

VERSION = 'author-use-evidence-1'


def audit_author_use(control, sources):
    """Не извлекает смысл: семантическое решение Codex остаётся явным входом.

    Проверка фрагментов и хронологии не является экспертной проверкой научной
    истинности. Принятие аргумента никогда не означает прогноз эмпирического эффекта.
    """
    require(control['usage_kind'] in {'method_adoption', 'argument_use', 'analysis_rationale'}, 'Unknown author-use kind')
    require(control['primary_status'] in {'confirmed', 'qualified_match', 'unconfirmed'}, 'Unknown primary support status')
    require(control['later_status'] in {'explicit_use', 'citation_only', 'unclear'}, 'Unknown later-use status')
    for key in ['shared_core', 'limitations']:
        require(isinstance(control[key], list) and all(isinstance(x, str) and x.strip() for x in control[key]), 'Invalid explicit semantic annotation')
    require(control['primary_status'] != 'qualified_match' or bool(control['limitations']), 'Qualified transfer needs limitations')
    for endpoint in ['earlier', 'later']:
        ref = control[endpoint]
        require(ref['source_id'] in sources, 'Unknown primary source')
        source = sources[ref['source_id']]
        require(digest(source['text']) == source['sha256'], 'Primary source hash differs')
        valid_date(ref['available_on'])
        require(isinstance(ref['family'], str) and ref['family'].strip(), 'Explicit study family required')
        p = ref['span']
        require(type(p['start']) is int and type(p['end']) is int and 0 <= p['start'] < p['end'] <= source['content_end'], 'Evidence enters references or is out of range')
        require(p['offset_encoding'] == 'unicode_code_points' and source['text'][p['start']:p['end']] == p['text'], 'Exact Unicode provenance differs')
    earlier, later = control['earlier'], control['later']
    reasons = []
    if earlier['available_on'] >= later['available_on']: reasons.append('not_strictly_earlier')
    if control['later_status'] != 'explicit_use': reasons.append('author_use_not_explicit')
    if control['primary_status'] == 'unconfirmed': reasons.append('primary_premise_not_confirmed')
    if not control['shared_core']: reasons.append('shared_argument_or_method_missing')
    accepted = not reasons
    kind = 'requires_review'
    if accepted:
        kind = 'verified_' + ('qualified_' if control['primary_status'] == 'qualified_match' else '') + control['usage_kind']
    return {'version': VERSION, 'id': control['id'], 'annotation_sha256': fingerprint(control),
            'accepted_for_author_use_diagnostic': accepted, 'classification': kind, 'reasons': reasons,
            'different_families': earlier['family'] != later['family'], 'receiving_family': later['family'],
            'shared_core': control['shared_core'], 'limitations': control['limitations'],
            'fact_equivalence_established': False, 'clinical_prediction_established': False,
            'author': 'Codex', 'expert_validated': False, 'semantic_extraction_performed': False}
