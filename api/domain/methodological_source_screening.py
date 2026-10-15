"""Допуск источника проверяет временную доступность предикторов отдельно от сходства контекста."""
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from domain.article_maps import digest, fingerprint, require

VERSION = 'methodological-source-screening-2'
BOOLEAN_FIELDS = ('baseline_il6', 'dementia_excluded', 'global_change', 'isolated_il6',
                  'predictors_available_at_origin', 'adjustments_available_at_origin')
FIELDS = (*BOOLEAN_FIELDS, 'matrix', 'minimum_age', 'followup_years')


def screen_source_analysis(record, source, historical_before):
    require(set(source) == {'text', 'sha256'} and digest(source['text']) == source['sha256'], 'Source hash differs')
    require(set(record) == {'id', 'article_id', 'family', 'source_kind', 'source_sha256', 'publication_date',
                            'facts', 'note_ru', 'note_en'}, 'Screening record fields differ')
    require(record['source_sha256'] == source['sha256'] and all(isinstance(record[k], str) and record[k]
            for k in ('id', 'article_id', 'family', 'note_ru', 'note_en')), 'Explicit identity and provenance required')
    require(record['source_kind'] in {'full_primary_article', 'primary_abstract'}, 'Unknown source kind')
    try:
        boundary = date.fromisoformat(historical_before)
        published = date.fromisoformat(record['publication_date'])
        require(boundary.isoformat() == historical_before and published.isoformat() == record['publication_date'], 'Canonical date required')
    except (ValueError, TypeError):
        require(False, 'Invalid historical date')
    facts = record['facts']
    require(set(facts) == set(FIELDS), 'Missing explicit screening field')
    references = re.search(r'(?im)^[ \t]*(?:\d+(?:\.\d+)*\.?[ \t]+)?(?:references|r[ \t]*eferences|bibliography)[ \t]*$', source['text'])
    own_body_end = references.start() if references else len(source['text'])
    blockers = []
    if published >= boundary:
        blockers.append({'field': 'publication_date', 'kind': 'mismatch', 'reason': 'not_before_frozen_boundary'})
    if record['source_kind'] != 'full_primary_article':
        blockers.append({'field': 'source_kind', 'kind': 'unknown', 'reason': 'abstract_is_exclusion_only'})
    for name, fact in facts.items():
        require(set(fact) == {'value', 'evidence'} and bool(fact['evidence']), 'Explicit source evidence required')
        for span in fact['evidence']:
            require(set(span) == {'start', 'end', 'text', 'offset_encoding'} and span['offset_encoding'] == 'unicode_code_points'
                    and type(span['start']) is int and type(span['end']) is int
                    and 0 <= span['start'] < span['end'] <= own_body_end
                    and source['text'][span['start']:span['end']] == span['text'], 'Screening source fragment differs')
        value = fact['value']
        if value is None:
            blockers.append({'field': name, 'kind': 'unknown', 'reason': 'not_established'})
        elif name in BOOLEAN_FIELDS:
            require(type(value) is bool, 'Boolean screening fact required')
            if not value:
                blockers.append({'field': name, 'kind': 'mismatch', 'reason': 'requirement_not_met'})
        elif name == 'matrix':
            require(value in {'plasma', 'serum', 'whole_blood_supernatant', 'whole_blood'}, 'Unknown specimen')
            if value != 'plasma':
                blockers.append({'field': name, 'kind': 'mismatch', 'reason': 'not_direct_plasma'})
        else:
            try:
                number = Decimal(str(value))
                require(not isinstance(value, bool) and number.is_finite() and number >= 0, 'Invalid duration or age')
            except (InvalidOperation, ValueError, TypeError):
                require(False, 'Invalid duration or age')
            minimum = 60 if name == 'minimum_age' else 2
            if number < minimum:
                blockers.append({'field': name, 'kind': 'mismatch', 'reason': 'below_frozen_minimum'})
    return {'version': VERSION, 'record': deepcopy(record), 'historical_before': historical_before,
            'input_sha256': fingerprint({'record': record, 'source_sha256': source['sha256'], 'historical_before': historical_before}),
            'eligible_for_frozen_question': not blockers, 'blockers': blockers,
            'status': 'ineligible' if any(b['kind'] == 'mismatch' for b in blockers) else 'unresolved' if blockers else 'eligible',
            'training_support_added': False, 'empirical_transfer_licensed': False, 'scientific_success': False,
            'expert_validated': False, 'model_calls': 0}
