"""Проверка материала и временных якорей до включения результата в прогноз по вопросу."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import re
from domain.article_maps import digest, require

VERSION = 'prospective-question-screening-1'
FIELDS = ('matrix', 'processing', 'exposure_visit', 'outcome_start_visit', 'dementia_excluded',
          'dementia_visit', 'minimum_age_at_exposure', 'outcome', 'followup_years')


def validate_screening_record(record, source):
    require(set(record) == {'id', 'family', 'source_sha256', 'features', 'note_ru', 'note_en'}, 'Screening record fields differ')
    require(record['id'] and record['family'] and record['source_sha256'] == source['sha256'] == digest(source['text']),
            'Screening provenance differs')
    require(set(record['features']) == set(FIELDS) and record['note_ru'] and record['note_en'], 'Explicit screening traits and bilingual notes required')
    references = re.search(r'(?im)^\s*(?:#{1,6}\s*)?references\s*$', source['text'])
    body_end = references.start() if references else len(source['text'])
    for trait in record['features'].values():
        require(set(trait) == {'status', 'value', 'evidence'} and trait['status'] in {'known', 'not_reported'}, 'Unknown screening status')
        require((trait['value'] is not None) == (trait['status'] == 'known') and bool(trait['evidence']), 'Missing screening evidence or presumed value')
        for span in trait['evidence']:
            require(set(span) == {'start', 'end', 'text', 'offset_encoding'} and span['offset_encoding'] == 'unicode_code_points'
                    and type(span['start']) is int and type(span['end']) is int
                    and 0 <= span['start'] < span['end'] <= body_end
                    and source['text'][span['start']:span['end']] == span['text'], 'Screening evidence fragment differs')
    return deepcopy(record)


def screen_continuous_mmse(record):
    """Неизвестное блокирует допуск, но не становится отрицательным научным результатом."""
    features = record['features']; blockers = []
    require(set(features) == set(FIELDS), 'Missing screening trait; no fallback')
    def known(name):
        trait = features[name]
        require(trait['status'] in {'known', 'not_reported'} and (trait['value'] is not None) == (trait['status'] == 'known'), 'Invalid screening value')
        if trait['status'] != 'known':
            blockers.append({'field': name, 'reason': 'not_established', 'kind': 'unknown'})
            return None
        return trait['value']
    matrix, processing = known('matrix'), known('processing')
    if matrix is not None and matrix != 'plasma': blockers.append({'field': 'matrix', 'reason': 'not_plasma', 'kind': 'mismatch'})
    if processing is not None and processing != 'direct_plasma_assay': blockers.append({'field': 'processing', 'reason': 'not_direct_plasma_assay', 'kind': 'mismatch'})
    age = known('minimum_age_at_exposure')
    if age is not None:
        try:
            value = Decimal(str(age)); require(value.is_finite() and value >= 0 and not isinstance(age, bool), 'Invalid exposure age')
        except (InvalidOperation, TypeError): require(False, 'Invalid exposure age')
        if value < 60: blockers.append({'field': 'minimum_age_at_exposure', 'reason': 'age_at_least_60_not_established', 'kind': 'unknown'})
    exposure, start, dementia_visit = known('exposure_visit'), known('outcome_start_visit'), known('dementia_visit')
    for visit in (exposure, start, dementia_visit):
        if visit is not None:
            require(set(visit) == {'axis', 'value'} and visit['axis'] and isinstance(visit['value'], str) and visit['value'], 'Explicit visit axis and label required')
    if exposure is not None and start is not None and exposure != start:
        blockers.append({'field': 'outcome_start_visit', 'reason': 'common_baseline_not_established', 'kind': 'unknown'})
    excluded = known('dementia_excluded')
    if excluded is not None:
        require(type(excluded) is bool, 'Explicit dementia exclusion required')
        if not excluded: blockers.append({'field': 'dementia_excluded', 'reason': 'baseline_dementia_not_excluded', 'kind': 'mismatch'})
    if exposure is not None and dementia_visit is not None and exposure != dementia_visit:
        blockers.append({'field': 'dementia_visit', 'reason': 'dementia_exclusion_at_exposure_not_established', 'kind': 'unknown'})
    outcome = known('outcome')
    if outcome is not None:
        require(set(outcome) == {'instrument', 'estimand'}, 'Explicit MMSE estimand required')
        if outcome['instrument'] != 'mmse' or outcome['estimand'] not in {'two_assessment_annual_change', 'last_available_annual_change'}:
            blockers.append({'field': 'outcome', 'reason': 'not_continuous_annual_mmse_change', 'kind': 'mismatch'})
    followup = known('followup_years')
    if followup is not None:
        require(set(followup) == {'basis', 'value'} and followup['basis'] in {'planned', 'median'}, 'Planned or median follow-up required')
        try:
            duration = Decimal(str(followup['value'])); require(duration.is_finite() and duration > 0 and not isinstance(followup['value'], bool), 'Invalid follow-up')
        except (InvalidOperation, TypeError): require(False, 'Invalid follow-up')
        if duration < 2: blockers.append({'field': 'followup_years', 'reason': 'duration_below_two_years', 'kind': 'mismatch'})
    return {'record_id': record['id'], 'family': record['family'], 'version': VERSION,
            'eligible_for_subquestion': not blockers, 'blockers': blockers, 'features': deepcopy(features),
            'comparison_context_equivalence_confirmed': False, 'every_participant_followed_two_years': False,
            'training_support_added': False, 'expert_validated': False}
