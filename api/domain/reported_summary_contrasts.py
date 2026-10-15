"""Закрытый порядок табличных сводок: весь родитель и статистический смысл сохраняются."""
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import re
import unicodedata

from domain.article_maps import fingerprint, require
from domain.statistical_primitives import attributes, number, roles

VERSION = 'source-bound-closed-summary-contrast-1'
PREDICATES = {'reported baseline summary', 'reported group summary'}
NUM = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)'
DEFINITIONS = {
    'median_iqr': 'Порядок опубликованных медиан; квартильный интервал сохраняется.',
    'mean_sd': 'Порядок опубликованных средних; стандартное отклонение сохраняется.',
    'count_percent': 'Отдельный порядок опубликованных численностей и долей; знаменатель не восстанавливается.',
}


def compact(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value).casefold())


def definition(label):
    text = compact(label)
    choices = []
    if 'median(iqr)' in text: choices.append('median_iqr')
    if 'mean±sd' in text: choices.append('mean_sd')
    if 'n(%)' in text: choices.append('count_percent')
    return choices[0] if len(choices) == 1 else None


def parse_summary(raw, kind):
    if not isinstance(raw, str) or kind not in DEFINITIONS:
        return None, 'summary_definition_missing'
    text = unicodedata.normalize('NFKC', raw).strip().replace('−', '-')
    if kind == 'median_iqr':
        match = re.fullmatch(rf'({NUM})\s*\(\s*({NUM})\s*(?:–|to|-)\s*({NUM})\s*\)', text)
        if match is None: return None, 'invalid_median_iqr_syntax'
        point, low, high = map(number, match.groups())
        if not low <= point <= high: return None, 'median_outside_reported_iqr'
        return {'statistic': kind, 'location': str(point), 'q1': str(low), 'q3': str(high), 'raw': raw}, None
    if kind == 'mean_sd':
        match = re.fullmatch(rf'({NUM})\s*±\s*({NUM})', text)
        if match is None: return None, 'invalid_mean_sd_syntax'
        point, sd = map(number, match.groups())
        if sd < 0: return None, 'negative_reported_sd'
        return {'statistic': kind, 'location': str(point), 'sd': str(sd), 'raw': raw}, None
    match = re.fullmatch(rf'(\d+)\s*\(\s*({NUM})\s*\)', text)
    if match is None: return None, 'invalid_count_percent_syntax'
    count, percent = map(number, match.groups())
    if not 0 <= percent <= 100: return None, 'reported_percent_out_of_range'
    return {'statistic': kind, 'count': str(count), 'percent': str(percent), 'raw': raw,
            'item_denominator': None, 'percent_recomputed': False}, None


def native_role(statement, role, concepts):
    matches = [r for r in statement['roles'] if r['role'] == role]
    if len(matches) != 1 or not {'role', 'concept_id'} <= set(matches[0]) <= {'role', 'concept_id', 'knowledge_id'}:
        return None
    if matches[0].get('knowledge_id') is not None: return None
    return concepts.get(matches[0]['concept_id'])


