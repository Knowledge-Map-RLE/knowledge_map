"""Автономный двуязычный просмотр зафиксированной гипотезы и ограничений."""
import argparse
import json
from pathlib import Path
from domain.article_maps import fingerprint,require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--run-id',required=True);p.add_argument('--evaluation-id',required=True)
    args=p.parse_args();root=Path(args.root).resolve();store=FilePredictionStore(root/'runs')
    seal=store.read_seal(args.run_id);require(seal is not None,'Seal missing')
    path=store.path(args.run_id)/'evaluations'/(args.evaluation_id+'.json')
    evaluation=json.loads(path.read_text(encoding='utf-8'))
    require(evaluation['binding']['seal_sha256']==fingerprint(seal),'Evaluation seal binding differs')
    evidence=json.loads((root/'prepared-v2/evidence.json').read_text(encoding='utf-8'))
    manifest=json.loads((root/'prepared-v2/manifest.json').read_text(encoding='utf-8'))
    require(fingerprint(evidence)==manifest['evidence']['sha256'],'Evidence changed')
    data={'seal':seal,'evaluation':evaluation,'evidence':evidence,
          'report_metadata':{'author':'Codex','expert_validated':False,'network_required':False,'model_calls':0,
                             'token_usage':'No model calls; Codex session consumption not measured',
                             'scientific_success':False,'retrospective':True}}
    template=(Path(__file__).resolve().parents[1]/'infrastructure/subject_mechanism_report.html').read_text(encoding='utf-8')
    payload=json.dumps(data,ensure_ascii=False,sort_keys=True).replace('<','\\u003c').replace('&','\\u0026')
    html=template.replace('__DATA__',payload)
    review=root/'review-v3'
    write_immutable(review/'data.json',(json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8'))
    write_immutable(review/'report.html',html.encode('utf-8'))
    markdown=f'''# Предметный фундамент: условный механизм обнаружения MCI

Получена одна условная гипотеза и одна нерешённая задача измерения. Подтверждённых новых научных знаний и выпущенных эмпирических прогнозов: **0**.

## Откуда взялась гипотеза

Сохранили прежний фундамент из 12 блоков без изменений. Добавили пять явных предметных и математических посылок. Четыре совместно используются в новой гипотезе; обзор когнитивного резерва остаётся фоном без автоматической стрелки из болезни Альцгеймера в изолированное нарушение памяти.

Авторы PAQUID уже предполагают более длинную стадию MCI при высоком образовании и большее обнаружение на промежуточном визите. Они также описывают возможный пропуск стадии между осмотрами. Это известные исходные знания, а не предсказания. Обзор Stern 2012 тоже не является новым эмпирическим результатом опыта: [источник](https://pmc.ncbi.nlm.nih.gov/articles/PMC3507991/).

## Условный результат

В идеальной модели с фиксированными длительностями H≥L>0, регулярными визитами, равномерной фазой начала эпизода, идеальным обнаружением и полным наблюдением P(обнаружение)=min(1,D/Δ). При сокращении Δ отношение вероятностей для H и L не растёт, а в некоторых режимах уменьшается. Это отношение обнаружения среди реальных эпизодов, **не** инцидентность, hazard ratio или причинный эффект образования.

Условное взаимодействие интервала визитов и образования отсутствует в выбранных разметках исходных утверждений. Полная новизна относительно научной литературы не проверена. Оператор задан вручную как математический механизм; он не обучен по нескольким независимым когортам. Поддержка биологической посылки — одна когорта PAQUID и гипотеза её авторов.

## Контрпример и граница применения

Вымышленные распределения, не оценки пациентов: L принимает 0,1 и 100 с равными вероятностями; H принимает 1 и 100. H стохастически доминирует L. При Δ=50 отношение равно 170/167≈1,018, при Δ=2 — 10/7≈1,429. Более частые визиты **увеличили** отношение. Поэтому ни большего среднего, ни даже стохастического доминирования недостаточно для переноса теоремы фиксированных окон.

## Диагностика семи источников

Все семь профилей не дают оснований для проверки этого следствия: условия длительности, фазы и сопоставимого изменения протокола не установлены. Профили — аудит применимости ранее прочитанных источников, не новая слепая проверка исходов. Неизвестные поля сохранены неизвестными. PAQUID имеет интервалы два и три года и диагностическую нестабильность. Полный аудит остальных протоколов сейчас не заявлен.

## Следующий проверяемый шаг

Нужны индивидуальные либо агрегированные распределения длительности MCI по образованию, явный процесс переходов и возвратов, расписание визитов, пропуски и диагностические ошибки. Сначала проверить устойчивость предполагаемого взаимодействия в модели этих данных и сравнить её с простой базой известных знаний. Затем зафиксировать гипотезы и только после этого открыть независимый контроль. Добавлять статьи лишь с недостающими измерениями, а не только с тематической близостью.

## Воспроизводимость

- Запуск: `{args.run_id}`; аудит: `{args.evaluation_id}`.
- Генератор читает только зарегистрированные входы и происхождение; профили открываются отдельным сценарием после фиксации.
- Нет LLM, эмбеддингов, переводчика и сетевых вызовов в CLI. Русские подписи подготовлены Codex; расход токенов сессии Codex не измерен.
- Новые экспериментальные модули не изменяют production-карты, GOLD и старые артефакты. Перезапуски сервисов не нужны.
- Разметка и выводы требуют экспертной проверки. Это ретроспективная разработка механизма, а не достижение основного научного критерия.
'''
    write_immutable(review/'report.ru.md',markdown.encode('utf-8'))
    print(json.dumps({'review':str(review/'report.html'),'scientific_success':False}))

if __name__=='__main__':main()
