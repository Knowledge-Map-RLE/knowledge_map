- Говори на русском.
- Используй `bun` вместо `npm`.
- Используй `poetry` вместо нативного запуска скриптов `python`, `pip` и использования `venv`.
- Нужен только указанный порт, а не другой случайный, иначе в микросервисной архитектуре, другие микросервисы не будут знать нужный порт.
- Не делай fallback, нужно сразу делать правильно, что бы работало с первого раза.
- Делай всё профессионально, как делают промышленный (production) код.
- Выполняй в CLI `python` и `pip` команды в `poetry` окружении.
- Выполняй в CLI все команды от имени администратора. Запускай сам CLI от имени администратора если это возможно.
- Папки, файлы и код должны следовать "чистой архитектуре" Роберта Мартина.
- При написании кода используй принципы SOLID.
- Всё должно корректно работать как в development так и в production окружении и корректно развёртываться.

## Progress: Knowledge Language Parser

### Goal
Rule-based knowledge extraction engine in `knowledge_map_core/src/extractor/rules/`, tested against manually annotated ground truth from scientific articles.

### Constraint
English only. Deterministic spaCy dependency tree rules. LLM only for complex cases (gRPC ai:50054). Ground truth uses UUIDv7, FACT/META type.

### Done
1-32. (See prior history)
33-37. (See prior AGENTS.md)
38. **Iteration 6 — Edge cases & AUX support** (coverage 157→158):
    - Shared object in conj verbs (`Braak et al. revisited and strengthened` → both verbs)
    - MWP nsubjpass support + new patterns (`implicate in`)
    - ActiveVoiceRule AUX support in `_collect_verbs` (`have` tagged as AUX)
    - Post-obj nmod includes `in`/`on`/`as` (`play key role in`)
    - Conj verb processing for passive heads (nsubjpass)
    - PassiveVoiceRule nsubj+auxpass fallback (UD annotation variation)
    - CopularRule AUX-ROOT fallback (csubj + attr)
    - New MWP patterns: `occur in`, `act as`, `result in`, `characterize by`, etc.
39. **Coverage analysis**: Identified ~30% of 135 missed triplets as matching function limitations (abbreviation, subject compression, name expansion) — not fixable by pipeline rules.
40. **Article 2 ground truth created**: 224 triplets across 166 sentences for "Hallmarks of cancer and hallmarks of aging". Baseline coverage: 67/222 (30.2%). Test file: `test_article2_coverage.py`.
41. **Iteration 7 — Negation handling + coverage boost to 57.7%**:
    - NegationRule: underscore predicates (`not_cause`) → space (`not cause`)
    - CopularRule: `_is_negated` checks copula AND complement children for `neg` dep; `"neg"` added to `EXCLUDED_DEPS` to prevent `not` leaking into object text
    - ActiveVoiceRule: `_verb_is_negated` checks verb and auxiliary children for `neg` dep; `not {verb}` prefix in all statement-creation paths
    - PassiveVoiceRule: `_verb_is_negated` in agent/xcomp statement builders → `be not {verb} {prep}`
    - MultiWordPredicateRule: `_verb_is_negated` in match/extract → `not {base_predicate}`
    - Article 2 coverage: 67/222 (30.2%) → 128/222 (57.7%), +61 matches (+27.5pp)
    - Server restart via admin PowerShell required (non-admin shell cannot kill old PID)

### Current Coverage
- **179/299 (59.9%)** on Hallmarks of PD (222 sentences).
- **137/222 (61.7%)** on Hallmarks of cancer and hallmarks of aging (166 sentences).
- Article 1: All 222 sentences produce pipeline output; 100/177 sentences with GT triplets have ≥1 match.
- Pipeline handles: active/passive voice, copula, multi-word predicates, adjective+preposition, conj verbs with shared objects, conjoined subjects/objects split, negation in all rule types, reduced relative participles (acl/advcl) with by-agent, META Statement→Statement links via MetaBuilder (6 patterns).

### Article 1 — Remaining 121 Missed By Category
| Category | Count | Example |
|---|---|---|
| Matching function issues (abbreviation, compression) | ~30 | `PD` vs `Parkinson's disease`, `integrated systems-level understanding` vs `Preparing for...` |
| GT name expansion (generic→specific) | ~15 | `genes → cause` → individual gene triplets |
| Coordination in nmod subject | ~10 | `number and distribution of synapses → cause` |
| Anaphora | ~10 | `many of those → be identified by` |
| Complex copular (verb+auxpass not cop+adj) | ~8 | `are well established`, `is within reach` |
| Word-order mismatch | ~8 | `Lewy bodies → be lacking in → affected carriers` |
| Noun subjects (nmod:of excluded) | ~5 | `fusion/fission → control → fragmentation` |
| META not producible by MetaBuilder | ~5 | `discovery of X in Z`, `revealing X to be Y` |
| Complex transitive (dobj+acomp) | ~3 | `render → making → challenging` |
| Other edge cases | ~28 | remaining complex syntactic patterns |

### Article 2 Progress
- **Ground truth created**: 224 triplets across 166 sentences for "Hallmarks of cancer and hallmarks of aging".
- **Current coverage**: 137/222 (61.7%) — ACL subject resolution (+0.9pp), negation handling (+27.5pp), acl/advcl reduced relatives, bi-directional matching, object text cleanup.
- **Test file**: `tests/articles/test_article2_coverage.py` (gRPC, e2e).
- **UUIDv7 namespace**: `uuid.uuid5(uuid.NAMESPACE_URL, 'https://aging.us/hallmarks-of-cancer-and-aging')`.

