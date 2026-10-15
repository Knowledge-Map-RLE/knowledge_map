"""Подготовленные Codex регистрации всех строк шести таблиц WHICAP, без AI."""
import argparse
from collections import Counter
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

from domain.article_maps import fingerprint, require
from domain.registered_table_rows import parse_row, numeric_group, rate_columns, rate_pattern
from domain.partition_label_constraints import infer_labels
from infrastructure.immutable_files import write_immutable
from tools.author_manly_definition_draft import SOURCE_SHA256
from tools.run_free_prediction import disable_network

VERSION = 'manly-six-tables-codex-registration-2'


def build(source):
    require(source['sha256'] == SOURCE_SHA256
            and sha256(source['text'].encode()).hexdigest() == SOURCE_SHA256, 'Reviewed WHICAP source changed')
    units = {u['id']: u for u in source['units']}
    rows = []
    def add(table, uid, label, ru, suffix, fields, **context):
        record = parse_row(source, uid, re.escape(label) + r'\s+' + suffix, fields)
        headers = []
        for header_id in context['header_units']:
            header = units[header_id]
            require(source['text'][header['start']:header['end']] == header['text']
                    and header['end'] <= source['content_end'], 'Table header source differs')
            headers.append({'unit_id': header_id, 'start': header['start'], 'end': header['end'],
                            'text': header['text'], 'sha256': sha256(header['text'].encode()).hexdigest()})
        record.update(table=table, row_index=sum(r['table'] == table for r in rows) + 1,
                      label_en=label, label_ru=ru, study='WHICAP', source_sha256=SOURCE_SHA256,
                      context=context, header_evidence=headers, statistical_significance_inferred=False,
                      scientific_equivalence_asserted=False, inference_licensed=False)
        record['id'] = fingerprint(record)
        rows.append(record)

    table1 = [
        (37, 'MCI with memory impairment', 'MCI с нарушением памяти'),
        (38, 'MCI-amnestic', 'Амнестический MCI'),
        (39, 'MCD with memory', 'Несколько нарушенных областей, включая память'),
        (40, 'MCI without memory impairment', 'MCI без нарушения памяти'),
        (41, 'MCI-executive', 'MCI с нарушением исполнительных функций'),
        (42, 'MCI-language', 'MCI с нарушением языка'),
        (43, 'MCI-visuospatial', 'MCI со зрительно-пространственным нарушением'),
        (44, 'MCD without memory', 'Несколько нарушенных областей без нарушения памяти'),
        (45, 'All MCI subtypes', 'Все подтипы MCI')]
    for uid, label, ru in table1:
        add(1, 'U' + str(uid), label, ru, rate_pattern('', separate_bounds=True), rate_columns(''),
            baseline='no MCI', endpoint='incident MCI subtype', risk_set_n='1800', person_years='7504.9',
            header_units=['U31', 'U33', 'U34', 'U35', 'U36'], printed_rate_mark='%',
            interpret_rate_as='header-defined incidence per 100 person-years; not cumulative risk percent')

    table2 = [(60, '65–69', 'Возраст 65–69 лет', 'age'), (61, '70–74', 'Возраст 70–74 года', 'age'),
              (62, '75–79', 'Возраст 75–79 лет', 'age'), (63, '80⫹', 'Возраст от 80 лет', 'age'),
              (65, '0–11', 'Образование 0–11 лет', 'education'), (66, '12⫹', 'Образование от 12 лет', 'education'),
              (68, 'White', 'Белые участники', 'ethnicity'), (69, 'Black', 'Чернокожие участники', 'ethnicity'),
              (70, 'Hispanic', 'Латиноамериканские участники', 'ethnicity'),
              (72, 'Male', 'Мужчины', 'sex'), (73, 'Female', 'Женщины', 'sex')]
    pattern2 = numeric_group('subjects') + r'\s+' + numeric_group('person_years') + r'\s+' + rate_pattern('memory_') + r'\s+' + rate_pattern('nonmemory_')
    fields2 = {'subjects': {'kind': 'count', 'unit': 'participants'},
               'person_years': {'kind': 'exposure_time', 'unit': 'person-years'},
               **rate_columns('memory_'), **rate_columns('nonmemory_')}
    for uid, label, ru, factor in table2:
        add(2, 'U' + str(uid), label, ru, pattern2, fields2,
            baseline='no MCI according to the table heading', stratifier=factor,
            endpoints=['incident memory MCI', 'incident nonmemory MCI'],
            header_units=['U52', 'U53', 'U55', 'U56', 'U57', 'U58',
                          {'age': 'U59', 'education': 'U64', 'ethnicity': 'U67', 'sex': 'U71'}[factor]], printed_rate_mark='%',
            subjects_column_status='as printed; totals differ by stratifier; do not repair or pool')

    fields3 = {'subjects': {'kind': 'count', 'unit': 'participants'},
               'person_years': {'kind': 'exposure_time', 'unit': 'person-years'}, **rate_columns('')}
    pattern3 = numeric_group('subjects') + r'\s+' + numeric_group('person_years') + r'\s+' + rate_pattern('')
    table3 = [(86, 'No MCI', 'Без исходного MCI', 'normal'),
              (87, 'Age 65–69 yr', 'Возраст 65–69 лет', 'normal'),
              (88, 'Age 70–74 yr', 'Возраст 70–74 года', 'normal'),
              (89, 'Age 75–79 yr', 'Возраст 75–79 лет', 'normal'),
              (90, 'Age 80⫹ yr', 'Возраст от 80 лет', 'normal'),
              (91, 'MCI with memory impairment', 'Исходный MCI с нарушением памяти, как напечатано', 'memory-heading'),
              (92, 'Age 65–69 yr', 'Возраст 65–69 лет', 'memory-heading'),
              (93, 'Age 70–74 yr', 'Возраст 70–74 года', 'memory-heading'),
              (94, 'Age 75–79 yr', 'Возраст 75–79 лет', 'memory-heading'),
              (95, 'Age 80⫹ yr', 'Возраст от 80 лет', 'memory-heading'),
              (96, 'MCI without memory impairment', 'Исходный MCI без нарушения памяти, как напечатано', 'nonmemory-heading'),
              (97, 'Age 65–69 yr', 'Возраст 65–69 лет', 'nonmemory-heading'),
              (98, 'Age 70–74 yr', 'Возраст 70–74 года', 'nonmemory-heading'),
              (99, 'Age 75–79 yr', 'Возраст 75–79 лет', 'nonmemory-heading'),
              (100, 'Age 80⫹ yr', 'Возраст от 80 лет', 'nonmemory-heading')]
    for uid, label, ru, group in table3:
        add(3, 'U' + str(uid), label, ru, pattern3, fields3,
            baseline_group=group, endpoint='incident Alzheimer disease',
            header_units=['U80', 'U81', 'U82', 'U83', 'U84', 'U85'], printed_rate_mark='%',
            population_attribution_status='age-subtotal and parent n disagree' if group != 'normal' else 'as printed')

    for uid, label, ru in [(108, 'Not MCI', 'Без исходного MCI'), *[(u, a, b) for u, a, b in
        [(109, 'MCI-amnestic', 'Амнестический MCI'), (110, 'MCI-executive', 'MCI с нарушением исполнительных функций'),
         (111, 'MCI-language', 'MCI с нарушением языка'), (112, 'MCI-visuospatial', 'Зрительно-пространственный MCI'),
         (113, 'MCI-MCDM', 'Многодоменный MCI с нарушением памяти'), (114, 'MCI-MCDN', 'Многодоменный MCI без нарушения памяти')]]]:
        fields = {'estimate': {'kind': 'estimate', 'unit': 'dimensionless'}}
        suffix = numeric_group('estimate')
        if uid != 108:
            fields.update(low={'kind': 'confidence_bound', 'unit': 'dimensionless'}, high={'kind': 'confidence_bound', 'unit': 'dimensionless'})
            suffix += r'\s+' + numeric_group('low') + r'\s+' + numeric_group('high')
        add(4, 'U' + str(uid), label, ru, suffix, fields,
            endpoint='incident Alzheimer disease', reference='no baseline MCI',
            model='Cox proportional hazards in APOE subset n=2067', printed_estimate_label='Relative Risk',
            interpretation='Cox-model relative estimate as labelled RR; not an absolute incidence rate',
            header_units=['U103', 'U104', 'U105', 'U106', 'U107', 'U115', 'U116', 'U117', 'U118', 'U119'])

    table5 = [(136, 'n', 'Число участников', 'participants', 'count'),
              (137, 'Mean age, yr', 'Средний возраст', 'year', 'mean'),
              (138, 'Mean education, yr', 'Среднее образование', 'year', 'mean'),
              (139, 'Black, %', 'Чернокожие участники', 'percent', 'sample_proportion'),
              (140, 'Hispanic, %', 'Латиноамериканские участники', 'percent', 'sample_proportion'),
              (141, 'Women, %', 'Женщины', 'percent', 'sample_proportion'),
              (143, 'Apolipoprotein', 'Носители аллеля APOE ε4', 'percent', 'sample_proportion'),
              (145, 'Stroke, %', 'Инсульт в анамнезе', 'percent', 'sample_proportion'),
              (146, 'Hypertension, %', 'Гипертония в анамнезе', 'percent', 'sample_proportion'),
              (147, 'Diabetes, %', 'Диабет в анамнезе', 'percent', 'sample_proportion'),
              (148, 'Heart disease, %', 'Болезнь сердца в анамнезе', 'percent', 'sample_proportion'),
              (149, 'Average years of', 'Среднее время наблюдения', 'year', 'mean'),
              (151, 'Average number of', 'Среднее число повторных обследований, как напечатано', 'evaluations', 'mean')]
    groups5 = ['all_normal', 'all_mci', 'all_ad', 'first_normal', 'first_mci', 'first_ad']
    for uid, label, ru, unit, kind in table5:
        fields = {g: {'kind': kind, 'unit': unit} for g in groups5}
        add(5, 'U' + str(uid), label, ru, r'\s+'.join(numeric_group(g) for g in groups5), fields,
            baseline='MCI, n=564', phases=['all available follow-ups', 'first follow-up only'],
            group_order=groups5, other_dementia_cases_excluded='7',
            header_units=['U129', 'U131', 'U132', 'U133', 'U134', 'U135', 'U153', 'U154'],
            interpretation_status='first-follow-up evaluation means repeat n column; unresolved' if uid == 151 else 'as printed')

    table6 = [(164, 'MCI-amnestic', 'Амнестический MCI'), (165, 'MCI-executive', 'Исполнительный MCI'),
              (166, 'MCI-language', 'Языковой MCI'), (167, 'MCI-visuospatial', 'Зрительно-пространственный MCI'),
              (168, 'MCI-MCD with memory impairment', 'Многодоменный MCI с нарушением памяти, строка 5'),
              (169, 'MCI-MCD with memory impairment', 'Повторная подпись многодоменного MCI с памятью, строка 6'),
              (170, 'MCI with memory impairment', 'MCI с нарушением памяти, совокупная строка'),
              (171, 'MCI without memory impairment', 'MCI без нарушения памяти, совокупная строка')]
    fields6 = {prefix + field: {'kind': 'count' if field == 'n' else 'sample_proportion',
                              'unit': 'participants' if field == 'n' else 'percent'}
               for prefix in ('normal_', 'persistent_', 'ad_') for field in ('n', 'percent')}
    for uid, label, ru in table6:
        add(6, 'U' + str(uid), label, ru, r'\s+'.join(numeric_group(k) for k in fields6), fields6,
            baseline='MCI', phase='all available follow-ups', other_dementia_cases_excluded='7',
            interpretation_status='duplicated printed subtype label; unresolved attribution' if uid == 169 else 'as printed',
            header_units=['U160', 'U161', 'U162', 'U163', 'U172', 'U173', 'U174'])

    require(Counter(r['table'] for r in rows) == {1: 9, 2: 11, 3: 15, 4: 7, 5: 13, 6: 8}, 'A registered data row is missing')
    # Проверяются напечатанные суммы; причина несогласованности источнику не приписывается.
    def cell(row, column):
        return Decimal(next(c['value'] for c in row['cells'] if c['column'] == column))
    diagnostics = []
    for table, group_name, selected, expected in [
        (2, factor, [r for r in rows if r['table'] == 2 and r['context']['stratifier'] == factor], Decimal('1800'))
        for factor in ('age', 'education', 'ethnicity', 'sex')]:
        total = sum(cell(r, 'subjects') for r in selected)
        diagnostics.append({'table': table, 'check': 'subjects_sum_vs_header_risk_set', 'group': group_name,
                            'sum': str(total), 'printed_header_n': str(expected), 'agrees': total == expected,
                            'row_ids': [r['id'] for r in selected], 'numerical_deduction_only': True})
    for group_name in ('normal', 'memory-heading', 'nonmemory-heading'):
        group = [r for r in rows if r['table'] == 3 and r['context']['baseline_group'] == group_name]
        total = sum(cell(r, 'subjects') for r in group[1:])
        parent = cell(group[0], 'subjects')
        diagnostics.append({'table': 3, 'check': 'age_subtotal_vs_group_n', 'group': group_name,
                            'sum': str(total), 'printed_parent_n': str(parent), 'agrees': total == parent,
                            'row_ids': [r['id'] for r in group], 'numerical_deduction_only': True})
    return {'version': VERSION, 'source_sha256': SOURCE_SHA256, 'rows': rows,
            'row_count': len(rows), 'numeric_cells': sum(len(r['cells']) for r in rows),
            'row_counts_by_table': dict(Counter(r['table'] for r in rows)), 'numerical_consistency_checks': diagnostics,
            'model_calls': 0, 'expert_validated': False, 'full_map_created': False,
            'new_empirical_predictions': 0, 'scientific_graph_advantage': False,
            'annotation_author': 'Codex',
            'policy_ru': 'Зарегистрированные строки транскрибированы из проверенного PDF. '
                         'Числовая проверка не исправляет источник и не устанавливает клиническую истину. '
                         'Печатный знак процента в таблицах заболеваемости сохранён отдельно от единицы заголовка.'}


