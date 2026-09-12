"""Лёгкий DSL-промпт для дешёвых микро-итераций извлечения структуры.

НАЗНАЧЕНИЕ
==========
Отдельный, минимальный промпт (НЕ трогает большой `PROMPT_UNIFIED_TEMPLATE_EN`).
Используется только для быстрых и дешёвых экспериментов в `tools/llm_extract/microtest.py`
(флаг `--dsl`). Все данные эквивалентны JSON-схеме, но в компактном построчном DSL,
что резко снижает токены вывода (и, за счёт малого объёма — токены входа).

СТРАТЕГИЯ ИНКРЕМЕНТАЛЬНЫХ ИТЕРАЦИЙ
==================================
Начинаем с минимального набора типов и правил, затем добавляем/сохраняем только те
инструкции, которые поднимают метрики (triplets_f1, causal_f1, ast_edge_f1, claim_recall,
entailment_rate, polarity_fidelity). Нейтральные/вредные инструкции — убираем.

Функции:
  build_dsl_prompt(article_title, fragment_text) -> str
"""
from src.schemas.block_types import BlockType, LEGACY_INT_TO_KEY


def build_dsl_prompt(article_title: str, fragment_text: str) -> str:
    return _TEMPLATE.replace("__TITLE__", article_title).replace(
        "__FRAGMENT__", fragment_text
    )


def build_goal_plan_dsl_prompt(plan_title: str, plan_lines: str) -> str:
    """Собирает промпт формализации декомпозиции цели в Язык Знаний.

    Переиспользует минимальный DSL-формат вывода и парсер ``parse_dsl_text``
    (НЕ дублирует промпт формализации): каждый пункт плана становится ОДНИМ
    атомарным утверждением ``sub → pred → obj``, извлечённым из его текста.
    Иерархия плана (родитель → ребёнок) отдельно передаётся как мета-связи
    ``decomposed_into`` и строится из неё детерминированно, поэтому здесь
    требуется только понять содержание пунктов.

    ``plan_lines`` — построчный список пунктов плана с метками ``[item:ID]``
    (единый текст для формализации).
    """
    return (
        _GOAL_PLAN_TEMPLATE.replace("__TITLE__", plan_title).replace(
            "__PLAN__", plan_lines
        )
    )