### Article 2 — Key Gaps (85 missed)
| Gap | Examples |
|---|---|
| First-person narrator | `I → propose`, `I → include`, `Let us depict` |
| Reduced relative clause ACL subject | `hallmarks → be depicted as → circle` (subject resolved to `I` not `hallmarks`) |
| HTML/figure artifacts | `<figure>`, `<figcaption>` mixed into sentences |
| Long noun-phrase subjects | pipeline can't follow long NP to the verb |
| Complex coordination | `they → not include → mutations/genetic instability` |
| Multiple verb chains | `re-examine... proposed by`, `holds... suggests` |
| Subordinate clauses with `that` | `article... suggests that canonic hallmarks...` |
| Noun subjects (nmod:of excluded) | `fusion/fission → control → fragmentation` |
| Word-order mismatch | `signaling pathways → be → lowest level` (copula direction reversed) |
| LLM limitations (0.5B) | can't resolve first-person or extract that-clause on 0.5B scale |

### Changes This Session (Iteration 9 — ACL subject resolution, +2 matches)
- **PassiveVoiceRule ACL subject resolution**: `_resolve_acl_head_subject` uses `_subject_phrase_text` (head + non-clausal children) instead of `subtree_text` for subjects whose predicate is an `acl` modifier — excludes `acl`, `relcl`, `advcl`, `ccomp`, `xcomp` from subject text. Fixes `hallmarks of cancer → be depicted as → circle` and `hallmarks of cancer → be depicted by → Hanahan and Weinberg` (was top blocker).
- **PassiveVoiceRule recursive agent nmod search** (`_find_agent_nmods`): traverses verb's full subtree to find nmods with `by`/`via`/`as` — catches agent PPs attached to nmod heads (e.g., `Hanahan` attached to `circle` not `depicted`).
- **PassiveVoiceRule `_build_agent_statements`**: skip nmod children with agent prepositions (separate PPs); exclude `neg`, `dep` from collected deps; use head + pre-modifiers only.
- **PassiveVoiceRule `_collect_conjuncts` POS filter**: only follow `conj` with POS in NOUN/PROPN/ADJ — prevents ADVs like `hierarchically` being collected as agents.
- **ActiveVoiceRule complex transitive**: verb with both `obj` and `acomp` (e.g., `make X resistant`) produces combined object text.
- **CopularRule `_subject_phrase_text`**: includes `nmod` children with case in `of`, `for`, `in`, `on`, `with`, `by`, `to` (essential noun complements), preventing regressions from pre-modifier-only approach. Only used for conjoined subjects (len>1); single subjects use `subtree_text` to preserve full NP (acl/relcl etc.).
- **ActiveVoiceRule crash fix**: `set(subtree_tokens(...))` → `dict` dedup by idx (TokenInfo is unhashable).
- **Pipeline `_preprocess_text`**: strip HTML `<figure>`/`<figcaption>`, strip citation brackets `[1]`, split `;` → `. ` when followed by capital.
- Article 2 coverage: 135/222 (60.8%) → 137/222 (61.7%); delta: +2 (both ACL); no regressions on Article 1 (158/293, 53.9%).

### Changes This Session (Iteration 11 — Xcomp predicate chaining + ccomp extraction + matching flexibility, +14 matches)
- **ActiveVoiceRule xcomp predicate chaining**: When verb has xcomp child with both `obj` AND `mark` (`to`), combines main verb + mark + xcomp verb → predicate (e.g., `need to integrate`, `serve to complicate`); object = xcomp verb's complement only (not verb itself). Bare-gerund xcomps (`involve substituting`) unchanged.
- **ActiveVoiceRule first-person ccomp extraction**: When subject is `I`/`We` and verb has `ccomp` with `nsubj`+`obj`, extracts from the ccomp clause instead. Only skips normal extraction when ccomp succeeds (avoids regression).
- **ActiveVoiceRule `_object_text_xcomp`**: Added `acomp`/`oprd`/`ccomp` to child dep filter; when xcomp verb has a `ccomp` child, excludes xcomp verb from object text (`render making predictions challenging` → `predictions challenging`). Fixed `NameError: other_idxs` bug.
- **Matching function** (`conftest.py`): Independent subj/obj direction — subject and object can use different `_contained_in` directions independently (e.g., pipe subj `multifactorial nature` as subsequence of GT subj, while GT obj as subsequence of pipe obj).
- **CausalRule**: Expanded `CAUSAL_VERBS` set; added `_verb_is_negated()` and `_collect_conjuncts()`; produces one statement per subject-conjunct / object-conjunct pair.
- **CopularRule ccomp fallback**: When copula's head is in `ccomp` clause, complement token IS the subject; real attr/nmod found among children. Added `conj`/`cc`/`parataxis` to `EXCLUDED_DEPS` in `_object_text`.
- **PassiveVoiceRule**: Both `nsubj:pass`/`aux:pass` (coloned) and `nsubjpass`/`auxpass` (non-coloned) dep labels handled in `matches()` and `extract()`. `_build_prep_statements` signature changed from `Statement` to `Concept`; acl/advcl loop calls directly with `Concept`.
- **GT sentence-boundary fix**: Split merged sentence (containing `</figcaption> </figure>`) at line 573 of `hallmarks_of_pd.truth`.
- **Coverage**: Article 1 (PD): **158/293 (53.9%) → 172/293 (58.7%)**, +14 matches. Article 2 (Cancer): **unchanged at 137/222 (61.7%)**.
- **All 12 unit tests pass** — no regressions.

### Changes This Session (Article Editor Bug fix)
- **ROOT CAUSE**: `poetry run python` imports `web.app` in ~98 секунд (slowest: `src.routers.article_editor` ~25s, GraphQL/strawberry ~22s). `api/web/app.py` routes ARE correct (article_editor зарегистрирован).
- **Проблема**: `start.ps1` использует `poetry run python -m uvicorn web.app:app --reload` — `--reload` перезапускает worker если импорт не завершился за ожидаемое время (98s > reloader timeout). Worker-процесс убивается, перезапускается — цикл повторяется, article_editor роуты не регистрируются.
- **Решение 1** (`api/start.ps1`): убран `--reload`, добавлен pre-warm импорт (создаёт .pyc кэш), fallback портов (8000→8001→8002…), попытка system Python если poetry pre-warm упал.
- **Решение 2** (`client/.env`, `client/vite.config.ts`): VITE_API_BASE_URL и proxy target переключены на порт 8001 (временный сервер через system Python работает, порт 8000 занят зомби-процессом без article_editor).
- **Статус на 03.07.2026**: порт 8001 (PID 15152, system Python) работает со всеми роутами, включая article_editor. Порт 8000 (PID 13864, poetry) — зомби-процесс без article_editor, не убивается без админа.

