"""Чистые операции над явно записанными статистиками, без научных допущений."""
from decimal import Decimal, InvalidOperation
import re

def number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    raw = str(value).strip().replace('−', '-').replace('–', '-')
    if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', raw):
        return None
    try:
        result = Decimal(raw)
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def p_bound(value):
    if isinstance(value, str):
        match = re.fullmatch(r'\s*(<=|>=|<|>|≤|≥|=)?\s*([\d.]+)\s*', value)
        if not match:
            return None
        op, raw = match.groups()
        op = {'≤': '<=', '≥': '>='}.get(op, op or '=')
    else:
        op, raw = '=', value
    result = number(raw)
    if result is None or not Decimal(0) <= result <= Decimal(1):
        return None
    return op, result


def statistical_finding(p_value, alpha):
    # Без явно заданного порога стандартные .05 не подставляются.
    alpha = number(alpha)
    bound = p_bound(p_value)
    if alpha is None or not Decimal(0) < alpha < Decimal(1) or bound is None:
        return 'not_established'
    op, value = bound
    if op == '=':
        return 'detected_at_declared_threshold' if value < alpha else 'not_detected_at_declared_threshold'
    if op == '<' and value <= alpha or op == '<=' and value < alpha:
        return 'detected_at_declared_threshold'
    if op in ('>', '>=') and value >= alpha:
        return 'not_detected_at_declared_threshold'
    return 'not_established'


def interval_diagnostic(value, point):
    if value is None:
        return 'not_reported'
    raw = str(value).replace('−', '-').strip()
    match = re.fullmatch(r'\(?\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s+to\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*\)?', raw)
    if not match:
        return 'not_interpreted'
    low, high = map(number, match.groups())
    if low > high:
        return 'reported_interval_bounds_reversed'
    return 'reported_point_outside_interval' if not low <= point <= high else 'reported_interval_contains_estimate'


def attributes(statement):
    values = {}
    for a in statement['attributes']:
        if a['name'] in values:
            return None
        values[a['name']] = a
    return values


def roles(statement):
    values = {}
    for role in statement['roles']:
        if role['role'] in values:
            return None
        values[role['role']] = role['value']
    return values


def direction(value, null=Decimal(0)):
    return 'above_null' if value > null else 'below_null' if value < null else 'at_null'