def authored_items(rows):
    """Готовит канонические родители и типизированные утверждения для общей схемы 6."""
    items = []
    for row in rows:
        table = row['table']
        values = {c['column']: {'value': c['value'], 'unit': c['unit']} for c in row['cells']}
        context = row['context']
        ambiguous = (table == 2 and context['stratifier'] != 'age'
                     or context.get('population_attribution_status') == 'age-subtotal and parent n disagree'
                     or context.get('interpretation_status', '').startswith(('duplicated', 'first-follow-up')))
        base = {'key': f"table{table}-row{row['row_index']}", 'kind': 'state', 'type': 'result',
                'units': [row['source_unit_id'], *context['header_units']],
                'predicate': 'reported table entry', 'roles': {'cohort': 'WHICAP', 'stratum': row['label_en'],
                    'evidence_origin': 'direct observation in this primary study'},
                'conditions': [] if ambiguous else ['Observational WHICAP study; printed table ' + str(table),
                                                    'As printed; no causal interpretation or inferred significance'],
                'time': None if ambiguous else 'During the reported WHICAP follow-up',
                'attrs': {}, 'claims': [], 'source_table_record_id': row['id'],
                'interpretation_status': 'unresolved source attribution or inconsistent field' if ambiguous else 'source as printed'}
        if table in (1, 2, 3):
            base['predicate'] = 'reported cohort incidence'
            base['attrs']['printed_rate_mark'] = {'value': '%', 'unit': None}
            base['attrs']['confidence_level'] = {'value': '95', 'unit': 'percent'}
            if table in (2, 3):
                base['attrs'].update(subjects_as_printed=values['subjects'], person_years=values['person_years'])
            else:
                base['attrs'].update(at_risk_n={'value': '1800', 'unit': 'participants'},
                                     person_years={'value': '7504.9', 'unit': 'person-years'})
            base['roles']['baseline_group'] = context.get('baseline_group', 'without baseline MCI')
            if table == 2:
                base['roles']['stratifier'] = context['stratifier']
            for prefix, endpoint in ([('memory_', 'incident MCI with memory impairment'),
                                      ('nonmemory_', 'incident MCI without memory impairment')] if table == 2 else
                                     [('', 'incident Alzheimer disease' if table == 3 else 'incident ' + row['label_en'])]):
                base['claims'].append({'roles': {'outcome': endpoint},
                    'attrs': {name: values[prefix + original] for name, original in
                              [('incident_cases', 'cases'), ('incidence_rate', 'rate'),
                               ('confidence_low', 'low'), ('confidence_high', 'high')]}})
        elif table == 4:
            base['predicate'] = 'reported Cox relative estimate'
            base['roles'].update(outcome='incident Alzheimer disease', reference='WHICAP adults without baseline MCI')
            base['attrs'] = {**values, 'source_estimate_label': {'value': 'Relative Risk', 'unit': None},
                             'model': {'value': 'Cox proportional hazards; APOE subset n=2067', 'unit': None}}
            if 'low' in values:
                base['attrs']['confidence_level'] = {'value': '95', 'unit': 'percent'}
            base['claims'] = [{}]
        elif table == 5:
            base['predicate'] = 'reported group summary'
            base['roles']['variable'] = {7: 'APOE epsilon4 carrier status', 12: 'follow-up duration',
                                        13: 'number of follow-up evaluations'}.get(row['row_index'], row['label_en'])
            base['units'] += {7: ['U142', 'U144'], 12: ['U150'], 13: ['U152']}.get(row['row_index'], [])
            base['roles']['baseline_group'] = 'WHICAP adults with baseline MCI'
            for column, value in values.items():
                phase, outcome = column.split('_', 1)
                base['claims'].append({'roles': {'followup_phase': 'all available follow-ups' if phase == 'all' else 'first follow-up',
                                                'outcome_group': {'normal': 'no MCI', 'mci': 'persistent MCI', 'ad': 'Alzheimer disease'}[outcome]},
                                       'attrs': {'reported_value': value}})
        else:
            base['predicate'] = 'reported diagnostic outcome distribution'
            base['roles']['baseline_group'] = 'WHICAP adults with baseline MCI'
            for prefix, outcome in [('normal_', 'no MCI'), ('persistent_', 'persistent MCI'), ('ad_', 'Alzheimer disease')]:
                base['claims'].append({'roles': {'outcome': outcome, 'followup_phase': 'all available follow-ups'},
                                       'attrs': {'participants': values[prefix + 'n'], 'proportion': values[prefix + 'percent']}})
        base['logic'] = 'conjunction' if len(base['claims']) > 1 else 'single'
        en_cells = '; '.join(c['column'] + '=' + c['printed_value'] + ' ' + c['unit'] for c in row['cells'])
        ru_names = {'subjects': 'число участников', 'person_years': 'человеко-лет', 'cases': 'случаи',
                    'rate': 'ставка', 'low': 'нижняя граница ДИ', 'high': 'верхняя граница ДИ',
                    'estimate': 'относительная оценка', 'normal': 'без MCI', 'persistent': 'сохраняющийся MCI',
                    'ad': 'болезнь Альцгеймера', 'percent': 'доля, %', 'n': 'число'}
        def ru_column(column):
            if column in ru_names:
                return ru_names[column]
            return ' / '.join({'memory': 'с нарушением памяти', 'nonmemory': 'без нарушения памяти',
                              'all': 'все визиты', 'first': 'первый визит', 'mci': 'MCI',
                              **ru_names}.get(part, part) for part in column.split('_'))
        ru_cells = '; '.join(ru_column(c['column']) + ': ' + c['printed_value'].replace('.', ',') for c in row['cells'])
        base['en'] = f"WHICAP Table {table}, {row['label_en']}: {en_cells}."
        base['ru'] = f"WHICAP, таблица {table}, {row['label_ru']}: {ru_cells}."
        if table <= 3:
            base['en'] += ' Rates follow the table heading per 100 person-years; printed percent signs are retained as source notation.'
            base['ru'] += ' Ставки — на 100 человеко-лет по заголовку таблицы; печатный знак процента сохранён как обозначение источника.'
        if ambiguous:
            base['en'] += ' Source attribution or field interpretation remains unresolved; no correction is applied.'
            base['ru'] += ' Привязка к группе или смысл поля остаются неоднозначными; источник не исправлен.'
        items.append(base)
    return items