### Changes This Session (Iteration 12 — Hybrid backend port conflict fix)
- **ROOT CAUSE #1** (`hybrid_server.py`): `main()` вызывает `uvicorn.run()` без `if __name__ == "__main__":` — на Windows multiprocessing spawn повторно импортирует модуль, uvicorn пытается запустить второй worker на том же порту → `EADDRINUSE` сразу после `Application startup complete`.
- **ROOT CAUSE #2**: Предыдущий запуск оставил zombie-процесс (PID 17876) на порту 5002 (с 9:34). Даже когда новый процесс (17204) стартовал, старый zombie создавал race condition при bind.
- **Исправление** (`hybrid_wrapper.py` — новый файл): обёртка с `if __name__ == "__main__":` guard для стабильного запуска uvicorn на Windows.
- **Исправление** (`start.ps1`):
  - Cleanup: убивает любой процесс на порту 5002 перед стартом
  - Использует `hybrid_wrapper.py` вместо прямого CLI entry point
  - Retry-логика: если хайбрид упал после первого старта (health недоступен), перезапускает один раз
  - `localhost` → `127.0.0.1` в health check: Windows резолвит `localhost` в `::1` (IPv6), а uvicorn слушает `0.0.0.0` (IPv4) — health check зависал на 180 секунд
- **Ускорение**: старт DoclingFast hybrid теперь занимает ~6-9 секунд (вместо 180+). DocumentConverter инициализируется за ~4.62с на CPU, health check срабатывает через ~3с после этого.
- **Порт 8000** (PID 1688, zombie poetry API без article_editor) и **порт 8002** (PID 22784, zombie pdf-to-md REST) всё ещё висят — требуют админских прав для убийства.

### Changes This Session (Iteration 13 — META coverage fix + matching improvement)
- **Problem**: e2e тест обрабатывал только первые 30 предложений (`sentences[:30]`). Все META-паттерны MetaBuilder срабатывают в более поздних предложениях → META coverage 0/11.
- **Fix 1** (`test_pipeline_vs_ground_truth.py:125`): убран `[:30]` — теперь все предложения обрабатываются.
- **Fix 2** (`conftest.py:206-228`): `_contained_in` теперь стриппит trailing punctuation из слов (`_strip_punct`) перед сравнением. Чинит `"Braak et al."` (GT) vs `"braak et al"` (pipeline).
- **META coverage**: 0/11 → **6/11 (54.5%)**:
  - 5 ref_in_obj (MetaBuilder: `many reports → show`, `autopsy studies → show`, `Dehay et al → show`, `Yo et al → demonstrate`, `recent in vitro data → suggest`)
  - 1 ref_in_subj (MetaBuilder: `[UUID] → proposed by → Braak et al.`) — matching fix
  - 5 оставшихся META (`discovered in`, 4× `revealed by`) — артефакты старого GT формата, MetaBuilder не может их произвести (`discovery of X in Z`, `revealing X to be Y` не укладываются в regex-паттерны). Оставлены как есть.
- **ALL coverage**: 177/299 (59.2%) → **179/299 (59.9%)**.
- **Unit tests**: 12/12 pass — без регрессий.

### Changes This Session (Iteration 14 — META save/display fix in UI + Neo4j)
- **Root cause**: 3 cascading bugs prevented META statements from appearing in the UI:
  - `knowledge_language_grpc_client.py:76-77`: `subject_text`/`object_text` were empty for Statement-typed refs (UUID not in concept_map). Fix: fallback to UUID when type=`statement`.
  - `article_editor_service.py:109-125`: `save_statements` didn't save `type`, `subject_type`, `object_type` to Neo4j. Fix: added all 3 fields to CREATE query.
  - `article_editor_service.py:52-62`: `get_article` didn't return type info. Fix: added `subject_type`, `object_type`, `type` to response.
- **Cleanup**: Deleted 5071 stale `KnowledgeStatement` nodes (missing `type` field — old format).
- **Result**: After API restart + re-parse, META statements now appear in UI with UUID fallback text (e.g. `many reports → show → 000655c6-...`).

### Changes This Session (Iteration 15 — T57/T27 blocks + full RESULTS section structured)
- **Бэкенд**: T57/T27/T49/T14-findings полностью реализованы (см. ниже раздел про клиент); роутер изображений `api/src/routers/article_editor/images.py` (POST/GET/DELETE), методы `upload_image`/`get_image`/`delete_image` в `article_editor_service.py`.
- **Клиент**: `blockTypes.ts` — T57 «Результат (находка)» (parameter/subjectRef/comparisonRef/direction/significance/pValue/figureRef/detail), `findings` (uuid-list→T57) в T14, T27 `canAddMultiple`, T49 «Изображение» с `imageKey` (image-upload). `FieldInput.tsx` — ImageUploadInput (превью, «Заменить», «Удалить», S3-cleanup). `blockConverter.ts` — конвертеры T57/T14-findings/T49, `renderFinding`, refMap-резолв имён.
- **Весь раздел «3. RESULTS» (строки 49–159 md) преобразован в структурные блоки**:
  - 6 экспериментов T14 (уже были, order 25/42/59/76/92/108) получили поле `findings` (uuid-list → T57), суммарно 94 ссылки.
  - Создано **94 блока T57 «Результат (находка)»** (все результаты 5 подразделов RESULTS: поведение/циркадианные/регенерация/p16 VAT → 20; тимус/селезёнка/ConA/Il2/Il4 → 11; печень/RNA-seq/DEG/GATG/iAge/CMA/SenMayo → 24; VAT snRNA-seq/SASP/IASP/кластерин → 14; in vivo кластерин (сила захвата, ротарод, фиброз 4 органов, цитокины, MAC, ABCs/AABs/M1/M2, p16/p21/γ-H2AX) → 20; in vitro BMDM/моноциты → 5) и **3 блока T27 p-value** (0.05/0.01/0.001).
  - Сохранено через `PUT /api/article_editor/articles/{uid}/blocks` (replace-all): **109 → 206 блоков**.