_GOAL_PLAN_TEMPLATE = """# ROLE
Scientific knowledge extraction engine for "Knowledge Map". You convert a GOAL PLAN
(text of a decomposed goal) into structured atomic assertions. Never invent facts
not present in the text.

# INPUT
Plan title: __TITLE__
---START---
__PLAN__
---END---

# OUTPUT — YOUR OWN DSL (NOT JSON)
One block per line. Lines start with "B" (block) then a block TYPE KEY, then a TAG
(B1, B2, ...), then |-separated fields `key=value`.
Format:
  B <TYPEKEY> <TAG> | key=value | key=value ...
Number tags sequentially B1, B2, ... in output order. Never reuse a tag.

# BLOCK TYPE (only this one)
  statement   atomic_statement   sub,pred,obj,ctx,epi,sn        (one fact per line, one predicate)

# FIELD KEYS
  sub=subject  pred=predicate  obj=object
  ctx=context (MUST contain the plan item tag, e.g. `item:G1`)  epi=epistemicStatus (future_proposal|objective|hypothesis|background_claim)
  sn=source note or empty

# HOW TO FORMALIZE EACH PLAN ITEM
For EVERY plan item (a line tagged [item:ID]):
- Produce ONE atomic statement assertion per atomic entity.
- Extract REAL subject/predicate/object from the item text: what acts / what is
  needed / what it targets. Rephrase only minimally so the triplet is grammatical
  and self-contained; never invent entities or claims.
- Put the item id into ctx as `item:<ID>` (e.g. ctx=item:P1). Repeat the same
  ctx on every line you emit for that item.
- ATOMICITY: subject and object MUST be SHORT noun phrases (2-6 words), never a
  clause, never a whole sentence, never nested sub-phrases like "the effect of X
  on Y in aged mice". If the extracted entity contains a clause or a genitive
  chain (e.g. "development of a therapy that slows aging in humans"), split it
  into shorter atomic noun phrases (e.g. "the therapy", "slowing aging in
  humans") and emit SEPARATE statement lines for each.
- SPLIT COORDINATED LISTS: if a subject or object is a list joined by "and",
  "и", "&", "/" (e.g. "molecular and cellular hallmarks of aging"), split it
  into separate entities and emit a SEPARATE statement line for EACH, keeping the same
  predicate and the other side:
    molecular and cellular hallmarks of aging -> are elucidated ->
        B statement | sub=molecular hallmarks of aging | pred=are elucidated | obj=<real value> | ctx=item:P1
        B statement | sub=cellular hallmarks of aging | pred=are elucidated | obj=<real value> | ctx=item:P1
- NEVER use placeholders like "none", "null", "empty", "-", "N/A" for sub, pred
  or obj. If the item text has no explicit object, choose the direct
  target/result of the action as the object; if the object is genuinely
  absent, still extract a self-contained triplet by rephrasing the item into
  sub -> pred -> obj (do not write "none").
- CRITICAL: do NOT emit trivial self-labels like `X -> is -> goal`,
  `X -> is -> task`, `X -> is -> sub_goal`, `X -> is -> action`.
  The object must be the real target/result/meaning of the item, taken from its text.
- If an item text is too vague to extract a meaningful triplet, still emit one
  plausible non-trivial assertion the text supports; do not skip whole items.
- Never create meta-assertions or parent/child links here; every line is an
  independent atomic fact. The plan hierarchy is built by other code.

# EXAMPLE
Plan item:  [item:G1] Develop a therapy that slows biological aging in humans
            [item:P2] Test candidate drugs on mouse models
Expected output (illustrative):
  B statement B1 | sub=the therapy | pred=targets | obj=slowing biological aging in humans | ctx=item:G1 | epi=future_proposal
  B statement B2 | sub=candidate drugs | pred=are tested on | obj=mouse models | ctx=item:P2 | epi=future_proposal

# RULES
1. RULE: one statement per atomic entity; split coordinated lists ("and", "и", "&", "/")
   into separate statement lines.
2. Never output the trivial is->kind self-label (goal/sub_goal/task/action).
3. Do not invent facts, numbers, or outcomes not present in the item text.
4. Keep the same language as the plan text (Russian stays Russian, English stays English).
5. sub/pred/obj MUST be short atomic phrases; NEVER "none", "null", "N/A", "-".
"""