def bind_table_row(native, source, concepts):
    """Определение берётся из точной строки/заголовка источника, не из формы чисел."""
    statements = native['semantic_frame']['statements']
    measure = native_role(statements[0], 'measure', concepts)
    if not measure: return None, 'native_measure_label_missing'
    grouping = native_role(statements[0], 'grouping', concepts)
    units = {u['id']: u for u in source['units']}
    ids = statements[0]['provenance']['unit_ids']
    if any(s['provenance']['unit_ids'] != ids for s in statements):
        return None, 'different_part_table_provenance'
    candidates = []
    for uid in ids:
        require(uid in units, 'Summary source unit missing')
        unit = units[uid]
        require(source['text'][unit['start']:unit['end']] == unit['text']
                and 0 <= unit['start'] < unit['end'] <= source['content_end'], 'Summary source unit changed')
        header = None
        offset = unit['start']
        for line in unit['text'].splitlines(keepends=True):
            row = line.rstrip('\r\n'); cells = [c.strip() for c in row.split('|')]
            if len(cells) > 1 and cells[0] and all(not c or c == '(%)' for c in cells[1:]):
                header = {'text': row, 'label': cells[0], 'start': offset, 'end': offset + len(row)}
            if len(cells) > 1 and compact(cells[0]) == compact(measure):
                raw_attrs = [next((a['value'] for a in s['qualifiers']['attributes'] if a['name'] == 'printed_summary'), None)
                             for s in statements]
                if len(cells[1:]) != len(statements) or any(not isinstance(v, str) or compact(v) != compact(c)
                                                           for v, c in zip(raw_attrs, cells[1:])):
                    return None, 'printed_summary_differs_from_source_row'
                own_kind = definition(cells[0]); declared = cells[0]; used_header = None
                if own_kind is None:
                    # Наследование разрешено лишь от ближайшего явного заголовка той же таблицы.
                    if header is None or not grouping or compact(header['label']) != compact(grouping):
                        return None, 'explicit_row_or_section_definition_missing'
                    declared = ' '.join(c for c in header['text'].split('|') if c.strip())
                    own_kind = definition(declared); used_header = header
                if own_kind is None: return None, 'explicit_row_or_section_definition_missing'
                candidates.append({'definition': own_kind, 'definition_text': declared,
                    'definition_from': 'row_label' if used_header is None else 'explicit_section_header',
                    'row': {'start': offset, 'end': offset + len(row), 'text': row},
                    'header': deepcopy(used_header), 'unit_id': uid,
                    'source_unit': deepcopy(unit), 'source_sha256': source['sha256'],
                    'measure_label': measure})
            offset += len(line)
    if len(candidates) != 1: return None, 'source_row_not_unique_or_missing'
    return candidates[0], None


def measurement_basis(label, kind, key):
    if kind == 'count_percent':
        return {'count_unit': 'reported_category_count', 'percent_unit': 'percent', 'item_denominator': None,
                'cross_source_measure_equivalence': False}
    text = compact(label)
    markers = {'inyears': 'year', '(kg/m2)': 'kg/m2', '(pg/ml)': 'pg/ml', '(mg/dl)': 'mg/dl', '(kg)': 'kg'}
    units = {unit for marker, unit in markers.items() if marker in text}
    if len(units) == 1:
        return {'location_and_spread_unit': next(iter(units)), 'unit_basis': 'explicit_source_row_label',
                'cross_source_measure_equivalence': False}
    return {'location_and_spread_unit': None, 'unit_basis': 'opaque_source_local_same_row',
            'opaque_basis_id': fingerprint({'key': key, 'label': label}),
            'cross_source_measure_equivalence': False}


