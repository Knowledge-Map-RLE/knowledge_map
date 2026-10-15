"""Возрастные серии для воспроизводимой диагностики числового переноса."""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

from domain.article_maps import fingerprint


VERSION = 'age-series-operator-v4'
_DIRECT_AGE_ROLES = {'age band', 'age group', 'age range', 'age category'}
_RATE_METRICS = {
    'incidence rate': 'primary_incidence_rate',
    'total rate': 'primary_incidence_rate',
    'rate': 'primary_incidence_rate',
    'median ir': 'review_median_incidence_rate',
}
_NUMERIC_VALUE = re.compile(r'^[+-]?\d+(?:[.,]\d+)?$')


@dataclass(frozen=True, order=True)
class AgeBand:
    """Нормализованный возрастной интервал; верхняя граница None означает открытую."""

    lower: int
    upper: int | None
    label: str


def parse_age_band(value):
    """Читает только явно заданные интервалы и открытые возрастные группы."""
    if not isinstance(value, str):
        return None
    label = value.strip()
    normalized = label.casefold().replace('years', '').replace('year', '').strip()
    normalized = normalized.replace('–', '-').replace('—', '-').replace('−', '-')
    normalized = re.sub(r'^age\s+', '', normalized)
    if normalized in {'all ages', 'all age groups'}:
        return None

    match = re.fullmatch(r'(\d{2,3})\s*(?:-|to)\s*(\d{2,3})', normalized)
    if match:
        lower, upper = int(match.group(1)), int(match.group(2))
        if lower <= upper:
            return AgeBand(lower, upper, label)
        return None

    match = re.fullmatch(r'(?:>=|≥)\s*(\d{2,3})', normalized)
    if not match:
        match = re.fullmatch(r'(\d{2,3})\s*(?:\+|⫹|or\s+older|and\s+older)', normalized)
    if match:
        return AgeBand(int(match.group(1)), None, label)
    return None


def _age_from_roles(roles):
    by_role = {item['role'].strip().casefold(): item['value'] for item in roles}
    excluded = set()
    for role in _DIRECT_AGE_ROLES:
        if role in by_role:
            band = parse_age_band(by_role[role])
            if band is not None:
                excluded.add(role)
                if str(by_role.get('stratifier', '')).casefold() in {'age', 'age group', 'age band'}:
                    excluded.add('stratifier')
                return band, excluded
    if str(by_role.get('stratifier', '')).casefold() in {'age', 'age group', 'age band'}:
        for role in ('stratum', 'group', 'comparison group'):
            if role in by_role:
                band = parse_age_band(by_role[role])
                if band is not None:
                    return band, {'stratifier', role}
    if 'age' in by_role:
        band = parse_age_band(by_role['age'])
        if band is not None:
            return band, {'age'}
    return None, excluded


def _normalized_unit(value):
    unit = str(value or '').casefold().replace('years', 'year').replace('persons', 'person')
    return re.sub(r'[^a-z0-9]+', '', unit)


def _numeric_value(value):
    text = str(value).strip()
    if not _NUMERIC_VALUE.fullmatch(text):
        return None
    try:
        return Decimal(text.replace(',', '.'))
    except InvalidOperation:
        return None


def _study_count(attributes):
    for attribute in attributes:
        if attribute['name'].strip().casefold() == 'number of studies':
            match = re.match(r'^\s*(\d+)', str(attribute['value']))
            return int(match.group(1)) if match else None
    return None


def _context(statement, excluded_age_roles):
    roles = [
        (item['role'].strip().casefold(), item['value'])
        for item in statement['roles']
        if item['role'].strip().casefold() not in excluded_age_roles
    ]
    roles.sort(key=lambda item: (item[0], fingerprint(item[1])))
    return {
        'predicate': statement['predicate'].strip().casefold(),
        'roles': roles,
        'scope': statement.get('scope'),
        'negated': statement.get('negated', False),
    }