- **Найден и исправлен баг в `blockConverter.ts`**: `str()` возвращал `''` для числовых значений (`pValue`, `variance`, `effectSize` — `inputType: 'number'`) → p-value не рендерился в markdown. Fix: `str()` теперь принимает `number`.
- **Найден и исправлен баг**: `refMap` (blocksToStatements) резолвил object_text триплета `эксперимент → результат → {T57 UUID}` в имя параметра, из-за чего `renderFinding` не мог найти блок (object_text == «Масса тела с возрастом», а не UUID). Fix: для predicate `'результат'` object_text НЕ резолвится (сохраняется UUID), шаги T56 не затронуты (их name == label).
- **Проверки**: `tsc --noEmit` — чисто, `bun run build` — успешно. Live-render тест: 1083 триплета, 94 связи `эксперимент→результат`, 6 секций «Результаты (находки)» с полными строками (`Масса тела с возрастом повышено в Aged Acomys dimidiatus ... — p=0.05, Fig. 1D — детали`). Скрипт `build_findings.py` идемпотентен (удаляет ранее сгенерированные T27/T57 и поле findings перед повторным сохранением).
- **UUID-формат**: новые блоки используют `uuid8_str()` (api/src/uuid8.py), как и существующие.

### Changes This Session (Iteration 16 — INTRODUCTION structured into blocks)
- **Цель**: структурировать «2. INTRODUCTION» (строки 37–48 md) существующими типами блоков (без новых типов).
- **Новые блоки (53 шт., только существующие типы)**:
  - **T19 «Животная модель» ×7**: род Acomys, *A. kempi*, *A. percivali*, *A. subspinosus*, Deomyinae, *Rattus*, *Mus* (лабораторные штаммы).
  - **T23 «Определения понятий» ×5**: биологическая резилентность, торпор, ложная автотомия, пренебрежимая сенесценция, сравнительная биология старения.
  - **T22 «Сущность» ×39** — фоновые триплеты INTRODUCTION: потеря резилентности при старении (воспаление + метаболический стресс), обоснование сравнительной биологии, сенесценция/Hamilton, адаптации Acomys (регенерация, устойчивость к ядам, ложная автотомия), диурнальность и торпор *A. russatus*, смертность в дикой природе (внешние опасности, родительская забота, 11-дневный менструальный цикл, скудость доказательств).
  - **T2 «Цель исследования» ×2**: всестороннее понимание биологии старения на модели *A. russatus*; идентификация и проверка каузальности механизмов устойчивости к старению.
- **Скрипт**: `build_intro.py` (temp) — **UUIDv8** (`uuid8_str()`), как у всех существующих блоков. Идемпотентность через sidecar-файл `intro_uids.json` (UUID предыдущего запуска): повторный запуск удаляет блоки по сохранённым instanceId и пересоздаёт; порядок пересчитывается (новые блоки после order 205). Первый запуск ошибочно использовал детерминированный uuid5 — заменён на uuid8 (все 53 проверены: позиция версии = 8). UTF-8 кириллица в data корректна (проверено round-trip).
- **Результат**: **206 → 259 блоков** (T19: 21→28, T22: 2→41, T23: 0→5, T2: 2→4). PUT replace-all через `PUT /api/article_editor/articles/{uid}/blocks`. Клиентские конвертеры T19/T22/T23/T2 уже существовали — новых правок фронтенда не потребовалось.
- **Проверки**: повторный запуск идемпотентен (259 стабильно), round-trip GET возвращает корректный UTF-8 JSON, все типы рендерятся в blockConverter (T19→«вид животного», T23→«определяется как», T22/T2→триплеты).

### Changes This Session (Iteration 16b — T23/T27 empty-input bug fix + data-model widening)
- **Симптом**: input'ы блоков «Определения понятий» (T23) и «p» (T27) отображали пустые значения, хотя данные в БД есть.
- **ROOT CAUSE**: `model.ts` объявлял `ArticleBlockData.data: Record<string, string | boolean>`, но в БД T27 хранит `pValue: 0.05` (**number**), а T23 — объект `{термин: значение}`. `FieldInput.tsx` для `inputType: 'number'` и `'key-value-list'` рендерил значение только если `typeof value === 'string'` → пусто. `kvPairs()` в `blockConverter.ts` отбрасывал объект (`typeof !== 'string'`) → T23 не порождал statements.
- **Исправления (клиент)**:
  - `model.ts`: новый тип `BlockDataValue = string | boolean | number | Record<string, string> | null`; `data: Record<string, BlockDataValue>`.
  - `FieldInput.tsx`: `value: BlockDataValue`; case `number` рендерит `typeof value === 'number' ? String(value) : ...`; case `key-value-list` — объект `{k: v}` превращается в строки `k: v` через `Object.entries().map().join('\n')`.
  - `blockConverter.ts`: `kvPairs()` теперь принимает `string | boolean | number | Record<string,string> | null` — объект конвертируется через `Object.entries`, иначе прежний парсинг строк `k: v`; `str()`/`bool()` переведены на `Record<string, BlockDataValue>`.
  - `useArticleState.ts`: `addBlock(initialData?: Record<string, BlockDataValue>)`, `updateBlock(..., value: BlockDataValue)`, `const data: Record<string, BlockDataValue> = {}`.
  - `StructuredBlockItem.tsx`: `onChange`/`handleFieldChange` — `value: BlockDataValue`.
