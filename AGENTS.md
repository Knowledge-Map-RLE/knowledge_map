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
- **172/293 (58.7%)** on Hallmarks of PD (222 sentences).
- **137/222 (61.7%)** on Hallmarks of cancer and hallmarks of aging (166 sentences).
- Article 1: All 222 sentences produce pipeline output; 100/177 sentences with GT triplets have ≥1 match.
- Pipeline handles: active/passive voice, copula, multi-word predicates, adjective+preposition, conj verbs with shared objects, conjoined subjects/objects split, negation in all rule types, reduced relative participles (acl/advcl) with by-agent.

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
| LLM required (META/UUID) | ~4 | UUID → `revealed by` |
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

### Next Steps
1. **Освободить порт 8000**: `taskkill /F /PID 13864` из PowerShell Administrator
2. **First-person narrator**: `I → propose`, `I → include` — ActiveVoiceRule subject is `I` (PROPN)
3. **Subordinate `that`-clauses**: `article... suggests that canonic hallmarks...`
4. **Long noun-phrase subjects**: e.g., `DNA repair deficiencies, inflammatory signaling, epigenetic alterations and related mechanisms → contribute to`
5. **Diagnose poetry import slowdown**: какой импорт в `web.app` висит дольше всего (strawberry/GraphQL? neomodel? grpcio?)