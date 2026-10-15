"""Русский отчёт отделяет диагностику переносов от логических выводов."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from domain.article_maps import fingerprint, require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.render_template_barrier_audit import render_lines

NAMES = {'graph': 'Совместные предпосылки карты', 'without_dependencies': 'Без зависимостей',
         'permuted_dependencies': 'Перемешанные зависимости'}
CASES = {'tros-prophylactic': 'TROS: профилактика', 'tros-manifest': 'TROS: проявленная болезнь',
         'atrosimab-manifest': 'Atrosimab: проявленная болезнь'}


def main():
    p = argparse.ArgumentParser()
    for name in ('run', 'evaluation', 'tests', 'review'):
        p.add_argument('--' + name, required=True)
    args = p.parse_args(); root = Path(args.run).resolve()
    r = FilePredictionStore(root.parent).read_seal(root.name)
    evaluation = json.loads((root / 'evaluations' / (args.evaluation + '.json')).read_bytes())
    require(fingerprint(evaluation) == args.evaluation and evaluation['forecast_sha256'] == fingerprint(r), 'Evaluation differs')
    prior = json.loads((root / 'input-applicability.json').read_bytes())
    require(fingerprint(prior) == r['binding']['input_sha256'], 'Applicability input differs')
    tests = Path(args.tests).read_bytes(); suites = ET.fromstring(tests).findall('testsuite')
    require(suites and all(int(s.attrib.get('failures', 0)) == int(s.attrib.get('errors', 0)) == 0 for s in suites), 'Tests failed')
    count = sum(int(s.attrib['tests']) for s in suites)
    totals = {mode: sum(len(f['predictions']) for f in folds) for mode, folds in r['modes'].items()}
    require(not any(totals.values()) and not evaluation['resubstitution_diagnostic']['candidates'],
            'Revise report for nonzero candidates')
    lines = ['# Перенос с исключением целого исследования', '',
        '**Новых прогнозов — 0. Новых предметных логических выводов этот оператор не формирует. '
        'Преимущество Карты Знаний пока не установлено.**', '',
        'Добавлена отдельная процедура обучения по источниковым операциям. При проверке принимающего '
        'опыта все записи его экспериментального семейства исключаются до просмотра заключений. '
        'Отдельный вход принимающего опыта содержит только действия, измерения, участников и условия. '
        'Он не содержит направления результата, ключа заключения или доказательства результата. '
        'Обучение в каждом разбиении исключает все заключения принимающего семейства до обращения к ним. '
        'Оценщик открывает их после неизменяемой фиксации прогноза.', '',
        '## Материал и охват', '',
        f"Сохранены {r['coverage']['sources']} карт, {r['coverage']['canonical_blocks']} канонических знаний и "
        f"{r['coverage']['licensed_parts']} доступных аналитических частей. Три явно размеченных контракта "
        'относятся к двум первичным работам. Остальные 898 частей перечислены в покрытии и не получили '
        'выдуманных контрактов. Проверка относится к этому семейству операций; прогнозирование по всей '
        'карте ещё не достигнуто.', '',
        'Разметка и подбор этих опытов подготовлены Codex на уже прочитанных результатах. Это '
        'ретроспективная инженерная диагностика. Источниковый адаптер читает известные результаты для '
        'проверки происхождения разметки. Разделение входов обучения и оценщика не превращает '
        'её в слепой будущий контроль.', '',
        '## Проверка по независимым семействам', '',
        '| Принимающий опыт | Применимых правил с зависимостями | Новых гипотез |',
        '| --- | ---: | ---: |']
    lines += [f"| {CASES[f['receiver_id']]} | {len(f['rules'])} | {len(f['predictions'])} |"
              for f in r['modes']['graph']]
    lines += ['', '| Режим | Новых гипотез | Оценённых совпадений |', '| --- | ---: | ---: |']
    lines += [f"| {NAMES[mode]} | {total} | {len(evaluation['modes'][mode])} |" for mode, total in totals.items()]
    lines += ['', 'При исключении одной из двух первичных работ остаётся только одно независимое '
        'семейство. Оно не удовлетворяет принятому минимуму двух. Профилактический опыт TROS не '
        'превращается в третье независимое исследование и не смешивается с лечением проявленной болезни.', '',
        '## Дополнительный разрыв в семантике', '',
        'Прежний контракт нашёл одну общую терапевтическую форму по семи признакам. Новый оператор '
        'дополнительно сохраняет связи равенства участников и названия их ролей в обеих посылках. '
        'У Atrosimab и профилактического TROS роль контроля сравнения присутствует в блоке введения. '
        'У терапевтического TROS в K48 она отсутствует, хотя исходная подпись рисунка 4 прямо упоминает PBS.', '',
        'Поэтому даже диагностическое повторное применение на всём обучении сейчас даёт ноль '
        'кандидатов. Это не доказательство различия биологических механизмов. Это установленное '
        'различие машинных представлений. Добавлять роль следует по источнику с отдельным доказательством; '
        'удалять роль сравнения из остальных опытов ради совпадения нельзя.', '',
        '## Что считается результатом', '',
        'С учётом уточнённой цели учитываются отдельно: логические выводы с проверкой следования '
        'из посылок; вычислительные выводы с явными допущениями; индуктивные и аналогические гипотезы '
        'с независимой эмпирической оценкой. Паттерн описывает структуру, операция мышления — '
        'преобразование знаний, оператор — исполняемую процедуру с условиями применения. '
        'Эмпирический паттерн этого прогона не является силлогизмом или доказанным законом.', '',
        'Совпадение семи классов не объявляет одинаковыми генотипы, дозы, контролы и расписания. '
        'Полные исходные фреймы сохраняются. Возможное применение выдаёт только условную гипотезу, '
        'с обязательствами проверить эти различия. Число эффекта, значимость и причинность не выводятся.', '',
        'Сравнение без зависимостей использует те же заранее размеченные тройки. Это ограничение '
        'контроля: его состав также подготовлен с учётом авторских групп. Здесь оно не создаёт '
        'преимущества, потому что все режимы пусты. Для общего сравнительного опыта требуется '
        'независимый поиск посылок по всему семантическому корпусу.', '',
        '## Следующая содержательная проверка', '',
        'Сначала восполнить источниково подтверждённую роль PBS в терапевтическом TROS и повторить '
        'тот же состав корпуса. Затем нужны ещё независимые совместимые экспериментальные данные: '
        'два семейства для обучения и отдельное третье для проверки. Два результата одной работы '
        'не заменяют независимость. Уже прочитанные результаты используются только для ретроспективной '
        'разработки; новый контроль фиксируется с журналом доступов.', '',
        'Параллельно логические, силлогистические и вычислительные выводы должны проверяться на '
        'полной карте с сохранением контекста и отдельным графом доказательства. Их полезность '
        'не засчитывается как подтверждение эмпирического прогноза. Увеличение числа тестов или '
        'разметок само по себе не доказывает преимущество карты.', '',
        '## Воспроизводимость', '',
        f'{count} проверок прошли через Poetry. Проверены исключение всей семьи до обращения к '
        'исходу, неизвестные условия, роли участников, сохранность чисел и контекста, запрет '
        'результата во входе, раздельная оценка и сохранность прогноза при ошибке оценщика. '
        'Положительные примеры трёх семейств в тестах синтетические и не являются научным подтверждением.', '',
        'В CLI сеть и модельные вызовы запрещены. GOLD, production-карты и сервисы не менялись; '
        'перезапуск не требуется. Экспертная и визуальная проверки не заявляются.', '',
        f"Запуск: `{r['run_id']}`. Оценка: `{args.evaluation}`.", '']
    html = '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Перенос с исключением исследования</title><style>body{font:17px/1.6 system-ui;margin:30px auto;max-width:1100px;padding:0 20px;background:#f4f6f9;color:#172435}main{background:white;border:1px solid #ccd7e5;border-radius:12px;padding:28px}h1{font-size:28px}.table{overflow:auto}table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #ccd7e5;text-align:left}th{background:#eef3fa}code{overflow-wrap:anywhere}</style><main>' + render_lines(lines) + '</main></html>'
    data = {'run_id': r['run_id'], 'evaluation_id': args.evaluation, 'tests': count, 'coverage': r['coverage'],
            'hypotheses': totals, 'resubstitution_candidates': 0, 'new_subject_deductions': 0,
            'graph_advantage_demonstrated': False, 'model_calls': 0}
    files = {'report.ru.md': '\n'.join(lines).encode(), 'report.html': html.encode(), 'data.json': FilePredictionStore.encode(data)}
    review = Path(args.review).resolve(); review.mkdir(parents=True, exist_ok=True)
    for name, content in files.items(): write_immutable(review / name, content)
    builders = {str(path): sha256(path.read_bytes()).hexdigest() for path in
                (Path(__file__), Path(__file__).with_name('render_template_barrier_audit.py'))}
    write_immutable(review / 'verification.json', FilePredictionStore.encode({'run_id': r['run_id'],
        'evaluation_id': args.evaluation, 'tests_sha256': sha256(tests).hexdigest(), 'builders': builders,
        'files': {name: sha256(content).hexdigest() for name, content in files.items()}}))
    print(json.dumps(data))


if __name__ == '__main__': main()
