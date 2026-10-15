"""После оценки проверяет источники и строит автономный просмотр фундамента."""
import argparse
import json
from hashlib import sha256
from pathlib import Path
from domain.article_maps import digest, fingerprint, require
from domain.knowledge_foundation import normalize, validate_foundation, MODES
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_foundation_pilot import implementation

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--run-id',required=True)
    p.add_argument('--evaluation-id',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    root=Path(args.root).resolve();output=Path(args.output).resolve();store=FilePredictionStore(root/'runs')
    sealed=store.read_seal(args.run_id);require(sealed is not None,'Seal required')
    require(sealed['binding']['implementation']==implementation(),'Implementation changed')
    evaluation=json.loads((store.path(args.run_id)/'evaluations'/(args.evaluation_id+'.json')).read_text(encoding='utf-8'))
    require(evaluation['binding']['seal_sha256']==fingerprint(sealed),'Evaluation seal changed')
    manifest=json.loads((root/'prepared/manifest.json').read_text(encoding='utf-8'))
    annotation=json.loads((root/'annotation-spec.json').read_text(encoding='utf-8'))
    controls=json.loads((root/'prepared/hidden-controls.json').read_text(encoding='utf-8'))
    require(fingerprint(annotation)==manifest['annotation_sha256'] and fingerprint(manifest)==sealed['binding']['manifest_sha256'],'Input changed')
    require(fingerprint(controls)==evaluation['binding']['controls_sha256'],'Control changed')
    texts={s:Path(v['path']).read_text(encoding='utf-8') for s,v in annotation['sources'].items()}
    for s,v in annotation['sources'].items():require(digest(texts[s])==v['sha256'],'Source changed')
    for e in annotation['evidence'].values():
        require(texts[e['source_id']][e['start']:e['end']]==e['text'] and digest(e['text'])==e['text_sha256'],'Unicode fragment changed')
    foundation=sealed['foundation'];ranks=validate_foundation(foundation)
    for s in foundation['sources'].values():require(digest(s['text'])==s['sha256'],'Foundation source note changed')
    records={n['claim']['id']:n for n in annotation['records']};derivations={}
    for identifier,n in records.items():
        _,proof=normalize(n,foundation,'dependencies')
        if proof:derivations[identifier]=proof
    validation={'run_id':args.run_id,'evaluation_id':args.evaluation_id,'foundation_blocks':len(foundation['knowledge']),
                'foundation_sha256':fingerprint(foundation),'source_binding_repairs':len(annotation['repairs']),
                'verified_fulltexts':len(texts),'verified_fragments':len(annotation['evidence']),
                'qualitative_records':len(records),'conditional_consequences':len(derivations),'model_calls':0,
                'new_scientific_predictions':0,'expert_validated':False,'retrospective':True,'chronological_split':False,
                'production_maps_changed':False,'biological_mechanism_module_added':False,
                'baseline':'Earlier canonical comparator already gave three matches; no advantage over it demonstrated',
                'graph_scope':'Proof dependencies for mathematical operations; not a learned scientific DAG advantage'}
    data={'sealed':sealed,'evaluation':evaluation,'records':records,'evidence':annotation['evidence'],'texts':texts,
          'repairs':annotation['repairs'],'derivations':derivations,'ranks':ranks,'validation':validation}
    api=Path(__file__).resolve().parents[1];template=(api/'infrastructure/foundation_report.html').read_text(encoding='utf-8')
    html=template.replace('__DATA__',json.dumps(data,ensure_ascii=False,sort_keys=True,allow_nan=False).replace('<',r'\u003c'))
    labels={'articles':'Только исходные представления статей','comparison':'Фундамент для сопоставления',
            'derivation':'Фундамент и операции','dependencies':'Операции и DAG оснований'}
    report='''# Явный фундамент: первый опыт

Подготовлены 12 знаний по математике, логике и методологии. Английский текст, русские подписи, скрытые условия, участники и источники хранятся отдельно от эмпирических статей. Это небольшой экспериментальный контракт, а не опубликованная production-карта схемы 6 и не полный школьный/вузовский корпус. Биологические механизмы ещё не формализованы. Библиографические источники проверены; локальные заметки являются парафразами Codex, не копиями веб-страниц и не сертификатом их исторической редакции.

## Что реально вычисляется

Пять условных следствий обращают опубликованную ориентацию отношения или шаг fitted log-linear модели, сохраняя исходный контекст, округление, интервалы и статистическое обнаружение. Для Katz naMCI HR 0.95 на дополнительный год даёт примерно 1.0526 на один год меньше в той же модели. Для Katz aMCI HR 1.01 даёт примерно 0.9901, но связь остаётся необнаруженной. Значимость не устанавливается по округлённым границам CI; источник Manly с округлённой нижней границей 1.0 не переклассифицируется. Ни обращение модели, ни обращение отношения не устанавливают эффект вмешательства.

Логический оператор принимает только универсальные включения с совпадающим контекстом и не утверждает существование объектов. Ассоциации через промежуточную переменную не становятся транзитивными. Оператор единиц сохраняет вид показателя: процент не преобразуется в плотность инцидентности без дополнительной модели. Эти общие операции проверены тестами; вымышленные клинические посылки не добавлены в корпус.

## Четыре режима

Входы — 23 наблюдения семи ранее прочитанных первичных текстов, шесть когорт. Для каждого разбиения вся когорта исключается, включая обе LEILA-публикации. Общий бюджет — до 20 паттернов и не менее двух независимых когорт. Отдельного вопроса генератор не получает. Native orientation сохранена в этой ревизии; прежние ручные преобразования вынесены в явные правила.

| Режим | Совпадения паттерна | Неопределённость | Не охвачено |
|---|---:|---:|---:|
'''
    for mode in MODES:
        counts=evaluation['totals'][mode]
        report+='| '+labels[mode]+' | '+' | '.join(str(counts.get(k,0)) for k in ['qualitative_pattern_match','uncertain','not_addressed'])+' |\n'
    report+='''
Без обращения направления контрасты «меньше образования» и «дополнительный год образования» не объединяются. С математическими операциями воспроизводятся три согласования образования и неамнестического MCI. Это не улучшение относительно прежнего канонического сравнителя: тот уже содержал ручное обращение направления и получил те же три результата. Здесь изолируется часть предварительного преобразования исходных записей. Два первых режима не являются сильнейшими семантическими базами. Преимущество предсказания над прежними базами не установлено.

Добавление проверяемого DAG оснований не изменило прогнозы. Граф делает явными совместные посылки, ссылки и условия математической операции; его узлы не являются независимыми научными подтверждениями. Не проверено, улучшает ли научный dependency-граф обучение новых закономерностей. Повтор известного паттерна и математическое следствие помечены отдельно; новых эмпирических предсказаний — 0.

## Исправление происхождения

В новой ревизии исправлены пять привязок: три образовательные оценки Mayo ранее ссылались на примечания перед строкой HR; для пола LEILA не хватало строки HR; для Manly добавлено начало фразы в двухколоночном тексте. Значения и прежние результаты не переписаны. Старые JSON/HTML и production/GOLD сохранены. Для двух дозовых преобразований Katz отдельно сохранены строки методов Cox и исходные строки таблицы. Координаты — Unicode code points.

## Предел результата и следующий шаг

Это ретроспективная разработка на источниках, которые Codex уже читал, без хронологического ограничения внутри разбиений. Фиксация до программной оценки предотвращает чтение контроля генератором, но не устраняет прежнее человеческое знакомство с ответами. Независимое предсказание нового знания не подтверждено.

Следующий содержательный этап — предметный фундамент с действительно выраженными механизмами и условиями из учебных/обзорных источников, затем составление новой проверяемой гипотезы с цепочкой нескольких научных посылок. Нельзя подставлять отсутствующий механизм или использовать общий школьный силлогизм как доказательство причинной связи. Кандидаты фиксируются до открытия новой контрольной статьи; утверждения, уже содержащиеся в фундаменте, считаются известными. Требуется сравнение с прежней канонической базой и отдельно с абляцией научных dependency-связей.

Модельные вызовы, эмбеддинги, переводчики — 0. Сервисы не менялись. Экспертной научной проверки нет. Автономный интерфейс русский/английский; DOM-проверка через Bun документируется отдельно и не утверждает визуальный браузерный контроль.
'''
    for name,value in [('data.json',data),('validation.json',validation)]:
        write_immutable(output/name,json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False,indent=2).encode('utf-8'))
    write_immutable(output/'report.html',html.encode('utf-8'));write_immutable(output/'report.ru.md',report.encode('utf-8'))
    for name in ['tools/build_foundation_review.py','infrastructure/foundation_report.html']:
        write_immutable(output/'implementation'/name,(api/name).read_bytes())
    write_immutable(output/'manifest.json',store.encode({'files':{n:sha256((output/n).read_bytes()).hexdigest() for n in ['data.json','validation.json','report.html','report.ru.md']}}))
    print(json.dumps({'report':str(output/'report.html'),'conditional_consequences':len(derivations),'model_calls':0}))

if __name__=='__main__':main()
