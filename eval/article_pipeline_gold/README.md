# Gold standard нового article pipeline

Набор оценивает канонический маршрут:

```text
Full scientific article → DSL structural rows → Knowledge Map
```

`article.md` — неизменённый полный Markdown snapshot статьи из `Document` в
Neo4j и соответствующего S3-объекта. Технический результат прогона —
`run-vN.dsl`: строки `B T<code> B<tag> | ... | unit=S<n>` после финального
remap тегов. `gold.dsl` — только экспертно подтверждённый эталон; успешный
прогон модели не перезаписывает его. Существующие `gold.dsl` требуют повторной
экспертной выверки и не считаются подтверждёнными автоматически.
`source_units.json` — техническая provenance-запись, а не отчёт:
она хранит source units и их `[start,end)`-координаты в тексте после удаления
раздела References. Заголовки, metadata и markup сохраняются как контекстные
типы, а не подменяются T4. Для каждой caption unit нужен `image`-блок; все
явно выраженные результаты, сравнения, числа, методы, связи, ограничения и
неопределённости размечаются отдельными типизированными строками.

Для каждого source unit есть точный `start`/`end`, а каждая DSL-строка
ссылается на соответствующий `S<n>`. `run-warning-vN.dsl` содержит только DSL-комментарии
с семантическими предупреждениями: такие эвристические сигналы не отклоняют корректный
по схеме результат. `run-error-vN.dsl` создаётся только для неуспешного кейса и содержит
DSL-комментарии с блокирующей причиной и отклонёнными строками. Значит, оценка может проверять
всю трассу:

```text
Knowledge Map assertion → structural row → source unit → article.md
```

Этот corpus преднамеренно не совместим со старым `eval/gold`: тот хранит
editor blocks прежней схемы и не способен проверить DSL, typed references или
source spans нового конвейера.

Создание snapshots выполняется только вручную подготовленным списком из 20
PMCID и read-only запросом к Neo4j:

```powershell
cd D:\Knowledge_Map\api
poetry run python ..\eval\build_article_pipeline_gold.py
```

Первый live-прогон намеренно ограничен двумя статьями, чтобы разобрать ошибки
до обновления остальных 18:

```powershell
cd D:\Knowledge_Map\api
poetry run python ..\eval\run_article_pipeline_live.py --limit 2
```

До полного прогона можно проверить три первых содержательных предложения
первой статьи тем же production-промптом и моделью. Результат сохраняется как
`cases/pmc10000452/probe-vN-S7-S9.dsl`, не изменяя эталон:

```powershell
cd D:\Knowledge_Map\api
poetry run python ..\eval\probe_article_pipeline_sentences.py
```

Техническая целостность опубликованных DSL-артефактов проверяется так:

```powershell
poetry run python ..\eval\validate_article_pipeline_gold.py --limit 2
poetry run python ..\eval\validate_article_pipeline_gold.py --limit 2 --run-version 69
```

Валидатор читает только corpus и выводит DSL-совместимый текстовый результат;
он не создаёт JSON-отчётов и не изменяет gold-артефакты. Параметр
`--run-version` проверяет техническую целостность кандидата, но не подтверждает
научную верность. После экспертной проверки двух кейсов можно отдельно решить,
когда расширять прогон до остальных 18 и переносить проверенные строки в
`gold.dsl`. Legacy `gold.json` не удаляется автоматически.
