"""Русский автономный отчёт: интервальные следствия и научный прогноз учитываются отдельно."""
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

MODES={'graph':'Зависимости карты','same_rules_without_dependencies':'Те же правила без зависимостей',
    'source_neighborhood_without_dependencies':'Соседство без зависимостей','permuted_dependencies':'Перемешанные зависимости'}


def main():
    parser=argparse.ArgumentParser()
    for f in ('run','tests','review'): parser.add_argument('--'+f,required=True)
    args=parser.parse_args(); disable_network(); folder=Path(args.run).resolve()
    data=FilePredictionStore(folder.parent).read_seal(folder.name)
    require(data['version']=='source-bound-interval-knowledge-2','Wrong interval version')
    audit=json.loads((folder/'audit.json').read_bytes()); require(fingerprint(audit)==data['binding']['audit_sha256'],'Interval audit changed')
    tests_path=Path(args.tests).resolve(); tests_raw=tests_path.read_bytes(); suites=ET.fromstring(tests_raw).findall('testsuite')
    require(suites and all(int(s.attrib.get(k,0))==0 for s in suites for k in ('errors','failures','skipped')),'Interval tests failed')
    count=sum(int(s.attrib['tests']) for s in suites)
    require(data['canonical_blocks']==943 and data['licensed_parts']==910 and len(data['interval_consequences'])==2,'Unexpected interval corpus')
    require(all(not r['predictions'] and not r.get('rules',[]) for modes in data['policies'].values() for r in modes.values()),
            'Unexpected nonempty forecast requires its own scientific report')
    fields=sum(len(s['attributes']) for k in data['coverage'] for s in k['interval_fields'])
    parents=sum(any(s['attributes'] for s in k['interval_fields']) for k in data['coverage'])
    lines=['# Интервальные операции и качественные утверждения', '',
        '**Два источниковых интервальных следствия. Новых эмпирических прогнозов — 0; преимущество DAG не установлено.**','',
        f"Использованы все 11 прежних карт, {data['canonical_blocks']} знания и {data['semantic_statements']} семантических "
        f"утверждений. Парное обучение охватывает те же {data['licensed_parts']} допустимых частей без вопроса и тематического фильтра. "
        f"Полный реестр содержит {fields} полей с обозначением интервала в {parents} канонических блоках. "
        'Несколько полей одной оценки не считаются несколькими интервалами или исследованиями.','',
        '## Новые математические следствия','',
        'В PMC5651799 прямо сообщены две пары 95%-ных интервалов начала EAE. '
        'Группы TROS и PBS сравниваются внутри каждого собственного профилактического режима. '
        'Режимы 200 и 150 мкг не смешиваются. Начало болезни определено клиническими симптомами два последовательных дня.','',
        '| Режим | Напечатанный интервал TROS, дни | Напечатанный интервал PBS, дни | Геометрия разности TROS − PBS, дни | Статус теста у автора |',
        '| --- | --- | --- | --- | --- |']
    for p in data['interval_consequences']:
        regimen='200 мкг каждые два дня' if p['native_key'][1]=='K30' else '150 мкг каждые три дня'
        left,right=p['intervals']; difference=p['geometry']['difference']
        status='Задержка статистически обнаружена' if p['reported_detection']=='detected' else 'Задержка статистически не установлена'
        lines.append(f"| {regimen} | [{left['bounds'][0]}; {left['bounds'][1]}] | [{right['bounds'][0]}; {right['bounds'][1]}] "
                     f"| [{difference[0]}; {difference[1]}] | {status} |")
    lines+=['','Правило интервальной арифметики: если x ∈ [a; b] и y ∈ [c; d], то x − y ∈ [a − d; b − c]. '
        'Это точный вывод о множествах напечатанных границ. Он не доказывает, что истинные параметры находятся внутри '
        'этих границ, и не создаёт автоматически проверенный доверительный интервал разности.','',
        'В обоих случаях индивидуальные интервалы перекрываются, а геометрическая разность содержит ноль. '
        'Тем не менее автор сообщает разные результаты теста задержки. Поэтому перекрытие интервалов '
        'не используется как правило «эффекта нет» или «эффект статистически не обнаружен». Статус теста сохранён из источника.','',
        '## Условная гарантия совместного покрытия','',
        'Если каждая из двух корректных процедур имеет частотное покрытие не меньше 95%, то совместное '
        'покрытие не меньше 95% + 95% − 100% = 90%. Независимость не нужна. '
        'Это нижняя граница при неизвестной зависимости, а не 95% совместного покрытия и не вероятность '
        'того, что фиксированный параметр лежит в уже рассчитанном интервале.','',
        'У реальных опубликованных округлённых границ корректность покрытия не проверена. '
        'Нужны действительные процедуры, соответствующие неокруглённые границы и допустимый порядок выбора сравнений. '
        'Поэтому 90% хранится как условное математическое следствие с допущениями; '
        'проверенный 90%-ный интервал эффекта этой статье не приписывается.','',
        'Теоретическое основание: [неравенство Бонферрони в руководстве NIST]'
        '(https://www.itl.nist.gov/div898/handbook/prc/section4/prc463.htm). Формула и проверка границы '
        'реализованы отдельно от научных результатов.','',
        '## Извлечение качественного утверждения','',
        'Положительное утверждение о задержке уже записано автором. Из двух его отображений в аналитическом '
        'слое вынесены пять полей описания интервалов: четыре конца и уровень покрытия. Все числа, полные '
        'родительские блоки и исходные фрагменты сохранены в доказательстве. Участники, дозировка в условиях, '
        'время, отрицания и модальность не изменены.','',
        'Необнаруженная задержка при 150 мкг не стала положительным эффектом и не стала доказанным нулевым '
        'эффектом. Её интервальные поля не удалены для прогнозирования будущей статистической обнаруженности.','',
        '## Повтор полного обучения','',
        '| Политика | Режим | Первичные правила | Новые гипотезы | Отказы из-за числового заключения |',
        '| --- | --- | ---: | ---: | ---: |']
    for policy,modes in data['policies'].items():
        label='До проекции' if policy=='before_interval_summary' else 'Источниковая проекция ДИ'
        for mode,row in modes.items():
            rules=len(row['rules']) if 'rules' in row else len(modes['graph']['rules'])
            failures=str(row['learning']['rejected'].get('unmodelled_numeric_conclusion',0)) if 'learning' in row else '—'
            lines.append(f"| {label} | {MODES[mode]} | {rules} | {len(row['predictions'])} | {failures} |")
    lines+=['','Прежнее обучение воспроизведено по полным реестрам правил и отказов. Уменьшение '
        'числовых отказов с 244 до 236 в режиме карты не дало первично поддержанных новых правил. '
        'Восемь сопоставлений не считаются восемью новыми фактами.','',
        '## Что это даёт Карте Знаний','',
        'Добавлен проверяемый вычислительный оператор: скрытая семантика связывает числовые границы с '
        'группами, оценкой и режимом опыта; правило сохраняет происхождение и допущения. Это отдельный '
        'канал вывода, без эмпирического обучения и без категорических силлогизмов. Необходимы обе '
        'пары границ; их удаление делает вычисление неопределённым.','',
        'Геометрия получается и на тех же семантических фактах без видимых стрелок. '
        'Улучшение аудита и два математических следствия не удостоверяют преимущество DAG в прогнозировании. '
        'Для основной цели ещё нужны новые допустимые эмпирические комбинации, независимая проверка и сильные одинаковые базы.','',
        '## Следующий содержательный шаг','',
        'Оставшиеся заключения разделяются на условия опыта, вычислимые следствия и неизвестные '
        'эмпирические параметры. Для каждого требуется собственный оператор. Согласование предикатов '
        'и связываний участников должно опираться на определения измерений и исходные методы; '
        'нельзя отождествлять любые «улучшение» и «уменьшение» или объединять разные исходы ради поддержки.','',
        '## Проверка','',
        f'{count} теста через Poetry прошли: точная арифметика, пределы ввода, перебор совместных событий, '
        'источники, неизменность родителей, атомарность и повторный импорт. '
        'Первая неудачная тестовая квитанция сохранена: исправлено ожидание служебной оговорки в синтетическом примере. '
        'Модельных вызовов нет. CLI работает без сети; отдельное чтение NIST было проверкой математического основания, '
        'а не открытием будущего научного исхода. Это опыт на ранее прочитанном материале. '
        'Экспертная и визуальная проверки не заявляются; сервисы, GOLD и production-карты не изменены.','',
        f"Запуск: `{data['run_id']}`."]
    details=''.join('<details><summary>Источник и полный вывод: '+escape(p['native_key'][1])+'</summary><pre>'
        +escape(json.dumps(p,ensure_ascii=False,indent=2))+'</pre></details>' for p in data['interval_consequences'])
    html='<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    html+='<title>Интервальные операции Карты Знаний</title><style>body{font:17px/1.6 system-ui;background:#f5f7fa;color:#182434;margin:0}main{max-width:1160px;margin:auto;padding:30px}table{border-collapse:collapse;background:white;width:100%}td,th{border:1px solid #cad5df;padding:10px;text-align:left}.table{overflow:auto}details{background:white;padding:16px;margin:16px 0;border:1px solid #cad5df;border-radius:8px}summary{cursor:pointer;font-weight:650}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}code{overflow-wrap:anywhere}</style><main>'
    html+=render_lines(lines)+'<p><a href="https://www.itl.nist.gov/div898/handbook/prc/section4/prc463.htm">Математическое основание — руководство NIST</a></p>'
    html+='<h2>Полные исходные блоки и координаты фрагментов</h2>'+details+'</main></html>'
    descriptor=json.loads((folder/'input-corpus.json').read_bytes())
    compact={'run_path':str(folder),'baseline_path':descriptor['baseline'],'tests_passed':count,'interval_fields':fields,
        'interval_parents':parents,'run_id':data['run_id'],'model_calls':0,'new_forecasts':0}
    files={'report.ru.md':('\n'.join(lines)+'\n').encode(),'report.html':html.encode(),'data.json':FilePredictionStore.encode(compact)}
    receipt={**compact,'files':{n:sha256(raw).hexdigest() for n,raw in files.items()},'tests_path':str(tests_path),
        'tests_sha256':sha256(tests_raw).hexdigest(),'builder_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'helper_sha256':sha256((Path(__file__).parent/'render_template_barrier_audit.py').read_bytes()).hexdigest()}
    review=Path(args.review).resolve()
    for name,raw in files.items(): write_immutable(review/name,raw)
    write_immutable(review/'verification.json',FilePredictionStore.encode(receipt)); print(json.dumps(compact))


if __name__=='__main__': main()
