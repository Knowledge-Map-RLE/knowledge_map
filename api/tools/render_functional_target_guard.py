"""Русский отчёт о функциональных предпосылках, без объявления их прогнозами."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from domain.article_maps import fingerprint,require
from domain.functional_target_guard import VERSION
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.render_template_barrier_audit import render_lines
from tools.run_free_prediction import disable_network


def main():
    parser=argparse.ArgumentParser()
    for f in ('run','review','tests'):parser.add_argument('--'+f,required=True)
    args=parser.parse_args();disable_network();folder=Path(args.run).resolve()
    result=FilePredictionStore(folder.parent).read_seal(folder.name)
    require(result is not None and result['version']==VERSION,'Missing functional guard seal')
    for name,digest in result['binding']['implementation'].items():
        require(sha256((folder/'implementation'/name).read_bytes()).hexdigest()==digest,'Guard implementation differs')
    audit=json.loads((folder/'audit.json').read_bytes())
    require(fingerprint(audit)==result['binding']['audit_sha256'],'Functional audit differs')
    p=result['guarded_prototype'];certificates=result['functional_certificates']
    require(len(certificates)==2 and len(p['body'])==3 and len(p['certificates'])==3
            and len(p['primary_families'])==2 and not p['is_executable_rule']
            and not result['scientific_success'] and result['new_empirical_forecasts']==0,'Unexpected scientific claim')
    tests=Path(args.tests).resolve();raw=tests.read_bytes();suites=ET.fromstring(raw).findall('testsuite')
    require(suites and all(int(s.attrib.get(k,0))==0 for s in suites for k in ('errors','failures','skipped')),'Tests failed')
    names={(t.attrib['classname'],t.attrib['name']) for s in suites for t in s.findall('testcase')}
    count=len(names)
    lines=['# Функциональная предпосылка и совместимость мишени','',
        '**Две источниковые предпосылки для трёх прежних цепочек. Новых эмпирических прогнозов — 0.**','',
        'Прежний корпус сохранён: 11 карт, 943 канонических знания, 1897 утверждений и 915 аналитических частей. '
        'Уточнение касается двух препаратов и трёх уже прочитанных цепочек TROS/Atrosimab. '
        'Остальные знания не получили вымышленных функциональных характеристик.','',
        '## Исправленная граница смысла','',
        'Связывание с рецептором не доказывает ингибирование. Текст прежнего блока TROS описывает '
        'ингибирование, но соответствующая скрытая часть кодирует только связывание. '
        'Для анализа добавлено отдельное утверждение по точному источнику; исходная карта не переписана. '
        'У Atrosimab сохранён именно измеренный клеточный результат: подавление TNF-индуцированного '
        'выделения IL-8 в HT1080. Он не подменён прямой доказанной блокадой TNFR1 в организме.','',
        '| Препарат | Функциональное свидетельство | Конструкция модели | Происхождение |',
        '| --- | --- | --- | --- |']
    for c in certificates:
        name='TROS' if 'pmc5651799' in c['article_id'] else 'Atrosimab'
        origin='Ранее описанная работа; цитируемый контекст' if c['functional_origin']=='cited_or_prior_report' else 'Сообщение основного текста; приложение не прочитано'
        lines.append('| '+name+' | '+c['source_functional_context_ru']+' | '+c['source_model_context_ru']+' | '+origin+' |')
    lines+=['','Роли, стимул, исход и область применения нового утверждения сохранены машинно. '
        'Полные исходные составные блоки также сохранены: численные IC50, условия хранения, '
        'отрицания, отсутствие обнаруженного агонизма и остальные части не исчезли. '
        'Краткая проекция не доказывает отсутствие агонизма при всех дозах и условиях.','',
        '## Условная схема','',
        'Источниковое функциональное свидетельство и совместимость внеклеточной человеческой мишени TNFR1 '
        '+ введение средства конкретной группе + измерение того же клинического исхода '
        '→ кандидат гипотезы о меньшем клиническом бремени.','',
        'Выбрана только прежняя структура, где измеряемое свойство связано одной переменной с исходом заключения. '
        'Вариант, допускающий измерение массы тела вместо клинического исхода, не используется. '
        'Препарат и популяция также связаны с теми же переменными; человеческий внеклеточный домен TNFR1 '
        'остаётся фиксированной мишенью, а не произвольным рецептором.','',
        'Это прототип эмпирического правила, а не силлогизм. Третью предпосылку добавил компилятор: '
        'автор не утверждал эту тройку как совместно достаточное основание. Исходные стрелки DAG не изменены. '
        'Клеточный тест и совместимая конструкция модели не доказывают занятие мишени in vivo, '
        'доставку в мозг, функциональную сохранность TNFR2 или клиническую эффективность.','',
        '## Что ещё препятствует переносу','',
        'Прототип пока не исполняется как правило. Необходимо типизированно связать дозу, режим, '
        'часы опыта, генотип, пол, индукцию болезни и измерительную шкалу. '
        'Полная человеческая конструкция TROS и химерный рецептор Atrosimab не объявлены одинаковыми. '
        'Неизвестные значения не заполнены и условия не удалены ради совпадения.','',
        'TROS до проявления и после проявления EAE относится к одному первичному семейству; '
        'Atrosimab — к другому. Две функциональные записи не добавляют независимых клинических репликаций. '
        'Сведения относятся к уже прочитанным источникам и требуют экспертной проверки.','',
        'Новых эмпирических прогнозов и новых независимых подтверждений нет. '
        'Преимущество видимых зависимостей Карты Знаний не установлено. '
        'Этот этап делает условия последующего прогнозирования точнее и не подменяет конечный критерий успеха.','',
        '## Проверка','',
        f'{count} различных тестов прошли через Poetry. Проверены источник и координаты Unicode, '
        'различение связывания и функции, неправильная мишень, подмена препарата, добавленные участники, '
        'числа и временные обещания, сохранность исходных данных, повторное использование и отказ без замены результата. '
        'Независимая проверка через Bun оформляется отдельной квитанцией. '
        'Модельных и сетевых вызовов нет. GOLD, карты UI и сервисы сохранены; перезапуск не нужен. '
        'Визуальная и научная экспертиза не заявляются.','',f"Запуск: `{result['run_id']}`."]
    details=''.join('<details><summary>Источник и машинная структура: '+('TROS' if 'pmc5651799' in c['article_id'] else 'Atrosimab')
        +'</summary><pre>'+escape(json.dumps(c,ensure_ascii=False,indent=2))+'</pre></details>' for c in certificates)
    details+='<details><summary>Прототип, переменные и полные ограничения</summary><pre>'+escape(json.dumps(p,ensure_ascii=False,indent=2))+'</pre></details>'
    html='<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    html+='<title>Функциональная предпосылка и совместимость мишени</title><style>body{font:17px/1.6 system-ui;background:#f5f7fa;color:#182434;margin:0}main{max-width:1160px;margin:auto;padding:30px}table{border-collapse:collapse;background:white;width:100%}th,td{border:1px solid #cad5df;padding:10px;text-align:left}.table{overflow:auto}details{background:white;border:1px solid #cad5df;padding:16px;margin:16px 0;border-radius:8px}summary{cursor:pointer;font-weight:650}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}code{overflow-wrap:anywhere}</style><main>'
    html+=render_lines(lines)+'<h2>Исходные фрагменты и доказательства</h2>'+details+'</main></html>'
    descriptor=json.loads((folder/'input-corpus.json').read_bytes())
    data={'run_path':str(folder),'orientation_path':descriptor['orientation'],'run_id':result['run_id'],
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
