"""English-language prompts for LLM extraction of block structure.

Mirror of ``llm_triplet_extraction_prompt`` for the English original of
"Immunometabolic resistors of aging in long-lived golden spiny mice".
The structural reference (``tools/llm_extract/reference_blocks.json``) is
language-agnostic (type histograms / seq coverage / atomization / uuidref), so
the block-type catalog, field names and {Bn}/{SEQn} mechanics are identical to
the Russian version; only instruction/example language is translated.

Placeholders: __ARTICLE_TITLE__, __CHUNK_TEXT__, __CONTAINERS_JSON__.
JSON braces are single (substituted via ``str.replace``, no ``.format``).
"""

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

- **T57 "Result (finding)"** — EVERY numeric result: parameter, direction, significance, p, figure. There are dozens in the article (10-20 per results section). Do not skip any. If a sentence lists several parameters — each parameter is a separate T57.
- **T22 "Entity"** — every significant concept and its relation: `resistance mechanism → to what → aging`, `aging → is associated with → inflammation`. Every verbal/nominal link is a separate T22. BUT do not explode: the whole article has only ~45-50 unique entities (one block per UNIQUE concept, reused across fragments, not one per mention or per sentence). If you already created `aging → is associated with → inflammation`, do not recreate it later.
- **T56 "Experiment step"** — EVERY separate procedure step (weighing, open field test, tissue collection, ...). One experiment = 2-8 steps. Whole article ~45.
- **T14 "Experiment"** — each separate experiment (with its T56 steps and T57 results). Whole article ~6.
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
4. Experiments (T14): each experiment is a T14 block, then its steps (T56), then results (T57) and p-value (T27). Output steps and results AFTER the T14 block.
5. Statistics (T37), claims (T38), discussion (T39/40/44/46/47).
6. Funding (T51), if present in the fragment.
7. Everything in text reading order.

# Output format

JSON only, without explanations:

{"blocks": [
  {"blockType": 56, "tag": "{B1}", "data": {"stepName": "...", "details": "..."}},
  {"blockType": 14, "tag": "{B2}", "data": {"experimentName": "...", "steps": ["{B1}"]}},
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
