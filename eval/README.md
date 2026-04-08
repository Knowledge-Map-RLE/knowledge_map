# eval/ — Оценка качества Карты Знаний

Скрипты для измерения качества NLP-пайплайна и агрегированного графа знаний.

Все скрипты запускаются из окружения `api/`:

```
cd d:\Knowledge_Map\api
poetry run python ..\eval\<script>.py [args]
```

---

## Метрики

### Существующие (технические)

Реализованы в `quality_check.py`. Измеряют качество извлечения на уровне отдельных статей.

| Метрика | Что измеряет | Порог |
|---|---|---|
| **Alignment Rate** | % действий, чья фраза найдена в исходном предложении | — |
| **Coverage Rate** | Действий на 1000 символов текста | < 3.0 = мало |
| **Confirmed Rate** | % подтверждённых рёбер (LEADS_TO) | < 15% = мало |
| **DAG Integrity** | Наличие циклов в графе статьи | 0 циклов = ОК |

### Новые (качество агрегированного графа)

| Метрика | Файл | Что измеряет |
|---|---|---|
| **NRC** — Node Replication Count | UI | Сколько статей содержат данный блок (действие) |
| **ERC** — Edge Replication Count | UI | Сколько статей подтверждают данное направленное ребро |
| **LPF** — Linguistic Pattern Frequency | `pattern_frequency.py` | Устойчивые цепочки A→B→C по всему корпусу |
| **PRI** — Pattern Reliability Index | `pattern_frequency.py` | LPF × avg_confidence — надёжность паттерна |
| **ERA** — Entity Resolution Accuracy | `linguistic_quality.py` | % синонимов, объединённых в один norm_key |

NRC и ERC отображаются прямо в интерфейсе: число статей в правом верхнем углу блока и в центре ребра.

---

## Скрипты

### `quality_check.py` — основная проверка качества

Выборочно берёт 100 статей со статусом `done`, считает метрики и генерирует Markdown-отчёт в `reports/`.

```
poetry run python ..\eval\quality_check.py
poetry run python ..\eval\quality_check.py --limit 200
poetry run python ..\eval\quality_check.py --fix   # авто-исправление проблемных рёбер
```

Пример результата из `reports/`: Alignment Rate ~97%, Coverage ~2.9/1000, Confirmed Rate ~3%.

---

### `pattern_frequency.py` — LPF и PRI метрики

Ищет устойчивые лингвистические паттерны (цепочки действий длиной 2–4) во всём корпусе статей. Паттерн считается устойчивым, если встречается в ≥ 2 статьях.

```
poetry run python ..\eval\pattern_frequency.py
poetry run python ..\eval\pattern_frequency.py --top 50 --min-articles 3
poetry run python ..\eval\pattern_frequency.py --output ..\eval\reports\patterns.md
```

Аргументы:
- `--top N` — сколько топ-паттернов показать (по умолчанию 30)
- `--min-articles K` — минимум статей для "устойчивого" паттерна (по умолчанию 2)
- `--max-length L` — максимальная длина цепочки в рёбрах (по умолчанию 4)
- `--output PATH` — сохранить отчёт в файл

---

### `linguistic_quality.py` — ERA метрика

Проверяет, насколько хорошо биологические синонимы объединяются в один `norm_key`. Словарь из 12 групп синонимов (mTOR/mTORC1, autophagy/autophagic flux и т.д.).

```
poetry run python ..\eval\linguistic_quality.py
poetry run python ..\eval\linguistic_quality.py --verbose
poetry run python ..\eval\linguistic_quality.py --output ..\eval\reports\era.md
```

Интерпретация ERA:
- ≥ 70% — хорошо
- 50–70% — частичное объединение, граф фрагментирован
- < 50% — критично, синонимы создают дублирующиеся узлы

---

### `rerun_auto_review.py` — перезапуск авторевью

Сбрасывает все рёбра в `pending` и перегоняет их через обновлённые правила `should_confirm()`. Используется после изменения правил в `auto_review.py`.

```
poetry run python -W ignore ..\eval\rerun_auto_review.py
```

---

### `rerun_fast.py` — быстрый перезапуск авторевью

То же, что `rerun_auto_review.py`, но быстрее: загружает все рёбра в Python одним запросом и пишет обновления батчами. Лог пишется в `rerun_out.txt`.

```
poetry run python -W ignore ..\eval\rerun_fast.py
```

---

### `test_rules.py` — юнит-тесты правил авторевью

Проверяет `should_confirm()` на известных примерах (правильные и неправильные рёбра). Запускать после каждого изменения `auto_review.py`.

```
poetry run python ..\eval\test_rules.py
```

---

### Диагностические скрипты

| Скрипт | Назначение |
|---|---|
| `diagnose_empty.py` | Выясняет причины отсутствия Action-нод у конкретных статей |
| `diagnose2.py` | Дополнительная диагностика |
| `check_status.py` | Быстро показывает распределение статусов рёбер (confirmed/rejected/pending) |
| `check_index.py` | Проверяет наличие нужных индексов в Neo4j |
| `create_index_and_rerun.py` | Создаёт индексы и перезапускает авторевью |

---

## Отчёты

Папка `reports/` содержит исторические отчёты `quality_check.py` в формате `quality_report_YYYYMMDD_HHMMSS.md`.

По ним можно отслеживать динамику качества после изменений в пайплайне.

---

## Как читать результаты quality_check

Ключевые сигналы в отчёте:

- **`avg_confirmed_rate` < 5%** — авторевью слишком строгое или рёбра плохо размечены
- **`avg_coverage_rate` < 3.0** — NLP-сервис извлекает мало действий из текста
- **`zero_action_articles` > 0** — статьи с пустым Markdown или ошибкой конвертации
- **`articles_with_cycles` > 0** — логическая ошибка в графе статьи (не должно быть)
- **`avg_alignment_rate` < 80%** — действия не соответствуют исходному тексту