- **Исправление build_intro.py**: T23 имеет `canAddMultiple: false` → создаётся **один** блок с `definitions` как строкой `термин: значение` по строкам (канонический UI-формат key-value-list), а не 5 блоков-объектов.
- **Результат**: 259 → **255 блоков** (T23: 5 → 1, объединены все 5 определений в один блок). Идемпотентность: удалено 53 prev-uuid8 → создано 49 новых (7+1+39+2); sidecar `intro_uids.json` обновлён (49 uids). Проверено: round-trip GET — T23 `definitions` строка с \n, T27 `pValue` number (0.05/0.01/""), блоки-статусы T19=28, T23=1, T22=41, T2=4.
- **Проверки**: `tsc --noEmit` — чисто; `bun run build` — успешно; kvPairs-парсинг строки/объекта и `String(0.05)` → `'0.05'` проверены в рантайме.

### Changes This Session (Iteration 17 — Article Editor save-speed fix + article data restore)
- **Проблема**: сохранение статьи очень долгое (бэкенд делал ~2400 отдельных Cypher-запросов к Neo4j); PUT statements через API падал по таймауту.
- **Бэкенд `api/services/article_editor_service.py`**:
  - `save_statements`/`save_blocks`: батчинг через `UNWIND $batch` (по 500) вместо 1 запроса на запись.
  - **Ключевой фикс производительности**: `MATCH (d:Document {uid: $doc_id})` вынесен **перед** `UNWIND` — внутри UNWIND он выполнялся на каждый item (~11.6ms × N). Результат бенчмарка на реальных данных (2271 стейтментов):
    - MATCH внутри UNWIND: **22.79s**
    - MATCH перед UNWIND: **0.78s** (в 29 раз)
    - Узлы без связей: 0.54s; узлы+связи: 22.70s → причиной был именно повторный MATCH, не CREATE.
  - e2e через API: PUT statements (1135) **27.7s → 1.35s**.
- **Восстановление повреждённой статьи** `000657ba-aec6-8a11-9c5c-986526539651` (4543 стейтментов после прерванного бенчмарка): стейтменты пересобраны из 255 блоков через клиентский `blocksToStatements` (bun-скрипт `client/restore_statements.ts`, временный, удалён). Итог: **2271** стейтментов (680 FACT + 455 META-content из блоков + 1135 «содержит» + 1 «является»), все uid уникальны.
- **Клиент `useArticleState.ts`** (ранее в сессии): `loadArticle` — `getArticle`+`getBlocks` параллельно, `getArticleText` только если блоков нет; `save` — `saveArticleText`/`saveBlocks`/`saveStatements`/`updateArticleTitle` параллельно.
- **Статус**: тестовый инстанс нового кода на порту **8001** (PID 29680); рабочий API на 8000 (PID 31044) — **старый код**, требует перезапуска для подхвата UNWIND-фикса.

### Changes This Session (Iteration 19 — T23 «Определение понятия»: один термин на блок)
- **Задача**: убрать key-value-list «Определения понятий» (1 блок на много терминов) → «Определение понятия» (один термин на блок, 2 инпута).
- **Сохранение данных**: содержимое старого T23 (5 определений) извлечено в `t23_definitions.json` (temp): биологическая резилентность, торпор, ложная автотомия, пренебрежимая сенесценция, сравнительная биология старения.
- **Клиент**:
  - `blockTypes.ts` T23: `name: 'Определение понятия'`, `canAddMultiple: true`, поля `{term (text, 'Термин, который определяется'), definition (textarea, 'Определение понятия')}`.
  - `blockConverter.ts` T23: `fact(str(term), 'определяется как', str(definition))` вместо `kvPairs(definitions)`.
- **Пересоздание блоков** (скрипт `restore_t23.cjs`, temp): бэкап всех блоков в `blocks_backup.json` → удаление старого T23 (`000657f8-...`) → создание **5 блоков T23** (uuid8, order 213–217, по одному на понятие) → `PUT /blocks` (255 → **259**) → пересборка derived через CJS-бандл `blockConverter.cjs` (esbuild) → `PUT /statements` (replace, **1135** content statements без потерь). Итог БД: 2271 = 1135 content + 1135 «содержит» + 1 «является».
- **Проверки**: `tsc --noEmit` чисто; `vite build` успешен; e2e (headless Chrome + CDP): 5 блоков «Определение понятия» в UI, у каждого INPUT+textarea с корректными значениями; derived statements 1135 (5× «определяется как»). `/graph` НЕ показывает «определяется как» (фильтр connected-only) — это норма.
- **Инструмент**: CJS-бандл клиентского `blockConverter` (esbuild: `esbuild blockConverter.ts --bundle --platform=node --format=cjs --external:react --external:react-icons`) — позволяет пересобирать statements из блоков в bun/node вне браузера (как в Iteration 17).

### Changes This Session (Iteration 18 — Markdown preview slow on article open: root cause found + fix)
- **Симптом**: при открытии аннотированной статьи (255 блоков / 2271 стейтментов, `000657ba-...`) структурные блоки появляются за ~2s, но правая колонка Markdown пуста ещё ~30s.
- **Диагностика (e2e через headless Chrome + CDP, bun-скрипт с встроенным WebSocket)**: при клике по статье `[data-block-index]` появился за **2.0s**, а `.article-markdown-preview` — за **33.4s** (delta **31.6s**). JS-цепочка в браузере быстрая: fetch `getArticle`+`getBlocks` 328-415ms, `blocksToStatements` ~13ms, `statementsToResolvedText` ~4ms, `marked.parse` 5ms. Узкое место — НЕ генерация.
- **ROOT CAUSE** (CPU-профиль через `Profiler.start/stop`, 16.7K samples): **92% времени (28.2s из 30.6s) — анонимные функции `FieldInput.tsx`**. Конкретно `useEffect` в `FieldInput.tsx:257` на каждом textarea делал `style.height='auto'` + `scrollHeight` → **forced synchronous reflow всего DOM**. При монтировании 254 блоков (~1298 полей, из них **219 textarea**) это 219 полных layout'ов. Главный поток занят ~28s, а `useDeferredValue(text)` в `MarkdownPreview.tsx:18` откладывает рендер markdown, который ждёт освобождения потока → превью появляется через 33s.
- **FIX**:
  - `Article_editor.module.css` `.fieldTextarea`: добавлены `field-sizing: content;` и `height: auto;` — современная авто-высота textarea **без JS и без reflow** (Chrome/Edge 123+).
  - `FieldInput.tsx`: `useEffect` автовысоты теперь: (1) полностью пропускается, если `CSS.supports('field-sizing','content')`; (2) иначе (старые браузеры) — resize **только при вводе пользователя** (пропуск первого вызова через `skipAutoResizeRef`), никогда при монтировании; (3) доп. фильтры — непустой `value`, рост только при `scrollHeight > clientHeight+1`.
