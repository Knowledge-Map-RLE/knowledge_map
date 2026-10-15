"""Проверяет фиксацию, источники и сравнение; создаёт отчёт без моделей."""
import argparse
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path

from domain.article_maps import require,fingerprint,digest
from infrastructure.incidence_transfer_scope import FileIncidenceScopeInputs
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_incidence_transfer_scope import implementation
from tools.run_free_prediction import disable_network


def evaluation(folder,sealed):
    paths=list((folder/'evaluations').glob('*.json'));require(len(paths)==1,'One explicit evaluation required')
    value=json.loads(paths[0].read_text(encoding='utf-8'))
    require(value['binding']['sealed_sha256']==fingerprint(sealed),'Evaluation seal changed')
    require(value['evaluation_id']==fingerprint(value['binding']),'Evaluation identity changed')
    return value


def main():
    parser=argparse.ArgumentParser()
    for key in ['root','primary','run-id','previous-run']:parser.add_argument('--'+key,required=True)
    args=parser.parse_args();disable_network();root=Path(args.root).resolve();primary=Path(args.primary).resolve()
    store=FilePredictionStore(root/'runs');sealed=store.read_seal(args.run_id);require(sealed is not None,'Seal required')
    require(sealed['binding']['implementation']==implementation(),'Frozen implementation changed')
    evaluated=evaluation(store.path(args.run_id),sealed)
    port=FileIncidenceScopeInputs(root/'prepared/manifest.json');inputs=port.read_inputs()
    require(fingerprint(inputs['registry'])==sealed['binding']['registry_sha256'],'Context registry changed')
    require(fingerprint(inputs['scope_manifest'])==sealed['binding']['scope_manifest_sha256'],'Scope manifest changed')
    require([fingerprint(f) for f in inputs['folds']]==sealed['binding']['folds_sha256'],'Original folds changed')
    controls=json.loads((primary/'prepared/hidden-controls.json').read_text(encoding='utf-8'))
    require(fingerprint(controls)==evaluated['binding']['controls_sha256'],'Evaluation controls changed')
    old_path=Path(args.previous_run).resolve();old_store=FilePredictionStore(old_path.parent);old=old_store.read_seal(old_path.name)
    require(old is not None,'Previous seal missing');previous=evaluation(old_path,old)
    require(old['binding']['manifest_sha256']==sealed['binding']['manifest_sha256'],'Previous corpus differs')
    require(previous['binding']['controls_sha256']==evaluated['binding']['controls_sha256'],'Previous outcomes differ')
    predictions={p['query_id']:p for f in sealed['folds'] for p in f['predictions']}
    query_scopes={q['id']:inputs['registry']['scopes'][q['context']['study_id']+':'+q['context']['endpoint']]
                  for f in inputs['folds'] for q in f['queries']}
    texts={};proof_count=0
    bindings={b['reference']['article_id']:b for b in inputs['registry']['source_bindings']}
    for record in inputs['registry']['scopes'].values():
        source=record['source_id'];raw=(primary/'sources'/source/'article.layout.txt').read_bytes()
        require(sha256(raw).hexdigest()==bindings[source]['source_sha256'],'Primary source changed')
        text=raw.decode('utf-8');texts[source]=text
        for p in record['provenance']:
            require(0<=p['start']<p['end']<=len(text) and digest(text[p['start']:p['end']])==p['text_sha256'],'Method fragment differs')
            proof_count+=1
    receipt=json.loads((store.path(args.run_id)/'input-read-receipt.json').read_text(encoding='utf-8'))
    require(receipt['reads']==port.reads,'Unexpected scope input read')
    unknown_queries=sum(any(v is None for v in p['semantic_scope']['critical'].values()) for p in predictions.values())
    prior_rows={r['query_id']:r for r in previous['modes']['exploratory']['rows']}
    require(set(prior_rows)==set(predictions),'Previous query identities differ')
    removed={'previous_matches':sum(r['matched'] is True and predictions[q]['order'] is None for q,r in prior_rows.items()),
             'previous_errors':sum(r['matched'] is False and predictions[q]['order'] is None for q,r in prior_rows.items())}
    blockers=Counter();unknown=Counter()
    for p in predictions.values():
        for key,value in p['semantic_scope']['critical'].items():
            if value is None:unknown[key]+=1
        for a in p['candidate_audits']:
            if 'different_age_bounds' in a['reasons']:continue
            blockers.update(v['field'] for v in a['comparison']['different'])
    validation={'run_id':args.run_id,'evaluation_id':evaluated['evaluation_id'],'known_results_retrospective':True,
        'critical_unknown_queries':unknown_queries,'fully_specified_queries':len(predictions)-unknown_queries,
        'unknown_field_query_counts':dict(unknown),'different_field_witness_counts_same_age':dict(blockers),
        'rejected_previous_results':removed,'method_fragments_verified':proof_count,
        'model_calls':0,'future_control_abstract_or_fulltext_read':False,'scientific_success':False,'expert_validated':False,
        'policy_chosen_after_prior_results':'Development; no claim of blind validation',
        'eligibility_does_not_prove_effect_transport':True,'input_read_receipt':receipt}
    require((len(predictions),unknown_queries,removed['previous_matches'],removed['previous_errors'])==(30,21,7,3),'Diagnostic summary changed; revise fixed report text')
    data={'predictions':predictions,'query_scopes':query_scopes,'registry':inputs['registry'],
          'previous':previous,'previous_rows':prior_rows,'evaluation':evaluated,'texts':texts,'validation':validation}
    api=Path(__file__).resolve().parents[1];template=api/'infrastructure/incidence_scope_report.html'
    raw_json=json.dumps(data,ensure_ascii=False,allow_nan=False).replace('<','\\u003c')
    page=template.read_text(encoding='utf-8').replace('__DATA__',raw_json).encode('utf-8')
    md='''# Применимость переноса знаний

Новый оператор проверяет типизированную семантику вместо равенства описаний. Существенные поля: популяция, проживание, исходное состояние, фенотип, способ учёта возраста, пол, тип показателя, единица, диагностический порог, нормы тестов, жалоба/беспокойство, повседневная функция, прямой переход к деменции и оценённая величина.

Различие этих полей запрещает перенос **этому консервативному оператору**; неизвестность также запрещает его, даже когда поле отсутствует с обеих сторон. Страна, период, наблюдение и размер выборки отмечаются как модераторы. Эти правила не доказаны как универсальные условия биологической переносимости. Изменения видимой карты и её основных промптов не вносились.

На прежних 30 запросах новый оператор выдал 0 гипотез и воздержался 30 раз. Частотная база с тем же допуском также воздержалась 30 раз. Прежний исследовательский режим: 10 гипотез, 7 совпадений, 3 ошибки; прежняя неограниченная частотная база: 26 совпадений из 30.

Отсечены как 3 ошибки, так и 7 совпадений. Это не улучшение продемонстрированной точности и не научный успех. 21 запрос содержит неизвестные существенные поля. Для остальных 9 (Mayo) нет двух допущенных других когорт. Два опубликованных результата одного когортного проекта не создают два независимых голоса.

Нужны сопоставимые первичные статьи с явно описанными методами либо отдельно проверенный мост между различающимися определениями. Просто увеличивать число произвольных статей недостаточно. Вопросы с неизвестным учётом возраста требуют документального уточнения; он не выведен из чисел исхода. Писать авторам не планируется.

Политика разработана после знакомства с прежними результатами. Это разработка и ретроспективная диагностика, а не слепая проверка. Входы, политика, реализация и прогноз фиксируются до программного доступа оценщика к удержанным значениям. Предиктор не читает PDF, полный извлечённый текст, новые результаты или будущие контрольные статьи. Методические фрагменты читаются для отчёта после оценки; происхождение проверено Unicode-координатами и хешами. Разметка Codex не прошла экспертную проверку.

Модельных вызовов — 0. Старые карты и результаты не менялись. Новые модули экспериментальные, сервисный перезапуск не требуется.

'''+f"Запуск `{args.run_id}`; оценка `{evaluated['evaluation_id']}`.\n\n```json\n"+json.dumps(validation,ensure_ascii=False,indent=2)+'\n```\n'
    output=root/'review-v1';files={'report.html':page,'report.ru.md':md.encode('utf-8'),
        'data.json':store.encode(data),'validation.json':store.encode(validation)}
    for name,raw in files.items():write_immutable(output/name,raw)
    code=('infrastructure/incidence_scope_report.html','tools/build_incidence_scope_review.py','tools/prepare_incidence_transfer_scope.py')
    for name in code:write_immutable(output/'implementation'/name,(api/name).read_bytes())
    write_immutable(output/'manifest.json',store.encode({'files':{n:sha256(raw).hexdigest() for n,raw in files.items()},
        'implementation':{n:sha256((api/n).read_bytes()).hexdigest() for n in code},'run_id':args.run_id}))
    print(json.dumps({'report':str(output/'report.html'),'unknown_queries':unknown_queries,'rejected_previous_results':removed,'model_calls':0}))


if __name__=='__main__':main()
