"""Русский отчёт о временных ограничениях и календарных, а не клинических, выводах."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from domain.article_maps import fingerprint,require
from domain.treatment_episode_context import VERSION
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.render_template_barrier_audit import render_lines
from tools.run_free_prediction import disable_network

LABELS={'tros-prophylactic':'TROS до проявления болезни','tros-manifest':'TROS при проявленной болезни',
    'atrosimab-manifest':'Atrosimab при проявленной болезни'}
ANCHORS={'post_immunization':'После иммунизации','manifest_disease_day':'Дни проявленной болезни'}


def main():
    p=argparse.ArgumentParser()
    for name in ('run','review','tests'):p.add_argument('--'+name,required=True)
    args=p.parse_args();disable_network();folder=Path(args.run).resolve()
    result=FilePredictionStore(folder.parent).read_seal(folder.name)
    require(result is not None and result['version']==VERSION,'Missing episode seal')
    for f,d in result['binding']['implementation'].items():require(sha256((folder/'implementation'/f).read_bytes()).hexdigest()==d,'Episode implementation differs')
    require(fingerprint(json.loads((folder/'audit.json').read_bytes()))==result['binding']['audit_sha256'],'Episode audit differs')
    require(result['canonical_blocks']==943 and result['semantic_statements']==1897 and result['input_parts']==915
        and len(result['episodes'])==3 and len(result['calendar_consequences'])==4
        and result['new_empirical_forecasts']==0 and not result['scientific_success'],'Unexpected scientific assertion')
    tests=Path(args.tests).resolve();raw=tests.read_bytes();suites=ET.fromstring(raw).findall('testsuite')
    require(suites and all(int(s.attrib.get(k,0))==0 for s in suites for k in ('errors','failures','skipped')),'Episode tests failed')
    names={(t.attrib['classname'],t.attrib['name'])for s in suites for t in s.findall('testcase')};count=len(names)
    lines=['# Временные эпизоды: календарь не является длительностью эффекта','',
        '**Сохранены четыре календарных следствия и два источниковых расхождения. Новых эмпирических прогнозов — 0.**','',
        'Прежний корпус из 11 карт, 943 знаний, 1897 утверждений и 915 аналитических частей не изменён. '
        'Адресно проверены три прежние клинические цепочки и один отдельный тканевой курс. '
        'Это уточнение входов общего генератора, а не заявление о полной временной разметке всех знаний.','',
        '## Разделённые часы и эпизоды','',
        '| Опыт | Часы | Введение | Клинический конец | Дополнительное ограничение |',
        '| --- | --- | --- | --- | --- |']
    for row in result['episodes']:
        e=row['entry'];clinical=next(t for t in e['episodes']if t['purpose']=='clinical_followup')
        schedule=clinical['schedule'];points=schedule.get('points')
        course=', '.join(points)if points else schedule['first']+'–'+schedule['last']+' с шагом '+schedule['step']
        endpoint=clinical['observation_end']or'Не установлен'
        caveat='Основной текст и рисунок расходятся в частоте дозы 200 мкг.'if e['dose_frequency_conflict'] else (
            'Курс 8, 12 для тканей с забором на 16 отделён от курса 8, 12, 16 для клиники.'if e['case_id']=='tros-manifest' else
            'На рисунке есть подтверждённая точка 18; отметка 20 не является установленным концом измерений.')
        lines.append('| '+LABELS[e['case_id']]+' | '+ANCHORS[clinical['anchor']]+' | '+course+' | '+endpoint+' | '+caveat+' |')
    lines+=['','Дни после иммунизации не переведены в дни проявленной болезни. '
        'Год собственного отчёта Atrosimab сохранён в старой карте как метаданные; он не используется '
        'как биологические часы новой аналитической записи. Ни популяции разных опытов, ни '
        'генотипы и расписания не объявлены эквивалентными.','',
        '## Что удалось вывести','',
        '| Эпизод | Разность календарных точек | Смысл |','| --- | --- | --- |']
    for c in result['calendar_consequences']:
        kind='Забор тканей после последнего введения'if c['procedure']=='therapeutic_tissue'else(
            'Подтверждённая графическая точка после последнего введения'if c['source_kind']=='confirmed_plot_point'else
            'Конец указанного наблюдения после последнего введения')
        lines.append('| '+LABELS[c['case_id']]+' | '+c['difference_days']+' дней | '+kind+' |')
    lines+=['','Это точная календарная арифметика внутри одного эпизода. '
        'Она не доказывает сохранение эффекта на всём интервале, отсутствие рецидива, '
        'значимость в каждой точке или причинную связь. Временное окно процедуры не становится '
        'длительностью фармакологической защиты.','',
        '## Графический источник Atrosimab','',
        'Рисунок 7 из ранее использованной обучающей статьи просмотрен Codex и сохранён по хешу. '
        'На панели A в отмеченный день 18 средние клинические оценки двух доз ниже контроля. '
        'Точные численные значения с графика не снимались, значимость именно этой точки не выводилась. '
        'Последняя измеренная точка не устанавливалась; верхняя отметка оси 20 не является наблюдением. '
        'Сама точка 18 взята из уже измеренного результата, поэтому она не используется для заполнения '
        'временного окна нового прогноза.','',
        'Рисунок не добавляет новую независимую когорту. Это визуальная разметка Codex, '
        'требующая экспертной проверки; автоматическая сверка байтов не проверяет научную интерпретацию пикселей.','',
        '## Два расхождения источника','',
        'В терапевтическом TROS дни 8, 12, 16 и клинический конец 30 дают 14 дней после последнего введения. '
        'Основной текст одновременно говорит «12 дней после последнего лечения». '
        'Обе записи сохранены, опечатка не предполагается и источник не исправлен.','',
        'В профилактическом TROS рисунок задаёт 200 мкг каждые два дня, тогда как раздел методов '
        'перечисляет 150 и 200 мкг каждые два и три дня соответственно. '
        'Полный прежний блок K65 с другими протокольными расхождениями сохранён. '
        'Общее название препарата не разрешает смешивать эти режимы.','',
        '## Что это меняет для прогноза','',
        'Окно будущего заключения разрешено получать из собственной клинической измерительной процедуры, '
        'но не из прочитанного исхода или предела рисунка. Даже такое окно задаёт лишь '
        'слабый квантор «в некоторый измеренный момент», а не улучшение непрерывно или во всех точках. '
        'В текущей разметке оба курса TROS имеют источниковые расхождения; у Atrosimab '
        'нет явного численного конца клинической процедуры. Двух первичных семейств с '
        'непротиворечивым полным методом задания окна пока нет.','',
        'Предыдущий трёхчастный прототип и все численные условия сохранены, '
        'но он не стал исполняемым универсальным правилом. Новых подтверждённых научных знаний '
        'и преимущества видимого DAG нет. Подтверждение уже известного направления и '
        'календарные выводы учитываются отдельно от новых прогнозов.','',
        'Далее требуется связывание дозы, генотипа, фазы, часов и измеряемого исхода '
        'в проверяемые условия кандидата. Сопоставимые ограничения должны оставаться одинаковыми '
        'в режиме карты и в сильной семантической базе без стрелок. Будущий контроль '
        'можно оценивать только после фиксации допустимого нового кандидата.','',
        '## Проверка','',
        f'{count} различных тестов прошли через Poetry. Проверены конечные расписания, '
        'разные часы и популяции, смешение тканевого и клинического курса, неизвестные окончания, '
        'подстановка края оси, ложная длительность эффекта, происхождение, атомарность и сохранность старого результата. '
        'Независимая проверка Bun оформляется отдельной квитанцией. '
        'CLI работает без сети и модельных вызовов. Рисунок получен отдельным чтением опубликованного источника '
        'через браузер; новый контрольный исход не читался. GOLD, карты UI и сервисы не изменены; '
        'перезапуск не требуется.','',f"Запуск: `{result['run_id']}`."]
    details=''.join('<details><summary>'+escape(LABELS[r['case_id']])+' — исходные фрагменты и ограничения</summary><pre>'
        +escape(json.dumps(r,ensure_ascii=False,indent=2))+'</pre></details>'for r in result['episodes'])
    details+='<details><summary>Календарные выводы и расхождения</summary><pre>'+escape(json.dumps(
        {k:result[k]for k in ('calendar_consequences','calendar_conflicts','protocol_conflicts')},ensure_ascii=False,indent=2))+'</pre></details>'
    html='<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    html+='<title>Временные эпизоды и календарные выводы</title><style>body{font:17px/1.6 system-ui;background:#f5f7fa;color:#182434;margin:0}main{max-width:1160px;margin:auto;padding:30px}table{border-collapse:collapse;background:white;width:100%}th,td{border:1px solid #cad5df;padding:10px;text-align:left}.table{overflow:auto}details{background:white;border:1px solid #cad5df;padding:16px;margin:16px 0;border-radius:8px}summary{cursor:pointer;font-weight:650}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}code{overflow-wrap:anywhere}img{max-width:100%;height:auto;background:white}</style><main>'
    html+=render_lines(lines)+'<h2>Сохранённый рисунок 7</h2><figure><img src="figure7.jpg" alt="Рисунок 7: клиническая шкала EAE, средние двух доз и контроля"><figcaption>Подлинный рисунок источника. Интерпретация времени и направления подготовлена Codex.</figcaption></figure>'
    html+='<h2>Полные доказательства</h2>'+details+'</main></html>'
    descriptor=json.loads((folder/'input-corpus.json').read_bytes());data={'run_path':str(folder),
        'functional_path':descriptor['functional'],'run_id':result['run_id'],'tests_unique':count,
        'model_calls':0,'new_empirical_forecasts':0}
    files={'report.ru.md':('\n'.join(lines)+'\n').encode(),'report.html':html.encode(),'data.json':FilePredictionStore.encode(data),
        'figure7.jpg':(folder/'figure7.jpg').read_bytes()}
    receipt={**data,'files':{f:sha256(b).hexdigest()for f,b in files.items()},
        'tests':[{'path':str(tests),'sha256':sha256(raw).hexdigest(),'tests':sum(int(s.attrib['tests'])for s in suites)}],
        'builder_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'helper_sha256':sha256((Path(__file__).parent/'render_template_barrier_audit.py').read_bytes()).hexdigest()}
    review=Path(args.review).resolve()
    for f,b in files.items():write_immutable(review/f,b)
    write_immutable(review/'verification.json',FilePredictionStore.encode(receipt));print(json.dumps(data))


if __name__=='__main__':main()