def closed_profile(record, native, source, concepts):
    frame = record['frame']; statements = frame['statements']
    if frame['logic'] != 'contrast' or len(statements) < 2: return None, 'not_a_closed_multigroup_contrast'
    if not record['eligible']: return None, 'unknown_parent_context'
    if frame['kind'] != 'state': return None, 'summary_state_required'
    require(native['semantic_frame']['logic'] == frame['logic'] and native['kind'] == frame['kind'],
            'Summary native parent logic or kind differs')
    first = statements[0]
    if first['predicate'] not in PREDICATES: return None, 'no_summary_contrast_operator'
    if first['negated']: return None, 'negated_report_is_not_a_measurement'
    require(len(statements) == len(native['semantic_frame']['statements']), 'Summary native statement order differs')
    first_roles = roles(first)
    if first_roles is None or not {'measure', 'population'} <= first_roles.keys(): return None, 'summary_axes_missing'
    comparison_roles = {k: v for k, v in first_roles.items() if k != 'population'}
    populations = []
    for s in statements:
        r = roles(s)
        if r is None or set(r) != set(first_roles): return None, 'ambiguous_summary_roles'
        if s['predicate'] != first['predicate'] or s['scope'] != first['scope'] or s['negated'] != first['negated']:
            return None, 'different_summary_scope_or_polarity'
        if {k: v for k, v in r.items() if k != 'population'} != comparison_roles:
            return None, 'different_summary_measures'
        if any(isinstance(v, dict) for v in r.values()): return None, 'nested_summary_roles'
        populations.append(r['population'])
    if len(set(populations)) != len(populations): return None, 'repeated_summary_population'
    binding, error = bind_table_row(native, source, concepts)
    if binding is None: return None, error
    parsed = []
    for i, s in enumerate(statements):
        a = attributes(s)
        if a is None or 'printed summary' not in a: return None, 'ambiguous_summary_attributes'
        if a['printed summary']['unit'] is not None: return None, 'unexpected_compound_summary_unit'
        native_values = [v['value'] for v in native['semantic_frame']['statements'][i]['qualifiers']['attributes']
                         if v['name'] == 'printed_summary']
        require(len(native_values) == 1 and a['printed summary']['value'] == native_values[0],
                'Summary normalized value differs from exact native source')
        summary, error = parse_summary(a['printed summary']['value'], binding['definition'])
        if error: return None, error
        group_n = None
        if 'group n' in a:
            group_n = number(a['group n']['value'])
            if group_n is None or group_n < 0 or group_n != int(group_n) or a['group n']['unit'] != 'participants':
                return None, 'invalid_declared_group_size'
            if binding['definition'] == 'count_percent' and number(summary['count']) > group_n:
                return None, 'count_exceeds_declared_group_size'
        parsed.append({'statement_position': i, 'population': populations[i], 'summary': summary,
                       'reported_group_n': str(group_n) if group_n is not None else None})
    fields = ['count', 'percent'] if binding['definition'] == 'count_percent' else ['location']
    orders = []
    for field in fields:
        # Ранги плотные: равные напечатанные величины остаются равными, без проверки значимости.
        values = sorted({number(p['summary'][field]) for p in parsed})
        ranks = [values.index(number(p['summary'][field])) + 1 for p in parsed]
        orders.append({'field': field, 'ascending_dense_ranks': ranks,
            'equality_basis': 'reported_rounded_decimal_only', 'statistical_significance': 'not_established'})
    proof = {'version': VERSION, 'key': list(record['key']), 'run_id': record['run_id'],
        'source_binding': binding, 'complete_native_knowledge': deepcopy(native),
        'parent_knowledge_sha256': fingerprint(native), 'complete_normalized_parent_frame': deepcopy(frame),
        'complete_parent_provenance': deepcopy(record['provenance']),
        'all_statement_positions': list(range(len(statements))), 'definition_ru': DEFINITIONS[binding['definition']],
        'new_empirical_measurement': False, 'independent_replication': False, 'causality_asserted': False,
        'groups_disjoint_or_independent_asserted': False, 'conditions_removed': False,
        'logic': 'conditional_order_of_complete_reported_row', 'expert_validated': False}
    profile = {'key': list(record['key']), 'kind': 'closed_reported_summary_profile', 'definition': binding['definition'],
        'scope': deepcopy(first['scope']), 'original_logic': frame['logic'],
        'measurement_basis': measurement_basis(binding['measure_label'], binding['definition'], record['key']),
        'rows': parsed, 'orders': orders, 'proof': proof,
        'forecast_of_future_article': False, 'separate_part_premise_license': False}
    profile['id'] = fingerprint(profile)
    return profile, None


def project_closed_summaries(records, maps):
    catalogs = {m['article_id']: m for m in maps}
    require(set(catalogs) == {k[0] for k in records}, 'Complete summary source registry required')
    native = {(m['article_id'], k['knowledge_id']): k for m in maps for k in m['graph']['knowledge']}
    require(set(native) == set(records), 'Complete summary native knowledge registry required')
    for source_map in maps:
        source = source_map['source']
        require(sha256(source['text'].encode()).hexdigest() == source['sha256'], 'Summary source hash changed')
    profiles = []; coverage = []; counts = Counter()
    for key, record in sorted(records.items()):
        source_map = catalogs[key[0]]; source = source_map['source']
        concepts = {c['id']: c['display_text'] for c in source_map['graph']['concepts']}
        profile, reason = closed_profile(record, native[key], source, concepts)
        if profile is not None: profiles.append(profile)
        counts[reason or 'licensed_closed_profile'] += 1
        coverage.append({'key': list(key), 'status': reason or 'licensed_closed_profile',
            'profile_id': profile['id'] if profile else None,
            'native_statements': len(record['frame']['statements'])})
    return {'version': VERSION, 'profiles': profiles, 'coverage': coverage, 'counts': dict(counts),
        'canonical_blocks': len(records), 'new_empirical_predictions': 0, 'model_calls': 0,
        'scientific_success': False, 'graph_advantage_demonstrated': False}
