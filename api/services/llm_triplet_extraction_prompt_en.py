"""English-language prompts for LLM extraction of block structure.

Unified one-stage prompt for whole-article extraction. Replaces the two-stage
(Structure → Atomize) approach with a single LLM call that produces all block
types including T4 triplets, T58 action dependencies, and T59 temporal relations.

This design is optimized for downstream pattern analysis of action dependencies
(successful/unsuccessful goal-achievement patterns in Neo4j).

Placeholders: __ARTICLE_TITLE__, __ARTICLE_TEXT__.
JSON braces are single (substituted via ``str.replace``, no ``.format``).
"""

PROMPT_UNIFIED_TEMPLATE_EN = """You are a knowledge representation expert extracting structured knowledge blocks from a scientific article.

# Task

Extract ALL knowledge blocks from the complete article below. Output container blocks (T1–T59) and atomic T4 triplets in a single JSON response.

# Input

Full article: «__ARTICLE_TITLE__»

--- ARTICLE START ---
__ARTICLE_TEXT__
--- ARTICLE END ---

# Block Catalog

Output ONLY these types and fields (omit empty fields):

- **1 Metadata** (META-STATEMENT — contains ALL authors): `doi`, `title`, `authors` (FULL array — every single author from the article, not abbreviated). Only once. This is a meta-block: it represents the entire article as a single entity. All author names must be included.
- **2 Research goal** (multiple allowed, up to 8): `subject` (2-3 words), `predicate` (1-2 words, e.g. "goal", "aims"), `object` (3-8 words — ONE atomic sub-goal, NOT a compound sentence). Break compound goals into multiple T2 blocks with `dependsOn` (array of `{Bn}` tags to prerequisite T2 blocks). Example: "reexamine hallmarks of cancer" → T2, "propose hallmarks of aging" → T2 (dependsOn: ["{B2}"]), "distinguish life-limiting hallmarks" → T2 (dependsOn: ["{B3}"]). Each T2 object must be a SINGLE concise statement — if the goal has multiple parts, split into separate T2 blocks.
- **7 Hypothesis** (META-STATEMENT — concise): `hypothesis` (1-2 sentences MAX — the core hypothesis, NOT a detailed explanation), `disproofExplanation` (1-2 sentences MAX). This is a meta-block: keep it SHORT. Detailed facts about the hypothesis are decomposed into T4 triplets that reference this block via `{Bn}` tag.
- **14 Experiment** (MANDATORY — every article must have at least 1): `experimentName`, `experimentType` (select: Behavioral, Histology, RNA-seq, In vivo intervention, In vitro, Computational, Review synthesis), `outcomes` (array), `steps` (array of tags `{Bn}` → T56 — MANDATORY), `findings` (array of tags `{Bn}` → T57 — MANDATORY), `duration`, `experimentalPairs` (array of objects `{"groupRef": "{Bn}"}` → T55 experimental groups — MANDATORY), `controlPairs` (array of objects `{"groupRef": "{Bn}"}` → T55 control groups — MANDATORY if control group exists). For review articles: create T14 with experimentType="Review synthesis".
- **16 Biological mechanism**: `mechanism` (text).
- **18 Intervention**: `intervention`, `dosage`, `dosageRegimen`.
- **19 Animal model**: `species`, `timeline`, `conditions`.
- **20 Conclusions**: `conclusions`.
- **22 Entity**: `subject`, `predicate`, `object` (text).
- **23 Concept definition**: `term`, `definition`.
- **27 p-value**: `pValue` (number). One block per unique p-value.
- **37 Statistical processing**: `statProcessing`, `expectationsComparison`.
- **38 Claim**: `claimSubject`, `claimPredicate` (one of: is, causes, inhibits, activates, correlates with, affects, is associated with, determines, contains, participates in, modulates, neutralizes, prevents, induces, leads_to, requires, depends_on, triggers, suppresses, enhances, promotes, impairs), `claimObject`, `confidenceNotes`, `isNegated` (true/false).
- **39 Study limitations**: `limitations`.
- **40 Side findings/hypotheses**: `sideFindings`.
- **44 Novelty**: `novelty`.
- **46 Future research**: `futureResearch`.
- **47 References**: `references`.
- **51 Funding**: `funding`.
- **54 Action**: `subject` (2-3 words), `predicate` (1-2 words), `object` (2-3 words). Concise noun phrases only.
- **55 Animal group**: `groupName`, `n`, `conditions`, `purpose`.
- **56 Experiment step**: `stepName`, `details`, `duration`.
- **57 Result (finding)**: `parameter`, `direction` (increased/decreased/no change/trend), `significance` (significant/non-significant/trend), `pValue` (tag `{Bn}` of T27 block OR number), `figureRef` (e.g. "Fig. 1F"), `detail`, `interventionRef` (tag `{Bn}` → T18/T54 — MANDATORY when this finding follows from an intervention; omit only for observational findings), `outcomeClass` (positive/negative/neutral).
- **58 Action dependency** ⭐ (CRITICAL for pattern analysis): `source` (concise text, 2-5 words, e.g. "mTOR hyperfunction"), `target` (concise text, 2-5 words, e.g. "cellular senescence"), `relationType` (one of: causes, enables, requires, precedes, inhibits, prevents, leads_to, enhances, suppresses), `confidence` (high/medium/low), `evidence` (SHORT text description of supporting fact, 3-8 words — NOT a `{Bn}` tag reference, since T4 blocks have no tags).
- **59 Temporal relation**: `earlier` (tag `{Bn}` → T56/T54 — MUST exist in this response), `later` (tag `{Bn}` → T56/T54 — MUST exist in this response), `relationType` (precedes/follows/during). Only output T59 if BOTH referenced blocks exist. Do NOT reference T4 blocks (they use `{SEQn}`, not `{Bn}`).

# T1 Metadata — META-STATEMENT

T1 is a meta-block that represents the entire article. It must contain:
- `doi`: the DOI from the article
- `title`: the full title
- `authors`: FULL array of ALL author names — do NOT abbreviate or omit any author. Include every author listed in the article.

T1 is resolved by the service into UUIDv8. All references to T1 use the `{Bn}` tag assigned to it.

# T2 Research Goals — MULTIPLE ALLOWED, DECOMPOSED INTO TRIPLETS

Break compound research goals into individual T2 triplet blocks with dependencies.

Each T2 must be ONE atomic goal (3-8 words in `object`). If the article states "we aim to X, Y, and Z", create THREE T2 blocks:
- T2: subject="we", predicate="goal", object="X"
- T2: subject="we", predicate="goal", object="Y", dependsOn=["{Bn_X}"]
- T2: subject="we", predicate="goal", object="Z", dependsOn=["{Bn_Y}"]

The `dependsOn` field (array of `{Bn}` tags) captures goal decomposition: which sub-goals must be achieved before this one. If a goal has no prerequisites, omit `dependsOn`.

Most articles have 3-8 T2 blocks (not just 2-4 compound ones).

Examples for an article about aging in spiny mice:
- T2({B2}): subject="we", predicate="goal", object="identify mechanisms of aging resistance"
- T2({B3}): subject="we", predicate="goal", object="test clusterin role in inflammaging", dependsOn=["{B2}"]
- T2({B4}): subject="we", predicate="goal", object="characterize immunometabolic biology", dependsOn=["{B2}"]
- T2({B5}): subject="we", predicate="goal", object="identify druggable targets", dependsOn=["{B3}", "{B4}"]

# T7 Hypothesis — META-STATEMENT (SHORT)

T7 is a meta-block. The `hypothesis` field must be 1-2 sentences MAX — the CORE claim, not a detailed explanation. The `disproofExplanation` must also be 1-2 sentences MAX.

Keep T7 SHORT because detailed facts about the hypothesis are decomposed into T4 triplets that reference T7 via `{Bn}` tag. Do NOT put a long explanation in T7.

# T14 Experiments — MANDATORY SEQUENCE LINKS

Every T14 MUST have:
- `steps`: array of `{Bn}` tags referencing T56 blocks (the steps of this experiment)
- `findings`: array of `{Bn}` tags referencing T57 blocks (the results of this experiment)
- `experimentalPairs`: array of objects `{"groupRef": "{Bn}"}` referencing T55 blocks that are the EXPERIMENTAL groups for this experiment
- `controlPairs`: array of objects `{"groupRef": "{Bn}"}` referencing T55 blocks that are the CONTROL groups (omit if no control group)

The linking chain MUST be complete: T14 → T55 groups + T56 steps + T57 findings + T18 interventions.

If you cannot reference specific T56/T57 blocks (because they haven't been output yet), output the T56/T57 blocks FIRST, then reference them in T14. The ordering rule: output T55 groups, T18 interventions, T56 steps, and T57 results BEFORE the T14 that references them.

For review articles (experimentType="Review synthesis"): the experimentalPairs/controlPairs may be omitted since there are no experimental groups.

# {Bn} Tags → UUID Resolution

You output `{Bn}` tags (e.g. `{B1}`, `{B15}`) as references between blocks. The service resolves these tags to real UUIDv8 identifiers after extraction. You do NOT need to generate UUIDs — just use consistent `{Bn}` tags.

Rules for {Bn} references:
- Every `{Bn}` you reference must be output in this same response as a block with `"tag": "{Bn}"`.
- T4 blocks have NO tag — they are identified by position and get UUIDs via `{SEQn}`.
- Do NOT embed block objects inside fields — only tag strings like `"{B1}"`.

# T57 Results — MANDATORY INTERVENTION LINKING

Every T57 finding MUST link to its source:
- If the finding follows from an intervention (drug, treatment, procedure — must be a T18 or T54 block): `interventionRef` = `{Bn}` tag → T18 or T54 block — MANDATORY
- If the finding is from an observational experiment (behavioral test, histology, RNA-seq, sequencing) with NO intervention: OMIT `interventionRef` entirely
- If the finding has a p-value: `pValue` = `{Bn}` tag → T27 block — MANDATORY
- `parameter` (2-5 words): the measured variable or outcome (e.g. "grip strength", "IL-1β level")
- `direction`: increased / decreased / no change / trend
- `significance`: significant / non-significant / trend
- `outcomeClass`: positive / negative / neutral

Example WITH intervention: clusterin treatment improves grip strength → T57(parameter="grip strength", direction="increased", significance="significant", interventionRef="{Bn_clusterin_T18}", pValue="{Bn_pvalue_T27}", outcomeClass="positive")

Example WITHOUT intervention (observational): aged A. russatus shows no change in rearing → T57(parameter="rearing behavior", direction="no change", significance="significant", figureRef="Fig. 1F", outcomeClass="positive")

**interventionRef MUST point to a T18 or T54 block — NEVER to T37, T56, or any other type.**
- T18 = the substance/procedure itself (e.g. "recombinant mouse clusterin")
- T54 = an action/process (e.g. "clusterin → suppresses → inflammaging")
- T56 = an experiment STEP (e.g. "inject clusterin daily") — this is NOT an intervention, do NOT reference it from T57
- If no T18/T54 intervention applies, omit interventionRef

# T58 Action Dependencies — CRITICAL

**T58 is the most important block type for downstream analysis.** Every causal, enabling, or inhibitory relationship between biological actions, mechanisms, and outcomes MUST be captured as a T58 block.

**When to create T58:**
- Text says X "causes", "leads to", "results in", "drives", "promotes" Y
- Text says X "inhibits", "suppresses", "prevents", "blocks" Y
- Text says X "is required for", "enables", "is necessary for" Y
- Text says X "precedes" Y in a biological cascade
- Text says X "enhances", "amplifies" Y
- Any mechanistic link between entities at different hierarchical levels

**Examples:**
- "aging → drives → inflammaging" → T58(source="aging", target="inflammaging", relationType="causes", evidence="aging increases inflammatory markers")
- "mTOR hyperfunction → leads to → age-related diseases" → T58(source="mTOR hyperfunction", target="age-related diseases", relationType="leads_to", evidence="mTOR activation drives pathologies")
- "rapamycin → inhibits → mTOR" → T58(source="rapamycin", target="mTOR", relationType="inhibits", evidence="rapamycin blocks mTOR signaling")

**Priority:** T58 blocks are HIGH priority. Extract them even if uncertain (use confidence=medium/low). Missing a causal link is worse than extracting a weak one.

**source, target, and evidence must be SHORT TEXT (2-5 words each), NOT `{Bn}` tag references.**

# T59 Temporal Relations

Capture temporal sequences between experimental steps or biological events. BOTH `earlier` and `later` must be `{Bn}` tags of blocks that exist in this response (typically T56 steps or T54 actions).

- "first X, then Y" → T59(earlier=`{Bn_X}`, later=`{Bn_Y}`, relationType="precedes")
- "X occurs during Y" → T59(earlier=`{Bn_Y}`, later=`{Bn_X}`, relationType="during")

**Do NOT create T59 if:** the referenced blocks don't exist, or if you'd have to reference T4 blocks (T4 uses `{SEQn}`, not `{Bn}`). Skip T59 rather than create broken references.

# Decomposition Rules

One T4 triplet = one simple fact (subject → predicate → object). Each S/P/O is 1-3 words except indivisible terms.

**Predicates (semantic role):** `whom`/`what`/`which`/`what kind`/`where`/`when`/`how much`/`how long`/`for what`/`in what`/`from what`/`with what`/`to what`/`after what`/`before what`.

**Cross-references:** When a term is already decomposed by a T4 triplet in this response, reference it as `{SEQn}` (n = ordinal number of that triplet in the blocks array). ~20-30% of T4 triplets should contain such references.

**Decomposition by container type:**
- **T1 (Metadata)**: decompose into T4 triplets about authors, DOI, title, journal. Usually 3-5. Each T4 references T1 via container tag.
- **T7 (Hypothesis)**: decompose the hypothesis into individual claims. Usually 5-10 T4 triplets covering the core claim, evidence, and disproof logic.
- **T56 (Step)**: each procedure element → separate T4. Usually 5-10.
- **T57 (Result)**: unfold parameter, group, direction, significance, p, figure. Usually 3-6.
- **T19 (Model)**: species + conditions + lifespan. Usually 3-5.
- **T38 (Claim)**: subject/predicate/object + confidence + scope. Usually 3-5.
- **T14 (Experiment)**: name + type + each included test. Usually 2-5.

# Expected Scale (review article ~275 lines)

- T1 metadata: 1
- T2 goals: 4-8 (decomposed triplets with dependsOn)
- T7 hypothesis: 1
- T4 triplets: 15-25
- T22 entities: 5-10
- T38 claims: 6-12
- T54 actions: 3-5 (concise: 2-3 words per field)
- T58 action deps: 12-20
- T59 temporal: 3-8 (only for existing T56/T54 blocks)
- T14 experiments: 3-8 (MANDATORY, including Review synthesis for review articles)
- T56 steps: 15-30
- T57 results: 20-50
- T55 groups: 10-25
- T19 models: 5-15

# Output Order

1. T1 Metadata
2. T2 Goals (all of them)
3. T7 Hypothesis
4. T19 Animal models, T55 Groups
5. T56 Steps → T57 Results → T27 p-values (BEFORE T14)
6. T14 Experiments (with tags to T56/T57 from step 5)
7. T54 Actions → T58 Action dependencies
8. T59 Temporal relations
9. T22 Entities, T23 Definitions
10. T38 Claims
11. T16 Mechanism, T18 Interventions
12. T37 Statistics
13. T39/T40/T44/T46/T47 Discussion elements
14. T51 Funding
15. T4 Atomic triplets (last, referencing all above via {Bn} tags)

# Output Format

JSON only, no explanations:

{"blocks": [
  {"blockType": 1, "tag": "{B1}", "data": {"doi": "...", "title": "...", "authors": ["Author One", "Author Two", ...]}},
  {"blockType": 2, "tag": "{B2}", "data": {"subject": "we", "predicate": "goal", "object": "reexamine hallmarks of cancer"}},
  {"blockType": 2, "tag": "{B3}", "data": {"subject": "we", "predicate": "goal", "object": "propose hallmarks of aging", "dependsOn": ["{B2}"]}},
  {"blockType": 7, "tag": "{B4}", "data": {"hypothesis": "Short 1-2 sentence hypothesis.", "disproofExplanation": "Short 1-2 sentence disproof."}},
  {"blockType": 56, "tag": "{B10}", "data": {"stepName": "...", "details": "..."}},
  {"blockType": 57, "tag": "{B15}", "data": {"parameter": "...", "direction": "increased", "significance": "significant", "pValue": "{B20}", "figureRef": "Fig. 1F", "interventionRef": "{B8}", "outcomeClass": "positive"}},
  {"blockType": 14, "tag": "{B20}", "data": {"experimentName": "...", "experimentalPairs": [{"groupRef": "{B10}"}], "steps": ["{B10}", "{B11}"], "findings": ["{B15}", "{B16}"]}},
  {"blockType": 58, "tag": "{B25}", "data": {"source": "mTOR hyperfunction", "target": "age-related diseases", "relationType": "causes", "confidence": "high", "evidence": "mTOR drives pathologies"}},
  {"blockType": 4, "data": {"subject": "...", "predicate": "...", "object": "..."}},
  ...
]}

# Hard Rules

1. Every `{Bn}` referenced in data must exist as a tag in this response.
2. T4 blocks have NO `tag` field — they are identified by position in the array.
3. Do NOT output duplicate blocks for the same entity/step/result.
4. Numeric results (p-values, n, years, percentages) must NOT be lost.
5. Do NOT output T54 for author contribution credits (CRediT roles).
6. No markdown, no explanations outside JSON.
7. T14 steps/findings arrays are MANDATORY — every experiment must reference its steps and results.
8. T1 authors array must contain ALL authors — no abbreviations, no omissions.
9. T7 hypothesis must be SHORT (1-2 sentences) — it is a meta-statement, not a detailed explanation.
10. T2 objects must be SHORT (3-8 words) — break compound goals into separate T2 blocks with dependsOn.
11. T58 evidence must be SHORT TEXT (3-8 words) — do NOT use `{Bn}` tags (T4 has no tags).
12. T59 earlier/later must reference existing T56/T54 blocks — skip T59 if references would be broken.
13. Every article MUST have at least 1 T14 experiment block (use experimentType="Review synthesis" for review articles)."""


