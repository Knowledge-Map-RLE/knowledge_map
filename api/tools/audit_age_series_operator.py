"""Создаёт воспроизводимый аудит возрастных рядов из зафиксированного манифеста."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'api'))

from domain.age_series_operator import VERSION, build_series, evaluate_series, extract_rows, summarize
from domain.article_maps import fingerprint
from domain.whole_map_ablation import permuted_groups
from domain.whole_map_forecast import project
from domain.whole_map_context import VERSION as CONTEXT_AUDIT_VERSION


DEFAULT_MANIFEST = ROOT / 'eval/whole_map_forecast/research-corpus-extension-v1/sydney2013-extension-forecast-v1/numeric-audit-runs/c7495b88d24b59152b775b2d83cc072d25b18e7949f8a285e0ad011e6dadfe22/source-manifest.json'
TARGET_SOURCE_SHA256 = 'f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8'
OUTPUT_DIR = ROOT / 'eval/whole_map_forecast/research-corpus-extension-v1/age-series-operator-v4'


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _load_inputs(manifest_path):
    raw_manifest = manifest_path.read_bytes()
    manifest = json.loads(raw_manifest.decode('utf-8'))
    maps = []
    for source in manifest['sources']:
        path = Path(source['path'])
        map_bytes = path.read_bytes()
        item = json.loads(map_bytes.decode('utf-8'))
        if _sha256(map_bytes) != source['file_sha256']:
            raise ValueError(f"Хеш карты не совпадает с манифестом: {path}")
        if fingerprint(item['graph']) != source['graph_sha256']:
            raise ValueError(f"Хеш графа не совпадает с манифестом: {path}")
        if _sha256(item['source']['text'].encode('utf-8')) != source['source_sha256']:
            raise ValueError(f"Хеш текста источника не совпадает с манифестом: {path}")
        maps.append(item)
    if any(source['source_sha256'] == TARGET_SOURCE_SHA256 for source in manifest['sources']):
        raise ValueError('Целевая статья PMC10000452 обнаружена в обучающем манифесте')
    return manifest, maps, _sha256(raw_manifest)


def _build_context_audit(maps):
    """Лицензирует только таблицу PAQUID по её точной исходной единице."""
    article = next(item for item in maps if item['article_id'] == 'larrieu2002-codex')
    knowledge = next(item for item in article['graph']['knowledge'] if item['knowledge_id'] == 'K8')
    source_units = {unit['id']: unit for unit in article['source']['units']}
    unit_ids = sorted({unit_id for statement in knowledge['semantic_frame']['statements']
                       for unit_id in statement['provenance']['unit_ids']})
    evidence = []
    for unit_id in unit_ids:
        unit = source_units[unit_id]
        if 'Table 1 Incidence rates' in unit['text'] and '1993–1998' in unit['text']:
            evidence.append({
                'unit_id': unit_id,
                'start': unit['start'],
                'end': unit['end'],
                'text': unit['text'],
                'sha256': _sha256(unit['text'].encode('utf-8')),
            })
    if len(evidence) != 1:
        raise ValueError('Не найден единственный точный фрагмент таблицы PAQUID с периодом 1993–1998')
    return {
        'version': CONTEXT_AUDIT_VERSION,
        'author': 'Codex',
        'expert_validated': False,
        'model_calls': 0,
        'entries': [{
            'article_id': article['article_id'],
            'knowledge_id': knowledge['knowledge_id'],
            'run_id': article['run_id'],
            'source_sha256': article['source']['sha256'],
            'graph_sha256': fingerprint(article['graph']),
            'knowledge_sha256': fingerprint(knowledge),
            'decision': 'resolve_for_pattern_analysis',
            'context_resolution': 'source_local_report',
            'reason_ru': 'Таблица 1 прямо задаёт период PAQUID 1993–1998 и единый набор возрастных строк; разрешается только внутристатейное сопоставление этих строк в контексте отчёта. Период или состав выборки за пределами указанной таблицы не выводятся.',
            'reason_en': 'Table 1 explicitly identifies the PAQUID period as 1993–1998 and contains the age rows in one table; only within-article comparison in this source-local report is admitted. No time period or population beyond the stated table is inferred.',
            'evidence': evidence,
            'attribute_types': [],
        }],
    }


def _series_key(series):
    return (series['article_id'], series['context_id'], series['metric_family'], series['unit'])


def _direction(value):
    return {1: 'рост', -1: 'снижение', 0: 'без изменения', None: 'воздержание'}[value]


def _article_ru(article_id):
    return {
        'larrieu2002-codex': 'Larrieu, 2002',
        'luck2010': 'Luck, 2010',
        'manly2008-complete': 'Manly, 2008',
        'pilot-pmc10000452-pmc6416157-502eaa3572eaf017': 'PMC6416157, систематический обзор',
    }.get(article_id, article_id)


def _cohort_ru(value):
    return {
        'paquid': 'PAQUID',
        'leila 75+': 'LEILA75+',
        'whicap': 'WHICAP',
        'population-based incidence review cohorts': 'популяционные исследования из обзора заболеваемости',
    }.get(value, value)


def _outcome_ru(value):
    return {
        'incident mci': 'новые случаи MCI',
        'incident total mci': 'новые случаи MCI без подтипизации',
        'incident mci with memory impairment': 'новые случаи MCI с нарушением памяти',
        'incident mci without memory impairment': 'новые случаи MCI без нарушения памяти',
        'mild cognitive impairment': 'лёгкое когнитивное нарушение (MCI)',
        'amnestic mild cognitive impairment': 'амнестический MCI',
        'nonamnestic mild cognitive impairment': 'неамнестический MCI',
    }.get(value, value)


def _age_label_ru(value):
    text = value.strip().casefold().replace('years', '').replace('year', '').strip()
    if text.endswith(' лет'):
        return value
    text = text.replace('—', '–').replace('-', '–')
    match = re.fullmatch(r'(\d{2,3})\s*–\s*(\d{2,3})', text)
    if match:
        return f'{match.group(1)}–{match.group(2)} лет'
    match = re.fullmatch(r'(?:≥|>=)\s*(\d{2,3})', text)
    if match:
        return f'≥{match.group(1)} лет'
    match = re.fullmatch(r'(\d{2,3})\s*(?:\+|⫹)', text)
    if match:
        return f'{match.group(1)} лет и старше'
    match = re.fullmatch(r'(\d{2,3})\s*(?:or\s+older|and\s+older)', text)
    if match:
        return f'{match.group(1)} лет и старше'
    return value


def _status_ru(value):
    return {'correct': 'верно', 'error': 'ошибка', 'abstention': 'воздержание'}[value]


def _serialize_series(series):
    checks = evaluate_series(series)
    labels = {role: value for role, value in series['context']['roles']}
    outcome = labels.get('outcome') or labels.get('condition') or labels.get('status') or 'не уточнён'
    cohort = labels.get('cohort') or labels.get('population') or labels.get('study') or 'не указана'
    return {
        'series_id': series['series_id'],
        'article_id': series['article_id'],
        'outcome': outcome,
        'cohort': cohort,
        'metric_family': series['metric_family'],
        'unit': series['unit'],
        'graph_supported': bool(series['shared_dependency_groups']),
        'dependency_groups': series['shared_dependency_groups'],
        'rows': [{
            'age_label': row['band'].label,
            'age_lower': row['band'].lower,
            'age_upper': row['band'].upper,
            'value': str(row['value']),
            'knowledge_id': row['knowledge_id'],
            'number_of_studies': row['study_count'],
        } for row in series['rows']],
        'checks': [{**check,
            'target_band': check['target_band'],
            'predicted_direction': _direction(check['predicted_direction']),
            'observed_direction': _direction(check['observed_direction'])}
            for check in checks],
    }


def _metric_table(title, summary):
    return (f"| {title} | {summary['series']} | {summary['checks']} | {summary['issued']} | "
            f"{summary['correct']} | {summary['errors']} | {summary['abstentions']} |")


def _build_report(data):
    version_number = data['operator_version'].rsplit('-', 1)[-1].lstrip('v')
    included_articles = {series['article_id'] for series in data['series']}
    has_paquid = 'larrieu2002-codex' in included_articles
    has_context_audit = bool(data.get('context_audit', {}).get('entries'))
    superseded_note = (
        'предварительный диагностический прогон; его заменяет версия 4 после адресного аудита контекста PAQUID.'
        if version_number == '3' else None
    )
    if has_paquid:
        extraction_note = 'Ранее использовавшийся извлекатель находил 5 рядов; расширенный извлекатель добавил PAQUID (Larrieu 2002) и LEILA75+ (Luck 2010).'
    else:
        extraction_note = 'Ранее использовавшийся извлекатель находил 5 рядов; расширенный извлекатель добавил LEILA75+ (Luck 2010). Таблица PAQUID была обнаружена, но исключена из-за неизвестной формальной области времени.'
    if has_context_audit:
        paquid_note = 'Блок PAQUID K8 допущен только после проверки точного фрагмента исходной таблицы, где явно указан период 1993–1998 годов. Аудит ограничивает сопоставление этой таблицей и этой статьёй; данные не переносятся в другие источники.'
    else:
        paquid_note = 'Блок PAQUID K8 остаётся исключённым: его формальная область времени неизвестна. В исходном фрагменте виден период таблицы 1993–1998 годов, но этот предварительный прогон ещё не применил адресный аудит контекста.'
    if has_paquid:
        paquid_graph_note = 'PAQUID демонстрирует ограничение текущей графовой группировки: блок таблицы с возрастными ставками используется как предпосылка отдельного авторского заключения, но сам не имеет входящей группы, поэтому графовый режим не считает его рядом с поддержанными предпосылками. Это повод отдельно проверять использование таблиц как доказательств для выводов, а не добавлять рёбра задним числом.'
    else:
        paquid_graph_note = 'В предварительной версии 3 таблица PAQUID не попала даже в безрёберный режим из-за неизвестной формальной области времени. Проверка источника подтвердила таблицу за 1993–1998 годы; версия 4 допускает её только в безрёберный ряд, поскольку у блока нет входящей группы зависимостей.'
    if data['semantic_summary']['series'] > data['graph_summary']['series']:
        coverage_note = 'На рядах, доступных обоим основным режимам, количество совпадений и ошибок одинаково. Полный режим без рёбер охватывает PAQUID без входящей группы зависимостей и потому имеет больше проверок; его нельзя использовать как парное сравнение точности с графом.'
    else:
        coverage_note = 'Все семантически допустимые ряды имеют общую входящую группу предпосылок, поэтому парные метрики режимов совпадают.'
    lines = [
        '# Расширенный аудит оператора возрастных рядов',
        '',
        *( [f'Статус: {superseded_note}', ''] if superseded_note else [] ),
        f"Версия оператора: {version_number}. Манифест: `{data['manifest_sha256']}`.",
        f"Вход — {data['source_count']} зафиксированных карт схемы 6; SHA-256 источника целевой PMC10000452 исключён.",
        'Хеши файлов карт, графов и исходных текстов проверены. Внешние и локальные модели, сеть и проектные генераторы не вызывались.',
        '',
        '## Что было исправлено',
        '',
        'Извлечение распознаёт варианты роли «возрастной интервал» и «возрастная группа», а также сочетание «стратификатор = возраст» с ролью «возрастной слой». Открытые интервалы понимаются как «85 лет и старше» и «не менее 85 лет». Показатели берутся только из явных числовых полей частоты заболеваемости на человеко-время. Медиана обзора остаётся отдельной величиной и допускается только при числе включённых исследований не менее двух. Оценки по образованию и полу не смешиваются с общей ставкой.',
        '',
        f"Найдено {data['row_count']} возрастных числовых наблюдений, сгруппированных в {data['semantic_summary']['series']} сопоставимых рядах. {extraction_note}",
        paquid_note,
        '',
        '## Сравнение на одинаковых рядах',
        '',
        'В режимах применяется одно правило: упорядочить соседние возрастные интервалы и предсказывать следующий интервал только при едином направлении всех предыдущих изменений; при смешанном направлении воздерживаться. В контроль без рёбер передаются те же семантические поля, метрика, единица и фильтр минимум двух включённых исследований для обзорной медианы.',
        '',
        '| Режим | Рядов | Проверок следующего интервала | Выдано направлений | Верно | Ошибок | Воздержаний |',
        '|---|---:|---:|---:|---:|---:|---:|',
        _metric_table('Исходные зависимости', data['graph_summary']),
        _metric_table('Без рёбер, только те же 6 рядов', data['paired_summary']),
        _metric_table('Без рёбер, все семантически допустимые ряды', data['semantic_summary']),
        _metric_table('Перемешанные зависимости', data['permuted_summary']),
        '',
        coverage_note,
        '',
        '## Ряды и проверки',
        '',
        '| Статья / когорта / исход | Значения по возрасту | Продолжение | Карта даёт общую группу предпосылок |',
        '|---|---|---|---|',
    ]
    for series in data['series']:
        values = ', '.join(f"{_age_label_ru(row['age_label'])}: {row['value']}" for row in series['rows'])
        checks = '; '.join(
            f"для {_age_label_ru(check['target_band'])} прогноз {check['predicted_direction']}, факт {check['observed_direction']} ({_status_ru(check['status'])})"
            for check in series['checks']) or 'проверок нет'
        lines.append(f"| {_article_ru(series['article_id'])} / {_cohort_ru(series['cohort'])} / {_outcome_ru(series['outcome'])} | {values} | {checks} | {'да' if series['graph_supported'] else 'нет'} |")
    lines.extend([
        '',
        '## Интерпретация',
        '',
        f"Для общего набора из {data['semantic_summary']['issued']} выданных направлений правильными оказались {data['semantic_summary']['correct']}, ошибочными — {data['semantic_summary']['errors']}; ещё {data['semantic_summary']['abstentions']} проверки завершились воздержанием. Это последовательные проверки внутри уже прочитанных статей и обзора, а не прогноз целой новой статьи. Проверки из одной таблицы зависимы между собой; их нельзя считать независимыми научными подтверждениями.",
        '',
        'Графовый и безрёберный режим совпали на общей выборке. Следовательно, этот оператор не показывает преимущества Карты Знаний по точности. Общая группа предпосылок сохраняет методологическое членение: например, метааналитические оценки PMC6416157 отделены от одиночного описательного результата. Но эта структура не улучшила направление прогноза.',
        '',
        paquid_graph_note,
        '',
        'PMC6416157 является обзором, а не независимой первичной когортой; в предыдущем аудите подтверждено включение WHICAP Manly 2008 [36]. Их совпадение не считается независимым повторением. Числа WHICAP сохранены как отображены в карте; исходная таблица неоднозначно печатает процентный знак и заголовок единицы, поэтому научная интерпретация этой ставки требует экспертной проверки.',
        '',
        '## Вывод для основной цели',
        '',
        'Расширение извлечения исправило пропуск возрастных форматов, но не нашло доказательства превосходства графа. Этот оператор остаётся узким: он продолжает направление числового ряда, а не ищет свободно новые знания во всей карте. Следующий результат для основной цели должен проверять замороженные семантические операторы на статьях, исключённых целиком, считать поддержку по независимым когортам и сравнивать исходный граф с теми же знаниями без рёбер и с корректно переставленными рёбрами.',
        '',
        'Модельных, сетевых и эмбеддинговых вызовов не было. Эталон PMC10000452 не использовался как обучающий источник. Экспертная проверка научной точности не выполнена.',
        '',
    ])
    return '\n'.join(lines)


def run(manifest_path, output_dir):
    manifest, maps, manifest_hash = _load_inputs(manifest_path)
    context_audit = _build_context_audit(maps)
    records, groups, coverage = project(maps, context_audit)
    rows = extract_rows(records)
    semantic, semantic_rejected = build_series(rows, groups, require_shared_dependencies=False)
    graph, graph_rejected = build_series(rows, groups, require_shared_dependencies=True)
    graph_ids = {item['series_id'] for item in graph}
    paired = [item for item in semantic if item['series_id'] in graph_ids]
    rewired = permuted_groups(records, groups)
    permuted, permuted_rejected = build_series(rows, rewired, require_shared_dependencies=True)

    data = {
        'operator_version': VERSION,
        'manifest_sha256': manifest_hash,
        'source_count': len(maps),
        'target_source_sha256': TARGET_SOURCE_SHA256,
        'target_excluded': True,
        'canonical_knowledge_count': len(records),
        'visible_dependency_groups': len(groups),
        'row_count': len(rows),
        'graph_summary': summarize(graph),
        'paired_summary': summarize(paired),
        'semantic_summary': summarize(semantic),
        'permuted_summary': summarize(permuted),
        'rejections': {'graph': graph_rejected, 'semantic': semantic_rejected, 'permuted': permuted_rejected},
        'coverage_count': len(coverage),
        'context_audit': {
            'version': context_audit['version'],
            'entries': [{key: value for key, value in entry.items() if key != 'evidence'}
                        for entry in context_audit['entries']],
            'evidence': context_audit['entries'][0]['evidence'],
        },
        'series': [_serialize_series(item) for item in semantic],
        'paired_series_ids': sorted(graph_ids),
        'permuted_series_count': len(permuted),
        'model_calls': 0,
        'network_calls': 0,
    }
    data['report'] = _build_report(data)
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / 'audit.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (output_dir / 'report.ru.md').write_text(data['report'], encoding='utf-8')
    return data


def refresh_report(output_dir):
    """Пересобирает только русское представление из уже зафиксированного JSON."""
    audit_path = output_dir / 'audit.json'
    data = json.loads(audit_path.read_text(encoding='utf-8'))
    data['report'] = _build_report(data)
    audit_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (output_dir / 'report.ru.md').write_text(data['report'], encoding='utf-8')
    return data


def main():
    parser = argparse.ArgumentParser(description='Аудит возрастных рядов на зафиксированных картах')
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--output', type=Path, default=OUTPUT_DIR)
    parser.add_argument('--refresh-report', action='store_true')
    args = parser.parse_args()
    if args.refresh_report:
        data = refresh_report(args.output)
        print(json.dumps({'report': str(args.output / 'report.ru.md'),
                          'graph': data['graph_summary'],
                          'paired_without_dependencies': data['paired_summary'],
                          'all_without_dependencies': data['semantic_summary']}, ensure_ascii=False, indent=2))
        return
    data = run(args.manifest, args.output)
    print(json.dumps({
        'report': str(args.output / 'report.ru.md'),
        'input_manifest_sha256': data['manifest_sha256'],
        'graph': data['graph_summary'],
        'paired_without_dependencies': data['paired_summary'],
        'all_without_dependencies': data['semantic_summary'],
        'permuted': data['permuted_summary'],
        'new_series': data['semantic_summary']['series'] - 5,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
