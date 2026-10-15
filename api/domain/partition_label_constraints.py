"""Условное восстановление подписей по полной взаимоисключающей разбивке счётчиков."""
from itertools import permutations

from domain.article_maps import require

VERSION = 'conditional-partition-label-constraints-1'


def infer_labels(totals, known_parts, unresolved_rows, assumptions):
    require(isinstance(totals, dict) and 1 <= len(totals) <= 6
            and len(totals) == len(unresolved_rows), 'One unresolved row per partition group required')
    require(set(known_parts) == set(totals), 'Known categories must cover each named group')
    require(set(assumptions) == {'mutually_exclusive', 'exhaustive', 'common_phase', 'counts_correct'}
            and all(type(v) is bool for v in assumptions.values()), 'Explicit partition assumptions required')
    if not all(assumptions.values()):
        return {'version': VERSION, 'status': 'blocked_missing_assumption', 'assignments': [],
                'source_correction_authorized': False}
    vectors = [*totals.values(), *unresolved_rows.values(), *(v for group in known_parts.values() for v in group)]
    require(vectors and all(isinstance(v, (list, tuple)) for v in vectors)
            and len(vectors[0]) > 0 and len({len(v) for v in vectors}) == 1
            and all(type(n) is int and n >= 0 for v in vectors for n in v), 'Aligned nonnegative count vectors required')
    residuals = {group: [n - sum(part[i] for part in known_parts[group]) for i, n in enumerate(total)]
                 for group, total in totals.items()}
    assignments = []
    groups = sorted(totals)
    for row_order in permutations(sorted(unresolved_rows)):
        if all(list(unresolved_rows[row]) == residuals[group] for group, row in zip(groups, row_order)):
            assignments.append(dict(zip(row_order, groups)))
    return {'version': VERSION, 'status': 'unique_conditional_assignment' if len(assignments) == 1 else
            'ambiguous_conditional_assignment' if assignments else 'inconsistent_under_assumptions',
            'residuals': residuals, 'assignments': assignments, 'assumptions': assumptions,
            'source_correction_authorized': False, 'empirical_forecast': False,
            'policy_ru': 'Уникальность условна на корректности всех остальных счётчиков и полной разбивки. '
                         'Она не доказывает, какая часть публикации ошибочна, и не разрешает изменение источника.'}