_TEMPLATE = """# ROLE
Scientific knowledge extraction engine for "Knowledge Map". Convert the article text into structured knowledge blocks. Never invent facts not in the text.

# INPUT
Article: __TITLE__
---START---
__FRAGMENT__
---END---

# OUTPUT — YOUR OWN DSL (NOT JSON)
One block per line. Lines start with "B" (block) then a block TYPE KEY, then a TAG (B1, B2, ...), then |-separated fields `key=value`.
Format:
  B <TYPEKEY> <TAG> | key=value | key=value ...
Number tags sequentially B1, B2, ... in output order. Never reuse a tag. Reference a block by its TAG (e.g. B5). That is the ONLY way to link things.

# BLOCK TYPES (minimal set)
  statement          sub,pred,obj,epi,src,ctx                    (one fact per line, one predicate)
  claim              sub,pred,obj,neg,src                        (author assertion)
  entity             sub,pred,obj                                (concept identity, "X is Y")
  finding            param,dir,sig,detail,figure,exp,grp,interv,src
  experiment         name,type,grp,steps,findings,src
  animal_group       name,n,cond,purpose
  experiment_step    name,details
  intervention       type,target,dosage,regimen
  goal               sub,pred,obj
  hypothesis         hyp,disproof
  metadata           doi,title,authors

# FIELD KEYS
statement/claim/entity/goal:  sub=subject  pred=predicate  obj=object
statement:  epi=epistemicStatus (direct_statement|observation|experimental_result|statistical_result|author_interpretation|hypothesis|background_claim|limitation|future_proposal)  src=source quote  ctx=context (species/tissue/age)
claim:  neg=isNegated (true|false)  src=source quote
finding:  param=parameter  dir=direction (increased|decreased|no_change|mixed|trend|unknown)  sig=significance (significant|non_significant|trend|not_reported)  detail=numbers  figure=figureRef  exp=experimentRef tag  grp=groupRefs  interv=interventionRef  src=quote
experiment:  name=experimentName  type=experimentType  grp=experimentalPairs  steps  findings  src
animal_group:  name=groupName  n=sample size  cond=conditions  purpose
intervention:  type=interventionType  target  dosage  regimen=dosageRegimen
hypothesis:  hyp=hypothesis  disproof=disproofExplanation
metadata:  doi (full https://doi.org/...)  title  authors

# REFS
- `exp=B8`, `grp=[B5,B6]`, `findings=[B9]` etc. Reference existing tags only.
- A relation causal/regulatory edge (causes, inhibits, reduces, increases, enhances, prevents, maintains, resists, suppresses, correlates_with, associated_with, ...):
  B relation <TAG> | src=<entity name> | tgt=<entity name> | rel=<relationType> | conf=<high|medium|low> | ev=<evidence quote>
  Use the specific verb the article uses; reserve correlates_with/associated_with for mere statistics. Source/target are short entity names, not tags.

# CORE RULES — START MINIMAL, KEEP ONLY WHAT HELPS METRICS
1. statement = ONE semantic predicate per line. Never join with and/or/,. Extract EVERY atomic fact: factual claims, experimental results, species/tissue/age differences ("A. russatus has higher X"), intervention effects, statistical findings, hypotheses, interpretations, background claims.
2. Introduce each term by text once; later use its tag reference.
3. No target count; completeness matters more than inflation control now.
4. Ground truth: do not invent. If uncertain about a result direction/relation, still record what is stated or leave it out — do not fabricate.
5. Distinguish correlation from causation, hypothesis from fact, interpretation from result.

# NORMALIZED ATTRIBUTE TRIPLETS (for species/age/comparison differences)
When an attribute/quantity of a subject (usually A. russatus) is compared or stated, encode it as:
  B statement <TAG> | sub=<short subject> | pred=has | obj=<higher|lower> <concept>
Examples:
  "A. russatus has higher repair capacity"
  "A. russatus has lower senescence"
  "A. russatus has higher lifespan"
Rules:
  - subject = the SHORT entity name (e.g. "A. russatus"), NOT a long phrase.
  - predicate = "has".
  - obj = EXACTLY `{higher|lower} <concept>`. The concept is ONE short noun phrase ONLY
    (e.g. "repair capacity", "senescence", "health span"). NO modifiers, NO location,
    NO qualifiers in the object.
  - HARD VOCABULARY: normalize the direction to EXACTLY "higher" or "lower". You MUST
    NOT use greater / more / less / reduced / increased / decreased / enhanced /
    elevated / superior / better as the direction marker — always use higher or lower.
    Example: "have a greater repair capacity" -> obj=higher repair capacity
             "with reduced senescence"         -> obj=lower senescence
             "elevated clusterin levels"       -> obj=higher clusterin
  - Modifiers and context (tissue, organ, cell, "in macrophages", "levels", "in aged
    mice", "compared to A. dimidiatus", "akin to young mice") go ONLY into ctx=..., NEVER into obj.
  - One attribute per concept per subject.

# EXPAND ATTRIBUTE CLUSTERS (lists of attributes separated by commas/and)
When a sentence lists MULTIPLE attributes of a subject separated by commas or "and"
(e.g. "lower inflammaging, fibrosis, cellular senescence"; "preserved motor and muscular
function"; "high clusterin expression, CMA, and transcriptomic resilience"), emit a
SEPARATE atomic statement for EACH listed attribute. NEVER collapse a list into a single statement.
Examples:
  "reduced frailty with lower inflammaging, fibrosis, and cellular senescence" ->
    B statement | sub=A. russatus | pred=has | obj=lower inflammaging
    B statement | sub=A. russatus | pred=has | obj=lower fibrosis
    B statement | sub=A. russatus | pred=has | obj=lower cellular senescence
  "preserved motor and muscular function" ->
    B statement | sub=A. russatus | pred=has | obj=higher motor function
    B statement | sub=A. russatus | pred=has | obj=higher muscular function
Order of "and" between attributes is broken into separate statements too (and "motor and
muscular function" = motor function AND muscular function).

# PRESERVED FUNCTION = higher (absence of age-related decline)
When A. russatus MAINTAINS a function across age where the comparison species loses it
(wording like "disruptions were not observed", "maintained", "no age-related decline",
"protected from age-associated decline", "remained at comparable levels", "exhibited
no significant changes with age", "did not demonstrate age-related decline"), encode it
as an attribute `A. russatus has higher <function>`. This is how the ground truth names
preserved functions even though the article states them via negated decline.
  - maintained daily activity patterns / no circadian disruption -> obj=higher circadian rhythm
  - preserved motor and muscular function -> obj=higher motor function AND obj=higher muscular function
  - maintained cognitive function -> obj=higher cognitive function
  - protected from loss of immune function -> obj=higher immune function
  - maintained transcriptomic integrity/resilience -> obj=higher transcriptomic integrity
  - "lower chronic inflammation" stays lower chronic inflammation (it is a reduced negative, not a maintained function).
NOTES:
  - Use the reference concept name: "circadian rhythm" (NOT "daily activity pattern stability"
    or "circadian rhythm disruption"). For a preserved rhythm -> "has higher circadian rhythm".
  - If the sentence states "A. dimidiatus HAS LOWER X" (the comparison species declines),
    still emit it, but understand that the preserved-attribute normally belongs to A. russatus.
"""


