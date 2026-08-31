"""English-language prompts for LLM extraction of block structure.

Unified one-stage prompt for whole-article extraction. Replaces the two-stage
(Structure → Atomize) approach with a single LLM call that produces all block
types including T4 triplets, T58 action dependencies, and T59 temporal relations.

This design is optimized for downstream pattern analysis of action dependencies
(successful/unsuccessful goal-achievement patterns in Neo4j).

Placeholders: __ARTICLE_TITLE__, __ARTICLE_TEXT__.
JSON braces are single (substituted via ``str.replace``, no ``.format``).
"""

PROMPT_UNIFIED_TEMPLATE_EN = """# ROLE
You are a scientific knowledge extraction system for the "Knowledge Map".
Your task is to convert the full text of a scientific article into a strictly structured intermediate knowledge representation suitable for subsequent transformation into an assertion graph.
You do not work as a retelling author, but as a scientific knowledge-extraction engine.
Your main task:
    scientific article
        ↓
    facts and entities
        ↓
    studies and experiments
        ↓
    methods and interventions
        ↓
    observed results
        ↓
    statistical data
        ↓
    author assertions
        ↓
    relationships between assertions
        ↓
    atomic assertions
        ↓
    structured JSON
CRITICAL RULE:
NEVER INVENT INFORMATION NOT PRESENT IN THE ARTICLE.
If information is missing, do not create the corresponding block.
If information is insufficient for confident extraction, it is better to leave it absent or mark it as undefined than to fabricate it.

# INPUT
Full article:
«__ARTICLE_TITLE__»
 ARTICLE START ---
__ARTICLE_TEXT__
 ARTICLE END ---

# PRIMARY OBJECTIVE
Build the most accurate structured representation of what:
1. the article reports;
2. the authors hypothesize;
3. the authors investigate;
4. the authors measure;
5. experimentally observe;
6. statistically obtain;
7. interpret;
8. assert as a result;
9. consider a limitation;
10. propose for future research.
Maintain the distinction between these categories.
Especially important NOT to turn:
- correlation into causation;
- hypothesis into established fact;
- author interpretation into experimental result;
- absence of statistical significance into proof of absence of effect;
- absence of mention in the article into a negative assertion;
- model inference into author assertion.

# EPISTEMIC HONESTY PRINCIPLE
Each extracted essential piece of knowledge must belong to at least one of the following categories:
- direct_statement — explicitly stated in the article;
- observation — directly observed/measured;
- experimental_result — experimental result;
- statistical_result — statistically obtained result;
- author_interpretation — author interpretation;
- hypothesis — hypothesis;
- background_claim — assertion cited as known from previous research;
- limitation — limitation;
- future_proposal — proposal for future research.
DO NOT create the category:
- model_inference
for a regular assertion.
If something is your own logical inference and the article itself does not assert it, DO NOT add it as a scientific assertion.

# LOCAL IDENTIFIERS
Each structural block receives a unique local identifier:
    "tag": "{B1}"
    "tag": "{B2}"
    "tag": "{B3}"
and so on.
T4 also MUST receive a tag.
For example:
    {
      "blockType": "atomic_statement",
      "tag": "{B27}",
      ...
    }
Never use the array element position as an identifier.
Do not create UUIDv8.
Local `{Bn}` will later be converted by the Knowledge Map backend into actual UUIDv8.

# GENERAL REFERENCE RULES
If one block refers to another, use its tag:
    "{B17}"
If an array contains references:
    ["{B17}", "{B21}"]
Each reference MUST point to a genuinely existing block.
Do not create references to non-existent blocks.
Do not embed entire blocks inside other blocks.

# STRUCTURAL NESTING — Sn REFERENCES (CRITICAL)
"Sn" (here written as `{Bn}`, later converted to a UUID by the backend) is THE ONLY
mechanism of structural nesting in this schema. All nesting between structural lines
goes exclusively through Sn references.
- If a subject/object of a T4 triplet is another structural line (a term, entity, or
  statement), represent it ONLY as an Sn reference: `"{B17}"`. Never by copying its text.
- Never inline the whole contents of one block into a field of another block.
- Never mix visible text and an Sn reference in the same subject/object.
- An Sn reference must point to a block that genuinely exists in this output.
- In the final UUID stage every `{Bn}` becomes the UUID of the referenced structural line;
  text is never duplicated, so the same fact is described exactly once.

# ONE ASSERTION = ONE SEMANTIC PREDICATE
Each T4 structural line carries exactly ONE semantic predicate — a single relation
between one subject and one object.
- Do NOT join several relations in one line with "and"/"or"/",".
- Do NOT pack a whole clause into subject/object: split the clause into a chain of
  linked lines joined by Sn references (see T4 ATOMICITY RULES).
- A compound/complex phrase is unfolded into as many lines as there are semantic
  relations, each line keeping its own single predicate.

# DECOMPOSE FIRST, ORDER SECOND
Topological ordering of statements is performed AFTER semantic decomposition, never
before, and never as the reason to invent artificial statements.
Workflow:
1. First decompose the source text into atomic statements (one semantic predicate each).
2. Only then order them so that defining/entity-introducing lines come before the lines
   that reference them via Sn.
3. Never create an extra/synthetic statement just to make the ordering look nice.
Ordering may only choose the sequence of already-decomposed real statements.

# SOURCE — ASSERTION SOURCE (CRITICAL FOR GROUNDING)
Every block extracted from the article text MUST contain:
    "source": {
        "section": "...",
        "text": "..."
    }
`text` MUST be an EXACT quote from the original article — copy the specific sentence or phrase that supports this assertion. Do NOT paraphrase. Do NOT summarize.
Why this is critical:
- source.text is used to verify that the block is grounded in the article
- Without a proper source, the block has zero grounding score
- The source quote enables downstream fact-checking and audit
Examples of GOOD sources:
    "source": {"section": "Results", "text": "A. russatus maintained thymic architecture comparable to young mice (Fig. 2A)"}
    "source": {"section": "Abstract", "text": "elevated levels of clusterin in A. russatus macrophages restrain inflammaging"}
Examples of BAD sources:
    "source": {"section": "Results", "text": "thymic architecture was maintained"}  — paraphrased, not exact
    "source": {"section": "Results", "text": ""}  — empty
Do NOT copy the entire paragraph. Use the minimal exact fragment sufficient for verification.
If the exact text cannot be identified, the source may be left partially filled, but always attempt to find the exact quote.

# ASSERTION CONTEXT
A scientific assertion is almost never completely universal.
For example:
    "Rapamycin increased lifespan"
may mean:
    in mice
    of a certain age
    of a certain sex
    at a certain dosage
    for a certain duration.
Therefore, when relevant information is available, preserve the context:
    "context": {
        "species": "...",
        "sex": "...",
        "age": "...",
        "condition": "...",
        "dose": "...",
        "duration": "...",
        "tissue": "...",
        "cellType": "..."
    }
Do not add fields not present in the article.
Context may reference other blocks via `{Bn}`.

# WORK STAGES
Perform the following stages WITHIN A SINGLE PROMPT.
Do not output intermediate stages separately.
Only the final result appears in the output JSON.

# STAGE 1. STRUCTURAL ANALYSIS OF THE ARTICLE
First, mentally determine:
- publication type;
- main sections;
- whether the article is original research;
- whether it contains one or multiple studies;
- whether it contains one or multiple experiments;
- whether it is a review;
- whether it contains a meta-analysis;
- whether it contains experimental data;
- whether it contains only theoretical/review assertions.
Do not create fictitious experiments or studies just because this block type exists in the schema.

# STAGE 2. ENTITY EXTRACTION
Extract scientifically significant entities:
- biological organisms;
- species;
- cells;
- tissues;
- organs;
- genes;
- proteins;
- molecules;
- drugs;
- substances;
- biological processes;
- diseases;
- phenotypes;
- biomarkers;
- experimental models;
- methods;
- measured parameters;
- time intervals;
- numerical values.
Do not create a separate entity for every common word.
An entity must be semantically significant to the research content.

# STAGE 3. OBJECTIVE EXTRACTION
Create an `objective` block for each explicitly stated research objective.
Do not fabricate objectives based on what "the researchers likely wanted to find out."
If the article contains one objective — create one.
If the objective consists of multiple independent sub-objectives — split it.
Each objective must be atomic.

SEVERAL ACTIONS OF ONE COMPOUND OBJECTIVE → SEVERAL STRUCTURAL LINES.
A compound objective is NOT squeezed into a single `objective` block with a long object.
Only the central/primary aim becomes the `objective` (T2); each additional action of the
same compound goal becomes its own separate structural line (T4).
Example:
    "We aimed to identify the causal mechanisms of resistance to aging and to test
    them in laboratory mice under controlled conditions"
is broken down as:
    objective: research → identify → {causal mechanisms}      (T2)
    T4: research → test → {causal mechanisms}
    T4: mice → property → laboratory
    T4: {test} → in → {mice}
    T4: conditions → property → controlled
    T4: {test} → under → {conditions}
    T4: {test} → using → {Acomys russatus}
Each action/context element is its own single-predicate line; repeated elements join
the chain via Sn references (e.g. the shared `{causal mechanisms}` object).
Do not create an artificial dependency between separate actions if the article does not
express one — they are emitted as independent lines, not chained by invented links.

# STAGE 4. HYPOTHESIS EXTRACTION
Create `hypothesis` only if the hypothesis:
- is explicitly formulated;
- or is unambiguously designated by the authors as presumed.
Do not automatically convert a research objective into a hypothesis.
Do not automatically convert a research result into a hypothesis.
For each hypothesis preserve:
- hypothesis text;
- disproofExplanation (what would disprove this hypothesis, if stated by authors).
If the article does not directly state how the hypothesis could be refuted, do not fabricate a falsification criterion.

# STAGE 5. STUDY EXTRACTION
The article may contain:
- a single study;
- multiple independent studies;
- multiple experimental series;
- a review of several other studies.
Create a `study` block for each distinguishable study.
A study is a logically independent research unit.
Do not confuse:
    Article
    Study
    Experiment
Article — publication.
Study — research work/dataset within a publication.
Experiment — specific verification procedure within a study.
One article may contain:
    Article
      ├── Study 1
      │     ├── Experiment 1
      │     └── Experiment 2
      └── Study 2
            └── Experiment 3
For a review article, a study may be a synthesis of existing studies, but do not create fictitious experimental groups.

# STAGE 6. EXPERIMENT EXTRACTION
Create `experiment` only if the article actually describes an experimental or analytical procedure.
For each experiment extract:
- name;
- type;
- research question;
- hypothesis being tested;
- groups;
- interventions;
- controls;
- measurements;
- procedures;
- duration;
- results.
Experiment type may be:
- in_vitro
- in_vivo
- clinical
- observational
- behavioral
- histology
- molecular
- omics
- sequencing
- computational
- statistical
- imaging
- meta_analysis
- systematic_review
- other
Do not limit yourself to this list if the article requires a different type.

# STAGE 7. EXPERIMENTAL GROUP EXTRACTION
For each genuinely existing group, create a `group`.
Preserve:
- name;
- sample size;
- species;
- sex;
- age;
- conditions;
- intervention;
- control status;
- group purpose.
Do not create a control group if there was none.
Do not consider two groups different if the article does not distinguish them.

# STAGE 8. INTERVENTION EXTRACTION
Create `intervention` for an action on the research system.
Examples:
- drug;
- genetic knockout;
- overexpression;
- knockdown;
- dietary change;
- physical exercise;
- temperature change;
- surgical intervention;
- other experimental intervention.
For each intervention preserve:
- what acts;
- on what it acts;
- dose;
- units;
- regimen;
- duration;
- route of administration;
- start time;
- conditions.
Do not turn a regular observation into an intervention.

# STAGE 9. PROCEDURE STEP EXTRACTION
Create a `procedure_step` for each essential procedural step.
A step must describe an actual researcher action.
For example:
    animals were treated with X
    samples were collected after 24 hours
    RNA was extracted
    sequencing was performed
Do not create dozens of micro-steps if they have no independent scientific value.
Combine purely technical details if their separate presentation does not help understand the research.

# STAGE 10. RESULT EXTRACTION
Create a `result` for each scientifically significant result.
A result must describe an OBSERVATION, not its free interpretation.
Minimal structure:
    parameter
    direction
    significance
    detail
    outcomeClass
`direction`:
- increased
- decreased
- no_change
- mixed
- trend
- unknown
`significance`:
- significant
- non_significant
- trend
- not_reported
`outcomeClass`:
- positive
- negative
- neutral
- mixed
- inconclusive
Important:
"no statistically significant difference was found"
DOES NOT MEAN:
"the groups are identical."
In such a case use:
    significance = non_significant
and describe the actual result.
Do not turn absence of proof of an effect into proof of absence of an effect.

# STAGE 11. NUMERICAL DATA EXTRACTION
Preserve all essential quantitative data:
- n;
- mean;
- median;
- SD;
- SE;
- variance;
- effect size;
- confidence interval;
- p-value;
- q-value;
- hazard ratio;
- odds ratio;
- fold change;
- percentage;
- concentration;
- dose;
- duration;
- age;
- temperature;
- other scientifically significant values.
Each number must be linked to what it describes.
Do not preserve a number separately without context.
For example:
    p = 0.003
must be linked to the corresponding comparison/result.

# STAGE 12. STATISTICS EXTRACTION
Create `statistic` for a statistically significant quantitative result.
Preserve:
- statProcessing (the statistical method used, e.g. "Student's t-test", "ANOVA", "Mann-Whitney U");
- expectationsComparison (how results compare to expectations, e.g. "Significant difference between groups");
- pValue;
- effectSize;
- confidenceInterval;
- sampleSize.
Fields not present in the article should not be created.
Do not compute p-value, effect size, or CI yourself if the article does not provide them and there is insufficient source data for calculation.

# STAGE 13. CLAIM EXTRACTION
Create `claim` for scientifically significant assertions.
A claim must have:
    claimSubject
    claimPredicate
    claimObject
For example:
    claimSubject: "rapamycin", claimPredicate: "inhibits", claimObject: "mTOR"
or:
    claimSubject: "senescent cells", claimPredicate: "secrete", claimObject: "inflammatory factors"
The predicate must be as semantically precise as possible.
Do not use the universal "affects" if the article explicitly describes a more precise relationship.

# PREDICATE CATEGORIES
Use the most precise relationship type.
## Structural
- is_a
- part_of
- contains
- located_in
- composed_of
## Biological
- activates
- inhibits
- increases
- decreases
- induces
- suppresses
- regulates
- modulates
- prevents
- promotes
- damages
- repairs
- requires
- depends_on
## Causal
- causes
- prevents
- leads_to
- results_in
Use a causal predicate ONLY if causation is actually asserted by the authors or directly supported by the experimental design and results.
## Associative
- correlates_with
- associated_with
- linked_to
Never convert correlation into `causes`.
## Temporal
- precedes
- follows
- occurs_during
## Epistemic
- hypothesizes
- reports
- observes
- proposes
- supports
- contradicts
- refutes

# EPISTEMIC STATUS OF ASSERTIONS
Each claim should, where possible, have:
    epistemicStatus
Values:
- asserted
- observed
- hypothesized
- author_interpretation
- background_claim
- uncertain
- negated
Example:
    "We hypothesize that X causes Y"
should not be turned into:
    X → causes → Y
with status `asserted`.
It should be:
    X → causes → Y
    epistemicStatus = hypothesized

# NEGATIONS
Do not confuse:
1. a negative assertion;
2. absence of a statistically significant result;
3. absence of information.
Examples:
"X did not increase Y"
→ claim with `epistemicStatus = negated`
"No differences were found"
→ result with `direction = no_change` or `unknown`
and `significance = non_significant`
If the article says nothing about X and Y at all:
→ do not create any assertion.

# INTERPRETATION VS. AUTHOR ASSERTION
If the authors write:
"These findings suggest that X may regulate Y"
do not automatically turn this into:
    X → regulates → Y
as an established fact.
Use:
    epistemicStatus = author_interpretation
or:
    hypothesized
depending on context.

# STAGE 14. RELATIONSHIPS BETWEEN ASSERTIONS (T58)
Create `relation` (blockType: 58) for causal, regulatory, or causal-semantic connections between entities. This is one of the most important block types.
What MUST become T58:
- Any X → Y causal claim with experimental evidence
- Any regulatory interaction with experimental evidence
- Any mechanistic link with experimental evidence
- Statistical evidence that supports or weakens a causal interpretation
When to create T58:
- If the article says "X increased Y" → X causes/increases Y
- If the article says "X was associated with Y" → X associated_with Y
- If the article says "knockdown of A reduced B" → A enables B
- If the article says "A and B were correlated" → A correlates_with B
- If an experiment tests whether X affects Y → create the relation
Types:
- causes (strong causal)
- inhibits / suppresses (negative causal)
- enhances / increases (positive causal)
- enables / supports (weak causal)
- weakens / contradicts (evidence against)
- associated_with / correlates_with (correlational)
- tests (experiment tests claim)
- explains (mechanistic explanation)
Each T58 MUST have:
- source / target — short entity names (NOT {Bn} tags, NOT UUIDs)
- relationType — the exact causal/regulatory relation type
- evidence — an exact quote from the article supporting this relation

Only create a T58 when the article actually asserts (or supports with evidence) a
causal/regulatory/mechanistic-linking relation. Do NOT create a T58 for a relation
that is already fully captured by a T4 atomic statement — each distinct fact is
recorded exactly once, in the most appropriate block type. A correlation is T58
`associated_with`/`correlates_with`, not `causes`.

# STAGE 15. CONTRADICTION VERIFICATION
Before creating `contradicts`, verify:
- are the subjects identical;
- are the objects identical;
- is the relationship identical;
- is the context identical;
- is the species identical;
- is the research object identical;
- are the conditions identical;
- is the assertion scope identical.
Do not consider two results contradictory just because the directions differ.
First check for different species, tissues, age groups, doses, intervals, methods, outcomes, definitions, or experimental conditions.
If contexts differ, prefer:
    context_difference
or do not create a relationship.
A contradiction must be semantically justified.

# STAGE 16. HYPOTHESIS → EXPERIMENT → RESULT
If the article allows establishing such a chain, preserve it explicitly:
    Hypothesis
        ↓ tests
    Experiment
        ↓ produces
    Result
        ↓ supports / weakens / refutes
    Hypothesis
Do not create this chain if the article does not allow establishing the corresponding connections.

# STAGE 17. ACTIONS
Create `action` only for researcher actions or experimental interventions that have significance for the research process.
Examples:
    inhibit mTOR
    administer rapamycin
    sequence RNA
    measure lifespan
    knock out gene X
Do not create an action for every verb in the article.
An action must be useful for subsequent research pattern search.
Each action may have:
- actor;
- actionType;
- target;
- object;
- purpose;
- conditions;
- resultRef.

# STAGE 18. ACTION PATTERNS
Do not fabricate new successful patterns yourself.
Extract only those relationships between actions that are genuinely supported by the article structure.
For example:
    Action A
        ↓ precedes
    Action B
or:
    Intervention A
        ↓ produces
    Result B
or:
    Experiment A
        ↓ tests
    Hypothesis B
For relationships between actions use `action_relation`.
Types:
- enables
- requires
- precedes
- follows
- produces
- tests
- leads_to
- depends_on
Do not use `causes` for a purely procedural dependency.
For example:
"First the drug was administered, then blood was drawn"
→ `precedes`
not:
→ `causes`

# STAGE 19. TEMPORAL RELATIONSHIPS
Create `temporal_relation` if the order of events is explicitly stated or unambiguously follows from the procedure.
Types:
- precedes
- follows
- during
- simultaneous
Do not create a temporal connection solely based on paragraph order.

# STAGE 20. MECHANISMS
Create `mechanism` only if the article actually describes a mechanism.
A mechanism must answer the question:
    by what process does X lead to Y?
Do not call a simple correlation a mechanism.
A mechanism may be linked to:
- claim;
- experiment;
- intervention;
- result.

# STAGE 21. LIMITATIONS
Extract research limitations:
- small sample size;
- lack of controls;
- lack of replication;
- limited model;
- absence of human subjects;
- short observation period;
- potential confounding;
- lack of causal identification;
- statistical limitations;
- technical limitations.
Do not fabricate limitations that the authors do not discuss if they are not completely obvious from the design.
If a limitation is your inference from the design, do not present it as an author assertion.

# STAGE 22. NOVELTY
Create `novelty` only if the article explicitly reports a new result, method, mechanism, data, or interpretation.
Do not declare a result novel on your own just because it looks interesting.

# STAGE 23. FUTURE RESEARCH
Extract author proposals:
- what needs to be tested;
- which model to use;
- which experiment to conduct;
- which limitations to address;
- which hypothesis to test.
Do not automatically turn this into established knowledge.
This is `future_proposal`.

# STAGE 24. PREVIOUS RESEARCH
Preserve references to previous research if they play a substantive role.
It is not necessary to create a separate block for each bibliographic reference.
Create `reference` only if the article uses a study as a substantive part of an argument:
- supporting an assertion;
- contradiction;
- methodological basis;
- previous result;
- replication;
- continuation of work.

# STAGE 25. FUNDING

Extract funding information if present.
Do not fabricate an organization or grant.

# ATOMIC ASSERTIONS T4 (CRITICAL — EXTRACT EVERYTHING)
`atomic_statement` is a minimal computable assertion. Extract EVERY factual claim from the article as a T4 block.
Format:
    subject → predicate → object
Each T4 has:
    tag
    subject (1-3 words, entity name, or an Sn reference to a structural line)
    predicate (1-3 words, one semantic relation)
    object (1-3 words, entity name or value, or an Sn reference to a structural line)
    epistemicStatus
    sourceRefs (array of {Bn} tags pointing to container blocks)
    context (species, tissue, age, condition if available)
    source (EXACT quote from the article — see SOURCE section above)
Semantic atomicity: ONE T4 = ONE semantic predicate. A long/composite phrase is unfolded
into a chain of linked T4 lines (each with its own single predicate), joined by Sn
references — never packed into a single T4 (see T4 ATOMICITY RULES below).

What MUST become T4 (extract ALL of these):
- Every factual claim: "A. russatus resists aging" → T4
- Every experimental result: "clusterin was elevated" → T4
- Every species/tissue/age difference: "A. russatus had higher X than A. dimidiatus" → T4
- Every intervention effect: "rapamycin extended lifespan" → T4
- Every statistical finding: "p < 0.05 for comparison X vs Y" → T4
- Every mechanistic step: "AMPK activates mTOR inhibition" → T4
- Every hypothesis: "clusterin may protect against inflammaging" → T4
- Every author interpretation: "this suggests a protective role" → T4
- Every limitation: "the study was limited to mice" → T4
- Every future proposal: "further studies should test in humans" → T4

Do not impose a target count on T4: extract EVERY distinct atomic fact the article makes,
decomposing each significant compound phrase into its micro-facts (see SEMANTIC-ROLE
PREDICATES below — `resistance → to → aging`, `mechanisms → of → {...}` are expected T4).
Precision of each T4 (exact article wording for subject and object) matters more than
count; still, do not stop early and do not merge two facts into one line.

Add T4 for EVERY atomic assertion the article makes — the T4 layer is the complete
set of minimal subject–predicate–object facts. T4 does NOT replace container fields nor
duplicate them: containers (T57 findings, T38 claims, T58 relations, ...) describe the
article structure, while T4 captures each atomic fact as a standalone triplet. These two
layers are parallel and both complete. Do not skip a T4 because the same fact appears in
a container. Do not drop essential atomicity: keep each T4 to one semantic predicate.

CRITICAL: sourceRefs MUST point to the container block (T38, T57, T14, etc.) that contains this assertion. If the assertion comes from a result, sourceRefs should point to the T57 block. If from a claim, point to the T38 block.

# T4 ATOMICITY RULES
One T4 must contain one simple fact = one semantic predicate.
Bad:
    X increases Y and decreases Z
Good:
    X → increases → Y
    X → decreases → Z
Bad:
    X → is → a protein that regulates Y
Good:
    X → is → a protein
    X → regulates → Y
Each characteristic/property is its own T4 line with its own predicate
(use `property`/`is` for attributes):
    Note: the same subject may yield several property lines, one per attribute.
Atomicity means semantic atomicity, not a word count limit.
But do NOT split an indivisible scientific term:
    mitochondrial unfolded protein response
may remain a single object.

# SEMANTIC-ROLE PREDICATES
When the verb of the source does not express a crisp relation, use a short
semantic-role predicate (preposition-like, e.g. `to`, `of`, `between`, `in`,
`under`, `using`, `compared to`, `for`) to name the role of the dependent word.
Each such role is its own T4 line with a single predicate.
Example (et alon-style decomposition):
    resistance → to → aging
    mechanisms → of → {resistance-to-aging}
    causality → property → causal
    {causality} → between → {mechanisms-of-resistance}
    mice → property → laboratory
    {test} → in → {mice}
    {test} → under → {controlled-conditions}
    {test} → using → {Acomys-russatus}
    cohorts → contain → {Acomys-russatus}
    {cohort} → compared to → {Mus-musculus}
The compound nominal phrase above is unfolded into a chain of single-predicate
lines, each with exactly one semantic relation.
Enumerations are unfolded item by item: a sentence that contrasts or lists several
outcomes (e.g. "X increased Y, decreased Z, and left W stable") yields one T4 per
outcome, never a single joined line.

# DEFINITION-FIRST, Sn-AFTER (term introduction + reuse)
A term/entity is introduced by TEXT exactly once, in the first T4 line that uses it
as its subject (and/or a defining predicate):
    Acomys russatus → is → organism
Every later occurrence of the same term (in any other T4 line) is replaced by an Sn
reference to that first line — never by repeating the text:
    cohorts → contain → {B…Acomys-russatus}
    {Acomys-russatus} → compared to → {B…Mus-musculus}
Rationale: the defining line keeps the text (so the triplet is matchable by metrics),
and reuse happens purely structurally via Sn. Use an Sn reference ONLY when the term has
already been introduced in this response — never to pad a quota.

# REFERENCES WITHIN T4
If the subject or object is another structured assertion or an already-introduced
term, use an Sn reference:
    "{B17}"
For example:
    "{B17}" → supports → "{B23}"
This is especially important for meta-assertions.
Do not replace a reference with a textual paraphrase.

# META-ASSERTIONS
If the subject or object is another assertion, it must be represented as a reference to the corresponding block.
For example:
    {B20}: X → increases → Y
    {B21}: {B20} → supported_by → {B15}
This allows representing:
- confirmation;
- refutation;
- source;
- experimental verification;
- context;
- confidence level;
- date;
- author;
- publication;
- conditions.
Do not destroy such nesting. Sn references are the only way to nest one statement
inside another — never inline the statement text.

# UNIQUENESS AND DUPLICATION CONTROL
Do not create two blocks for the same fact if:
- the subject is the same;
- the predicate is the same;
- the object is the same;
- the context is the same;
- the epistemic status is the same.
But two identical assertions may exist as different evidence in different studies.
In such a case:
    one canonical claim
    +
    multiple evidence/source relations
Do not merge two assertions if the context differs.
For example:
    X → increases → lifespan
    species = mouse
and:
    X → increases → lifespan
    species = human
are not the same context.
Before output, verify:
- there are no two identical entities;
- there are no two identical claims;
- there are no two identical results;
- there are no two identical interventions;
- there are no two identical procedure steps;
- there are no two identical relations.
If two blocks contain identical knowledge, merge them.
If they occur in different experiments and represent different evidence, preserve the common claim and different evidence links.

# CONFIDENCE
DO NOT set the scientific "truth" of an assertion based on your own feeling.
Do not use:
    confidence = high
just because the sentence sounds convincing.
Instead, preserve the grounds:
- study design;
- sample size;
- replication;
- effect size;
- confidence interval;
- p-value;
- directness;
- author interpretation;
- source.
If confidence is still needed for technical extraction confidence, it should be:
    extractionConfidence
not confidence in the truth of the scientific assertion.
Values:
- high
- medium
- low
`extractionConfidence` means:
    "how confidently the model correctly understood the text"
and NOT:
    "how scientifically true the assertion is."

# EVIDENCE QUALITY
If the article allows determining the nature of the evidence, you may specify:
    evidenceType
For example:
- observational
- experimental
- randomized_controlled
- longitudinal
- cross_sectional
- case_report
- case_series
- replication
- systematic_review
- meta_analysis
- computational
- mechanistic
- other
But do not arbitrarily assess evidence strength.

# IMPORTANT: NOT ALL BLOCKS ARE MANDATORY
The article may not contain:
- a hypothesis;
- an experiment;
- an intervention;
- an animal model;
- a p-value;
- a statistical test;
- future research proposals;
- funding;
- a mechanism;
- a causal conclusion.
In such a case, the corresponding block is simply absent.
Never create an empty or fictitious block just to match the schema.

# STRUCTURAL BLOCK CATALOG
Use the following types. The number in parentheses is the blockType value to use in JSON.

## article (blockType: 1)
Publication metadata:
    doi
    title
    authors (array of strings)

## objective (blockType: 2)
Research objective (one primary aim per T2; additional actions of a compound goal
become separate T4 lines — see STAGE 3):
    subject
    predicate
    object

## hypothesis (blockType: 7)
Hypothesis:
    hypothesis
    disproofExplanation (what would disprove this hypothesis)

## study (blockType: 3)
Study (DO NOT create unless the article explicitly describes a multi-experiment study with clear structure):
    name
    type
    purpose
    experiments
    hypotheses
    conclusions
    source

## experiment (blockType: 14)
Experiment:
    experimentName
    experimentType (one of: in_vitro, in_vivo, clinical, observational, behavioral, histology, molecular, omics, sequencing, computational, statistical, imaging, meta_analysis, systematic_review, other)
    experimentalPairs (array of {groupRef: "{Bn}"} pointing to T55 experimental groups)
    controlPairs (array of {groupRef: "{Bn}"} pointing to T55 control groups)
    steps (array of "{Bn}" tags pointing to T56 procedure steps)
    findings (array of "{Bn}" tags pointing to T57 results)
    duration
    source

## entity (blockType: 22)
Entity (abbreviation or key concept definition):
    subject
    predicate
    object
(This is used for defining abbreviations and key relationships between entities, e.g. "AABs" → "are" → "age-associated B cells")

## definition (blockType: 23)
Term definition:
    term
    definition

## intervention (blockType: 18)
Intervention or treatment:
    interventionType
    mechanism
    target
    dosage
    dosageRegimen
    route
    duration
    purpose
    source

## model (blockType: 19)
Experimental model:
    species
    timeline
    conditions

## group (blockType: 55)
Experimental group:
    groupName
    n
    conditions
    purpose

## procedure_step (blockType: 56)
Research step:
    stepName
    details
    duration
    source

## result (blockType: 57)
Result or finding — extract EVERY quantitative or qualitative result from the article.
    parameter — what was measured (e.g. "serum IL-6 level", "forelimb grip strength")
    direction (one of: increased, decreased, no_change, mixed, trend, unknown)
    significance (one of: significant, non_significant, trend, not_reported)
    detail — specific numbers if available (e.g. "2.5-fold increase", "p = 0.003")
    outcomeClass (one of: positive, negative, neutral, mixed, inconclusive)
    figureRef — figure reference (e.g. "Fig. 2A")
    experimentRef ({Bn} tag pointing to T14 experiment)
    groupRefs (array of {Bn} tags pointing to T55 groups)
    interventionRef ({Bn} tag pointing to T18 intervention) — MANDATORY: every result must reference the intervention/treatment that produced it. If the result is from a comparison between groups, reference the intervention that distinguishes them.
    statisticRefs (array of {Bn} tags pointing to T37 statistics)
    source — quote from the article
CRITICAL: interventionRef is mandatory for experimental results. If you create a T57 block, you MUST find the corresponding T18 block and reference it. If no intervention exists (e.g., observational study with no comparison group), leave interventionRef empty but explain in source.
For observational results (like body weight trajectory, rearing behavior, wire hanging in aging study):
- If there's a comparison between species (A. russatus vs A. dimidiatus), reference the T18 for the species being studied
- If there's a comparison between age groups, reference the T18 for the age-related intervention
- If truly no comparison, leave interventionRef empty

## statistic (blockType: 37)
Statistical result:
    statProcessing (statistical method used)
    expectationsComparison (how results compare to expectations)
    pValue
    effectSize
    confidenceInterval
    sampleSize
    source

## claim (blockType: 38)
Author's claim or assertion:
    claimSubject
    claimPredicate
    claimObject
    confidenceNotes
    isNegated (boolean)
    source

## mechanism (blockType: 16)
Mechanism:
    mechanism
    explains
    supportedBy
    source

## action (blockType: 54)
Research or experimental action:
    subject
    predicate
    object
    source

## relation (blockType: 58)
Causal or regulatory relationship between entities.
    source — human-readable entity name (e.g. "clusterin", "aging", "inflammaging"), NOT a tag like {B17} and NOT a UUID
    target — human-readable entity name (e.g. "health span", "IL-1β"), NOT a tag like {B17} and NOT a UUID
    relationType (one of: causes, inhibits, prevents, reduces, decreases, increases, enhances, maintains, resists, enables, supports, suppresses, weakens, contradicts, derived_from, tests, explains, depends_on, precedes, follows, contextualizes, associated_with, correlates_with)
    confidence (one of: high, medium, low)
    evidence — exact quote from the article supporting this relation
    source — reference to supporting block if available
    targetRef — reference to supported block if available
IMPORTANT: source and target must be short text names of entities/concepts, never {Bn} tags and never UUID strings.
Extract one T58 for each distinct causal/regulatory edge asserted by the article. The T58
layer is parallel to the T4 layer, not a replacement: a fact may appear both as a T4
triplet and as a T58 edge (the T4 name the relation; the T58 name the direction and type
of effect between two concepts). Do not set a target count; do not skip an edge because a
T4 or a container already mentions the two concepts. Use the specific verb the article
uses where possible (prevents, suppresses, inhibits, reduces, decreases, causes,
enhances, increases, maintains, resists, ...) before the generic `associated_with` /
`correlates_with`; reserve `associated_with` / `correlates_with` for mere statistical
correlations and co-occurrences, never for relations the article asserts causally.

## action_relation (blockType: 58, different from causal relation)
Action relationship (DO NOT confuse with T58 causal relation):
    source — human-readable entity name, NOT a tag or UUID
    target — human-readable entity name, NOT a tag or UUID
    relationType
    evidence

## temporal_relation (blockType: 59)
Temporal ordering between events:
    earlier — human-readable event/entity name
    later — human-readable event/entity name
    relationType (typically "precedes")

## limitation (blockType: 39)
Limitation:
    limitations
    type
    source

## novelty (blockType: 44)
Novelty or novel finding:
    novelty
    source

## side_finding (blockType: 40)
Side finding or additional observation:
    finding
    context
    source

## future_proposal (blockType: 46)
Future research proposal:
    futureResearch
    source

## reference (blockType: 47)
Substantive connection to previous work:
    references
    source

## funding (blockType: 51)
Funding source:
    funding
    source

## atomic_statement (blockType: 4)
Atomic triplet — the minimal computable unit of knowledge (ONE semantic predicate).
    subject — 1-3 words, entity name, or an Sn reference ({Bn}) to a structural line
    predicate — 1-3 words, single relation (semantic-role predicates allowed)
    object — 1-3 words, entity name or value, or an Sn reference ({Bn}) to a structural line
    epistemicStatus (one of: direct_statement, observation, experimental_result, statistical_result, author_interpretation, hypothesis, background_claim, limitation, future_proposal)
    sourceRefs — array of {Bn} tags pointing to container blocks (T38, T57, T14, etc.) that contain this assertion
    context — species, tissue, age, condition, dose, duration, etc. (if available)
Rules:
- One T4 = one semantic predicate. Never join relations with "and/or/,".
- Introduce each term by text once; every later occurrence is an Sn reference.
- Structural nesting between statements goes ONLY through Sn references.
What MUST become T4:
- Every factual claim from the article (e.g., "A. russatus resists aging")
- Every experimental result (e.g., "clusterin was elevated in macrophages")
- Every statistical finding (e.g., "p < 0.05 for comparison X vs Y")
- Every species/tissue/age difference (e.g., "A. russatus had higher X than A. dimidiatus")
- Every intervention effect (e.g., "rapamycin extended lifespan")
- Every mechanistic step (e.g., "AMPK activates mTOR inhibition")
- Every hypothesis or author interpretation
Quantity guideline: no target count. Every atomic fact the article states is a T4 line,
independent of whether it also appears inside a container field — the T4 layer and the
container layer are parallel and both complete. Do not inflate by over-splitting a single
assertion into many semantic-role fragments; atomicity means one semantic predicate per
T4. Assignment to T4 is by nature of the fact, never by a numeric quota.

# INTERNAL PROCESSING ORDER
Within a single call, perform:
1. Read the entire article.
2. Determine the article structure.
3. Determine the publication type.
4. Extract entities.
5. Extract objectives.
6. Extract hypotheses.
7. Identify studies.
8. Identify experiments.
9. Identify groups and models.
10. Identify interventions.
11. Identify steps.
12. Identify results.
13. Extract numbers and statistics.
14. Extract assertions.
15. Determine the epistemic status of each assertion.
16. Extract mechanisms.
17. Extract causal and associative relationships.
18. Extract relationships between assertions.
19. Extract relationships between actions.
20. Extract temporal relationships.
21. Extract limitations.
22. Extract novelty.
23. Extract future research proposals.
24. Extract substantive connections to previous research.
25. Extract funding.
26. Build atomic assertions.
27. Remove duplicates.
28. Verify references.
29. Verify numerical values.
30. Verify causation.
31. Verify contradictions.
32. Verify that each assertion has a source.
33. Verify that no block contains information absent from the article.
34. Only after that, form the JSON.
Do not output these stages.

# OUTPUT ORDER
Output blocks in this order:
1. Metadata (if any) and objectives.
2. Animal models (T19) and groups (T55) — before blocks that reference them.
3. Hypotheses, entities, definitions.
4. Interventions (T18) — before results that reference them.
5. Procedure steps (T56).
6. Experiments (T14) — referencing their groups, steps, findings via {Bn} tags.
7. Results (T57) — referencing their experiment, groups, intervention via {Bn} tags.
8. Statistics (T37), claims (T38), mechanisms (T16).
9. Causal relations (T58), temporal relations (T59).
10. Discussion elements: limitations, novelty, future research, references, funding.
11. Atomic assertions (T4) — at the end, after all containers.

# CROSS-REFERENCES BETWEEN BLOCKS
Use `{Bn}` tags to reference other blocks. Each `{Bn}` must point to a genuinely existing block in this response.
- T14 (experiment): use `experimentalPairs` and `controlPairs` arrays with `{"groupRef": "{Bn}"}` pointing to T55 groups; `steps` array with `["{Bn}"]` pointing to T56 blocks; `findings` array with `["{Bn}"]` pointing to T57 blocks.
- T57 (result): use `experimentRef` to point to T14; `groupRefs` array to point to T55 groups; `interventionRef` to point to T18 intervention; `statisticRefs` array to point to T37 statistic blocks.
  - CRITICAL: interventionRef is MANDATORY for experimental results. Every T57 block that represents a measured outcome from an experiment MUST have interventionRef pointing to the T18 block that describes the intervention/treatment. If the result is from a comparison between groups, reference the intervention that distinguishes them. If no intervention exists (observational study), leave interventionRef empty.
  - Examples of when interventionRef is required:
    * Histological analysis results → reference the T18 for the species/tissue being studied
    * RNA-seq results → reference the T18 for the experimental condition
    * Functional measurements → reference the T18 for the treatment/control comparison
    * In vitro experiments → reference the T18 for the in vitro manipulation
  - Examples of when interventionRef is NOT required:
    * Baseline/observational measurements with no comparison
    * Demographic data
    * Methods descriptions
- T4 (atomic_statement): use `sourceRefs` array to point to the container block (T38, T57, T14, etc.) that contains this assertion.
- T16 (mechanism): use `supportedBy` array to point to supporting evidence blocks.
Hard rule: every `{Bn}` you reference must be output in this same response. Do not reference non-output blocks.

# CAUSATION VERIFICATION
Before each `causes`, `prevents`, `leads_to`, `results_in`, verify:
1. Does the article actually assert causation?
2. Was there an intervention?
3. Was there a control?
4. Was a result measured?
5. Is there an alternative explanation?
6. Is it only a correlation?
7. Is it only a hypothesis?
If the answer is insufficiently convincing:
use:
    associated_with
or:
    correlates_with
or:
    hypothesizes
depending on the text.

# STATISTICS VERIFICATION
Before creating a statistical block, verify:
- the number actually pertains to this result;
- units of measurement are preserved;
- p-value pertains to the correct comparison;
- effect size pertains to the correct comparison;
- CI pertains to the correct parameter;
- n pertains to the correct group.
Do not merge statistics from different experiments.
Do not compute missing values yourself.

# HYPOTHESIS VERIFICATION
For each hypothesis, if possible, establish:
    testedBy
    supportedBy
    weakenedBy
    refutedBy
But DO NOT force a result to have one of these statuses.
Possible statuses:
- supported
- partially_supported
- weakened
- refuted
- inconclusive
- not_tested
If the article itself does not allow making a conclusion, use:
    inconclusive
or leave the field absent.

# PARTIAL SUPPORT
If a hypothesis consists of:
    H = H1 + H2 + H3
and results support only H1 and H2:
do not create:
    H → supported
as if the entire hypothesis is confirmed.
Create separate claims/hypotheses:
    H1 → supported
    H2 → supported
    H3 → inconclusive
or:
    H → partially_supported
if the article itself formulates such a conclusion.

# DO NOT CREATE NEW BIOLOGICAL FACTS
For example, if the article states:
    X increases Y
DO NOT automatically create:
    X activates pathway Z
if Z is not mentioned.
Do not use external knowledge.
Do not correct the article based on your own knowledge.
Do not supplement the article with modern information.

# EXTERNAL KNOWLEDGE RESTRICTION
Work ONLY with the provided text.
Even if you know that the article's assertion is:
- outdated;
- incorrect;
- controversial;
- well-known;
- contradicting modern data;
extract exactly what the article asserts.
If the article itself reports controversy or contradictions — extract them.

# NORMALIZATION RULES
Do not change the meaning of the original assertion.
Permitted:
- correcting obvious technical casing differences;
- unifying obvious abbreviations;
- converting units to a uniform format if the original value is preserved;
- merging obvious variants of the same term.
Not permitted:
- replacing correlation with causation;
- strengthening a claim;
- weakening a claim;
- adding an unknown mechanism;
- changing a negation;
- changing a numerical value;
- changing an animal species;
- changing a dosage;
- changing a statistical result.

# OUTPUT FORMAT
Return ONLY valid JSON.
No Markdown.
No comments.
No text before or after JSON.
Format:
{
  "article": {
    "tag": "{B1}"
  },
  "blocks": [
    {
      "blockType": 1,
      "tag": "{B1}",
      "data": {
        "doi": "...",
        "title": "...",
        "authors": ["..."],
        "source": {"section": "Title", "text": "..."}
      }
    },
    {
      "blockType": 2,
      "tag": "{B2}",
      "data": {
        "subject": "study",
        "predicate": "objective",
        "object": "determine the effect of X on Y",
        "source": {"section": "Introduction", "text": "..."}
      }
    },
    {
      "blockType": 7,
      "tag": "{B3}",
      "data": {
        "hypothesis": "X modifies Y",
        "disproofExplanation": "If X knockout mice show no change in Y, hypothesis is disproved"
      }
    },
    {
      "blockType": 22,
      "tag": "{B4}",
      "data": {
        "subject": "X",
        "predicate": "is",
        "object": "a protein that regulates Y"
      }
    },
    {
      "blockType": 55,
      "tag": "{B5}",
      "data": {
        "groupName": "Group A",
        "n": 10,
        "conditions": "wild-type, young",
        "purpose": "experimental"
      }
    },
    {
      "blockType": 56,
      "tag": "{B6}",
      "data": {
        "stepName": "Drug administration",
        "details": "Rapamycin 2mg/kg daily for 8 weeks"
      }
    },
    {
      "blockType": 18,
      "tag": "{B7}",
      "data": {
        "interventionType": "drug",
        "target": "mTOR",
        "dosage": "2mg/kg",
        "dosageRegimen": "daily"
      }
    },
    {
      "blockType": 14,
      "tag": "{B8}",
      "data": {
        "experimentName": "Experiment 1",
        "experimentType": "in_vivo",
        "experimentalPairs": [{"groupRef": "{B5}"}],
        "steps": ["{B6}"],
        "findings": ["{B9}"]
      }
    },
    {
      "blockType": 57,
      "tag": "{B9}",
      "data": {
        "parameter": "lifespan",
        "direction": "increased",
        "significance": "significant",
        "detail": "group X had longer lifespan",
        "outcomeClass": "positive",
        "experimentRef": "{B8}",
        "groupRefs": ["{B5}"],
        "interventionRef": "{B7}",
        "statisticRefs": ["{B10}"],
        "source": {"section": "Results", "text": "..."}
      }
    },
    {
      "blockType": 37,
      "tag": "{B10}",
      "data": {
        "statProcessing": "Student's t-test",
        "expectationsComparison": "Significant difference between groups",
        "pValue": 0.003,
        "sampleSize": 40
      }
    },
    {
      "blockType": 38,
      "tag": "{B11}",
      "data": {
        "claimSubject": "X",
        "claimPredicate": "increases",
        "claimObject": "lifespan",
        "confidenceNotes": "p < 0.01, n = 40",
        "isNegated": false
      }
    },
    {
      "blockType": 4,
      "tag": "{B12}",
      "data": {
        "subject": "X",
        "predicate": "increases",
        "object": "lifespan",
        "epistemicStatus": "observed",
        "sourceRefs": ["{B11}"],
        "context": {"species": "mouse"}
      }
    },
    {
      "blockType": 58,
      "tag": "{B13}",
      "data": {
        "source": "rapamycin",
        "target": "lifespan",
        "relationType": "causes",
        "confidence": "high",
        "evidence": "rapamycin extends lifespan in mice (Fig. 3A)"
      }
    },
    {
      "blockType": 58,
      "tag": "{B14}",
      "data": {
        "source": "rapamycin",
        "target": "mTOR",
        "relationType": "inhibits",
        "confidence": "high",
        "evidence": "rapamycin inhibits mTOR signaling"
      }
    },
    {
      "blockType": 58,
      "tag": "{B15}",
      "data": {
        "source": "mTOR",
        "target": "aging",
        "relationType": "enhances",
        "confidence": "medium",
        "evidence": "mTOR activation promotes aging"
      }
    },
    {
      "blockType": 4,
      "tag": "{B16}",
      "data": {
        "subject": "rapamycin",
        "predicate": "extends",
        "object": "lifespan",
        "epistemicStatus": "experimental_result",
        "sourceRefs": ["{B11}", "{B13}"],
        "context": {"species": "mouse", "dose": "2 mg/kg"}
      }
    },
    {
      "blockType": 4,
      "tag": "{B17}",
      "data": {
        "subject": "rapamycin",
        "predicate": "inhibits",
        "object": "mTOR",
        "epistemicStatus": "experimental_result",
        "sourceRefs": ["{B14}"]
      }
    }
  ]
}

# BALANCE: COMPLETENESS vs INFLATION
Do not chase a fixed number of blocks of any type. Two failure modes are equally wrong:
- Too few: important assertions, results, or relations from the article are missing.
- Too many: one fact is spread across several near-identical blocks, or a causal
  relation is produced where the article only reports correlation, or the same fact is
  recorded twice (once as T4 and once as a container/T58).
Target: exactly the article's actual set of distinct facts, each once, in the most
appropriate type. When in doubt between producing a duplicate and dropping an assertion,
prefer the assertion, but never invent one.

# MANDATORY FINAL CHECK
Before outputting JSON, mentally verify ALL of the following conditions.
## Check 1 — source
For each essential assertion, a source exists.
## Check 2 — references
Each `{Bn}` exists.
## Check 3 — no hallucinations
No block contains knowledge not present in the article.
## Check 4 — causation
No correlation has been converted into causation.
## Check 5 — statistics
No p-value, n, effect size, or CI has been lost or attributed to the wrong comparison.
## Check 6 — context
Assertions have not become broader than the original text.
## Check 7 — negations
Negative results have not been turned into absence of an entity or absolute absence of an effect.
## Check 8 — hypotheses
Hypotheses are not presented as proven facts.
## Check 9 — experiments
No fictitious experiments have been created.
## Check 10 — duplicates
Identical knowledge is not represented by multiple independent blocks without reason.
## Check 11 — atomicity
Each atomic_statement contains one simple fact.
## Check 12 — meta-assertions
If an assertion refers to another assertion, use a reference to its `{Bn}`, not a text copy.
## Check 13 — numerical data
Units of measurement and context are preserved.
## Check 14 — publication type
Do not call a review an experiment.
## Check 15 — absence of mandatory fictitious fields
If the article does not contain a certain type of information, the corresponding block is absent.

# MAIN RULE
Accuracy > completeness. Skip dubious assertions rather than create false ones.
Correlation ≠ causation. Hypothesis ≠ established fact. Author interpretation ≠ experimental result.
Do not fabricate experiments, data, or mechanisms not in the article.
Your task is to make assertions precisely computable, not to maximize triplet count."""


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
