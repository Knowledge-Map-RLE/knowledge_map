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
1. 8 extraction rules: copular, passive_voice, active_voice, coordination, negation, causal, temporal, relative_clause.
2. gRPC server on 50056, auto-proto-generation, `en_core_sci_scibert` via `spacy-transformers`.
3. NLP service fixed: `CUDA_VISIBLE_DEVICES="0"` in `nlp/start.ps1`, removed `spacy-curated-transformers`.
4. Direct pipeline test suite: `tests/articles/test_pipeline_direct.py` (bypass gRPC for fast iteration).
5. 84 ground truth triplets for Hallmarks of PD article.
6. **PassiveVoiceRule**: Rewritten with forward-direction (preserve passive: `X → be VERBed by → Y`), `nsubjpass`/`auxpass`/`nmod` labels, `"by"`/`"via"` agent prepositions (via→by normalized), recursive coordination chain (`_collect_conjuncts`), case/excluded deps stripped from agent text.
7. **CopularRule**: EXCLUDED_DEPS extended (`mark`, `acl`, `relcl`, `advcl`, `ccomp`, `xcomp`), xcomp-chain fallback for nsubj.
8. **AsRoleRule**: New rule for `X as Y` → `X → be → Y` (noun pattern: `discovery of X as Y`, verb pattern: `reveal X as Y`). Handles both `case` and `mark` dependency labels.
9. **ConceptNormalizerImpl**: Strips leading determiners (a/an/the) and singularizes (populations → population).
10. **ActiveVoiceRule**: Verb coordination support (`_collect_verbs` recursive conj chain). Post-object advmod inclusion (populations worldwide → object text includes "worldwide"). Inter-verb copula check instead of blanket tree-level check.
11. **Word-subsequence matching**: `_contained_in` in `conftest.py` uses word-order subsequence (not contiguous substring), e.g. GT "age-related disease" matches pipeline "age-related multifactorial disease".
12. **ACL-participle passive**: PassiveVoiceRule extended to handle reduced relative clauses (past participial modifiers with dep=acl + by-agent), e.g. `disease, influenced by factors` → `PD → be influenced by → factors`. Subject resolved from head noun's copular nsubj.
13. **ActiveVoiceRule relative pronoun resolution**: `_resolve_subject` + `_head_phrase_text` resolves `that`/`which` → antecedent with premodifiers only (no clausal descendants). Handles: `nonmotor symptoms that precede disorder` → `nonmotor symptoms → precede → typical movement disorder`.
14. **ActiveVoiceRule object truncation**: `_object_text` excludes relative clauses and `such as` nmod subtrees, producing clean object text (e.g. "typical movement disorder" without "such as hyposmia...").
15. **CopularLikeRule**: New rule for `represent`/`constitute`/`form` → `be`. Handles `aging represents risk factor` → `aging → be → risk factor`.
16. **SuchAsRule**: New rule for `such as`/`including` → `include`. Resolves through nmod → relcl → antecedent chain. Handles `symptoms, such as hyposmia, depression` → `nonmotor symptoms → include → hyposmia/depression/etc`.
17. **Singular/plural tolerance**: `_words_match` now handles `-ies → -y` (studies ↔ study) and `-es → ∅` (processes ↔ process).
18. **MultiWordPredicateRule** (working): New rule for `start prior to`, `arise from`, `present as`, `lead to`, `evolve into`. Handles 1-word seq (`arise from`: verb → nmod → case prep), 2-word seq (`start prior to`: verb → advmod(prior) → nmod(onset) → case(to)).
19. **ActiveVoiceRule xcomp fallback**: Verbs like `involve` with xcomp (not dobj/obj) produce statements: `treatment → involve → substituting dopamine`. Handles xcomp conj chain with individual statement per xcomp verb.
20. **`split_sentences` markdown fix**: `conftest.py` strips markdown headers (`## ...`) before sentence splitting, preventing header/inline merge. Enabled match for `IPD → be → age-related disorder`.
21. **Test scope expanded**: from `[:30]` to `[:60]` sentences (222 total in article), covering more ground truth.
22. **WithHaveRule**: `X with Y` → `X → have → Y`. Splits adjectival conjunctions (`dominant or recessive` → two statements). Relies on `case=with` nmod children of nouns.
23. **PassiveVoiceRule non-agent preps**: Extended `AGENT_PREPOS` to include `to`, `in`, `for` alongside `by`, `via`. Handles `be linked to` (4 triplets in sent 47: `living`, `gardening`, `farming`, `occupational exposure`).
24. **NamedRule**: New rule for `named`/`called`/`termed` (acl) → `be`. Handles `an atypical form ... named Kufor-Rakeb syndrome` → `atypical form of PD with dementia → be → Kufor-Rakeb syndrome`.
25. **AdjectivePrepositionRule**: `X → be ADJ prep → Y` for ADJ/VERB + cop/aux + nmod/advcl(for/in/at). Handles `be important for`, `be lacking in`. Splits coordinated subjects (PINK1 and Parkin → two statements).
26. **CopularRemainRule**: `X remains Y → X → remain → Y` for `remain`/`stay`/`become` + xcomp. Handles `exact role → remain → elusive`.
27. **TemporalComparisonRule**: `X increases when Y increases → X → increase when → Y`. Handles `level of DJ-1 → increase when → cellular levels of ROS increase`.
28. **ActiveVoiceRule post-obj nmod**: Extended `_object_text` to include `from`/`into` post-object nmod subtrees. Handles `protect → neurons from cell death`.
29. **MultiWordPredicateRule extended**: Added `translocate to/from`. Handles `oxidized form of DJ-1 → translocate to → mitochondrial outer membrane`.
30. **Test scope expanded**: from `[:60]` to `[:100]` sentences, auto-capturing `be controlled by` (via→by), `be involved in` (in prep), `dysfunction → be hallmark`, `facilitate → accumulation` (6 new matches).
31. **ActiveVoiceRule `for` in post-obj nmod**: Added `for` to post-object nmod inclusion. Handles `astrocytes → play → supportive role for brain neurons` (was `supportive role` without `for brain neurons`).
32. **Test scope fixed to full article**: `[:222]` (all 222 sentences), capturing `PD research → evolve into → very mature research field` (sent 214, was outside previous `[:200]` scope).

### Current Coverage
- **72/84 (85.7%)** on Hallmarks of PD article (all 222 sentences).
- +2 this session (70→72): post-obj `for` fix (1: play supportive role for brain neurons), scope expansion to 222 (1: evolve into).

### Key Patterns Still Missed
- `REM sleep behavior disorder → start prior to` (REM ≠ Rapid Eye Movement abbreviation)
- `cell-based view → improve → communication` (complex gerund in "with the aim of")
- `many chromosomal regions → be identified by` (anaphora: "many of those" → antecedent)
- `Lewy bodies → be lacking in → affected carriers` (word-order: "mutations in the Parkin gene" vs GT "Parkin mutations")
- `body of knowledge → be → rich/complex` (inferred from "rich and complex body", LLM territory)
- `PD research field → develop → arsenal of symptomatic treatments` (relcl antecedent semantic interpretation: pipeline picks "very mature research field" as subject, GT prefers "PD research field")
- 4 META UUID-subject triplets (LLM territory)