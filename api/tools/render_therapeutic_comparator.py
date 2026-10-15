"""Русский парный отчёт источниковой роли контроля и независимого переноса."""
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


def load_run(path):
    root = Path(path).resolve()
    return root, FilePredictionStore(root.parent).read_seal(root.name)


def main():
    p = argparse.ArgumentParser()
    for name in ('main', 'control', 'evaluation', 'control-evaluation', 'tests', 'review'):
        p.add_argument('--' + name, required=True)
    args = p.parse_args()
    main_root, main = load_run(args.main); control_root, control = load_run(args.control)
    require(main['binding']['implementation'] == control['binding']['implementation'], 'Transfer code differs')
    require(main['version'] == control['version'] == 'family-held-out-operation-transfer-3', 'Transfer version differs')
    def evaluation(root, run, eid):
        result = json.loads((root/'evaluations'/(eid+'.json')).read_bytes())
        require(fingerprint(result) == eid and result['forecast_sha256'] == fingerprint(run), 'Evaluation differs')
        return result
    observed = evaluation(main_root, main, args.evaluation)
    old_observed = evaluation(control_root, control, args.control_evaluation)
    require(not any(f['predictions'] for r in (main, control) for folds in r['modes'].values() for f in folds),
            'Revise report for independent hypotheses')
    reapplications = observed['resubstitution_diagnostic']['candidates']
    require(len(reapplications) == 2 and {c['receiver_id'] for c in reapplications} == {'tros-manifest','atrosimab-manifest'}
            and not old_observed['resubstitution_diagnostic']['candidates'], 'Repair result differs')
    tests = Path(args.tests).read_bytes(); suites = ET.fromstring(tests).findall('testsuite')
    require(suites and all(int(s.attrib.get('failures',0)) == int(s.attrib.get('errors',0)) == 0 for s in suites), 'Tests failed')
    count = sum(int(s.attrib['tests']) for s in suites)
    applicability = json.loads((main_root/'input-applicability.json').read_bytes())
    descriptor = json.loads((main_root/'input-corpus.json').read_bytes())
    forecast_descriptor = json.loads((Path(descriptor['snapshot'])/'input-corpus.json').read_bytes())
    _, forecast = load_run(forecast_descriptor['snapshot'])
    role_proofs = forecast['operation_role_bindings']['proofs']
    repair = [pr for pr in role_proofs if pr['entry']['variant'] == 'explicit_therapeutic_pbs_comparator']
    require(len(repair) == 4 and main['coverage']['licensed_parts'] == 910 and control['coverage']['licensed_parts'] == 906,
            'Repair coverage differs')
    lines = ['# Источниковое исправление контроля PBS', '',
        '**Разрыв семантической разметки устранён. Повторных применений на обучающих данных — 2; '
        'независимых новых прогнозов — 0. Преимущество Карты Знаний пока не доказано.**', '',
        'Всё выполнено на прежних 11 картах и 943 знаниях. Четыре новых аналитических представления '
        'добавляют роль PBS к терапевтическому введению TROS, уменьшению прогрессирования болезни, '
        'потери массы тела и максимального клинического балла. Каждая роль проверена по точной цитате '
        'полного источника. Новых канонических знаний и эмпирических измерений не добавлено.', '',
        'Оригинальные 894 представления сохранены. Семантика прежних 12 источниковых дополнений '
        'сохранилась; их идентификаторы доказательств изменились вместе с хешем расширенной разметки. '
        'Общее число доступных частей выросло с 906 до 910. Карты и исходные тексты не переписаны.', '',
        '## Что изменилось в операторе', '',
        'Относительный результат должен ссылаться на тот же контроль, что и посылка о введении '
        'лечения. Наличие и идентичность контроля проверяются при обучении; принимающий контроль '
        'подставляется в заключение. Неизвестный контроль или другой контроль блокирует использование '
        'этого примера. Обе стороны парного опыта выполнены одной версией кода.', '',
        'Отдельные сравнения TROS с TNFR1−/− мышами сохранены с генетическим контролом. Кумулятивный '
        'индекс не получил новую роль PBS без отдельной прямой цитаты. Незначимость этих сравнений '
        'не превращена в доказательство эквивалентности. Все дозы, фазы, генотипы, сроки и полные '
        'исходные блоки сохраняются в доказательствах.', '',
        '## Парный результат', '',
        '| Проверка | Прежняя разметка | С ролью PBS |', '| --- | ---: | ---: |',
        '| Повторное применение без исключения своего семейства | 0 | 2 |',
        '| Гипотезы при исключении целого семейства: зависимости карты | 0 | 0 |',
        '| Гипотезы при исключении целого семейства: без зависимостей | 0 | 0 |',
        '| Гипотезы при исключении целого семейства: перемешанные зависимости | 0 | 0 |', '',
        'Два повторных применения воспроизводят уже сообщённое уменьшение клинических проявлений '
        'в терапевтических опытах TROS и Atrosimab относительно собственных контролов. Эти исходы '
        'входят в обучение этого диагностического режима. Это не два предсказания, не два независимых '
        'подтверждения и не новые предметные логические выводы.', '',
        'При исключении всей работы TROS либо Atrosimab остаётся только одно независимое '
        'совместимое семейство. Порог поддержки равен двум. Профилактический опыт той же работы '
        'не становится независимой репликацией и не заменяет терапевтическую фазу.', '',
        '## Повтор всего семантического корпуса', '',
        'Основной генератор обработал все 943 знания и 910 частей. Поддержанных первичных правил '
        'и новых прогнозов во всех четырёх режимах по-прежнему ноль. Изменение числа неподдержанных '
        'шаблонов фиксируется отдельно и не считается научным успехом.', '',
        '| Режим обучения | Неподдержанных шаблонов после исправления |', '| --- | ---: |']
    for mode, name in [('graph','Зависимости карты'), ('source_neighborhood_without_dependencies','Соседство без зависимостей'),
                       ('permuted_dependencies','Перемешанные зависимости')]:
        lines.append(f"| {name} | {len(forecast['learning_by_mode'][mode]['unsupported_origin_support'])} |")
    lines += ['', '## Смысл результата и следующий шаг', '',
        'Теперь можно обучать сравнительный паттерн с явно связанными участниками. Его применение '
        'остаётся условной эмпирической гипотезой: общий тип мишени и заболевания не удостоверяет '
        'одинаковый эффект при разных дозах, генотипах, контролах и расписаниях. Причинность, величина '
        'эффекта и будущая статистическая значимость не выводятся.', '',
        'Следующий содержательный шаг — ещё одно независимое совместимое первичное исследование '
        'с полным текстом, чтобы два семейства могли обучать перенос, а третье проверяло его. '
        'Ранее просмотренные результаты пригодны для ретроспективной разработки, но не получают '
        'статус нового слепого контроля. Одновременно сохраняется отдельная проверка выводов по '
        'логике, 24 силлогистическим формам, вычислениям и операциям мышления на всей карте.', '',
        '## Воспроизводимость', '',
        f'{count} проверок прошли через Poetry. Контрольные тесты отклоняют относительный эффект '
        'без контроля и с другим контролом, сохраняют область действия, числа, независимость семейств '
        'и запрет результата во входе принимающего опыта. Положительные примеры независимого переноса '
        'в тестах синтетические и не являются научным подтверждением.', '',
        'Разметка Codex требует экспертной проверки. Результаты ранее читались для разметки '
        'и её источниковой валидации; исключение их из обучения в разбиении не делает опыт слепым. '
        'Сеть и модельные вызовы в CLI запрещены. GOLD, production-карты и сервисы не менялись; '
        'перезапуск не требуется. Визуальная проверка не заявляется.', '',
        f"Основной перенос: `{main['run_id']}`. Контроль: `{control['run_id']}`.", '',
        f"Полный семантический прогон: `{forecast['run_id']}`. Контракт: `{applicability['run_id']}`.", '']
    evidence = {fingerprint(pr['entry']['add_roles'][0]['evidence']): pr['entry']['add_roles'][0]['evidence'] for pr in repair}
    quotes = ''.join('<details><summary>Исходный фрагмент ' + escape(e['unit_id']) + '</summary><p>Координаты Unicode: '
                     + str(e['start']) + '–' + str(e['end']) + '</p><blockquote>' + escape(e['text']) + '</blockquote></details>'
                     for e in evidence.values())
    html = '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Исправление контроля PBS</title><style>body{font:17px/1.6 system-ui;margin:30px auto;max-width:1100px;padding:0 20px;background:#f4f6f9;color:#172435}main{background:white;border:1px solid #ccd7e5;border-radius:12px;padding:28px}.table{overflow:auto}table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #ccd7e5;text-align:left}th{background:#eef3fa}code{overflow-wrap:anywhere}details{padding:16px;border:1px solid #ccd7e5;margin:15px 0}blockquote{white-space:pre-wrap}</style><main>' + render_lines(lines) + '<h2>Происхождение роли контроля</h2>' + quotes + '</main></html>'
    data = {'run_id':main['run_id'], 'control_run_id':control['run_id'], 'evaluation_id':args.evaluation,
            'control_evaluation_id':args.control_evaluation, 'forecast_run_id':forecast['run_id'],
            'applicability_run_id':applicability['run_id'], 'sources':11, 'canonical_blocks':943,
            'parts_before':906, 'parts_after':910, 'repair_role_views':4, 'resubstitution_candidates':2,
            'independent_hypotheses':0, 'new_subject_deductions':0, 'tests':count,
            'graph_advantage_demonstrated':False, 'model_calls':0}
    files = {'report.ru.md':'\n'.join(lines).encode(), 'report.html':html.encode(), 'data.json':FilePredictionStore.encode(data)}
    review = Path(args.review).resolve(); review.mkdir(parents=True,exist_ok=True)
    for name, content in files.items(): write_immutable(review/name,content)
    builders = {str(path):sha256(path.read_bytes()).hexdigest() for path in
                (Path(__file__),Path(__file__).with_name('render_template_barrier_audit.py'))}
    write_immutable(review/'verification.json',FilePredictionStore.encode({'files':{name:sha256(b).hexdigest() for name,b in files.items()},
        'builders':builders,'tests_sha256':sha256(tests).hexdigest(),'main_snapshot':str(main_root),'control_snapshot':str(control_root)}))
    print(json.dumps(data))


if __name__ == '__main__': main()