def extract_rows(records):
    """Извлекает скалярные ставки, сохраняя исход, роли, метод и единицу."""
    rows = []
    for key, record in records.items():
        if not record.get('eligible', True):
            continue
        for index, statement in enumerate(record['frame']['statements']):
            band, excluded_roles = _age_from_roles(statement['roles'])
            if band is None:
                continue
            attributes = statement['attributes']
            study_count = _study_count(attributes)
            context = _context(statement, excluded_roles)
            for attribute in attributes:
                metric_name = attribute['name'].strip().casefold()
                metric_family = _RATE_METRICS.get(metric_name)
                unit = _normalized_unit(attribute.get('unit'))
                if metric_family is None or 'person' not in unit or 'year' not in unit:
                    continue
                value = _numeric_value(attribute['value'])
                if value is None:
                    continue
                # Медиана по обзору не сопоставляется с единичной первичной оценкой.
                if metric_family == 'review_median_incidence_rate' and (study_count is None or study_count < 2):
                    continue
                rows.append({
                    'key': key,
                    'statement_index': index,
                    'article_id': key[0],
                    'knowledge_id': key[1],
                    'band': band,
                    'value': value,
                    'metric_name': metric_name,
                    'metric_family': metric_family,
                    'unit': unit,
                    'study_count': study_count,
                    'context': context,
                    'context_id': fingerprint(context),
                })
    return rows


def _valid_ordered_rows(rows):
    ordered = sorted(rows, key=lambda row: (row['band'].lower, row['band'].upper is None,
                                           row['band'].upper or 10_000, row['knowledge_id']))
    if len(ordered) < 3:
        return None, 'fewer_than_three_age_bands'
    for previous, current in zip(ordered, ordered[1:]):
        if previous['band'].upper is None or current['band'].lower <= previous['band'].upper:
            return None, 'overlapping_age_bands'
        if current['band'].lower != previous['band'].upper + 1:
            return None, 'nonadjacent_age_bands'
    return ordered, None


def build_series(rows, groups, require_shared_dependencies=False):
    """Группирует только совпадающие контексты и при запросе требует общей группы рёбер."""
    parent_groups = defaultdict(set)
    for body, head in groups:
        parent_groups[head].add(tuple(sorted(body)))

    buckets = defaultdict(list)
    for row in rows:
        identity = (row['article_id'], row['context_id'], row['metric_family'], row['unit'])
        buckets[identity].append(row)

    series = []
    rejected = defaultdict(int)
    for identity, bucket in buckets.items():
        ordered, reason = _valid_ordered_rows(bucket)
        if reason:
            rejected[reason] += 1
            continue
        if len({(row['band'].lower, row['band'].upper) for row in ordered}) != len(ordered):
            rejected['duplicate_age_band'] += 1
            continue

        signatures = [parent_groups.get(row['key'], set()) for row in ordered]
        shared = set.intersection(*(set(value) for value in signatures)) if signatures else set()
        if require_shared_dependencies and not shared:
            rejected['no_shared_incoming_dependency_group'] += 1
            continue

        series.append({
            'series_id': fingerprint({'identity': identity, 'rows': [
                (row['band'].lower, row['band'].upper, str(row['value'])) for row in ordered
            ]}),
            'article_id': identity[0],
            'context_id': identity[1],
            'metric_family': identity[2],
            'unit': identity[3],
            'context': ordered[0]['context'],
            'rows': ordered,
            'shared_dependency_groups': [list(group) for group in sorted(shared)],
        })
    return sorted(series, key=lambda item: (item['article_id'], item['context_id'])), dict(rejected)


def evaluate_series(series):
    """Проверяет продолжение единого направления соседних оценок с воздержанием."""
    checks = []
    rows = series['rows']
    values = [row['value'] for row in rows]
    for target_index in range(2, len(rows)):
        earlier_differences = [values[index] - values[index - 1] for index in range(1, target_index)]
        if all(value > 0 for value in earlier_differences):
            predicted = 1
        elif all(value < 0 for value in earlier_differences):
            predicted = -1
        else:
            predicted = None
        observed_difference = values[target_index] - values[target_index - 1]
        observed = 1 if observed_difference > 0 else -1 if observed_difference < 0 else 0
        status = 'abstention' if predicted is None else 'correct' if predicted == observed else 'error'
        checks.append({
            'target_band': rows[target_index]['band'].label,
            'predicted_direction': predicted,
            'observed_direction': observed,
            'status': status,
            'previous_values': [str(value) for value in values[:target_index]],
            'observed_values': [str(values[target_index - 1]), str(values[target_index])],
        })
    return checks


def summarize(series):
    """Возвращает счётчики диагностических проверок, не трактуя их как независимые."""
    checks = [check for item in series for check in evaluate_series(item)]
    issued = [check for check in checks if check['status'] != 'abstention']
    return {
        'series': len(series),
        'checks': len(checks),
        'issued': len(issued),
        'correct': sum(check['status'] == 'correct' for check in issued),
        'errors': sum(check['status'] == 'error' for check in issued),
        'abstentions': sum(check['status'] == 'abstention' for check in checks),
    }
