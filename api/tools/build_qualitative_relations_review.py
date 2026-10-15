"""Проверяет источники и строит автономный отчёт после фиксации и оценки."""
import argparse,json
from hashlib import sha256
from pathlib import Path
from domain.article_maps import digest,fingerprint,require
from domain.qualitative_relations import validate_claim,compare_claims
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_qualitative_relations import implementation

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--run-id',required=True);p.add_argument('--evaluation-id',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    root=Path(args.root).resolve();output=Path(args.output).resolve();store=FilePredictionStore(root/'runs')
    sealed=store.read_seal(args.run_id);require(sealed is not None,'Missing seal');require(sealed['binding']['implementation']==implementation(),'Implementation changed')
    evaluation=json.loads((store.path(args.run_id)/'evaluations'/(args.evaluation_id+'.json')).read_text(encoding='utf-8'))
    require(evaluation['binding']['seal_sha256']==fingerprint(sealed),'Evaluation seal differs')
    spec=json.loads((root/'annotation-spec.json').read_text(encoding='utf-8'));manifest=json.loads((root/'prepared/manifest.json').read_text(encoding='utf-8'))
    require(fingerprint(spec)==manifest['annotation_sha256'],'Annotation changed')
    require(fingerprint(manifest)==sealed['binding']['manifest_sha256'],'Manifest changed')
    controls=json.loads((root/'prepared/hidden-controls.json').read_text(encoding='utf-8'))
    require(fingerprint(controls)==evaluation['binding']['controls_sha256'],'Evaluation controls changed')
    require(controls['manifest_sha256']==fingerprint(manifest),'Control manifest changed')
    texts={source:Path(entry['path']).read_text(encoding='utf-8') for source,entry in spec['sources'].items()}
    for source,entry in spec['sources'].items():require(digest(texts[source])==entry['sha256'],'Source changed')
    for evidence in spec['evidence'].values():
        text=texts[evidence['source_id']];fragment=text[evidence['start']:evidence['end']]
        require(evidence['source_sha256']==digest(text) and fragment==evidence['text'] and digest(fragment)==evidence['text_sha256'],'Source coordinates changed')
    claims={c['id']:c for c in spec['claims']}
    for c in claims.values():validate_claim(c)
    pairs=json.loads((root/'control-pairs.json').read_text(encoding='utf-8'))['pairs']
    for pair in pairs:
        pair['result']=compare_claims(claims[pair['left']],claims[pair['right']]);require(pair['result']['relation']==pair['expected'],'Manual comparison differs')
    validation={'run_id':args.run_id,'evaluation_id':args.evaluation_id,'protocol_sha256':manifest['protocol_sha256'],
                'annotation_sha256':manifest['annotation_sha256'],'comparison_controls':len(pairs),'source_fragments':len(spec['evidence']),
                'sources_verified':len(texts),'cohorts':len({c['family_id'] for c in claims.values()}),'qualitative_records':len(claims),
                'free_generation':'Training-only patterns; no target questions supplied','effect_sizes_in_comparator':False,
                'scientific_fact_equivalence_confirmed':0,'new_scientific_predictions':0,'model_calls':0,
                'retrospective':True,'chronological_split':False,'expert_validated':False,
                'maps_and_gold_changed':False,'graph_dependency_advantage_tested':False}
    data={'sealed':sealed,'evaluation':evaluation,'claims':claims,'texts':texts,'evidence':spec['evidence'],'pairs':pairs,'validation':validation}
    api=Path(__file__).resolve().parents[1];template=(api/'infrastructure/qualitative_relations_report.html').read_text(encoding='utf-8')
    html=template.replace('__DATA__',json.dumps(data,ensure_ascii=False).replace('<',r'\u003c'))
    totals=evaluation['totals'];report='''# Качественный перенос отношений: первый свободный диагностический опыт

Вместо прогнозирования чисел проверены направления качественных отношений: возраст, пол, образование и разные определения когнитивного нарушения. Направление точечной оценки и статистическое обнаружение хранятся раздельно; «не обнаружена» не означает отсутствие биологического эффекта. Числа эффектов в прогноз не передаются. Исходные числа, методы и ограничения сохранены в источниках для проверки.

## Материал и дизайн

23 выбранные качественные записи семи полных первичных текстов, шесть независимых когортных проектов. Busse и Luck — одна LEILA75+. Это частичная ручная аналитическая разметка Codex, не полные новые карты всех статей. Использованы отдельные семантические frames с двумя утверждениями результата и сохранёнными клиническими условиями; производственные карты и GOLD не менялись.

В шести разбиениях удерживается целая когорта. Генератор видит только другие когортные записи; отдельный вопрос ему не передаётся. Он выбирает до 20 направленных паттернов, опирающихся как минимум на две независимые когорты с обнаруженной связью одного направления. Противоположные обнаруженные направления блокируют гипотезу; необнаруженные связи остаются ограничениями. Будущая значимость, величина эффекта и причинность не предсказываются.

Все разбиения программно зафиксированы до отдельной оценки. Источники уже прочитаны Codex, хронологического ограничения внутри разбиений нет: это ретроспективная разработка, не исторический или слепой будущий контроль. Список кандидатов выбирается по обучению, а не по вопросам/результатам удержанной статьи. Сеть в CLI отключена; полные исходные фрагменты читает построитель отчёта после оценки.

## Результат

Получены три согласования качественного паттерна: при удержании WHICAP (Manly), Mayo (Roberts) и EAS (Katz) оставшиеся две когорты поддерживают направление «меньшее образование связано с большим риском неамнестического MCI». В шести разбиениях сохранено 10 применений двух паттернов; это не 10 независимых научных предсказаний. У остальных 20 из 23 контрольных записей семантический режим не имеет применимой гипотезы.

Порог <12/≥12, порог ≤12/>12 и эффект на год обучения не отождествляются. Сохраняются диагностические нормы, возрастная шкала, время, поправки и неизвестные поля. Согласование общего направления является сходством паттерна; полная эквивалентность научных фактов не подтверждена. Линейная переориентация эффекта года образования в Katz сохраняет допущение исходной модели.

| Режим | Совпадение паттерна | Несогласованный перенос | Неопределённость | Несколько известных направлений | Не охвачено |
|---|---:|---:|---:|---:|---:|
'''
    for mode,label in [('semantic','Семантический перенос'),('known_union','Известные паттерны'),('frequency','Частотная база')]:
        count=totals[mode];report+='| '+label+' | '+' | '.join(str(count.get(k,0)) for k in ('qualitative_pattern_match','inconsistent_transfer','uncertain','ambiguous_known_patterns','not_addressed'))+' |\n'
    report+='''
На общих трёх согласовавшихся случаях базы дали те же ответы. Семантический режим охватывает 3/23, поэтому отсутствие неудач не доказывает улучшение точности. Нового научного знания не предсказано: переносится уже известный паттерн, а контроль ретроспективный. Частотная база имеет больше согласований на большем охвате. Dependency-связи видимого DAG не обучались; пользу графа этот результат не устанавливает.

## Трудные качественные различия

Девять реальных контрольных пар проверяют сохранение смысла: одинаковый паттерн при различающихся измерениях; описательная частота против скорректированного риска; разные фенотипы; несогласованные направления; изменение обнаружения после поправки на смертность; неизвестное направление. Разметка Codex требует экспертной проверки.

В Roberts для амнестического MCI описательная частота при меньшем образовании выше, но скорректированная связь не обнаружена. Блок должен хранить оба утверждения вместе с разными основаниями. Сравнение «значимо в одной подгруппе, незначимо в другой» само по себе не является тестом различия эффектов или взаимодействия. В Caracciolo половые различия OCIND после поправки на смертность меняют статистический вывод при сохранении направления — это различие оценивания, а не логическое противоречие фактов.

## Следующий научный шаг

Качественный прогноз теперь можно проверять явно: направление, обнаружение и условия не сводятся к совпадению чисел. Однако нужно различать репликацию известного паттерна и новое научное утверждение. Для независимого теста показанного паттерна требуется новый не просмотренный исход неамнестического MCI с описанными методами; кандидаты фиксируются прежде открытия его результатов. Для основного критерия всей системы дополнительно нужна новая комбинация знаний, отсутствующая в обучении, с сохранёнными условиями и бюджетом. Эта работа не подменяет выполнение первого критерия знакомым общим утверждением. Выбор будущей цели и расширение правил по её ответам запрещены.

Артефакты и код версионированы, модели/эмбеддинги/переводчик не вызываются, сервисы не менялись. Английская семантика и русские/английские подписи подготовлены Codex. HTML автономен; проверка DOM через Bun документируется отдельно, визуальный браузерный контроль ей не утверждается.
'''
    for name,value in [('data.json',data),('validation.json',validation)]:write_immutable(output/name,store.encode(value))
    write_immutable(output/'report.html',html.encode('utf-8'));write_immutable(output/'report.ru.md',report.encode('utf-8'))
    for name in ['tools/build_qualitative_relations_review.py','infrastructure/qualitative_relations_report.html']:
        write_immutable(output/'implementation'/name,(api/name).read_bytes())
    write_immutable(output/'manifest.json',store.encode({'files':{n:sha256((output/n).read_bytes()).hexdigest() for n in ['data.json','validation.json','report.html','report.ru.md']}}))
    print(json.dumps({'report':str(output/'report.html'),'qualitative_matches':3,'model_calls':0,'new_scientific_predictions':0}))

if __name__=='__main__':main()
