"""Русский автономный отчёт об источниковых абстракциях и общих структурах."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from domain.article_maps import fingerprint,require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.render_template_barrier_audit import render_lines
from tools.run_free_prediction import disable_network

MODES={'graph':'Зависимости карты','same_rules_without_dependencies':'Те же правила без зависимостей',
    'source_neighborhood_without_dependencies':'Соседство без зависимостей','permuted_dependencies':'Перемешанные зависимости'}
CASES={'tros-prophylactic':'TROS до проявления EAE','tros-manifest':'TROS при проявленной EAE','atrosimab-manifest':'Atrosimab при проявленной EAE'}


def main():
    parser=argparse.ArgumentParser()
    for f in ('run','review'):parser.add_argument('--'+f,required=True)
    parser.add_argument('--tests',action='append',required=True)
    args=parser.parse_args();disable_network();folder=Path(args.run).resolve();result=FilePredictionStore(folder.parent).read_seal(folder.name)
    require(result['version']=='source-bound-measurement-orientation-1','Wrong orientation version')
    audit=json.loads((folder/'audit.json').read_bytes());require(fingerprint(audit)==result['binding']['audit_sha256'],'Orientation audit changed')
    require(result['canonical_blocks']==943 and result['input_parts']==910 and result['oriented_parts']==915
            and len(result['orientation_proofs'])==3,'Unexpected orientation corpus')
    tests,receipts=set(),[]
    for path in args.tests:
        p=Path(path).resolve();raw=p.read_bytes();suites=ET.fromstring(raw).findall('testsuite')
        require(suites and all(int(s.attrib.get(k,0))==0 for s in suites for k in ('errors','failures','skipped')),'Orientation tests failed')
        tests.update((t.attrib['classname'],t.attrib['name']) for s in suites for t in s.findall('testcase'))
        receipts.append({'path':str(p),'sha256':sha256(raw).hexdigest(),'tests':sum(int(s.attrib['tests'])for s in suites)})
    require(all(not r['predictions'] and not r.get('rules',[]) for modes in result['policies'].values() for r in modes.values()),
            'Nonempty forecasts need separate scientific evaluation')
    count=len(tests)
    lines=['# Ориентация измерений и общий клинический паттерн','',
        '**Найдена общая структурная схема в двух первичных семействах. Новых эмпирических прогнозов — 0.**','',
        'Обработан прежний полный корпус: 11 карт, 943 знания и 1897 семантических утверждений. '
        '910 прежних аналитических частей сохранены; отдельно добавлены пять абстракций для трёх проверенных клинических цепочек. '
        'Остальные знания не получили вымышленных ориентаций измерения. Это развитие общего генератора, '
        'но источниковое лицензирование ориентаций пока охватывает лишь эти три цепочки.','',
        '## Как получено обобщение','',
        'По определениям шкал больший балл соответствует более тяжёлому клиническому состоянию. '
        'Явно сообщённое улучшение motor disease и уменьшение клинического прогрессирования сопоставлены '
        'на уровне опубликованного направления клинического бремени в своём опыте. Это не глобальная '
        'замена слова «улучшение» словом «уменьшение»: у шкалы, где больший балл означает лучшее состояние, '
        'ориентация была бы противоположной. Необнаруженность не даёт нулевую величину или положительный эффект.','',
        'Источник связывает собственную измерительную процедуру с исходом. Обобщённое свойство '
        'использовано и в аналитическом представлении измерения, и в представлении результата. '
        'Поэтому роль измеряемого исхода может быть одной переменной двух посылок и заключения. '
        'Все исходные инструменты, участники, дозы, время, условия, оговорки и полные родители сохранены.','',
        '| Цепочка | Определение шкалы | Сохранённое ограничение |', '| --- | --- | --- |']
    for p in result['orientation_proofs']:
        anchors=p['entry']['anchors']; scale='; '.join(a['value']+' — '+a['meaning_ru'] for a in anchors)
        lines.append('| '+CASES[p['case_id']]+' | '+scale+' | '+p['entry']['scale_caveat_ru']+' |')
    lines+=['','**Численные шкалы и точные факты не объявлены эквивалентными.** '
        'Одно качественное направление не разрешает переносить величину эффекта, единицы, средние или '
        'временную устойчивость. Даже строго возрастающая перекодировка сохраняет порядок индивидуальных '
        'состояний, но может изменить порядок средних двух групп. Эта ошибка проверяется отдельным контрпримером.','',
        'У TROS сохранено расхождение: определение допускает 6 (смерть), а подписи рисунков указывают 0–5. '
        'Оно не исправлено автоматически. У Atrosimab половинные шаги и верхняя категория 5. '
        'Общая ориентация не устраняет эти различия.','',
        '## Обнаруженная структура','',
        'Ввести средство данной группе и измерить клинический исход той же группы → '
        'источник сообщает снижение клинического бремени относительно своего контроля. '
        'Это наблюдаемый статистический паттерн, а не доказательство, что любое введение средства обязательно улучшит исход.','',
        'Генератор нашёл два диагностических представления: в первом обобщённый исход остаётся '
        'константой, во втором он связан одной переменной с измерением. В первом представлении '
        'встречается и измерение массы тела при заключении о клиническом бремени. Авторская группа '
        'целых родителей не доказывает достаточность именно этой выбранной пары частей. '
        'Поэтому первый вариант не допущен к переносу без отдельного источникового отношения между исходами. '
        'Для следующего оператора выбран только один вариант с явно связанным измеряемым свойством. '
        'Это не два медицинских закона и не два подтверждения будущего прогноза.','',
        'TROS до и после проявления болезни относится к одному первичному семейству; '
        'Atrosimab — к другому. Отдельность исследовательских коллективов и участников не удостоверяется. '
        'Повторное описание одного измерения в двух режимах объединено без дублирования.','',
        '## Парный полный прогон','',
        '| Политика | Режим | Структуры минимум двух первичных семейств | Первичные правила | Новые гипотезы |',
        '| --- | --- | ---: | ---: | ---: |']
    for policy,modes in result['policies'].items():
        label='До ориентации' if policy=='before_measurement_orientation' else 'Источниковая ориентация'
        for mode,row in modes.items():
            structures=str(len(row['guard_barriers'])) if 'guard_barriers' in row else '—'
            rules=len(row.get('rules',modes['graph']['rules']))
            lines.append(f"| {label} | {MODES[mode]} | {structures} | {rules} | {len(row['predictions'])} |")
    lines+=['','Прежнее обучение воспроизведено по полным спискам правил и отказов. '
        'Два общих представления в режиме карты и одно в соседстве источника — разница диагностических '
        'каталогов, а не преимущество точности: оконная база не перебирает все сочетания и не является '
        'исчерпывающей сильной базой. Научное преимущество DAG по-прежнему не установлено.','',
        '## Почему это ещё не прогноз','',
        'Для поиска структур отдельно сравнивалась форма без ограничений. При обучении правила '
        'все ограничения остаются полными: разные препараты и контролы, генотипы и пол, дозы с разными '
        'размерностями, режимы, способы индукции, часы опыта и шкалы. Отдельный источник времени '
        '«отчёт 2021 года» не превращён в биологическое окно. Простое равенство слов недостаточно '
        'для их переноса, а удаление условий не разрешено.','',
        'Следующий оператор должен связывать протокол, измерение и временной контекст в типизированные '
        'параметры; перенос проверяется как условная эмпирическая гипотеза со всеми значениями и '
        'допущениями. Ни класс исхода, ни две публикации сами по себе не дают универсального закона. '
        'После получения допустимого нового кандидата нужен отдельный совместимый контроль и одинаковые сильные базы.','',
        '## Проверка','',
        f'{count} различных проверок прошли через Poetry. Квитанции повторного запуска частично перекрываются '
        'и не суммируются как разные тесты. Проверены направления, неизвестность, источник, конфликт шкал, '
        'сохранность всех чисел и контекстов и контрпример для средних. '
        'Разметка выполнена Codex на уже прочитанных источниках и требует экспертной проверки. '
        'Модельных и сетевых вызовов нет; GOLD, текущие карты UI и сервисы не изменены. '
        'Два начальных CLI завершились до публикации: исправлено точное Unicode-тире цитаты и затем использована '
        'успешно подготовленная ревизия. Визуальная и научная экспертиза не заявляются.','',
        f"Запуск: `{result['run_id']}`."]
    details=''.join('<details><summary>Исходные определения и обобщение: '+escape(CASES[p['case_id']])+'</summary><pre>'
        +escape(json.dumps(p,ensure_ascii=False,indent=2))+'</pre></details>' for p in result['orientation_proofs'])
    for r in result['policies']['source_bound_measurement_orientation']['graph']['guard_barriers']:
        details+='<details><summary>Общая структура и все различающиеся условия</summary><pre>'+escape(json.dumps(r,ensure_ascii=False,indent=2))+'</pre></details>'
    html='<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    html+='<title>Ориентация измерений и клинический паттерн</title><style>body{font:17px/1.6 system-ui;background:#f5f7fa;color:#182434;margin:0}main{max-width:1160px;margin:auto;padding:30px}table{border-collapse:collapse;background:white;width:100%}th,td{border:1px solid #cad5df;padding:10px;text-align:left}.table{overflow:auto}details{background:white;border:1px solid #cad5df;padding:16px;margin:16px 0;border-radius:8px}summary{cursor:pointer;font-weight:650}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}code{overflow-wrap:anywhere}</style><main>'
    html+=render_lines(lines)+'<h2>Исходные фрагменты, родители и полные условия</h2>'+details+'</main></html>'
    descriptor=json.loads((folder/'input-corpus.json').read_bytes())
    data={'run_path':str(folder),'previous_path':descriptor['previous'],'applicability_path':descriptor['applicability'],
        'run_id':result['run_id'],'tests_unique':count,'model_calls':0,'new_empirical_forecasts':0}
    files={'report.ru.md':('\n'.join(lines)+'\n').encode(),'report.html':html.encode(),'data.json':FilePredictionStore.encode(data)}
    receipt={**data,'files':{f:sha256(b).hexdigest()for f,b in files.items()},'tests':receipts,
        'builder_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'helper_sha256':sha256((Path(__file__).parent/'render_template_barrier_audit.py').read_bytes()).hexdigest()}
    review=Path(args.review).resolve()
    for f,b in files.items():write_immutable(review/f,b)
    write_immutable(review/'verification.json',FilePredictionStore.encode(receipt));print(json.dumps(data))


if __name__=='__main__':main()