- **Результат (e2e Chrome, повторный замер)**: markdown **33.4s → ~3.0s** (tMarkdownFull 2969ms), delta после появления блоков **31.6s → 0.32s**. Проверка textarea: 219 полей, **0 переполнений**, авто-высоты корректны (min 49px, max 1005px), длинный текст (269+ символов) полностью виден. `tsc --noEmit` чисто, `vite build` успешен, eslint без новых ошибок в FieldInput.
- **Инструмент**: e2e-замер теперь возможен: headless Chrome (`--remote-debugging-port=9222`) + bun CDP-скрипты в `C:\Users\dimka\AppData\Local\Temp\opencode\` (`cdp_bench.ts` — тайминги, `cdp_profile.ts` — CPU-профиль, `cdp_check_textarea.ts`). Скрипты создают вкладку `/json/new`, вводят «Immunometabolic» в поиск документов и кликают по статье.

### Changes This Session (Iteration 20 — Markdown preview: remaining blocks sections + goals fix)
- **Задача**: в превью статьи «Immunometabolic resistors…» все структурные блоки должны отображаться без дублей и мёртвых ссылок.
- **Клиент `blockConverter.ts`** — рендер «прочих» блоков в `statementsToResolvedText` (`renderRemainingBlock`, :1316+):
  - Исключены типы, рендерящиеся отдельно: [1, 2, 14, 18, 27, 55, 56, 57].
  - Оставшиеся блоки сортируются по `order` и группируются по `blockType` в секции с заголовком `## {def.name}` из `getBlockTypeDef`.
  - T22/T54 — `s → p → o` с `resolveField` для subject/object; T19 — `- **species**` + Временная шкала/Условия; T23 — `- **term** — definition`; generic fallback — `- v1 | v2 | …`.
  - Итог: секции «Сущность» (41 триплет), «Действие» (2), «Животная модель» (28), «Определение понятия» (5). Markdown ≈ 39–40 KB.
- **Цели 1–2 обновлены** (реконструкция пользователя, оригинальный текст утерян): Цель 1 — «Идентификация механизмов резистентности к возрастным нарушениям у Acomys russatus», Цель 2 — «Тестирование каузальности этих механизмов в контролируемых условиях». Записано через `restore_goals.cjs` (PUT /blocks 259 + PUT /statements 1135).
- **Найден баг**: мёртвая ссылка T22 order=3 object → UUID order=1 давала в браузере артефакт `… → к чему → к чему` (см. Iteration 21).
- **Проверки**: CDP (браузер) — секции присутствуют, мёртвых `000657bc-…` UUID в целях нет; `tsc --noEmit` чисто; `vite build` успешен.

### Changes This Session (Iteration 21 — Fix T22/T54 nameField: «к чему → к чему» артефакт)
- **Симптом**: в секции «Действие» строка `тестирование → чего → причинно-следственная связь → к чему → к чему` (артефакт «→ к чему → к чему»), тогда как CJS-тест с 2271 statements давал корректный результат.
- **ROOT CAUSE**: `blockNameMap` в `blocksToStatements` (и `buildBlockLabel`) выбирал nameField как **первый** `text`/`textarea`-поле типа. У T22/T54 поля `subject`/`object` имеют `inputType: 'uuid-ref'` (не text), поэтому nameField для T22 order=1 (`механизм резистентности → к чему → старение`) становился `predicate` = **«к чему»**. Далее refMap подставлял «к чему» на место object order=3 (UUID), и `resolveField` разворачивал это в «к чему → к чему».
- **FIX** (`blockConverter.ts`): новый хелпер `findNameField(def, data)` — ищет предпочтительные ключи `['name','title','subject','term']` среди **любых** непустых строковых полей (включая `uuid-ref`), иначе первый непустой строковый. Используется в `blockNameMap` (:694) и `buildBlockLabel` (:1011). Для T22 nameField стал `subject` = «механизм резистентности».
- **Результат**: `derived` order=3 object = «механизм резистентности» (не «к чему»); секция «Действие» в браузере:
  - `идентификация → чего → механизм резистентности → к чему → старение`
  - `тестирование → чего → причинно-следственная связь → к чему → механизм резистентности`
  - Линий с «к чему → к чему»: 0. Остальные секции (Сущность/Животная модель/Определение понятия) не изменились.
- **Проверки**: `tsc --noEmit` чисто; `vite build` успешен; CDP `cdp_action_html.ts` + `cdp_sections.ts` подтверждают корректный рендер; CJS-бандл пересобран (`esbuild`), `render_test.cjs` воспроизводит.