def build_unified_prompt_en(article_title: str, article_text: str) -> str:
    """Unified one-stage prompt: full article → all blocks."""
    return PROMPT_UNIFIED_TEMPLATE_EN.replace(
        "__ARTICLE_TITLE__", article_title
    ).replace("__ARTICLE_TEXT__", article_text)


# ── Legacy two-stage prompts (kept for Russian version compatibility) ────────

PROMPT_STRUCTURE_TEMPLATE_EN = """You are a knowledge representation expert. Your task is to extract from a fragment of a scientific article the **structural container blocks** (WITHOUT atomic T4 triplets — those are decomposed in a separate step).

# Input

Fragment of the article «__ARTICLE_TITLE__» (English original). There is no References section — do not invent a bibliography.

--- FRAGMENT START ---
__CHUNK_TEXT__
--- FRAGMENT END ---

# What to do

Output ONLY container blocks (all types except 4 "Direct triplet"). Assign each container a tag `{B1}`, `{B2}`, ... sequentially in order of appearance in the output `blocks` array. Do NOT output atomic T4 triplets — they are decomposed in the next step.

# Catalog of block types and their fields

Use ONLY these types and fields (output only fields you filled; omit empty ones):

- **1 Metadata**: `doi`, `title`, `authors` (array of strings). Only if the fragment contains DOI/title/authors (usually the 1st chunk).
- **2 Research goal**: `subject`, `predicate`, `object` (text; the goal is formulated as a triplet: subject → goal → object).
- **7 Hypothesis**: `hypothesis` (text), `disproofExplanation`.
- **14 Experiment**: `experimentName`, `experimentType` (e.g. "Behavioral", "Histology", "RNA-seq", "In vivo intervention", "In vitro"), `outcomes` (array of measured indicators), `steps` (array of tags `{Bn}` → T56 in execution order), `findings` (array of tags `{Bn}` → T57), `duration`, `experimentalPairs`/`controlPairs` (arrays of groups: group names + interventions).
- **16 Biological mechanism**: `mechanism`.
- **18 Intervention**: `intervention`, `dosage`, `dosageRegimen`.
- **19 Animal model**: `species`, `timeline`, `conditions`.
- **20 Conclusions**: `conclusions`.
- **22 Entity**: `subject`, `predicate`, `object` (text).
- **23 Concept definition**: `term`, `definition`.
- **27 p-value**: `pValue` (number, e.g. 0.05). One block per p value.
- **37 Statistical processing**: `statProcessing`, `expectationsComparison`.
- **38 Claim**: `claimSubject`, `claimPredicate` (one of: is, causes, inhibits, activates, correlates with, affects, is associated with, determines, contains, participates in, modulates, neutralizes), `claimObject`, `confidenceNotes`, `isNegated` (true/false).
- **39 Study limitations**: `limitations`.
- **40 Side findings/hypotheses**: `sideFindings`.
- **44 Novelty**: `novelty`.
- **46 Suggestions for future research**: `futureResearch`.
- **47 Links to previous research**: `references`.
- **51 Funding sources**: `funding`.
- **54 Action**: `subject`, `predicate`, `object` (text).
- **55 Animal group**: `groupName`, `n`, `conditions`, `purpose`.
- **56 Experiment step**: `stepName`, `details`, `duration`.
- **57 Result (finding)**: `parameter`, `direction` (increased/decreased/no change/trend), `significance` (significant/non-significant/trend), `pValue` (tag `{Bn}` of the T27 block OR a number if you do not output T27), `figureRef` (e.g. "Fig. 1F"), `detail`.

# Cross-references between containers (tags {Bn})

- In `T14.steps` put an array of step tags: `["{B2}", "{B5}"]`.
- In `T14.findings` put an array of result tags: `["{B7}", "{B8}"]`.
- In `T57.pValue` put the tag of the T27 block: `"{B9}"` (if you output T27). Output the T27 block separately from T57.
- **Hard rule:** every `{Bn}` you reference must be output in this same response. Do not reference non-output blocks. Do not embed block objects inside fields — only tag strings.

# When to use which type (important — container density!)

The text is densely packed with containers. A typical 15-25 word sentence yields **2-5 containers**. Do not compress the text into a few blocks — unfold every significant element. **But do NOT inflate:** create exactly ONE block per entity/group/step/result, not one per mention. If the same entity, group, species or experiment is repeated across sentences, reuse the already-created block (do not duplicate it). Balance: results, steps, findings and key relations get blocks; incidental repetitions do not.

**Whole-article scale calibration (critical).** The reference decomposition of this ENTIRE article contains approximately: 94 results (T57), 46 steps (T56), 47 entities (T22), 28 animal models (T19), 22 groups (T55), 8 claims (T38), 6 experiments (T14), 6 interventions (T18), 5 definitions (T23), 4 goals (T2), 3 p-values (T27), 3 actions (T54), 1 hypothesis (T7), 1 mechanism (T16), 1 statistics (T37), 1 limitations (T39), 1 side findings (T40), 1 novelty (T44), 1 future research (T46), 1 links (T47), 1 funding (T51), 1 metadata (T1), 1 conclusions (T20). This fragment is one chunk of ~18 — scale these totals proportionally (a results chunk has many T57, a methods chunk many T56/T55, a discussion chunk at most one each of T39/40/44/46/47). Do not exceed the article-wide totals; per-chunk counts must NOT sum above them.

**Per-fragment budget (critical — this fragment is ONE chunk, not the whole article).** These are HARD caps for ONE fragment. A term (species, group, entity, experiment) that repeats across sentences was almost certainly already extracted in an earlier chunk — do NOT re-create it, you have no memory of other chunks but assume the term exists. Caps per fragment: T22 ≤ 3, T55 ≤ 2, T19 ≤ 2, T14 ≤ 1, T38 ≤ 2, T2 ≤ 1, T7 ≤ 1 (hypothesis appears in the introduction chunk), T18 ≤ 1, T23 ≤ 1, T27 ≤ 1, T16 ≤ 1, T37 ≤ 1 (statistics section), T51 ≤ 1, T1 ≤ 1 (metadata only in the first chunk), T20 ≤ 1, T39 ≤ 1, T40 ≤ 1, T44 ≤ 1, T46 ≤ 1, T47 ≤ 1 (discussion elements — only if the fragment genuinely contains them; at most one each per article). If the fragment genuinely contains more distinct entities than the cap, prefer keeping the most significant ones — the others were likely already extracted previously.

**Facts that MUST NOT be dropped (critical).** The caps above apply to container types; they do NOT excuse missing results or steps:
- **T57 results:** every numeric result in the fragment — do NOT cap them. If a results paragraph lists 8 parameters, output 8 T57 blocks (the whole article has ~94).
- **T56 steps:** every distinct procedure step (the whole article has ~46). If a methods paragraph describes 8 steps, output 8 T56 blocks.
- **T54 actions:** if the fragment contains genuine verbal actions/processes (e.g. `clusterin → suppresses → inflammaging`, `cells → ingest → erythrocytes`), output T54 blocks (whole article ~3). This type exists in the reference and must be produced when applicable. Still NEVER for author contribution credits.

- **T57 "Result (finding)"** — EVERY numeric result: parameter, direction, significance, p, figure. MANDATORY linking: T57 MUST reference T18/T54 intervention via `interventionRef` when the finding follows from an intervention. There are dozens in the article (10-20 per results section). Do not skip any. If a sentence lists several parameters — each parameter is a separate T57.
- **T22 "Entity"** — every significant concept and its relation: `resistance mechanism → to what → aging`, `aging → is associated with → inflammation`. Every verbal/nominal link is a separate T22. BUT do not explode: the whole article has only ~45-50 unique entities (one block per UNIQUE concept, reused across fragments, not one per mention or per sentence). If you already created `aging → is associated with → inflammation`, do not recreate it later.
- **T56 "Experiment step"** — EVERY separate procedure step (weighing, open field test, tissue collection, ...). One experiment = 2-8 steps. Whole article ~45.
- **T14 "Experiment"** — each separate experiment (with its T55 groups, T56 steps, T57 results, T18 interventions). MANDATORY linking: T14 MUST reference T55 groups (experimentalPairs/controlPairs), T56 steps, and T57 findings. Whole article ~6.
- **T55 "Animal group"** — each experimental/control group (name, n, conditions, purpose). Whole article ~20-25. One block per group, reused across fragments.
- **T19 "Animal model"** — each species/line of animals (A. russatus, A. dimidiatus, M. musculus, ...). Whole article ~25-30 (one per species × condition combination).
- **T38 "Claim"** — general statements/conclusions of the text (claims). Whole article ~8.
- **T27 p-value** — VERY rare! Whole article 1-3: create a T27 block ONLY if you encountered the p value itself (0.05/0.01/0.001) separately. In T57.pValue put the tag `{Bn}` of this T27 block, not the number.
- **T2 "Research goal"** — goals (at the start of the article). Whole article 2-4.
- **T7 "Hypothesis"** — at most 1 per article (the main hypothesis).
- **T16 "Mechanism"** — at most 1-2 per article: create it when the text describes a biological mechanism/cascade/signaling pathway (e.g. a reelin-like cascade: ApoER2/VLDLR → Dab1 → Crk/C3G/Rap1). Do NOT skip it — it is a distinct block type present in the reference.
- **T18 "Intervention"** — substance administration/dosages (e.g. clusterin injection). Whole article ~6.
- **T23 "Definition"** — concepts explicitly defined in the text. Whole article ~5.
- **T37 "Statistics"** — statistical methods (Prism, t-test, ANOVA). Whole article 1.
- **T39/T40/T44/T46/T47** — discussion: limitations, side findings, novelty, future research, links to previous research. At most ONE per type per article: create them only in the DISCUSSION fragment, only when the text genuinely has that element. Do not create them speculatively.
- **T51 "Funding"**, **T1 "Metadata"** — if present in the fragment.
- **T20 "Conclusions"** — section conclusions. Whole article 1.
- **T54 "Action"** — verbal actions/processes. Whole article ~3. **Never** create T54 for author contribution credits (Conceptualization, Data curation, Formal analysis, Funding acquisition, Investigation, Methodology, Project administration, Resources, Software, Supervision, Validation, Visualization, Writing, Writing - original draft, Writing - review & editing) — these are NOT actions/knowledge triplets.

**Check after parsing:** if the fragment has definitions → T23; cascades/signaling pathways → T16; substance administration/dosages → T18; conclusions → T20; statistical methods → T37; p-values → T27. These types must appear when the text relates to them — do not skip them.

# Output order

1. Metadata (if any) and goals.
2. Animal models (T19) and groups (T55) — before the blocks that reference them.
3. Hypothesis, entities, definitions.
4. Experiments (T14): output T55 groups, T18 interventions, T56 steps, and T57 results FIRST, then the T14 block that references them. T14 must reference existing blocks via `{Bn}` tags. CRITICAL: T18 intervention blocks MUST appear in the output BEFORE any T57 blocks that reference them via `interventionRef`.
5. Statistics (T37), claims (T38), discussion (T39/40/44/46/47).
6. Funding (T51), if present in the fragment.
7. Everything in text reading order.

# Output format

JSON only, without explanations:

{"blocks": [
  {"blockType": 56, "tag": "{B1}", "data": {"stepName": "...", "details": "..."}},
  {"blockType": 14, "tag": "{B2}", "data": {"experimentName": "...", "experimentalPairs": [{"groupRef": "{B5}"}], "controlPairs": [{"groupRef": "{B6}"}], "steps": ["{B1}"], "findings": ["{B3}"]}},
  ...
]}

# Anti-patterns (forbidden)

- Do not output atomic T4 triplets (type 4) — that is the next step.
- Do not lose numeric results, sizes, n, p, temperatures, years, figure references.
- Do not invent DOI/authors/funding if they are not in the fragment.
- Do not output T1 "Metadata" more than once per fragment (title/authors appear once; subsequent chunks that merely repeat the article title must NOT produce another T1).
- Do not output T54 for author contribution credits (Conceptualization, Data curation, ...).
- Do not output explanations, markdown formatting, or text outside JSON."""  # noqa: E501