def conditional_subtype_assignment(rows, source):
    table = {r['row_index']: r for r in rows if r['table'] == 6}
    def counts(index):
        values = {c['column']: c['value'] for c in table[index]['cells']}
        return [int(values[prefix + 'n']) for prefix in ('normal_', 'persistent_', 'ad_')]
    result = infer_labels({'memory': counts(7), 'nonmemory': counts(8)},
                          {'memory': [counts(1)], 'nonmemory': [counts(2), counts(3), counts(4)]},
                          {'printed_row_5': counts(5), 'printed_row_6': counts(6)},
                          {'mutually_exclusive': True, 'exhaustive': True, 'common_phase': True, 'counts_correct': True})
    result['table_row_bindings'] = [r['id'] for r in table.values()]
    result['assumption_provenance'] = [u for u in source['units'] if u['id'] in ('U23', 'U25', 'U160', 'U161', 'U172', 'U173')]
    result['counts_correct_is_assumed_not_verified'] = True
    result['source_labels_changed'] = False
    require(result['status'] == 'unique_conditional_assignment', 'Registered example no longer yields a unique conditional assignment')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    disable_network()
    root = args.root.resolve() / 'eval/whole_map_forecast/manly-complete-map-v1'
    source = json.loads((root / 'source-v1/source.json').read_text(encoding='utf-8'))
    result = build(source)
    result['authored_knowledge_draft'] = authored_items(result['rows'])
    result['conditional_subtype_assignment'] = conditional_subtype_assignment(result['rows'], source)
    result['implementation_sha256'] = {name: sha256((Path(__file__).resolve().parents[1] / name).read_bytes()).hexdigest()
                                      for name in ('domain/registered_table_rows.py', 'domain/partition_label_constraints.py',
                                                   'tools/author_manly_table_records.py', 'domain/article_maps.py')}
    folder = root / 'table-records' / fingerprint(result)
    write_immutable(folder / 'data.json', json.dumps(result, ensure_ascii=False, indent=2).encode())
    report = ['# WHICAP: полная регистрация строк шести таблиц', '',
              f"Сохранены {result['row_count']} строки данных; числовых ячеек с исходными координатами — {result['numeric_cells']}.",
              'Это табличный этап формализации; законченная карта и эмпирические прогнозы пока не созданы.', '',
              '| Таблица | Строки данных |', '| --- | ---: |']
    report += [f"| {table} | {count} |" for table, count in result['row_counts_by_table'].items()]
    report += ['', '## Проверка числовой согласованности', '',
               '| Проверка | Сумма строк | Напечатанный общий размер | Согласовано |', '| --- | ---: | ---: | --- |']
    group_ru = {'age': 'Возраст', 'education': 'Образование', 'ethnicity': 'Этническая группа', 'sex': 'Пол',
                'normal': 'Без исходного MCI', 'memory-heading': 'Под заголовком MCI с памятью',
                'nonmemory-heading': 'Под заголовком MCI без памяти'}
    for d in result['numerical_consistency_checks']:
        report.append(f"| Таблица {d['table']}: {group_ru[d['group']]} | {d['sum']} | "
                      f"{d.get('printed_header_n', d.get('printed_parent_n'))} | {'Да' if d['agrees'] else 'Нет'} |")
    report += ['', 'Размеры напечатаны именно так в исходном PDF. Различия не исправлены перестановкой групп '
               'или подменой чисел; их причина не установлена. Таблица 5 также повторяет числа участников '
               'в строке среднего числа обследований для первого визита. В таблице 6 две разные строки имеют '
               'одинаковую подпись многодоменного MCI с нарушением памяти; второй строке не приписан другой подтип.', '',
               'Для таблиц 1–3 единица показателя взята из заголовка: случаи на 100 человеко-лет. '
               'Печатный знак процента хранится отдельно; ставка не преобразована в кумулятивный риск. '
               'Таблица 4 содержит относительные оценки модели Кокса, обозначенные авторами как относительный риск. '
               'Доли участников таблиц 5–6 относятся к другим показателям и фазам наблюдения.', '',
               'Все исходные строки сохранены; статистическая значимость из одних точечных оценок или перекрытия ДИ '
               'не выводилась. Обнаруженные арифметические несогласованности являются результатом проверки источника, '
               'не научным прогнозом. Модельных вызовов — 0; экспертная проверка отсутствует. Сервисы не менялись.', '']
    assignment = result['conditional_subtype_assignment']
    report += ['## Условный вывод о повторной подписи', '',
               'При допущении корректности всех счётчиков и полной взаимоисключающей разбивки шести подтипов '
               'существует единственное соответствие двух многодоменных строк совокупным группам.', '',
               f"Остаток группы с нарушением памяти после амнестической строки: {assignment['residuals']['memory']}. "
               f"Остаток группы без нарушения памяти после трёх изолированных подтипов: {assignment['residuals']['nonmemory']}.", '',
               'По всем трём исходам первый остаток совпадает со строкой 5, второй — со строкой 6. '
               'Таким образом, если остальные данные корректны, шестой строке соответствует группа без нарушения памяти. '
               'Это условное восстановление по ограничениям, а не установленное исправление публикации: '
               'ошибка могла находиться в подписи, счётчиках или другой части таблицы. Печатные подписи сохранены.', '',
               'Оператор использует сравнение и вычитание векторов счётчиков, проверяет обе перестановки подписей. '
               'Категорические силлогизмы и языковые модели для этого вывода не применялись. '
               'Условный вывод не является предсказанием нового эмпирического результата.', '']
    write_immutable(folder / 'report.ru.md', '\n'.join(report).encode())
    print(folder)
    print('Строк:', result['row_count'], 'числовых ячеек:', result['numeric_cells'])


if __name__ == '__main__':
    main()
