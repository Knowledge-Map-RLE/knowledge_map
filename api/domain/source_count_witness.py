"""Источник-привязанная непустота класса для условных категорических выводов."""
from hashlib import sha256
import re

from domain.article_maps import require
from domain.categorical_logic import check, validate

VERSION = 'positive-count-categorical-witness-1'


def positive_count_witness(source, cell, subject, scope, annotation):
    require(source['offset_encoding'] == 'unicode_codepoints'
            and sha256(source['text'].encode()).hexdigest() == source['sha256'], 'Witness source differs')
    require(cell['kind'] == 'count' and cell['unit'] in {'cases', 'participants'}, 'A percentage or rate is not a class count')
    start, end = cell['source_span']['start'], cell['source_span']['end']
    require(type(start) is int and type(end) is int and 0 <= start < end <= source['content_end']
            and source['text'][start:end] == cell['printed_value'], 'Witness count coordinates differ')
    require(re.fullmatch(r'\d+', cell['value']) and cell['printed_value'].replace(',', '') == cell['value'],
            'Exact nonnegative integer count required')
    require(isinstance(subject, str) and subject and annotation.get('subject') == subject
            and annotation.get('source_unit_id') == cell['source_unit_id']
            and annotation.get('author') == 'Codex' and annotation.get('source_row_id'), 'Explicit counted-class interpretation required')
    validate({'form': 'I', 'subject': subject, 'object': subject, 'scope': scope})
    if int(cell['value']) == 0:
        return {'version': VERSION, 'status': 'no_positive_count_witness', 'subject': subject, 'scope': scope}
    return {'version': VERSION, 'status': 'source_reported_nonempty_class', 'subject': subject,
            'scope': scope, 'count': cell['value'], 'source_sha256': source['sha256'],
            'source_span': cell['source_span'], 'annotation': annotation,
            'truth_of_source_count_expert_validated': False}


def check_with_witness(premises, conclusion, witness):
    terms = {p[k] for p in [*premises, conclusion] for k in ('subject', 'object')}
    require(witness['subject'] in terms and witness['scope'] == conclusion['scope'],
            'Existence belongs to another class or context')
    if witness['status'] != 'source_reported_nonempty_class':
        return {'status': 'blocked_no_existence_witness', 'entailed': False}
    proof = check(premises, conclusion, (witness['subject'],))
    return {'status': 'conditional_source_bound_deduction' if proof['entailed'] else 'not_entailed',
            **proof, 'witness': witness, 'empirical_forecast': False, 'expert_validated': False}
