"""Русский автономный отчёт полного парного опыта с точными ограничениями."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from domain.article_maps import fingerprint, require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.render_template_barrier_audit import render_lines
from tools.run_free_prediction import disable_network

MODES = {'graph': 'Зависимости карты', 'same_rules_without_dependencies': 'Те же правила без зависимостей',
    'source_neighborhood_without_dependencies': 'Соседство источника без зависимостей', 'permuted_dependencies': 'Перемешанные зависимости'}
POLICIES = {'legacy_digits_constant': 'Прежняя политика', 'typed_concept_participants': 'Типизированные участники'}


def main():
    parser = argparse.ArgumentParser()
    for f in ('run', 'tests', 'review'): parser.add_argument('--' + f, required=True)
    args = parser.parse_args(); disable_network(); run = Path(args.run).resolve()
    result = FilePredictionStore(run.parent).read_seal(run.name)
    require(result['version'] == 'whole-map-typed-participant-forecast-3', 'Unexpected participant version')
    descriptor = json.loads((run / 'input-corpus.json').read_bytes())
    source_path = Path(descriptor['snapshot']); source = FilePredictionStore(source_path.parent).read_seal(source_path.name)
    require(fingerprint(source) == result['binding']['source_sha256'], 'Source snapshot changed')
    tests_path = Path(args.tests).resolve(); raw_tests = tests_path.read_bytes()
    suites = ET.fromstring(raw_tests).findall('testsuite')
    require(suites and all(int(s.attrib.get(f, 0)) == 0 for s in suites for f in ('errors', 'failures', 'skipped')), 'Participant tests failed')
    count = sum(int(s.attrib['tests']) for s in suites)
    lines = ['# Участники с цифрами и повторяющиеся структуры всей карты', '',
        '**Новых прогнозов — 0. Преимущество зависимостей не установлено.**', '',
        f"Повторены все 11 карт: {result['canonical_blocks']} канонических знания, "
        f"{result['semantic_statements']} семантических утверждений и {result['licensed_parts']} допустимых частей. "
        'Вопрос, фактор или целевая болезнь генератору не задаются. Полные родители и происхождение частей сохранены.', '',
        '## Что изменено', '',
        'Прежний генератор оставлял константой любое название участника с цифрой. Например, '
        'TNFR1 — имя биологической сущности, а не числовая оценка эффекта. Новая отдельная политика '
        'допускает переменную для целиком связанного понятия. Цифры не удаляются из его значения. '
        'Если это группа с возрастным диапазоном, принимающее значение сохраняет весь диапазон. '
        'Само связывание участника не доказывает применимости научного вывода к другой группе.', '',
        'Чистый числовой литерал остаётся константой. Скрытая ссылка на другое знание не превращается '
        'в свободную переменную. Равенства участников между посылками и заключением, отрицания, '
        'кванторы, модальность, статус действия, время, условия, дозы, единицы и измеренные величины '
        'сохраняются. Копирование параметра протокола требует прежней отдельной источниковой лицензии.', '',
        f"Найдено {len(result['digit_participants'])} употреблений участников с цифрами и "
        f"{len({r['value'] for r in result['digit_participants']})} разных полных значений. "
        'Это не число новых знаний и не число научных ошибок.', '',
        '## Парное сравнение', '',
        '| Политика | Режим | Первичные правила | Новые гипотезы | Неподдержанные шаблоны |',
        '| --- | --- | ---: | ---: | ---: |']
    for policy, modes in result['policies'].items():
        for mode, row in modes.items():
            rules = len(row['rules']) if 'rules' in row else len(modes['graph']['rules'])
            unsupported = str(row['learning']['unsupported_templates']) if 'learning' in row else '—'
            lines.append(f"| {POLICIES[policy]} | {MODES[mode]} | {rules} | {len(row['predictions'])} | {unsupported} |")
    lines += ['', 'Прежнее обучение воспроизведено буквально: совпадают полные реестры отказов, '
        'неподдержанных правил и первично поддержанных правил для всех трёх источников обучающих групп. '
        'Одинаковые нулевые итоги сами по себе такой гарантией не являются.', '',
        'Первичная поддержка считается по независимым семействам исследований, минимум по двум. '
        'Цитируемый результат обзора и несколько частей одного опыта не являются новыми репликациями.', '',
        '## Близкие структуры и барьеры ограничений', '',
        'Дополнительно сгруппированы структуры с одинаковыми предикатами, отрицаниями, видами действий, '
        'связываниями участников и направлением внутренних зависимостей. Только для диагностики '
        'отдельно сравнивается топология без времени и атрибутов. Все полные ограничения каждого '
        'варианта сохранены рядом. Эти группы не используются для вывода и не становятся правилами.', '',
        '| Политика | Режим | Структуры с первичными примерами минимум двух семейств |', '| --- | --- | ---: |']
    for p, modes in result['policies'].items():
        for m, row in modes.items():
            if 'guard_barriers' in row: lines.append(f"| {POLICIES[p]} | {MODES[m]} | {len(row['guard_barriers'])} |")
    lines += ['', '## Значение результата', '',
        'Цифры в именах действительно разрывали часть обобщений, но их корректное связывание '
        'не дало достаточно повторяющихся правил при сохранённых научных ограничениях. '
        'Сокращение числа разрозненных шаблонов нельзя выдавать за успешное научное прогнозирование.', '',
        'Нулевой реестр структур относится только к шаблонам, прошедшим предварительные '
        'ограничения генератора. В режиме зависимостей 244 сопоставления отклонены из-за '
        'числовых заключений без поддержанного оператора. Они не входят в этот структурный '
        'поиск. Ноль не доказывает отсутствия закономерностей во всех научных данных корпуса.', '',
        'Следующий содержательный шаг — разбор предикатов, связываний участников и отклонённых '
        'числовых заключений по полным источникам. Нужно установить, где одинаковая операция '
        'выражена разными словами и где вычислимое качественное следствие отличается от '
        'неизвестного эмпирического числа. Если первичной поддержки действительно недостаточно, '
        'нужны независимые данные. Удаление условий ради совпадения запрещено.', '',
        '## Ограничения и проверки', '',
        'Это диагностический опыт на уже прочитанном корпусе. Будущие результаты и целевая '
        'PMC10000452 не открывались этим CLI; ранее известные исходы от этого не становятся слепыми. '
        'Первичные правила и новые гипотезы имеют одинаковый контракт во всех режимах. '
        'Полезность скрытой семантики и выигрыш видимого DAG оцениваются отдельно.', '',
        f'{count} проверок через Poetry прошли. Модельных и сетевых вызовов нет. '
        'Старые карты, GOLD, исходные прогнозы и неудачная первая тестовая квитанция сохранены. '
        'Живые сервисы не менялись; перезапуск не требуется. Экспертная и визуальная проверки не заявляются.', '',
        f"Запуск: `{result['run_id']}`."]
    details = []
    for p, modes in result['policies'].items():
        for m, row in modes.items():
            for group in row.get('guard_barriers', []):
                title = f"{POLICIES[p]} · {MODES[m]} · {len(group['primary_families'])} семейства · {len(group['variants'])} варианта"
                details.append('<details><summary>' + escape(title) + '</summary><p>Диагностическое сходство; правило не разрешено. '
                    'Машинные поля и исходные термины сохранены.</p><pre>' + escape(json.dumps(group, ensure_ascii=False, indent=2)) + '</pre></details>')
    html = '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    html += '<title>Типизированные участники и структуры карты</title><style>body{font:17px/1.6 system-ui;background:#f5f7fa;color:#182434;margin:0}main{max-width:1120px;margin:auto;padding:32px}table{border-collapse:collapse;width:100%;background:white}th,td{padding:10px;border:1px solid #cad5df;text-align:left}.table{overflow:auto}details{background:white;border:1px solid #cad5df;border-radius:8px;padding:14px;margin:14px 0}summary{cursor:pointer;font-weight:650}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}code{overflow-wrap:anywhere}</style><main>'
    html += render_lines(lines) + '<h2>Полные варианты диагностических структур</h2>' + ''.join(details) + '</main></html>'
    review = Path(args.review).resolve()
    data = {'run_path': str(run), 'source_path': str(source_path), 'run_id': result['run_id'],
        'canonical_blocks': result['canonical_blocks'], 'semantic_statements': result['semantic_statements'],
        'licensed_parts': result['licensed_parts'], 'digit_roles': len(result['digit_participants']), 'tests_passed': count,
        'model_calls': 0, 'graph_advantage_demonstrated': False}
    files = {'report.ru.md': ('\n'.join(lines) + '\n').encode(), 'report.html': html.encode(), 'data.json': FilePredictionStore.encode(data)}
    receipt = {**data, 'files': {n: sha256(b).hexdigest() for n, b in files.items()}, 'tests_path': str(tests_path),
        'tests_sha256': sha256(raw_tests).hexdigest(), 'builder_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'render_helper_sha256': sha256((Path(__file__).parent / 'render_template_barrier_audit.py').read_bytes()).hexdigest()}
    for name, raw in files.items(): write_immutable(review / name, raw)
    write_immutable(review / 'verification.json', FilePredictionStore.encode(receipt))
    print(json.dumps({'report': str(review / 'report.html'), 'tests': count}))


if __name__ == '__main__': main()