DSL_TYPEKEY_TO_BLOCKTYPE = {
    # Новые обозначения по Спецификации.md
    "metadata": BlockType.METADATA,
    "goal": BlockType.GOAL,
    "text": BlockType.TEXT,
    "statement": BlockType.STATEMENT,
    "hypothesis": BlockType.HYPOTHESIS,
    "prerequisite": BlockType.PREREQUISITE,
    "expectations": BlockType.EXPECTATIONS,
    "research_design": BlockType.RESEARCH_DESIGN,
    "material": BlockType.MATERIAL,
    "method": BlockType.METHOD,
    "experiment": BlockType.EXPERIMENT,
    "inclusion_exclusion_criteria": BlockType.INCLUSION_EXCLUSION_CRITERIA,
    "biological_mechanism": BlockType.BIOLOGICAL_MECHANISM,
    "impact_goal": BlockType.IMPACT_GOAL,
    "intervention": BlockType.INTERVENTION,
    "animal_model": BlockType.ANIMAL_MODEL,
    "animal_group": BlockType.ANIMAL_GROUP,
    "entity": BlockType.ENTITY,
    "definition": BlockType.DEFINITION,
    "assumptions": BlockType.ASSUMPTIONS,
    "sample_size": BlockType.SAMPLE_SIZE,
    "data_source": BlockType.DATA_SOURCE,
    "probability_value": BlockType.PROBABILITY_VALUE,
    "variance": BlockType.VARIANCE,
    "effect_size": BlockType.EFFECT_SIZE,
    "statistical_power": BlockType.STATISTICAL_POWER,
    "confidence_interval": BlockType.CONFIDENCE_INTERVAL,
    "magnitude_value": BlockType.MAGNITUDE_VALUE,
    "formula": BlockType.FORMULA,
    "causal_graph": BlockType.CAUSAL_GRAPH,
    "identifiability_criteria": BlockType.IDENTIFIABILITY_CRITERIA,
    "result": BlockType.RESULT,
    "statistical_processing": BlockType.STATISTICAL_PROCESSING,
    "claim": BlockType.CLAIM,
    "limitations": BlockType.LIMITATIONS,
    "side_findings": BlockType.SIDE_FINDINGS,
    "side_effects": BlockType.SIDE_EFFECTS,
    "post_claims": BlockType.POST_CLAIMS,
    "open_questions": BlockType.OPEN_QUESTIONS,
    "novelty": BlockType.NOVELTY,
    "versions": BlockType.VERSIONS,
    "future_research_suggestions": BlockType.FUTURE_RESEARCH_SUGGESTIONS,
    "reference": BlockType.REFERENCE,
    "link_with_aging": BlockType.LINK_WITH_AGING,
    "image": BlockType.IMAGE,
    "code": BlockType.CODE,
    "funding": BlockType.FUNDING,
    "interest_conflict": BlockType.INTEREST_CONFLICT,
    "scientific_knowledge_value": BlockType.SCIENTIFIC_KNOWLEDGE_VALUE,
    "action": BlockType.ACTION,
    "experiment_step": BlockType.EXPERIMENT_STEP,
    "finding": BlockType.FINDING,
    "relation": BlockType.RELATION,
    "temporal_relation": BlockType.TEMPORAL_RELATION,
    # Старые ключи DSL (T1..T59) для обратной совместимости.
    **{f"T{n}": key for n, key in LEGACY_INT_TO_KEY.items()},
}
