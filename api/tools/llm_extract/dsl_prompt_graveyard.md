# Реестр промпт-инструкций, которые НЕ улучшили метрики
#
# Назначение: не добавлять в промпт инструкцию дважды, если с ней уже был прогон
# и она не дала прироста метрик. Каждая запись: дата, версия DSL-промпта, текст
# инструкции, какие метрики смотрели, результат.
#
# Формат записи:
#   ## <дата> <версия-промпта>
#   - Метрики: <список>  (triplets_f1 / causal_f1 / ast_edge_f1 / claim_recall /
#     entailment_rate / polarity_fidelity / composite)
#   - Базлайн ДО: <значения>   → ПОСЛЕ: <значения>
#   - Вердикт: НЕ ПОВТОРЯТЬ
#   - Текст инструкции (verbatim, для сравнения):
#     <...>

# --- Пока пусто: ни один прогон DSL-промпта ещё не выполнен. ---
# Заполняется после каждого прогона; перед добавлением новой инструкции проверяй
# этот файл (grep по ключевым словам), чтобы не дублировать текст.

# ─────────────────────────────────────────────────────────────────────────────
# СПРАВОЧНЫЙ BASELINE (не "неудачная инструкция", а точка отсчёта)
## 2026-09-03 v1 (минимальный DSL-промпт, БЕЗ нормализации атрибутов)
- Фрагмент: abstract-intro, чанк 1 (Abstract, ~1011 симв.)
- Метрики: leaf triplets_f1 vs эталон (40 листовых T4)
- Результат: leaf recall=0.050 f1=0.080 matched=2; абстрактных 'A. has X'=0/35
- Наблюдение: модель извлекла 8 семантически верных абстракт-фактов, но в форме
  `Aged A. russatus have greater/reduced X compared to B` (длинный субъект,
  предикат 'have greater...compared to', группа в объекте) вместо нормализованной
  `A. russatus has higher/lower X` эталона. Расхождение лексики + структуры.
- Вывод: нужна инструкция нормализации атрибутов (субъект=короткий, pred=has,
  obj=higher/lower/noun, группа сравнения → ctx).

## 2026-09-03 v2 (добавлена инструкция "# NORMALIZED ATTRIBUTE TRIPLETS")
- Изменение: добавлено правило нормализованной формы атрибутивных T4
  `A. russatus has higher/lower/noun`.
- Статус: выполнен на Abstract чанке 1.
- Результат v2 (Abstract, ~4.33₽): leaf triplets_f1 recall=0.100 f1=0.154 matched=4;
  атрибутивные 'A. has X' recall=0.057 matched=2.
