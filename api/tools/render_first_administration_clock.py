"""Русский отчёт о смене координат и границах её применения в прогнозировании."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from domain.article_maps import require
from domain.first_administration_clock import VERSION
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.render_template_barrier_audit import render_lines
from tools.run_free_prediction import disable_network

LABELS={'prophylactic_clinical':'TROS: профилактическая клиника','therapeutic_clinical':'TROS: терапевтическая клиника',
    'therapeutic_tissue':'TROS: отдельный тканевой курс','manifest_clinical':'Atrosimab: терапевтическая клиника'}


def main():
    parser=argparse.ArgumentParser()
    for name in ('run','review','tests'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();disable_network();folder=Path(args.run).resolve()
    result=FilePredictionStore(folder.parent).read_seal(folder.name)
    require(result is not None and result['version']==VERSION,'Missing relative clock seal')
    for f,d in result['binding']['implementation'].items():require(sha256((folder/'implementation'/f).read_bytes()).hexdigest()==d,'Clock implementation differs')
    tests=Path(args.tests).resolve();raw=tests.read_bytes();suites=ET.fromstring(raw).findall('testsuite')
    require(suites and all(int(s.attrib.get(k,0))==0 for s in suites for k in ('errors','failures','skipped')),'Relative clock tests failed')
    count=len({(t.attrib['classname'],t.attrib['name'])for s in suites for t in s.findall('testcase')})
    require(len(result['clock_proofs'])==4 and result['source_temporal_relations']==result['normalized_temporal_relations']
        and result['new_empirical_forecasts']==0 and result['empirical_generator_run']is False,'Unexpected empirical outcome')
    lines=['# Время относительно первого введения','',
        '**Четыре обратимых временных представления. Новых эмпирических прогнозов — 0.**','',
        'Прежний корпус сохранён: 11 карт, 943 знания, 1897 утверждений и 915 аналитических частей. '
        'Преобразование применено к трём адресно проверенным клиническим цепочкам и отдельному '
        'тканевому курсу, а не объявлено полной временной разметкой всех знаний.','',
        '## Операция','',
        'Для каждой точки собственного эпизода вычисляется τ = t − t₀, где t₀ — '
        'координата первого введения именно в этом эпизоде. Обратное преобразование: t = τ + t₀. '
        'Отрицательная координата обозначает точку до первого введения; она не является отрицательной '
        'длительностью или свойством клинического эффекта. Исходные часы, числа и полные родители сохранены.','',
        '| Эпизод | Первое введение в исходных часах | Введения от первого | Известный конец процедуры от первого | Отдельная графическая точка |',
        '| --- | --- | --- | --- | --- |']
    for p in result['clock_proofs']:
        doses=', '.join(d['point']['value']for d in p['relative_doses'])
        endpoint=p['relative_endpoint']['point']['value']if p['relative_endpoint']is not None else'Не установлен'
        graphical=', '.join(d['point']['value']for d in p['relative_graphical_points'])or'—'
        lines.append('| '+LABELS[p['procedure']]+' | '+p['reference']['first_dose_day']+' | '+doses+' | '+endpoint+' | '+graphical+' |')
    lines+=['','В TROS исходные координаты отсчитываются после иммунизации, в Atrosimab — '
        'по дням проявленной болезни. Первый укол не отождествлён с началом болезни. '
        'Каждое начало отсчёта имеет отдельный идентификатор, включающий статью, эпизод и исходные часы. '
        'Одинаковая надпись «от первого введения» не разрешает объединять разные популяции.','',
        '## Что сохранено','',
        'Все интервалы между введениями и порядок событий сохранились. TROS при проявленной болезни '
        'остаётся курсом 0, 4, 8, Atrosimab — 0, 3, 7, 11. '
        'Профилактическая фаза TROS не стала терапевтической после того, как первый укол получил координату 0. '
        'Тканевой курс TROS остаётся отдельным: 0, 4 с забором на координате 8.','',
        'Не преобразованы дозы, единицы, шкалы и генотипы: 500 мкг TROS не объявлены '
        'эквивалентными 30 или 60 мг/кг Atrosimab. Полные составные родители сохраняют числа, '
        'отрицания, ограничения и протокольные расхождения.','',
        'У Atrosimab графический день 18 становится координатой 17 от первого введения. '
        'Эта точка не заполняет неизвестный конец клинической процедуры и не становится '
        'новой значимой временной границей эффекта. Свидетельство получено в прежнем этапе '
        'из уже прочитанного обучающего рисунка и требует экспертной проверки.','',
        '## Временные параметры и будущий вывод','',
        'Введена отдельная проверка происхождения временного параметра. Измеренную графическую '
        'точку запрещено подставлять в слот окна клинического метода; одинаковые численные '
        'координаты другого эпизода тоже отклоняются. Слот сохраняет собственный идентификатор '
        'часов, происхождение и единицу.','',
        'Известное окно процедуры TROS может быть выражено как 0–13 или 0–22 от первого '
        'введения со слабым квантором измеренного момента. Это не утверждение об улучшении '
        'непрерывно или в каждой точке и не разрешение на перенос окна в другой опыт. '
        'Неизвестный клинический конец Atrosimab остаётся неизвестным.','',
        '## Что не улучшилось автоматически','',
        'Факты о том, что известная оценка следует после последнего введения, одинаковы до '
        'и после преобразования. Смена начала отсчёта не добавила новых свидетельств, не '
        'создала дополнительные независимые семейства и не устранила источниковые расхождения. '
        'Первичные числа «12 дней» против разности 30−16=14 и разные профилактические частоты '
        'TROS сохранены буквально.','',
        'Это вычислительный оператор, основанный на арифметике координат. Он не является '
        'силлогизмом, выученным биологическим законом или новым эмпирическим прогнозом. '
        'На этом этапе эмпирический генератор не запускался заново: четыре представления '
        'хранятся отдельно и не подменяют его прежние части. Преимущество DAG не установлено; '
        'тот же расчёт возможен над теми же структурированными фактами без стрелок.','',
        'Следующий шаг — использовать типизированные связи координат, протокола и измерения '
        'в общем сопоставлении условий кандидата. Параметр, известный из посылки, нужно '
        'отличать от будущего неизвестного эффекта; сохранение такого различия необходимо '
        'для проверки гипотез на одинаковых знаниях и бюджете во всех контрольных режимах.','',
        '## Проверка','',
        f'{count} тестов прошли через Poetry. Проверены обратимость, отрицательные смещения, '
        'точные десятичные числа, порядок и расстояния, разные статьи и эпизоды, происхождение '
        'параметров, незавершённые действия, сохранность источников и атомарность. '
        'Первый прогон имел 22 успешных теста и одну ошибку подготовки временной папки; '
        'после подтверждения существования родительского каталога выполнен новый полный прогон. '
        'Первая квитанция не перезаписана, повторные тесты не считаются дополнительными.','',
        'Модельных и сетевых вызовов нет. Новые будущие исходы не читались. '
        'GOLD, производственные карты, живые сервисы и Git-индекс сохранены. '
        'Независимая проверка Bun оформляется отдельно. Визуальная и экспертная проверка отчёта '
        'не заявляются; локальный браузерный запрет предыдущего этапа не обходился.','',f"Запуск: `{result['run_id']}`."]
    details=''.join('<details><summary>'+escape(LABELS[p['procedure']])+' — обратимое преобразование и полный источник</summary><pre>'
        +escape(json.dumps(p,ensure_ascii=False,indent=2))+'</pre></details>'for p in result['clock_proofs'])
    details+='<details><summary>Сопоставления и сохранённые ограничения</summary><pre>'+escape(json.dumps(
        {k:result[k]for k in ('comparisons','source_temporal_relations','normalized_temporal_relations',
            'source_calendar_conflicts','source_protocol_conflicts')},ensure_ascii=False,indent=2))+'</pre></details>'
    html='<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    html+='<title>Время относительно первого введения</title><style>body{font:17px/1.6 system-ui;background:#f5f7fa;color:#182434;margin:0}main{max-width:1160px;margin:auto;padding:30px}table{border-collapse:collapse;background:white;width:100%}th,td{border:1px solid #cad5df;padding:10px;text-align:left}.table{overflow:auto}details{background:white;border:1px solid #cad5df;padding:16px;margin:16px 0;border-radius:8px}summary{cursor:pointer;font-weight:650}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}code{overflow-wrap:anywhere}</style><main>'
    html+=render_lines(lines)+'<h2>Полные доказательства</h2>'+details+'</main></html>'
    descriptor=json.loads((folder/'input-corpus.json').read_bytes())
    data={'run_path':str(folder),'episode_path':descriptor['episodes'],'run_id':result['run_id'],
        'tests_unique':count,'model_calls':0,'new_empirical_forecasts':0}
    files={'report.ru.md':('\n'.join(lines)+'\n').encode(),'report.html':html.encode(),'data.json':FilePredictionStore.encode(data)}
    receipt={**data,'files':{f:sha256(b).hexdigest()for f,b in files.items()},
        'tests':[{'path':str(tests),'sha256':sha256(raw).hexdigest(),'tests':sum(int(s.attrib['tests'])for s in suites)}],
        'builder_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'helper_sha256':sha256((Path(__file__).parent/'render_template_barrier_audit.py').read_bytes()).hexdigest()}
    review=Path(args.review).resolve()
    for f,b in files.items():write_immutable(review/f,b)
    write_immutable(review/'verification.json',FilePredictionStore.encode(receipt));print(json.dumps(data))


if __name__=='__main__':main()
