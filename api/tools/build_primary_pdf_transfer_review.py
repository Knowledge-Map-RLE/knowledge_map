"""Создаёт проверяемый автономный отчёт, только после фиксации и оценки."""
import argparse
import base64
import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import require,fingerprint
from domain.primary_pdf_rates import normalize_rate,transfer_barriers
from application.primary_pdf_transfer import prepare_primary_transfer
from infrastructure.primary_pdf_transfer import load_primary_inputs
from infrastructure.cohort_transfer_files import FileCohortTransferInputs
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network


def load_evaluation(folder,sealed):
    paths=list((folder/'evaluations').glob('*.json'));require(len(paths)==1,'Explicit single evaluation required')
    value=json.loads(paths[0].read_text(encoding='utf-8'))
    require(value['evaluation_id']==fingerprint(value['binding']),'Evaluation identity changed')
    require(value['binding']['sealed_sha256']==fingerprint(sealed),'Evaluation belongs to another seal')
    return value


def counts(rows):
    return {'queries':len(rows),'issued':sum(r['issued'] for r in rows),
            'matched':sum(r['matched'] is True for r in rows),'wrong':sum(r['matched'] is False for r in rows)}


def main():
    parser=argparse.ArgumentParser()
    for key in ['root','legacy-manifest','run-id','old-run']:parser.add_argument('--'+key,required=True)
    parser.add_argument('--revision',default='review-v1')
    args=parser.parse_args();disable_network();root=Path(args.root).resolve()
    require(args.revision.startswith('review-v') and args.revision.removeprefix('review-v').isdigit(),'Invalid review revision')
    store=FilePredictionStore(root/'runs');sealed=store.read_seal(args.run_id);require(sealed is not None,'Seal missing')
    folder=store.path(args.run_id);evaluation=load_evaluation(folder,sealed)
    annotation,evidence,legacy,bindings,identities,texts=load_primary_inputs(root,args.legacy_manifest)
    result=prepare_primary_transfer(annotation,evidence,legacy,bindings)
    require(fingerprint(result['manifest'])==sealed['binding']['manifest_sha256'],'Primary inputs changed')
    require([fingerprint(f) for f in result['folds']]==sealed['binding']['folds_sha256'],'Fold inputs changed')
    require(fingerprint(result['hidden'])==evaluation['binding']['controls_sha256'],'Hidden controls changed')
    receipts={'seal':json.loads((folder/'input-read-receipt.json').read_text(encoding='utf-8')),
              'evaluate':json.loads((folder/(evaluation['evaluation_id']+'.receipt.json')).read_text(encoding='utf-8'))}
    port=FileCohortTransferInputs(root/'prepared/inputs-manifest.json');port.read_inputs()
    require(receipts['seal']['reads']==port.reads,'Unexpected seal reads')
    require(receipts['evaluate']['reads']==[str(root/'prepared/hidden-controls.json')],'Unexpected evaluation reads')
    old_path=Path(args.old_run).resolve();old_store=FilePredictionStore(old_path.parent)
    old=old_store.read_seal(old_path.name);old_eval=load_evaluation(old_path,old)
    require(old['binding']['implementation']==sealed['binding']['implementation'],'Retrospective operator implementation changed')
    old_controls_path=Path(args.legacy_manifest).resolve().parent/'hidden-controls.json'
    old_controls=json.loads(old_controls_path.read_text(encoding='utf-8'))
    require(fingerprint(old_controls)==old_eval['binding']['controls_sha256'],'Old controls changed')
    common={q for q,c in result['hidden']['controls'].items() if q in old_controls['controls'] and
            c['ages']==old_controls['controls'][q]['ages'] and c['context']['endpoint']==old_controls['controls'][q]['context']['endpoint']}
    paired={m:{'old':counts([r for r in old_eval['modes'][m]['rows'] if r['query_id'] in common]),
               'primary':counts([r for r in evaluation['modes'][m]['rows'] if r['query_id'] in common])}
            for m in evaluation['modes']}
    predictions={};barriers={}
    for fold in sealed['folds']:
        for mode in ['strict','exploratory','frequency']:
            for prediction in (fold['frequency'] if mode=='frequency' else fold['predictions'][mode]):
                qid=prediction['query_id'];predictions.setdefault(qid,{})[mode]=prediction
                if mode!='exploratory':continue
                source,endpoint,ages=qid.removeprefix('Q:').split(':')
                query_frame=result['frames'][source+':'+endpoint+':'+ages.split('-')[0]]
                barriers[qid]=[{'source_observations':w['observation_ids'],
                    'barriers':transfer_barriers(result['frames'][w['observation_ids'][0]],query_frame)}
                    for w in prediction['witnesses']]
    images={key:'data:image/png;base64,'+base64.b64encode((root/'rendered'/key/f"table-page-{p['table_page']}.png").read_bytes()).decode('ascii')
            for key,p in annotation['profiles'].items()}
    validation={'run_id':args.run_id,'evaluation_id':evaluation['evaluation_id'],'predictor_unchanged':True,
        'annotation_sha256':fingerprint(annotation),'source_sha256':{k:v['layout_sha256'] for k,v in identities.items()},
        'sources':len(identities),'rates':len(annotation['rates']),'evidence_fragments':len(evidence),
        'offsets':'Unicode code points in exact UTF-8 LF extracted layout text',
        'table_pages_visually_inspected_by_Codex':7,'complete_PDF_visual_review_claimed':False,
        'same_age_study_outcome_queries':len(common),'model_calls':0,'network_calls':0,
        'new_scientific_predictions':0,'independent_success':False,'expert_validated':False,
        'operator_limitation':'Exploratory legacy labels and contextual differences do not establish clinical equivalence',
        'guarded_transport_equivalence_asserted':False,'receipts':receipts}
    data={'annotation':annotation,'audit':result['audit'],'evidence':evidence,'identities':identities,'texts':texts,
          'normalized':{r['id']:normalize_rate(r) for r in annotation['rates']},'images':images,
          'controls':result['hidden'],'predictions':predictions,'barriers':barriers,
          'evaluation':evaluation,'paired':paired,'validation':validation}
    template=Path(__file__).resolve().parents[1]/'infrastructure/primary_pdf_transfer_report.html'
    raw_json=json.dumps(data,ensure_ascii=False,allow_nan=False).replace('<','\\u003c')
    page=template.read_text(encoding='utf-8').replace('__DATA__',raw_json).encode('utf-8')
    audit=result['audit'];markdown=f'''# Первичные PDF: перенос знаний

Получены и проверены семь PDF. Научный критерий успеха **не достигнут**. Новых научных прогнозов — 0; внешних и локальных модельных вызовов — 0. Будущий контроль не открывался. Разметка Codex требует экспертной проверки.

Выполнен ретроспективный тест порядка соседних возрастных точечных оценок с исключением целой когорты. Код предиктора совпадает с прежним запуском побайтно. Тексты и значения уже прочитаны Codex; программное разделение входов и оценщика не делает этот опыт слепым.

| Режим | Запросов | Выдано | Совпало | Ошибок | Отказов |
|---|---:|---:|---:|---:|---:|
'''
    for mode,label in [('strict','Строгий'),('exploratory','Исследовательский'),('frequency','Частотная база')]:
        m=evaluation['modes'][mode];markdown+='| '+label+' | '+' | '.join(str(m[k]) for k in ['queries','issued','matched','wrong_order','abstained'])+' |\n'
    markdown+='''
Все три ошибки исследовательского режима относятся к Katz: aMCI 70–74→75–79; naMCI 70–74→75–79; naMCI 75–79→80–84. Предсказан рост, в таблице точечные оценки снижаются. ДИ пересекаются: это не доказанное уменьшение клинического риска. Преимущество структурного оператора над частотной базой не показано.

Первичная проверка: из прежних 45 записей подтверждены 42; 3 ставки Busse не подтверждены указанным DOI и исключены. Все 42 точечных значения числово совпали с обзором; исправлены 5 границ возраста (85+ → 85–89), 1 ДИ Katz (верхняя граница 73.2 → 73.0 на 1000 человеко-лет) и 6 обозначений групп WHICAP. Последние обозначают все MCI с памятью/без памяти, а не исключительно однодоменный амнестический подтип.

Сохранены ещё 4 ранее отсутствовавшие возрастные записи и 3 наблюдённые альтернативы Kungsholmen: всего 49 первичных ставок. Они не включены в повтор прежнего состава. Наблюдённые и скорректированные ставки одной когорты не становятся независимыми голосами. Busse и Luck используют LEILA75+; Katz и EAS2019 относятся к одному когортному проекту.

Различаются риск-сеты, пороги тестов, повседневная независимость, обработка прямого перехода к деменции, поправка на смертность и неучастие. Mayo использует возраст при включении, Einstein — достигнутый возраст. В других проверенных таблицах способ формирования возрастных групп не указан достаточно явно; он сохранён как неизвестный.

Полные знаменатели различаются: 32 запроса прежде, 30 теперь. Отдельно сопоставлены 25 запросов с одинаковыми возрастными границами, исследованием и общим обозначением исхода. Контекст уточнён, поэтому это диагностика изменения входов, не независимый тест.

Следующий шаг: оператор применимости по точному фенотипу, возрастной шкале, риск-сету и оценённой величине; затем фиксация прогноза и независимая будущая контрольная статья. Дополнительные источники полезны только при подтверждённой совместимости, а не как дополнительные произвольные голоса. Прежние карты, GOLD и эксперименты сохранены. Сервисные модули не менялись.

'''+f"Запуск: `{args.run_id}`. Оценка: `{evaluation['evaluation_id']}`.\n\n"
    markdown+='## Источники\n\n'+''.join(f"- {p['study']}: DOI {identities[k]['doi']}; таблица на PDF-странице {p['table_page']}.\n" for k,p in annotation['profiles'].items())
    markdown+='\n## Сопоставление 25 запросов\n\n```json\n'+json.dumps(paired,ensure_ascii=False,indent=2)+'\n```\n'
    output=root/args.revision;files={'report.html':page,'report.ru.md':markdown.encode('utf-8'),
        'data.json':FilePredictionStore.encode(data),'validation.json':FilePredictionStore.encode(validation)}
    for name,raw in files.items():write_immutable(output/name,raw)
    code=['domain/primary_pdf_rates.py','application/primary_pdf_transfer.py','infrastructure/primary_pdf_transfer.py',
          'infrastructure/primary_pdf_transfer_report.html','tools/prepare_primary_pdf_transfer.py','tools/build_primary_pdf_transfer_review.py']
    api=Path(__file__).resolve().parents[1]
    for name in code:write_immutable(output/'implementation'/name,(api/name).read_bytes())
    manifest={'files':{k:sha256(v).hexdigest() for k,v in files.items()},
              'implementation':{k:sha256((api/k).read_bytes()).hexdigest() for k in code},'validation':validation}
    write_immutable(output/'manifest.json',FilePredictionStore.encode(manifest))
    print(json.dumps({'report':str(output/'report.html'),'paired':paired,'model_calls':0}))


if __name__=='__main__':main()
