"""Русский автономный отчёт контракта, отдельно от научных прогнозов."""
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

NAMES = {'tros-prophylactic': 'TROS: профилактика', 'tros-manifest': 'TROS: проявленная болезнь',
         'atrosimab-manifest': 'Atrosimab: проявленная болезнь'}


def main():
    p = argparse.ArgumentParser()
    for name in ('run', 'tests', 'review'): p.add_argument('--' + name, required=True)
    a = p.parse_args(); root = Path(a.run).resolve()
    r = FilePredictionStore(root.parent).read_seal(root.name)
    prior = json.loads((root / 'input-predictions.json').read_bytes())
    require(fingerprint(prior) == r['binding']['input_sha256'], 'Input forecast differs')
    require(r['canonical_blocks'] == 943 and r['licensed_parts'] == 906 and len(r['binding']['map_hashes']) == 11, 'Corpus differs')
    supported = [s for s in r['schemata'] if s['minimum_primary_support']]
    require(len(supported) == 1 and supported[0]['case_ids'] == ['atrosimab-manifest', 'tros-manifest'], 'Schema differs')
    require(r['new_predictions'] == 0 and all(not p for p in prior['predictions'].values()), 'Revise report for nonzero forecast')
    tests = Path(a.tests).read_bytes(); suites = ET.fromstring(tests).findall('testsuite')
    require(suites and all(int(s.attrib.get('failures', 0)) == int(s.attrib.get('errors', 0)) == 0 for s in suites), 'Tests failed')
    count = sum(int(s.attrib['tests']) for s in suites)
    lines = ['# Условия применения общего оператора', '',
        '**Одна кандидатная схема имеет свидетельства двух терапевтических опытов. Новых научных прогнозов — 0; преимущество карты не доказано.**', '',
        'Проверен прежний запечатанный корпус: 11 карт, 943 знания, 906 доступных аналитических частей. '
        'Три источниковых контракта относятся к двум первичным работам. '
        'Остальные части перечислены без такого контракта; полнота предметного разбора корпуса не заявляется. '
        'Генератор не изменён, его результат переиспользован после проверки входов и версий.', '',
        '## Фаза болезни задаёт границу', '',
        'Профилактический и терапевтический опыты TROS разделены. Для лечения проявленной болезни '
        'выбрана самостоятельная цепочка TROS: введение K48, измерение K9, результат K49. '
        'Atrosimab представлен введением K21, клинической частью K20 и клиническим исходом K47.', '',
        '| Сравнение | Совпавших осей | Отличие обязательных осей | Совместимость формы |',
        '| --- | ---: | --- | --- |']
    for c in r['comparisons']:
        require(not c['different'] or c['different'] == ['phase'], 'Unexpected comparison needs explanation')
        lines.append(f"| {NAMES[c['left']]} / {NAMES[c['right']]} | {len(c['matched'])} | {'Фаза болезни' if c['different'] else 'Нет'} | {'Да' if c['applicable'] else 'Нет'} |")
    lines += ['', 'Семь осей: мышь, MOG-индуцированная EAE, человеческая мишень TNFR1, '
        'селективное подавление TNFR1, внутрибрюшинное введение, фаза болезни и клиническая оценка EAE. '
        'Каждое значение имеет точную цитату, Unicode-координаты, хеш и полное источниковое основание. '
        'Неизвестность блокирует сопоставление даже при двух неизвестных значениях. '
        'Разметка подготовлена Codex и требует экспертной проверки.', '',
        '## Кандидатная схема', '',
        '**Селективное подавление человеческого TNFR1 в мышиной MOG-EAE после проявления болезни '
        '+ клиническое измерение → сообщённое уменьшение клинических проявлений относительно контроля.**', '',
        'Это схема наблюдений двух заявленных первичных экспериментальных семейств. '
        'Несколько частей одного опыта не увеличивают поддержку; независимость лабораторий не утверждается. '
        'Схема не включена в выдачу научных прогнозов и не признана универсальным законом или доказательством причинности.', '',
        'Уменьшение прогрессирования TROS и улучшение моторных симптомов Atrosimab сопоставлены по '
        'конкретным цитатам как меньшее клиническое бремя. Исходные предикаты и показатели сохранены. '
        'Универсальное тождество «улучшение = уменьшение» не вводится; размеры эффектов и значимости не объединяются.', '',
        '## Различия сохранены', '',
        '| Условие | Терапевтический TROS | Atrosimab |',
        '| --- | --- | --- |',
        '| Рецепторная модель | Человеческий TNFR1 на фоне отсутствующего мышиного TNFR1 | Человеческие внеклеточные и мышиные трансмембранные/внутриклеточные домены |',
        '| Группа | Самцы | Самки |',
        '| Препарат | Нанотельная конструкция TROS | Моновалентная конструкция Atrosimab |',
        '| Доза | 500 мкг на мышь | 30 или 60 мг/кг |',
        '| Расписание | Дни 8, 12 и 16 после иммунизации | Дни 1, 4, 8 и 12 проявленной болезни |',
        '| Контроль | PBS | Контрольная конструкция FcΔab |',
        '| Шкала | Методы 0–6; подпись рисунка 0–5 | 0–5 с отдельными градациями |', '',
        'Все точные условия и числа остаются в полных родителях и исходных frames. '
        'Совместимость общей формы не делает протоколы эквивалентными и не разрешает перенос '
        'дозы, срока, величины эффекта, значимости или вывода на человека. Расхождение шкалы TROS не исправлено.', '',
        '## Что ещё требуется', '',
        'Следующий этап — применение схемы к новым совместимым комбинациям посылок: '
        'полная проверка контекста и известных заключений, фиксация условных гипотез с перечисленными отличиями, '
        'затем оценка на заранее выбранном не использованном контроле. '
        'Сравнение с плоской семантической базой и перемешанными зависимостями должно иметь одинаковый бюджет. '
        'Профилактика, другой рецептор, другая модель или неизвестная фаза не получают автоматического допуска.', '',
        'В прежнем генераторе все четыре режима по-прежнему дали ноль новых прогнозов. '
        'Результат этой проверки — контракт области применения. '
        'Он потенциально исполним над плоскими структурированными записями, поэтому преимущество DAG не доказано.', '',
        '## Воспроизводимость', '',
        f'{count} тестов Poetry прошли: происхождение, фазы, неизвестные оси, измерение другой популяции, '
        'отрицания и модальность, учёт семейств, сохранность родителей, неизменяемые запуски и отказ без публикации. '
        'CLI запрещает сеть и модельные вызовы. Это разработка на уже известных источниках; '
        'экспертная и визуальная проверки не заявляются.', '',
        'Сервисы, production-карты и GOLD не менялись; перезапуск не требуется. Цель остаётся недостигнутой.', '',
        f"Запуск контракта: `{r['run_id']}`. Исходный прогноз: `{r['input_run_id']}`.", '']
    quotes = []
    for c in r['cases']:
        evidence = {fingerprint(e): e for es in c['source_annotation']['feature_evidence'].values() for e in es}
        evidence.update({fingerprint(e): e for e in c['source_annotation']['direction_evidence']})
        quotes.append('<details><summary>' + escape(NAMES[c['case_id']]) + ' — исходные цитаты</summary>' + ''.join(
            '<p><code>' + escape(e['unit_id']) + ': ' + str(e['start']) + '–' + str(e['end']) + '</code></p><blockquote>' + escape(e['text']) + '</blockquote>'
            for e in evidence.values()) + '</details>')
    md = '\n'.join(lines)
    html = '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Условия применения оператора</title><style>body{font:17px/1.6 system-ui;margin:30px auto;max-width:1150px;padding:0 20px;background:#f4f6f9;color:#172435}main{background:white;border:1px solid #ccd7e5;border-radius:12px;padding:28px}h1{font-size:28px}h2{margin-top:32px}.table{overflow:auto}table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #ccd7e5;text-align:left}th{background:#eef3fa}code{overflow-wrap:anywhere}details{border:1px solid #ccd7e5;padding:14px;margin:16px 0}blockquote{white-space:pre-wrap}</style><main>' + render_lines(lines) + '<h2>Происхождение признаков</h2>' + ''.join(quotes) + '</main></html>'
    data = {'run_id': r['run_id'], 'input_run_id': r['input_run_id'], 'sources': 11, 'knowledge': 943, 'parts': 906,
            'cases': len(r['cases']), 'supported_schemata': len(supported), 'coverage': r['coverage'],
            'tests': count, 'new_predictions': 0, 'graph_advantage_demonstrated': False, 'model_calls': 0}
    files = {'report.ru.md': md.encode(), 'report.html': html.encode(), 'data.json': FilePredictionStore.encode(data)}
    folder = Path(a.review).resolve(); folder.mkdir(parents=True, exist_ok=True)
    for name, content in files.items(): write_immutable(folder / name, content)
    builders = {str(p): sha256(p.read_bytes()).hexdigest() for p in [Path(__file__), Path(__file__).with_name('render_template_barrier_audit.py')]}
    write_immutable(folder / 'verification.json', FilePredictionStore.encode({'files': {n: sha256(v).hexdigest() for n, v in files.items()},
        'builders': builders, 'tests_sha256': sha256(tests).hexdigest(), 'run_id': r['run_id'], 'new_predictions': 0, 'graph_advantage_demonstrated': False}))
    print(json.dumps(data))


if __name__ == '__main__': main()
