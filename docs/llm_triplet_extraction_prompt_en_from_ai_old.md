You are a knowledge representation expert extracting structured knowledge blocks from a scientific article.

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
13. Every article MUST have at least 1 T14 experiment block (use experimentType="Review synthesis" for review articles).