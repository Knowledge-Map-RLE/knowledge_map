"""Сохраняет локальный двуязычный отчёт без моделей и чтения будущего контроля."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.definition_robustness import AuditDefinitionRobustness
from domain.article_maps import fingerprint, require
from infrastructure.definition_robustness import FileDefinitionAudit
from infrastructure.immutable_files import write_immutable


def encode(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    root=Path(args.root).resolve();output=Path(args.output).resolve();port=FileDefinitionAudit(root);data=port.read()
    result=AuditDefinitionRobustness().execute(data['spec'],data['evidence'],data['texts'])
    prior=Path(data['repairs']['prior_path'])
    require(sha256(prior.read_bytes()).hexdigest()==data['repairs']['prior_sha256'],'Prior quarantine changed')
    api=Path(__file__).resolve().parents[1]
    files=['domain/definition_robustness.py','application/definition_robustness.py','infrastructure/definition_robustness.py',
           'infrastructure/definition_robustness_report.html','tools/build_definition_bridge_audit.py']
    implementation={n:sha256((api/n).read_bytes()).hexdigest() for n in files}
    validation={'version':result['version'],'input_sha256':fingerprint(data['manifest']),'implementation':implementation,
                'source_fragments_verified':len(data['evidence']),'rates_verified':12,'prior_quarantine_sha256':data['repairs']['prior_sha256'],
                'independent_cohorts':1,'new_independent_cohorts':0,'model_calls':0,'future_control_fulltext_access':False,
                'new_scientific_predictions':0,'bridge_activated':False,'expert_validated':False,'input_reads':port.reads,
                'scope':'Retrospective diagnostic; point-order preservation is not a significance test, fact equivalence or independent forecast.'}
    review={'result':result,'spec':data['spec'],'texts':data['texts'],'evidence':data['evidence'],
            'repairs':data['repairs'],'access':data['access'],'validation':validation}
    template=(api/'infrastructure/definition_robustness_report.html').read_text(encoding='utf-8')
    html=template.replace('__DATA__',json.dumps(review,ensure_ascii=False).replace('<','\\u003c'))
    report='''# Устойчивость порядка при изменении определения

Научный критерий предсказания пока не достигнут. Новый материал даёт полезный положительный и отрицательный контроль для семантики, но не новый независимый прогноз.

## Исправление происхождения

Три прежних изолированных значения Busse (5.3, 14.7, 8.8 / 1000 человеко-лет; соответствующие CI тоже совпали) найдены в полном PDF другой статьи: **10.1192/bjp.182.5.449**, таблица 3, PDF-страница 4. Обзор указывал Acta Neurol Scand **10.1034/j.1600-0404.2003.00118.x**, который этих показателей не содержит. Это несогласованность библиографической привязки обзора; прежняя автоматическая проверка корректно оставила числа неподтверждёнными.

Новый источник относится к LEILA75+, уже представленной Luck 2010. Независимая когорта не добавлена. Узкое изолированное амнестическое нарушение нельзя переименовать в любое MCI. Возраст явно указан на исходной волне. Действующие карты, разбиения, старый карантин и оценки не изменены; исправление хранится отдельно в `quarantine-resolution.json`. Правило подсчёта прямого перехода к деменции как MCI этим аудитом не разрешено.

## Семантическая проверка

Размечены 12 возрастных ставок: четыре определения × три непересекающиеся группы (75–79, 80–84, 85+). Каждое число, CI, число случаев и человеко-лет привязано к точной строке исходной таблицы; строки сверены с изображением PDF. Размеры групп риска и знаменатели отличаются между определениями и не объединяются.

- При удалении требования жалобы внутри MCI все три попарных возрастных порядка сохраняются. Внутри AACD — тоже: всего 6 из 6 описательных сравнений одной когорты. Это кандидат для проверки устойчивости, не шесть независимых подтверждений.
- Для 80–84 → 85+ у MCI: 14.7 → 8.8, у AACD: 40.4 → 109.8. Без жалобы: 21.4 → 11.9 против 74.1 → 116.7. Поэтому одинаковое слово «когнитивное нарушение» не разрешает перенос порядка. Между концептами отличаются фенотип и дополнительные критерии; причинный эффект одного критерия не оценён.
- Сравниваются точечные оценки. Проверка статистической значимости различий не выполнялась; перекрытие CI нельзя автоматически трактовать как доказательство равенства. Источник отдельно обсуждает селективное выпадение более старых/нарушенных участников и ограничения.

## Что это меняет в плане

Факт-эквивалентность и эмпирический перенос порядка должны оставаться разными задачами. Не требуется объявлять два исхода одинаковыми, чтобы проверять устойчивость определённого паттерна; нельзя и разрешить перенос лишь по одному удачному примеру. Новый анализатор проверяет явно зарегистрированные изменения внутри одного первоисточника, остальные поля и возрастные границы сохраняет. Он не генерирует прогнозы и не активирует мосты.

Следующая адресная проверка — MYHAT с парными нейропсихологическим и функциональным определениями, а затем независимое воспроизведение. Ganguli 2013: **10.1212/WNL.0b013e318295d776**. Выбранный Europe PMC JATS-маршрут дважды ответил HTTP 503. Нужны полный текст и приложение с таблицей e-2; числовые возрастные ставки из аннотации или рисунка не восстановлены. Отказ маршрута не означает, что статья нигде недоступна. Письма авторам не нужны.

Будущие контрольные полные тексты не открывались. Разработка ретроспективная, с предварительным чтением опубликованных сведений Busse; не является слепым опытом. При широком поиске встретился фрагмент результата о китайском исследовании 2025 года: он не использован, его нельзя впоследствии объявить непросмотренным контролем. Контрольные ответы не читаются анализатором. Модельных вызовов, переводчиков и эмбеддингов — 0. Русские подписи подготовлены Codex, экспертной научной проверки нет.

## Воспроизведение

Из `D:\\Knowledge_Map\\api`:

```powershell
poetry run python ..\\eval\\free_prediction\\definition-bridge-audit-v1\\annotate.py
poetry run python -m tools.build_definition_bridge_audit --root ..\\eval\\free_prediction\\definition-bridge-audit-v1 --output ..\\eval\\free_prediction\\definition-bridge-audit-v1\\review-v1
poetry run pytest tests/test_definition_robustness.py tests/test_incidence_transfer_scope.py tests/test_primary_pdf_transfer.py tests/test_cohort_transfer.py tests/test_conditional_cohort_transfer.py -q
```

Артефакты неизменяемы: повторный запуск с другим содержимым отклоняется. `inputs.json` фиксирует хеши всех входов, `validation.json` — версии реализации и список прочитанных файлов. HTML автономен; проверка DOM через Bun документируется отдельно. Сервисы не менялись и перезапуск не требуется.
'''
    for name,value in [('data.json',review),('validation.json',validation),('result.json',result)]:write_immutable(output/name,encode(value))
    write_immutable(output/'report.html',html.encode('utf-8'));write_immutable(output/'report.ru.md',report.encode('utf-8'))
    for name in files:write_immutable(output/'implementation'/name,(api/name).read_bytes())
    manifest={'data_sha256':fingerprint(review),'files':{n:sha256((output/n).read_bytes()).hexdigest() for n in
               ['data.json','validation.json','result.json','report.html','report.ru.md']}}
    write_immutable(output/'manifest.json',encode(manifest))
    print(json.dumps({'report':str(output/'report.html'),'rate_cells':12,'repaired_bindings':3,'independent_cohorts_added':0,'model_calls':0},ensure_ascii=True))


if __name__=='__main__':main()