PROMPT_ATOMIZE_TEMPLATE_EN = """You are a knowledge representation expert. Your task is to decompose the contents of the container blocks of a fragment into **atomic T4 triplets** (subject → predicate → object).

# Input

Fragment of the article «__ARTICLE_TITLE__» (English original):

--- FRAGMENT START ---
__CHUNK_TEXT__
--- FRAGMENT END ---

# Containers extracted from this fragment

A compact list of containers (type + name). Each container already has a tag `{Bn}`:

__CONTAINERS_JSON__

# What to do

Decompose the contents of ALL containers into **atomic T4 triplets**. Every significant fact of a container's content is a separate triplet. Do not condense details: a long field decomposes into a chain of triplets (5-10 per container depending on text volume), a short one into 2-4.

**Quantity floor (critical — the most important requirement of this task).** Never stop early. The total number of T4 triplets must be **at least 3× the number of containers**, and for dense fragments 3.5× or more. If a fragment has 20 containers, output at least 60 triplets. There is no upper bound other than the fragment's content — every meaningful fact gets its own triplet. Each container must yield at least 2 triplets (except truly one-line values like a p-value). A typical 15-25 word sentence decomposes into 3-6 triplets. If you produce fewer than 3× the containers, you are condensing details — expand until every clause, number, enumeration element and qualifier has its own triplet.

One simple fact = one triplet; each of S/P/O is 1-3 words (except indivisible terms: `Acomys russatus`, `two-tailed unpaired Student's t test`). The meaning of the source is preserved completely: do not lose negation, modality, numeric values, references, time frames.

**Output format:** each T4 block indicates WHICH container it belongs to via the field `"container": "{Bn}"` (a tag from the input list). No separate `sequences` mapping is needed. One container → several consecutive triplets with the same `container`.

# Decomposition by container type (important!)

- **T56 "Step"** (e.g. `Beam walking test`): each procedure element is a separate triplet. Usually 5-10: `beams → what kind → wooden`, `width → what → 33.45 × 4 × 0.5 cm`, `weighed → whom → mice`, `before → what → the test`, `purpose → what → balance assessment`, `handled → how → gently`, `trials → how many → 3`. Do not condense details.
- **T57 "Result (finding)"** (e.g. `Rearing decreased`): unfold parameter, group, direction, significance, p, figure. Usually 3-6: `rearing → in whom → A. dimidiatus`, `rearing → when → with age`, `rearing → what → decreased`, `decreased → by how much → significantly (p<0.05)`, `rearing → shown in → Fig. 1F`.
- **T22 "Entity" / T54 "Action"** (triplet containers): split each part into micro-facts, preserving all 3 components. Usually 3-6.
- **T19 "Model"** (e.g. `Acomys russatus`): species + conditions + life span. Usually 3-5: `A. russatus → lives → up to 4.5 years`, `A. russatus → under what conditions → wild`, `A. russatus → compared with → A. dimidiatus`.
- **T55 "Group"**: group name + n + purpose + conditions. Usually 3-5.
- **T38 "Claim"**: subject/predicate/object + confidence + scope. Usually 3-5.
- **T14 "Experiment"**: name + type + each included test. Usually 2-5.
- **T27 p-value / T19 one-liner / short**: 1-2 triplets.
- **T7/T16/T23/T37/T39/T40/T44/T46/T47**: decompose the long text field into a chain of facts. Usually 5-10.

# Decomposition rules

- One triplet = one simple fact. A construction longer than ~4 words splits into a chain of linked triplets.
- **Word minimization**: S/P/O in 1-3 words (except indivisible terms).
- Question predicates (semantic role): `whom`/`what`/`which`/`what kind`/`where`/`when`/`how much`/`how long`/`for what`/`in what`/`from what`/`with what`/`to what`/`after what`/`before what`. Examples: `weighed → whom → mice`, `before → what → the test`, `beams → what kind → wooden`, `increase → when → with age`.
- Enumerations via `include`/`comprise`/`contain`/`;`/`and`/`,` → split into separate triplets (each element is its own triplet).
- Each characteristic/definition → `X → is → characteristic`.
- Negation: `not increased`/`no differences`/`no change` → preserve in the predicate or object.
- **Distribute across containers:** facts about the procedure → the step container (T56); facts about parameter/direction/group → the result container (T57); facts about species/longevity → the model container (T19); group → T55; experiment as a whole → T14; concept/entity → T22.
- **Cross-references (required, not optional)**: when a term is already decomposed by a separate T4 triplet in THIS response, reference it as `{SEQn}` instead of repeating the full term, where `n` is the ordinal number of that triplet in the `blocks` array (1st triplet = `{SEQ1}`). Apply this to every recurring term (species, group, parameter, intervention, mechanism). Roughly 1 in 4 triplets (20-30%) should contain such a reference in S, P or O. This keeps triplets short and matches the reference structure.

# Example

Fragment: "The beams were wooden, 33.45 × 4 × 0.5 cm wide. Mice were weighed before the test."
Containers: `[{"tag": "{B1}", "blockType": 56, "name": "Beam walking test"}]`

Correct answer:

{"blocks": [
  {"blockType": 4, "container": "{B1}", "data": {"subject": "weighed", "predicate": "whom", "object": "mice"}},
  {"blockType": 4, "container": "{B1}", "data": {"subject": "before", "predicate": "what", "object": "the test"}},
  {"blockType": 4, "container": "{B1}", "data": {"subject": "beams", "predicate": "what kind", "object": "wooden"}}
 ]}

# Output format

JSON only, without explanations and markdown formatting:

{"blocks": [
  {"blockType": 4, "container": "{B1}", "data": {"subject": "...", "predicate": "...", "object": "..."}},
  {"blockType": 4, "container": "{B2}", "data": {"subject": "...", "predicate": "...", "object": "..."}}
 ]}

**Hard rules:** every `container` is a tag from the input list (do not invent new ones); `blocks` may contain ONLY `blockType: 4` (containers are already extracted — do not repeat them); every `{SEQn}` in cross-references must be ≤ the total number of triplets in the response."""  # noqa: E501


def build_structure_prompt_en(article_title: str, chunk_text: str) -> str:
    """Stage 1 (English): container-block extraction prompt."""
    return PROMPT_STRUCTURE_TEMPLATE_EN.replace("__ARTICLE_TITLE__", article_title).replace(
        "__CHUNK_TEXT__", chunk_text
    )


def build_atomize_prompt_en(
    article_title: str, chunk_text: str, containers_json: str
) -> str:
    """Stage 2 (English): container → atomic T4 decomposition prompt."""
    return PROMPT_ATOMIZE_TEMPLATE_EN.replace("__ARTICLE_TITLE__", article_title).replace(
        "__CHUNK_TEXT__", chunk_text
    ).replace("__CONTAINERS_JSON__", containers_json)
