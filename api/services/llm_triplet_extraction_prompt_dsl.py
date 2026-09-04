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


def build_dsl_prompt(article_title: str, fragment_text: str) -> str:
    return _TEMPLATE.replace("__TITLE__", article_title).replace(
        "__FRAGMENT__", fragment_text
    )


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
  T4   atomic_statement   sub,pred,obj,epi,src,ctx        (one fact per line, one predicate)
  T38  claim              sub,pred,obj,neg,src             (author assertion)
  T22  entity             sub,pred,obj                     (concept identity, "X is Y")
  T57  result             param,dir,sig,detail,figure,exp,grp,interv,src
  T14  experiment         name,type,grp,steps,findings,src
  T55  group              name,n,cond,purpose
  T56  step               name,details
  T18  intervention       type,target,dosage,regimen
  T2   objective          sub,pred,obj
  T7   hypothesis         hyp,disproof
  T1   article            doi,title,authors

# FIELD KEYS
T4/T38/T22/T2:  sub=subject  pred=predicate  obj=object
T4:  epi=epistemicStatus (direct_statement|observation|experimental_result|statistical_result|author_interpretation|hypothesis|background_claim|limitation|future_proposal)  src=source quote  ctx=context (species/tissue/age)
T38:  neg=isNegated (true|false)  src=source quote
T57:  param=parameter  dir=direction (increased|decreased|no_change|mixed|trend|unknown)  sig=significance (significant|non_significant|trend|not_reported)  detail=numbers  figure=figureRef  exp=experimentRef tag  grp=groupRefs  interv=interventionRef  src=quote
T14:  name=experimentName  type=experimentType  grp=experimentalPairs  steps  findings  src
T55:  name=groupName  n=sample size  cond=conditions  purpose
T18:  type=interventionType  target  dosage  regimen=dosageRegimen
T7:   hyp=hypothesis  disproof=disproofExplanation
T1:   doi (full https://doi.org/...)  title  authors

# REFS
- `exp=B8`, `grp=[B5,B6]`, `findings=[B9]` etc. Reference existing tags only.
- A T58 causal/regulatory edge (causes, inhibits, reduces, increases, enhances, prevents, maintains, resists, suppresses, correlates_with, associated_with, ...):
  B T58 <TAG> | src=<entity name> | tgt=<entity name> | rel=<relationType> | conf=<high|medium|low> | ev=<evidence quote>
  Use the specific verb the article uses; reserve correlates_with/associated_with for mere statistics. Source/target are short entity names, not tags.

# CORE RULES — START MINIMAL, KEEP ONLY WHAT HELPS METRICS
1. T4 = ONE semantic predicate per line. Never join with and/or/,. Extract EVERY atomic fact: factual claims, experimental results, species/tissue/age differences ("A. russatus has higher X"), intervention effects, statistical findings, hypotheses, interpretations, background claims.
2. Introduce each term by text once; later use its tag reference.
3. No target count; completeness matters more than inflation control now.
4. Ground truth: do not invent. If uncertain about a result direction/relation, still record what is stated or leave it out — do not fabricate.
5. Distinguish correlation from causation, hypothesis from fact, interpretation from result.

# NORMALIZED ATTRIBUTE TRIPLETS (for species/age/comparison differences)
When an attribute/quantity of a subject (usually A. russatus) is compared or stated, encode it as:
  B T4 <TAG> | sub=<short subject> | pred=has | obj=<higher|lower> <concept>
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
SEPARATE atomic T4 for EACH listed attribute. NEVER collapse a list into a single T4.
Examples:
  "reduced frailty with lower inflammaging, fibrosis, and cellular senescence" ->
    B T4 | sub=A. russatus | pred=has | obj=lower inflammaging
    B T4 | sub=A. russatus | pred=has | obj=lower fibrosis
    B T4 | sub=A. russatus | pred=has | obj=lower cellular senescence
  "preserved motor and muscular function" ->
    B T4 | sub=A. russatus | pred=has | obj=higher motor function
    B T4 | sub=A. russatus | pred=has | obj=higher muscular function
Order of "and" between attributes is broken into separate T4s too (and "motor and
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
    "T1": 1, "T2": 2, "T3": 3, "T4": 4, "T7": 7, "T14": 14, "T16": 16,
    "T18": 18, "T19": 19, "T22": 22, "T23": 23, "T27": 27, "T37": 37,
    "T38": 38, "T39": 39, "T40": 40, "T44": 44, "T46": 46, "T47": 47,
    "T51": 51, "T54": 54, "T55": 55, "T56": 56, "T57": 57, "T58": 58, "T59": 59,
}