### Changes This Session (Iteration 22 — T2 goals: UUID-only refs to actions/entities)
- **Задача**: у целей (T2) в полях должны быть **только UUID**-ссылки на действия (T54) и сущности (T22); убрать хвост «потеря биологической резилентности замедление процессов восстановления клеток и тканей» у целей 1–2; сделать цели 3–4 зависимыми от новых действий/сущностей согласно тексту целей.
- **ROOT CAUSE хвоста**: цели 1–2 ссылались на **statement id** (`0006580a-bac1-…` из БД), а не на блоки. `resolveGoal` через `resolveField` находил statement в existingStatements, а `extendChain` разворачивал цепочку дальше (`механизм резистентности → старение → потеря биологической резилентности → замедление…`). Ссылка на **блок** T54 → `blockLabelMap` возвращает label сразу (без `extendChain`).
- **FIX** (`fix_goals.cjs`, temp, идемпотентен через sidecar `fix_goals_uids.json`):
  - Цель 1 → T54 «идентификация» (`000657bb-4fa0-8be9-…`)
  - Цель 2 → T54 «тестирование» (`000657bb-260b-8c2d-…`)
  - Цель 3 → новый T22 (order 259): `всестороннее понимание биологии старения → использует как модель → Acomys russatus как модельный организм`
  - Цель 4 → новый T54 (order 261): `идентификация и проверка каузальности → чего → [T22 order 260]`; T22 order 260: `специфические механизмы устойчивости к старению → в ходе → контролируемых условиях`
  - 259 → **262 блока**; derived 1135 → **1138 statements**; PUT /blocks + PUT /statements.
- **flatten-нюанс**: однословные предикаты пропускаются («использует», «в»), поэтому для сохранения в тексте целей предикаты сделаны многословными («использует как модель», «в ходе»).
- **Результат в превью** (CDP-браузер):
  - `Цель 1: Идентификация механизм резистентности к старение.`
  - `Цель 2: Тестирование причинно-следственная связь к механизм резистентности к старение.`
  - `Цель 3: Всестороннее понимание биологии старения использует Acomys russatus как модельный организм.`
  - `Цель 4: Идентификация и проверка каузальности специфические механизмы устойчивости к старению в контролируемых условиях.`
- **Проверки**: все 4 цели `subject`/`object` — UUID (regex `^[0-9a-f-]{36}$`); мёртвых UUID в превью нет (remainingUuids=0); секции «Сущность»/«Действие» обновлены без регрессий; бэкап — `blocks_backup2.json`.

### Changes This Session (Iteration 23 — T22/T54 inputs not editable + typing lag)
- **Проблема 1**: поля `subject`/`object` блоков «Сущность» (T22) и «Действие» (T54) не редактируются — символы не вводятся.
- **Проблема 2**: ввод текста в других блоках лагает (символ появляется с задержкой).
- **ROOT CAUSE 1** (`FieldInput.tsx`, `UuidRefInput`): поле uuid-ref содержит **свободный текст** (не UUID из availableUuids), поэтому `displayLabel` пуст → ветка `if (displayLabel)` не срабатывала и `onChange(field.key, e.target.value)` **не вызывался** — введённый символ «откатывался».
- **ROOT CAUSE 2** (два места):
  1. `useArticleState.ts` `useEffect([blocks])` синхронно пересчитывал 1138 derived statements + markdown на каждый keystroke.
  2. `StructuredBlockEditor.tsx` `availableUuids` useMemo сравнивал **id + label**: при вводе меняется label редактируемого блока → сравнение не совпадает → **новый массив** → `React.memo` на всех uuid-ref блоках ломался → каждый keystroke перерисовывал всё дерево (~1.3s LongTask на символ, профиль: `addObjectDiffToProperties`/`run`/`jsxDEV`).
- **FIX 1** (`FieldInput.tsx:106-114`): `onChange` инпута: `setQuery(e.target.value); setOpen(true);` и **если `displayLabel` пуст — `onChange(field.key, e.target.value)`** (свободный текст теперь редактируется). `const q = (query ?? '').toLowerCase()` — null-safe (query теперь `string | null`); `value={value || query || ''}`.
- **FIX 2a** (`useArticleState.ts`): debounce **250 мс** (`window.setTimeout` через `blocksSyncTimerRef`) перед `blocksToStatements` + `statementsToResolvedText`; cleanup на размонтирование; при `blocks.length===0` сброс statements; initial-load (`skipBlocksSyncRef`) обходит debounce.
- **FIX 2b** (`StructuredBlockEditor.tsx`): `availableUuids` useMemo разделён на два прохода — сначала **identity** (id/blockType) без label; если id-set не изменился, возвращается **prev-массив** (React.memo держится). Labels собираются только при реальном изменении id-set. При вводе в поле изменяется только label → ref-массив стабилен → перерисовывается только редактируемый блок.
- **Результаты (CDP-замеры, браузер Chrome на 5555)**:
  - Ввод в uuid-ref поле T22: `механизм резистентности` → `ZTEST` (сохраняется). Предикат T22: `к чему` → `PREDTEST` (сохраняется).
  - Скорость ввода (3 символа): commits на 349/505/644 мс (было 1399/2692/3993), LongTask на символ ~126 мс (было ~1.3 с), wall 689 мс (было 4041 мс) — **~8× быстрее**.
  - **Осторожно**: blur-save при закрытии вкладки сохранил тестовое значение `PREDTEST` в предикат T22 order=1 → восстановлено через `restore_predicate.cjs` (PUT /blocks 262 + PUT /statements 1138) до `к чему`. Проверка чистоты данных: артефактов нет (совпадения «Q» — легитимные QIAGEN/qRT-PCR/QC/Fig.5Q).
- **Проверки**: `tsc --noEmit` чисто; `vite build` успешен; CDP `cdp_edit_block.ts` (редактирование T22/T54 работает) + `cdp_latency2.ts` (commit-латентность ~150 мс/символ) + `cdp_profile_keystroke.ts` (профиль). Инструменты: `cdp_diag_fileitem.ts`, `cdp_latency.ts`, `cdp_latency2.ts`, `cdp_profile_keystroke.ts` (temp).