- Эффект: субъект/предикат нормализованы (`A. russatus has ...` вместо
  `Aged A. russatus have ...`). Но объекты разбавлены контекстом
  ("higher clusterin levels in macrophages", "transcriptional integrity akin to
  young mice") — не проходят порог TextMatcher 0.7.
- Сохранено: сырой вывод v2 сохранён, см. `microtest_dsl_v1_chunk1.txt` (v1) и graveyard.

## 2026-09-03 v3 (ужесточена словарная нормализация направлений)
- Изменение: obj строго `{higher|lower} <concept>` без модификаторов; HARD VOCABULARY —
  только higher/lower (запрет greater/reduced/increased/decreased/enhanced/elevated);
  модификаторы/контекст → ctx.
- Статус: выполнен на Abstract чанке 1 (тот же фрагмент, что v2 — изолированное сравнение).
- Результат v3 (Abstract, ~3.53₽): leaf triplets_f1 recall=0.050 f1=0.093 matched=2;
  атрибутивные 'A. has X' recall=0.057 matched=2. precision=0.667 (выросла против 0.333 у v2).
- Эффект: модель эмитит точную эталонную форму `has higher repair capacity` /
  `has lower senescence`. precision выросла. НО recall абстрактных НЕ вырос — не из-за
  промпта, а из-за бедности Abstract (в нём есть лишь ~5 абстрактных концептов из 35:
  repair capacity, senescence, clusterin, health span, inflammaging; нет fibrosis, lifespan,
  motor/muscular/cognitive/immune/metabolic function, circadian rhythm, CMA и др.).
- ВЫВОД (важно): на Abstract recall абстрактных упирается в потолок фрагмента (~5/35),
  метрика triplets_f1 leaf на Abstract НЕ репрезентативна для оценки recall. Для реальной
  проверки recall абстрактных атрибутов нужен фрагмент с максимальным покрытием концептов:
  Discussion чанк 1 (3399 симв, покрывает 9/21 уникальных концептов: circadian rhythm,
  muscular function, clusterin, fibrosis, inflammaging, senescence, repair capacity, CMA,
  clusterin expression). Оценка ~2.84₽ за один чанк.
- НЕ повторять: излишне жёсткая нормализация не даёт прироста recall на бедном фрагменте,
  но повышает precision; применима, но мерять её влияние нужно на Discussion.

## 2026-09-03 Discussion чанк 1 (v3 промпт, репрезентативный тест recall)
- Фрагмент: discussion чанк 1 (3399 симв, покрывает 9/21 уникальных концептов эталона).
- Результат (v3, ~?₽): leaf triplets_f1 recall=0.050; извлечено 2/16 релевантных абстрактов
  (higher repair capacity, lower senescence) — точные эталонные формы ✓.
- Причина низкого recall: модель СХЛОПЫВАЕТ перечни атрибутов. Текст Discussion содержит
  "lower inflammaging, fibrosis, cellular senescence", "preserved motor and muscular function",
  "high clusterin expression, CMA, and transcriptomic resilience", "lower ... circadian rhythm,
  chronic inflammation, and cellular senescence" — НО модель не эмитила атомарные T4 для
  каждого элемента (lower fibrosis, lower inflammaging, higher muscular function,
  higher clusterin expression, higher CMA, higher circadian rhythm).
- ВЫВОД для v4: нужна инструкция РАЗВОРОТА КЛАСТЕРОВ — каждый элемент comma/and-перечня
  атрибутов → отдельный атомарный T4. Не коллапсить список в один T4.

## 2026-09-03 v4 (добавлена инструкция разворота кластеров атрибутов)
- Изменение: правило «список атрибутов через запятую/and → отдельный T4 на каждый элемент».
- Результат (Discussion чанк 1, тот же фрагмент, что v3-обсуждение; ~8.68₽, 29 блоков):
  leaf triplets_f1 recall=0.050→0.275 f1=0.093→0.293 matched=2→11;
  абстрактные 'A. has X' recall=0.057→0.257 matched=2→9.
- ЭФФЕКТ: сильный прирост recall (~5.5x). Модель разворачивает кластеры: lower fibrosis,
  lower inflammaging, higher motor function, higher muscular function, higher CMA,
  higher clusterin expression, higher life span, lower circadian disruption и др.
- СОВПАЛО (9/16 релевантных): lower fibrosis ✓, lower inflammaging ✓, higher motor function ✓,
  higher muscular function ✓, higher CMA ✓, higher clusterin expression ✓, lower circadian
  disruption ✓ (~0.72), higher repair capacity ✓, lower senescence ✓.
- ОСТАВШИЕСЯ НЕВЫРОВНЕННЫЕ: higher tissue repair capacity (лишнее "tissue" — TextMatcher
  разбавляет), higher life span (пробел lifespan→life span), higher transcriptomic
  resilience ✓ совпало на 0.72, higher centro... — всего 7 несовпало.
- ВЕРДИКТ: инструкция РАЗВОРОТА КЛАСТЕРОВ дала большой прирост — СОХРАНИТЬ навсегда.
- НЕ повторять: схлопывание кластеров (главный дефицит recall v3) — исправлено в v4.
- Замечание: выход вырос (15915 ток, ~8.68₽) из-за многословности; следить за экономией.

## АНАЛИЗ оставшихся 7 несовпадений (после v4 на Discussion чанке 1)
Из 16 релевантных эталон-абстрактов совпало 9. 7 несовпадений по ПРИЧИНАМ, НЕ разрешимым
простой промпт-инструкцией (это ограничения TextMatcher / стем-Jaccard 0.7):
- (A) СИНОНИМЫ НАПРАВЛЕНИЯ: эталон 'elevated clusterin' / 'reduced senescence' несопоставимы
  с 'higher'/'lower' (sim 0.40). TextMatcher не объединяет elevated/reduced/higher/lower.
- (B) ПРОБЕЛ В СОСТАВНЫХ КОНЦЕПТАХ: эталон 'lifespan'/'health span' vs модель 'life span'
  (sim 0.53) — 'lifespan' vs 'life span' нельзя объединить по стемам.
- (C) СЕМАНТИЧЕСКАЯ НОРМАЛИЗАЦИЯ: текст 'lower circadian disruption' (ритм сохранён)
  эталон кодирует как 'higher circadian rhythm' (sim 0.53); модель пишет буквально
  'lower circadian rhythm disruption'.
ВЫВОД: разворачивание кластеров (v4) дало max-прирост recall; остаток упирается в метрику
(лемматизация/синонимы/составные токены), а НЕ в промпт. Развилка: чинить TextMatcher
(добавить синонимы направлений + нормализацию пробелов — это повышение качества, не снижение
порога) ИЛИ продолжать жёсткие словарные инструкции (хрупко, частично не применимо к (C)).
Решение оставить за пользователем.
# ─────────────────────────────────────────────────────────────────────────────

## 2026-09-03 TextMatcher FIX (метрика, по решению пользователя)
- Изменение в `metrics.py/stem_tokens`: (1) синонимы-направления канонизируются к стемам
  higher/lower (greater/elevated/increased/enhanced → higher; reduced/decreased/diminished →
  lower); (2) составные концепты lifespan/healthspan → life span/health span.
- Это ПОВЫШЕНИЕ качества сопоставления, НЕ снижение порога (пороги s_th/o_th=0.7 не тронуты).
- Эффект на v4/Chunk1 Discussion: leaf recall 0.275→0.300, f1 0.293→0.320, matched 11→12;
  релевантные абстракты 9/16→14/16.
- Примеры: greater↔higher repair capacity 0.533→1.00; reduced↔lower senescence 0.40→1.00;
  elevated clusterin vs higher clusterin expression 0.40→0.80 (MATCH); lifespan vs life span
  0.53→1.00.
- Тесты: `pytest tests/unit/services/test_llm_triplet_extraction.py` — 10 passed, без регрессий.
- Остались неразрешимыми (корректно НЕ сопоставлены): 'higher health span' (health span НЕ
  упомянут как атрибут A. russatus в этом фрагменте; модель извлекла life span — разные
  концепты); 'higher circadian rhythm' vs 'lower circadian rhythm disruption' (семантическая
  инверсия: сохранение ритма закодировано по-разному, лексика не разрешает).
- ВЕРДИКТ: изменения метрики СОХРАНИТЬ (качество, без снижения порога).

## 2026-09-03 v4 переносимость на Results (R1 чанк 3, ~7.78₽, ~5 мин)
- Фрагмент: results1 чанк 3 (3446 симв; motor/muscular/cognitive/circadian/regeneration).
- Результат: leaf recall=0.075 (против всех 40); matched=3: higher motor function ✓,
  higher muscular function ✓, higher cognitive function ✓. recall абстрактных=0.086.
- ВЫВОД: v4 (разворот кластеров + нормализация) переносится на Results — motor/muscular
  нормализованы корректно. НО модель НЕ нормализует circadian: извлекла
  'higher daily activity pattern stability' / 'lower active phase activity' вместо
  'higher circadian rhythm' (эталон). Также много атрибутов про A. dimidiatus (negative,
  precision-шум, recall не бьют).
- Пропущено/не в этом чанке: lower p16 expression, higher regeneration capacity (чанк 4).
- Инструкция для v5: СОХРАНЕНИЕ функции вопреки возрасту ("not observed disruption",
  "maintained", "no age-related decline") = `has higher <function>` — распространить на
  circadian rhythm, cognitive/immune/metabolic function, transcriptomic integrity,
  thymic architecture (модель уже так делает для motor/muscular, но НЕ для circadian).
# ─────────────────────────────────────────────────────────────────────────────

## 2026-09-03 v5 (добавлена "PRESERVED FUNCTION = higher", включая circadian)
- Изменение: правило «отсутствие возрастного упадка/сохранение функции = has higher
  <function>», с нормализацией circadian (NOT "daily activity pattern stability",
  NOT "circadian rhythm disruption"). Применено к circadian/cognitive/immune/
  transcriptomic/thymic.
- Результат (Discussion чанк 1, тот же фрагмент, что v3/v4; ~4.95₽, ~5 мин):
  leaf f1=0.320→0.348, precision=0.343→0.414, recall=0.300 (matched 12, включая
  'higher circadian rhythm' ✓ — раньше модель давала 'lower circadian rhythm disruption').
- ЭФФЕКТ: модельный circadian теперь 'has higher circadian rhythm' (совпало с эталоном);
  объекты чище → precision выросла, шум меньше (26 vs 35 извлечённых листовых T4).
- recall абстрактных 'A. has X'=0.286 matched=10.
- ПОТОЛОК фрагмента достигнут: единственный недостижимый эталон-абстракт на Discussion
  чанке 1 — 'higher health span' (в тексте фрагмента НЕТ атрибутивного утверждения
  "health span у A. russatus выше"; есть только общая фраза "consistent with improved
  health span"). recall против всех 40 всегда разбавлен концептами из других секций.
- ВЕРДИКТ: v5 СОХРАНИТЬ (нормализация preserved-function + circadian дала f1 ↑ и precision ↑).
# ─────────────────────────────────────────────────────────────────────────────

## 2026-09-04 ПОЛНЫЙ ЦИКЛ всех секций на v5 (full-doc union recall)
- Объём: 22 чанк-файла (Intro, R1–R5, Discussion), union-агрегация test_aggregate.py
  против 40 листовых T4 эталона (reference_blocks_immuno.json). Все секции на промпте v5.
- Итог (union по всем секциям): 743 блока, 357 извлечённых листовых T4,
  **leaf recall=0.675 matched=27/40**; precision=0.076 f1=0.136 (шум от дублей по секциям).
- Посекционные вклады в recall:
  - discussion (3 чанка, 15.71₽): recall 0.400 matched=16  ← гл. вкладчик
  - results1 (4 чанка, 32.04₽): 0.225 matched=9
  - results3 (4 чанка, 25.95₽): 0.200 matched=8
  - results2 (2 чанка, 8.42₽): 0.125 matched=5
  - results5 (3 чанка, ~12₽): 0.050 matched=2
  - results4 (3 чанка): ~0.075 matched=2 (chunk1=1, chunk2/3=0)
  - intro (2 чанка, 13.33₽): 0.025 matched=1
- Достигнутые эталон-абстракты (27/40) включают: higher lifespan, health span, motor/
  muscular/immune function, circadian rhythm, CMA(+score), clusterin(+expression),
  lower fibrosis, inflammaging, senescence, p16 expression, reduced senescence, γ-H2AX,
  maintains thymic architecture, restrains inflammaging, resists age-related functional
  decline, elevated clusterin, higher repair capacity.
- Всё ещё НЕ совпадают (sim<0.7, 13/40; причины: лексическая инверсия/синонимы в объекте,
  различия концептов): lower circadian disruption (выдаёт 'lower circadian rhythm-related
  pathway activity'), better regeneration capacity, higher repair capacity (текст даёт
  'tissue repair capacity'→закрыт на 0.8 в discussion), higher cognitive/metabolic/
  transcriptomic integrity (модель даёт 'youthfulness'/'muscular'), и др.
- НЕСТАБИЛЬНОСТЬ ПРОВАЙДЕРА: два чанка из полного цикла падали с
  'Provider yandex-ai SDK call failed: Server disconnected' (results4 chunk1, results5
  chunk3). Повторный запуск того же чанка сработал (результат записан). Считать полный
  цикл завершённым, но следить за `Server disconnected` при длинных сериях чанков.
- СТОИМОСТЬ полного цикла: intro 13.33 + results1 32.04 + results2 8.42 + results3 25.95
  + results4 ~7.5 + results5 ~12 + discussion 15.71 + повторы ~4.5 ≈ 120₽.
- Сырьё: `microtest_dsl_{intro,results1..5,discussion}_chunk*.txt`,
  `cycle_{section}_stdout.txt`. Скрипт агрегации: `test_aggregate.py`.
- ВЫВОД: recall по v5 на полном документе 0.675 — против эталонных 40. Остаток упирается
  в (a) синонимию/инверсию в объектах (лучшее поле для правки TextMatcher без снижения
  порога), (b) расхождение концептов (cognitive→muscular и т.п. — ошибки модели, промпт
  почти исчерпан). precision низкая (0.076) из-за дублей одних и тех же T4 по секциям —
  при необходимости дедупликации union-подсчёт станет чище.
# ─────────────────────────────────────────────────────────────────────────────

## 2026-09-04 Дедупликация в test_aggregate.py (аналитический замер не-промптом)
- Изменение в test_aggregate.py: перед evaluate_triplets обе стороны дедуплицируются
  по точному кортежу (s,p,o в lowercase). Цель — честный union-подсчёт уникальных фактов,
  убрать задублированный знаменатель от повторения одного концепта по секциям.
- Результат: эталон 40→28 УНИКАЛЬНЫХ (12 были дублями одного концепта в разных секциях);
  извлечено 357→330. recall=0.750 (21/28), precision=0.064 (шум из-за повторов:
  lower fibrosis ×7, higher lifespan ×5, lower cellular senescence ×4).
- Вывод: recall по уникальным фактам уже высок (0.75); главный враг precision — повторение
  одного извлечённого факта во многих секциях (×3–×7), а не концептуальный шум.
- НЕ влияет на production metrics.py — только на скрипт-агрегатор microtest'ов.

## 2026-09-04 TextMatcher: синонимы-знания КОНЦЕПТОВ (метрика, решение пользователя)
- Изменение в metrics.py `_CONCEPT_CANON` + `stem_tokens`: приведение смысловых синонимов
  концептов к общему стему (аналогично направлениям, но для понятий, не направлений):
  - integrity == youthfulness  («transcriptomic integrity» == «transcriptomic youthfulness»)
  - capacity == performance == capability  («repair capacity» == «repair performance»)
- Это знание о домене (качество сопоставления), НЕ снижение порога.
- Эффект на union (уникальные 28): recall 0.750→0.786 (21→22 совпадения); закрыты
  'higher repair capacity'↔'higher repair performance' (0.80) и
  'higher transcriptomic integrity'↔'higher transcriptomic youthfulness' (0.80).
- Тесты: `pytest tests/unit/services/test_llm_triplet_extraction.py` — 10 passed, без регрессий.
- Остались НЕ разрешимыми синонимами (ошибки модели / отсутствие в тексте / инверсия знака):
  'lower circadian disruption' (модель даёт 'lower circadian rhythm-related pathway activity'),
  'better regeneration capacity' (модель даёт ПРОТИВОПОЛОЖНОЕ 'lower regeneration capacity'),
  'higher cognitive function' / 'higher metabolic function' (модель даёт 'muscular function').
  Эти НЕ закрывать синонимами — это либо фактическая ошибка направления, либо концепт
  отсутствует в тексте секций (потолок).
- Итоговый честный ориентир по уникальным концептам: recall 0.786 (22/28), f1 0.123.
- ВЕРДИКТ: дедуп (в агрегаторе, не в метрике) + концепт-синонимы (в метрике) — СОХРАНИТЬ.
# ─────────────────────────────────────────────────────────────────────────────