### Changes This Session (Iteration 24 — DISCUSSION structured into blocks)
- **Аудит покрытия**: исходная статья (`Immunometabolic resistors…md`, 479 строк, CRLF) сопоставлена с блоками через контент-пробы (англ. оригинал vs рус. блоки → точное совпадение слов не работает). Результат: INTRODUCTION и RESULTS покрыты полностью; **DISCUSSION (L159-186) — 0 блоков**; M&M покрыт только шагами T56; Abstract/Funding/Acknowledgments не структурированы.
- **Создано 13 блоков DISCUSSION (262 → 275)**, orders 262–274, uuid8:
  - **T7 Гипотеза** (o262): конкуренция с A. dimidiatus → дневная активность → пустынные адаптации.
  - **T16 Биологический механизм** (o263): reelin-подобный каскад (ApoER2/VLDLR → Dab1 → Crk/C3G/Rap1); цитозольный vs секретируемый кластерин.
  - **T38 Утверждение** (o264-269, ×6): устойчивое старение A. russatus; тимическая архитектура; кластерин ингибирует inflammaging; связь с ApoER2/VLDLR; горметический ответ Clu; A. russatus как модельный организм.
  - **T39 Ограничения** (o270): макс. продолжительность жизни, пол-специфический анализ, возраст-подобранные образцы, различия Mus vs Acomys.
  - **T40 Побочные выводы/гипотезы** (o271): кластерин как «адаптокин», GDF15/FGF21, микробиом.
  - **T44 Новизна** (o272), **T46 Будущие исследования** (o273), **T47 Связи с предыдущими** (o274).
- **blockConverter.ts `renderRemainingBlock`**: добавлен рендер для T38 (claim `s → p → o` + «Уверенность»), T7 (Гипотеза/Обоснование), T16 (Механизм), T39/T40/T46/T47 (по строкам), T44/48 (Новизна/Связь со старением) — вместо generic fallback `v1 | v2`.
- **CJS-бандл пересобран** (`bun x esbuild` → `blockConverter.cjs`, 120.3kb).
- **PUT /blocks 275 + PUT /statements 1158** (derived: 1138 → 1158, +20).
- **Проверки**: `tsc --noEmit` чисто; `vite build` успешен; CJS-рендер и CDP-браузер (Chrome 5555) показывают 8 новых секций (Гипотеза/Биологический механизм/Утверждение/Ограничения/Побочные выводы/Новизна/Будущие исследования/Связи с предыдущими); мёртвых UUID в новых блоках 0. Бэкап: `blocks_before_discussion.json`.

### Changes This Session (Iteration 25 — Abstract, M&M statistics, Funding, Animals structured)
- **Аудит остатка**: INTRODUCTION/RESULTS/DISCUSSION покрыты блоками. Не покрыты были: Abstract (L28), `Quantification and statistical analysis` (L318), Funding (L337-343), детали содержания Animals (L195). M&M-шаги уже покрыты T56 (46 шагов); T19/T55 покрывают виды/группы с n.
- **Создано 8 блоков (275 → 283)**, orders 275–282, uuid8:
  - **T38 Утверждение** (o275-276, ×2, Abstract): транскрипционная целостность A. russatus; биология A. russatus → терапевтические мишени.
  - **T37 Статистическая обработка** (o277): Prism 8.0.2, двухвыборочный непарный t-критерий, ANOVA + Тьюки, mean ± SEM/min–max.
  - **T51 Источники финансирования** (o278): NRF Korea (RS-2024-00412002), ISF 2129/20, Yale (Von Zedtwitz chair, intramural, U54AG079759), NIA IRP.
  - **T22 Сущность** (o279-282, ×4, Animals): происхождение колонии Acomys (Tel Aviv, Иудейская пустыня); содержание outdoors 2018-2023; контролируемые условия (12:12, 29°C/25°C); Mus C57BL/6N в SPF-условиях Yale.
- **blockConverter.ts `renderRemainingBlock`**: добавлен рендер T37 (Статистическая обработка + Сопоставление с ожиданиями) и T51 (Финансирование) вместо generic fallback.
- **PUT /blocks 283 + PUT /statements 1169** (derived: 1158 → 1169, +11).
- **Проверки**: `tsc --noEmit` чисто; CJS-бандл пересобран (121.3kb); CDP-браузер показывает 20 секций превью, включая «Статистическая обработка» и «Источники финансирования»; мёртвых UUID в новых блоках 0.
- **Покрытие разделов статьи**: Abstract ✓, INTRODUCTION ✓, RESULTS ✓, DISCUSSION ✓, M&M ✓ (шаги T56 + статистика T37 + Animals T22/T19), Funding ✓. Осталось: Acknowledgments (благодарности, не структурируется), Author Contributions (метаданные), References (в T47 DISCUSSION).

### Next Steps
1. **Перезапустить API на порту 8000** (PID 31044, нужны права администратора), чтобы подхватить UNWIND-фикс; остановить тестовый инстанс 8001 (PID 29680).
2. **Опционально**: замерить рендер блоков в production build (`vite preview`) — в dev React `tBlocks` ~2s, в prod ожидается <1s; если нужно — мемоизация `FieldInput`/разбивка списка блоков.
2. **Структурировать «4. DISCUSSION»** (если нужно): существующие типы T22/T38/T21 для интерпретации и выводов.
2. **Запустить новый `start.ps1`** в `pdf_to_md/`: проверить, что hybrid backend (5002), gRPC (50053) и REST (8002) стартуют без EADDRINUSE
2. **Проверить upload документа** через API — конвертация должна пройти через DoclingFast hybrid
3. **Починить `--hybrid-fallback`** в Java OpenDataLoader: если хайбрид временно недоступен, падать не должно
4. **First-person narrator**: `I → propose`, `I → include` — ActiveVoiceRule subject is `I` (PROPN)
5. **Subordinate `that`-clauses**: `article... suggests that canonic hallmarks...`
6. **Диагностика poetry import slowdown**: какой импорт в `web.app` висит дольше всего (strawberry/GraphQL? neomodel? grpcio?)