"""Каноническая DSL-спецификация структурных строк.

Описывает, какие поля (короткий DSL-ключ → JSON-поле блока) разрешены для
каждого типа структурной строки и какого рода значение каждое поле принимает
(string/int/float/bool/ref/refs/strs). Единый источник истины для:
  - генерации LLM-промпта прямой типизации (какие поля модель может выводить);
  - парсера DSL-ответа (короткие ключи → JSON-поля `data` блока);
  - валидации структурных строк (`kind`, обязательные поля для связи);
  - связывания строк-свидетельств и детерминированных переходов карты знаний.

Каждая строка DSL содержит обязательное поле ``unit=S<n>`` с указанием source
unit (предложения) — это единственный канал provenance (квота-поля не нужны).
Ссылки на другие строки задаются тегами ``B<число>``. Рёбра карты выводятся
построителем из ролей типов, полей и порядка строк; DSL не содержит общих полей
зависимости.
"""
from __future__ import annotations

import re
from typing import Dict, FrozenSet, List, NamedTuple, Optional, Tuple

from .block_types import BlockType


class FieldSpec(NamedTuple):
    """Каноническое описание одного поля структурной строки.

    kind:
      "str"   — одиночная короткая строка;
      "int"   — целое число;
      "float" — число с плавающей точкой;
      "bool"  — true/false;
      "ref"   — одиночная ссылка-тег ``B5``;
      "refs"  — список ссылок-тегов ``[B5,B6]``;
      "ref_groups" — группы альтернативных ссылок ``[[B5,B6],[B7]]``;
      "strs"  — список строк ``[a,b]``;
    required: поле обязательно для типа (иначе data считается неполной);
    description: справка для LLM-промпта (англ.).
    """

    json_field: str
    kind: str = "str"
    required: bool = False
    description: str = ""
    choices: Tuple[str, ...] = ()


def _spec(json_field: str, kind: str = "str", *, required: bool = False,
          description: str = "", choices: Tuple[str, ...] = ()) -> FieldSpec:
    return FieldSpec(json_field, kind, required, description, choices)


# Канонический реестр полей. Ключ — тип структурной строки (BlockType.XXX).
# Значение — словарь «короткий DSL-ключ → FieldSpec».
DSL_FIELDS: Dict[str, Dict[str, FieldSpec]] = {
    BlockType.METADATA: {
        "doi": _spec("doi", description="full DOI"),
        "title": _spec("title", description="article title"),
        "authors": _spec("authors", "strs", description="author names"),
        "orcid": _spec("authorsOrcid", "strs", description="author ORCIDs aligned with authors"),
        "orgs": _spec("organizations", "strs", description="author affiliations"),
        "corr": _spec("correspondingAuthors", "strs", description="corresponding authors"),
        "pubdate": _spec("publicationDate", description="publication date"),
        "journal": _spec("journal", description="journal name"),
        "volume": _spec("volume", description="journal volume"),
        "issue": _spec("issue", description="journal issue"),
        "pages": _spec("pages", description="page range"),
        "publisher": _spec("publisher", description="publisher"),
        "license": _spec("license", description="license"),
        "funds": _spec("funding", "strs", description="funding sources"),
        "conflict": _spec("conflictOfInterest", "strs", description="competing interests"),
        "reg": _spec("studyRegistration", description="study/clinical registration number"),
        "year": _spec("publication_date", description="publication year"),
    },
    BlockType.GOAL: {
        "sub": _spec("subject", required=True, description="subject entity"),
        "pred": _spec("predicate", required=True, description="predicate"),
        "obj": _spec("object", required=True, description="object entity"),
    },
    BlockType.TEXT: {
        "content": _spec("content", required=True, description="verbatim text"),
    },
    BlockType.STATEMENT: {
        "sub": _spec("subject", required=True, description="subject entity"),
        "subop": _spec("subjectOperation", description="identify_subjects; use only with subref"),
        "subref": _spec("subjectStatementRef", "ref", description="B-tag of the direct assertion qualified by subop"),
        "pred": _spec("predicate", required=True, description="single semantic predicate"),
        "obj": _spec("object", required=True, description="object entity"),
        "neg": _spec("negated", "bool", description="negation"),
        "epi": _spec(
            "epistemicStatus",
            description="epistemic role",
            choices=(
                "direct_statement", "observation", "experimental_result",
                "statistical_result", "author_interpretation", "hypothesis",
                "background_claim", "limitation", "future_proposal",
            ),
        ),
        "ctx": _spec("context", description="species/tissue/age/comparison context"),
        "srcs": _spec("sourceRefs", "refs", description="container block refs containing this assertion"),
    },
    BlockType.HYPOTHESIS: {
        "hyp": _spec("hypothesis", required=True, description="hypothesis statement"),
        "hsub": _spec("hypothesisSubject", description="hypothesis subject"),
        "hpred": _spec("hypothesisPredicate", description="hypothesis predicate"),
        "hobj": _spec("hypothesisObject", description="hypothesis object"),
        "disproof": _spec("disproofExplanation", description="what would disprove it"),
        "dsub": _spec("disproofSubject", description="disproof subject"),
        "dpred": _spec("disproofPredicate", description="disproof predicate"),
        "dobj": _spec("disproofObject", description="disproof object"),
    },
    BlockType.PREREQUISITE: {
        "pre": _spec("prerequisites", "strs", required=True, description="background prerequisites"),
    },
    BlockType.EXPECTATIONS: {
        "exp": _spec("expectations", "strs", required=True, description="expected outcomes"),
    },
    BlockType.RESEARCH_DESIGN: {
        "design": _spec("design", required=True, description="study design"),
        "type": _spec("studyType", description="case report|case series|replication|original research|review|systematic review|meta-analysis|clinical trial (phase I-IV)"),
        "rand": _spec("randomization", "bool", description="randomized controlled trial (RCT)"),
        "blind": _spec("blinding", "bool", description="blinding"),
        "primary": _spec("primaryEndpoints", "strs", description="primary endpoints"),
        "secondary": _spec("secondaryEndpoints", "strs", description="secondary endpoints"),
        "exps": _spec("experiments", "refs", description="experiment refs"),
        "hyps": _spec("hypotheses", "refs", description="hypothesis refs"),
        "concl": _spec("conclusions", "strs", description="conclusions"),
    },
    BlockType.MATERIAL: {
        "mats": _spec("materials", required=True, description="materials/reagents/samples"),
    },
    BlockType.METHOD: {
        "meth": _spec("methods", required=True, description="method description"),
        "meas": _spec("measurementMethods", "strs", description="measurement methods"),
    },
    BlockType.EXPERIMENT: {
        "name": _spec("experimentName", required=True, description="experiment name"),
        "type": _spec("experimentType", description="in_vitro|in_vivo|clinical|observational|behavioral|histology|molecular|omics|sequencing|computational|statistical|imaging|meta_analysis|systematic_review|other"),
        "outcome": _spec("outcomes", "strs", description="outcomes (tag-list)"),
        "grp": _spec("experimentalPairs", "refs", description="animal_group refs"),
        "ctrl": _spec("controlPairs", "refs", description="control group refs"),
        "steps": _spec("steps", "refs", description="experiment_step refs"),
        "findings": _spec("findings", "refs", description="finding refs"),
        "duration": _spec("duration", description="duration"),
    },
    BlockType.INCLUSION_EXCLUSION_CRITERIA: {
        "crit": _spec("inclusionExclusionCriteria", required=True, description="criterion text (list of statements)"),
        "type": _spec("criterionType", description="inclusion|exclusion"),
    },
    BlockType.BIOLOGICAL_MECHANISM: {
        "mech": _spec("mechanism", required=True, description="biological mechanism"),
        "expl": _spec("explains", description="what the mechanism explains"),
        "sup": _spec("supportedBy", "refs", description="supporting evidence refs"),
    },
    BlockType.IMPACT_GOAL: {
        "target": _spec("target", required=True, description="impact target"),
        "level": _spec("level", description="cell|tissue|organ|pathway|molecule"),
    },
    BlockType.INTERVENTION: {
        "type": _spec("interventionType", required=True, description="intervention type"),
        "target": _spec("target", description="target pathway/molecule"),
        "mech": _spec("mechanism", description="mechanism"),
        "dosage": _spec("dosage", description="dose"),
        "regimen": _spec("dosageRegimen", description="dosage regimen"),
        "route": _spec("route", description="administration route"),
        "duration": _spec("duration", description="duration"),
        "purpose": _spec("purpose", description="intervention purpose"),
    },
    BlockType.ANIMAL_MODEL: {
        "species": _spec("species", required=True, description="animal species/model"),
        "speciesRef": _spec("speciesRef", "ref", description="entity block introducing the species"),
        "timeline": _spec("timeline", description="event timeline / model history"),
        "cond": _spec("conditions", description="housing/SPF/treatment conditions"),
    },
    BlockType.ANIMAL_GROUP: {
        "name": _spec("groupName", required=True, description="group name"),
        "speciesRef": _spec("speciesRef", "ref", description="animal_model ref"),
        "intervRef": _spec("interventionRef", "ref", description="intervention ref"),
        "n": _spec("n", "int", description="group size"),
        "cond": _spec("conditions", description="group conditions"),
        "purpose": _spec("purpose", description="group role"),
    },
    BlockType.ENTITY: {
        "sub": _spec("subject", required=True, description="entity name"),
        "pred": _spec("predicate", required=True, description="identity predicate (is_a)"),
        "obj": _spec("object", required=True, description="superclass/holder"),
        "type": _spec("type", description="species|gene/protein|process|tissue|disease|cell|drug|date|duration"),
        "value": _spec("value", description="numeric value if this entity is a named magnitude"),
        "aliases": _spec("aliases", "strs", description="known aliases"),
        "canonical": _spec("canonicalName", description="canonical name"),
    },
    BlockType.DEFINITION: {
        "term": _spec("term", required=True, description="defined term"),
        "is": _spec("is", description="identity predicate (is)"),
        "definition": _spec("definition", required=True, description="definition"),
    },
    BlockType.ASSUMPTIONS: {
        "ass": _spec("assumptions", "strs", required=True, description="assumptions"),
    },
    BlockType.SAMPLE_SIZE: {
        "n": _spec("sampleSize", required=True, description="sample size (N)"),
    },
    BlockType.DATA_SOURCE: {
        "src": _spec("dataSources", "strs", required=True, description="data sources"),
    },
    BlockType.PROBABILITY_VALUE: {
        "p": _spec("pValue", "float", required=True, description="p-value"),
    },
    BlockType.VARIANCE: {
        "var": _spec("variance", required=True, description="variance (SD/SE/IQR)"),
    },
    BlockType.EFFECT_SIZE: {
        "eff": _spec("effectSize", required=True, description="effect size value"),
        "type": _spec("effectType", description="OR|HR|RR|d"),
    },
    BlockType.STATISTICAL_POWER: {
        "power": _spec("power", required=True, description="statistical power"),
    },
    BlockType.CONFIDENCE_INTERVAL: {
        "ci": _spec("ci", required=True, description="confidence interval"),
        "level": _spec("ciLevel", description="confidence level (95%)"),
        "lo": _spec("ciLower", "float", description="lower bound"),
        "hi": _spec("ciUpper", "float", description="upper bound"),
    },
    BlockType.MAGNITUDE_VALUE: {
        "nums": _spec("namedNumbers", "strs", required=True, description="named numbers with units"),
    },
    BlockType.FORMULA: {
        "formula": _spec("formula", required=True, description="formula (LaTeX)"),
        "vars": _spec("variables", "strs", description="variable names and their units"),
    },
    BlockType.CAUSAL_GRAPH: {
        "dag": _spec("dagDescription", required=True, description="causal graph description"),
        "data": _spec("graphData", description="graph data (JSON nodes, edges)"),
    },
    BlockType.IDENTIFIABILITY_CRITERIA: {
        "crit": _spec("criteria", "strs", required=True, description="identifiability criteria"),
    },
    BlockType.RESULT: {
        "sum": _spec("resultsSummary", required=True, description="results summary"),
        "results": _spec("results", "strs", description="individual results"),
        "rows": _spec("rows", "strs", description="table rows"),
        "raw": _spec("rawData", description="raw data"),
    },
    BlockType.STATISTICAL_PROCESSING: {
        "stat": _spec("statProcessing", required=True, description="statistical test/analysis"),
        "comp": _spec("expectationsComparison", description="how results compare to expectations"),
        "p": _spec("pValue", "float", description="p-value"),
        "eff": _spec("effectSize", "float", description="effect size"),
        "ci": _spec("confidenceInterval", description="confidence interval"),
        "n": _spec("sampleSize", "int", description="sample size"),
    },
    BlockType.CLAIM: {
        "sub": _spec("claimSubject", required=True, description="claim subject"),
        "pred": _spec("claimPredicate", required=True, description="is_a|causes|inhibits|activates|correlates_with|affects|associated_with|defines|contains|participates_in|modulates|neutralizes, snake_case"),
        "obj": _spec("claimObject", required=True, description="claim object"),
        "neg": _spec("isNegated", "bool", description="negation"),
        "conf": _spec("confidenceNotes", description="confidence notes"),
        "seq": _spec("sequence", "strs", description="sequence of triplets"),
    },
    BlockType.LIMITATIONS: {
        "lim": _spec("limitations", "strs", required=True, description="limitations"),
        "type": _spec("type", description="limitation type"),
    },
    BlockType.SIDE_FINDINGS: {
        "finding": _spec("sideFindings", "strs", required=True, description="side findings"),
    },
    BlockType.SIDE_EFFECTS: {
        "effects": _spec("sideEffects", "strs", required=True, description="side effects"),
    },
    BlockType.POST_CLAIMS: {
        "claims": _spec("postClaims", "strs", required=True, description="conclusions"),
        "comp": _spec("comparisonWithExpectations", description="comparison with expectations"),
    },
    BlockType.OPEN_QUESTIONS: {
        "q": _spec("openQuestions", "strs", required=True, description="open questions"),
    },
    BlockType.NOVELTY: {
        "nov": _spec("novelty", required=True, description="novelty statement"),
    },
    BlockType.VERSIONS: {
        "ver": _spec("versions", required=True, description="version value (software/dataset/protocol/model)"),
        "desc": _spec("description", description="what the version describes"),
    },
    BlockType.FUTURE_RESEARCH_SUGGESTIONS: {
        "future": _spec("futureResearch", "strs", required=True, description="future research suggestions"),
    },
    BlockType.REFERENCE: {
        "refs": _spec("references", "strs", required=True, description="related prior works"),
    },
    BlockType.LINK_WITH_AGING: {
        "aging": _spec("agingConnection", required=True, description="aging/longevity/senescence link"),
    },
    BlockType.IMAGE: {
        "caption": _spec("caption", required=True, description="figure/table caption"),
        "title": _spec("title", description="figure/table title"),
        "desc": _spec("description", description="figure/table description"),
        "file": _spec("file", description="attached file"),
    },
    BlockType.CODE: {
        "code": _spec("code", required=True, description="code"),
        "lang": _spec("language", description="programming language"),
    },
    BlockType.FUNDING: {
        "funding": _spec("funding", "strs", required=True, description="funding sources"),
    },
    BlockType.INTEREST_CONFLICT: {
        "conflict": _spec("conflictOfInterest", required=True, description="competing interests"),
    },
    BlockType.SCIENTIFIC_KNOWLEDGE_VALUE: {
        "value": _spec("uncertaintyReduced", required=True, description="uncertainty reduced by the study"),
        "excl": _spec("excludedHypotheses", "strs", description="hypotheses excluded"),
        "likely": _spec("moreLikelyHypotheses", "strs", description="hypotheses made more likely"),
        "new": _spec("newHypotheses", "strs", description="new hypotheses raised"),
        "next": _spec("nextExperiment", description="next experiment with the greatest knowledge gain"),
    },
    BlockType.ACTION: {
        "sub": _spec("subject", required=True, description="actor"),
        "pred": _spec("predicate", required=True, description="action"),
        "obj": _spec("object", required=True, description="object of action"),
    },
    BlockType.EXPERIMENT_STEP: {
        "name": _spec("stepName", required=True, description="step name"),
        "details": _spec("details", description="step details"),
        "duration": _spec("duration", description="step duration"),
    },
    BlockType.FINDING: {
        "param": _spec("parameter", required=True, description="measured parameter"),
        "dir": _spec("direction", description="increased|decreased|no_change|mixed|trend|unknown"),
        "sig": _spec("significance", description="significant|non_significant|trend|not_reported"),
        "out": _spec("outcomeClass", description="positive|negative|neutral|mixed|inconclusive"),
        "detail": _spec("detail", description="numbers/details"),
        "figure": _spec("figureRef", description="figure reference"),
        "exp": _spec("experimentRef", "ref", description="experiment ref"),
        "grp": _spec("groupRefs", "refs", description="animal_group refs"),
        "cmp": _spec("comparisonGroupRefs", "refs", description="comparison animal_group refs"),
        "interv": _spec("interventionRef", "ref", description="intervention ref"),
        "cond": _spec("conditionRef", "ref", description="animal_model ref (experimental condition)"),
        "pval": _spec("pValueRef", "ref", description="probability_value ref"),
        "stats": _spec("statisticRefs", "refs", description="statistical_processing refs"),
        "seq": _spec("sequence", "strs", description="sequence of triplets"),
    },
    BlockType.RELATION: {
        "src": _spec("source", required=True, description="source entity name"),
        "tgt": _spec("target", required=True, description="target entity name"),
        "srcRef": _spec("sourceRef", "ref", description="source block ref"),
        "tgtRef": _spec("targetRef", "ref", description="target block ref"),
        "rel": _spec("relationType", required=True, description="causes|enables|requires|precedes|inhibits|prevents|leads_to|enhances|suppresses|associated_with|correlates_with, snake_case"),
        "conf": _spec("confidence", description="high|medium|low"),
        "ev": _spec("evidence", description="short supporting fact, 3-8 words"),
    },
    BlockType.TEMPORAL_RELATION: {
        "earlier": _spec("earlier", required=True, description="earlier event"),
        "later": _spec("later", required=True, description="later event"),
        "rel": _spec("relationType", description="precedes|follows|during|after|before"),
    },
}

# Default map roles. Every structural type is a map node or source evidence.
# Typed evidence references can attach evidence to a node but do not promote it.
MAP_NODE_TYPES: FrozenSet[str] = frozenset({
    BlockType.GOAL, BlockType.IMPACT_GOAL, BlockType.ACTION, BlockType.INTERVENTION,
    BlockType.EXPERIMENT, BlockType.EXPERIMENT_STEP, BlockType.METHOD,
    BlockType.RESEARCH_DESIGN, BlockType.PREREQUISITE, BlockType.EXPECTATIONS,
    BlockType.HYPOTHESIS, BlockType.INCLUSION_EXCLUSION_CRITERIA,
    BlockType.STATEMENT, BlockType.CLAIM, BlockType.ENTITY, BlockType.DEFINITION,
    BlockType.BIOLOGICAL_MECHANISM, BlockType.ASSUMPTIONS, BlockType.RESULT,
    BlockType.FINDING, BlockType.STATISTICAL_PROCESSING, BlockType.LIMITATIONS,
    BlockType.SIDE_FINDINGS, BlockType.SIDE_EFFECTS, BlockType.POST_CLAIMS,
    BlockType.OPEN_QUESTIONS, BlockType.NOVELTY,
    BlockType.FUTURE_RESEARCH_SUGGESTIONS, BlockType.LINK_WITH_AGING,
    BlockType.SCIENTIFIC_KNOWLEDGE_VALUE, BlockType.IDENTIFIABILITY_CRITERIA,
})
MAP_EVIDENCE_TYPES: FrozenSet[str] = frozenset(
    set(BlockType.ALL_TYPES_SET) - set(MAP_NODE_TYPES)
)

# Only these typed references assign a non-node row as evidence/property of
# the referring node. Other references are interpreted by map transition rules.
EVIDENCE_OWNER_FIELDS: FrozenSet[str] = frozenset({
    "experimentalPairs", "controlPairs", "groupRefs", "comparisonGroupRefs",
    "pValueRef", "statisticRefs", "conditionRef", "supportedBy", "sourceRefs",
})

# Поля, хранящие одиночную ссылку-тег B##.
REF_FIELDS: FrozenSet[str] = frozenset({
    "experimentRef", "interventionRef", "conditionRef", "speciesRef",
    "pValueRef", "sourceRef", "targetRef", "subjectStatementRef",
})

# Поля, хранящие список ссылок-тегов [B##, ...].
REFS_FIELDS: FrozenSet[str] = frozenset({
    "experimentalPairs", "controlPairs", "steps", "findings", "groupRefs",
    "comparisonGroupRefs", "statisticRefs", "sourceRefs", "experiments",
    "hypotheses", "supportedBy",
})

# Kept empty for source compatibility with older imports.
REF_GROUPS_FIELDS: FrozenSet[str] = frozenset()


def fields_for(block_type: str) -> Dict[str, FieldSpec]:
    """Канонические поля типа (пусто, если тип не описан в спецификации)."""
    return DSL_FIELDS.get(block_type, {})


def required_fields(block_type: str) -> List[str]:
    """Обоазательные JSON-поля типа (их присутствие проверяет валидация)."""
    return [spec.json_field for spec in DSL_FIELDS[block_type].values() if spec.required]


def required_dsl_fields(block_type: str) -> Dict[str, str]:
    """Обратная карта обязательных полей: JSON-поле → DSL-ключ.

    Нужна для сообщений модели: модель пишет только короткие DSL-ключи, тогда
    как сохранённый ``data`` использует JSON-поля.
    """
    return {
        spec.json_field: key
        for key, spec in DSL_FIELDS[block_type].items()
        if spec.required
    }


# Only direct-triple rows map to precisely one Assertion. Free-text and typed
# containers may yield 0..N Assertions, so they cannot be an unambiguous target.
DIRECT_ASSERTION_TYPES: FrozenSet[str] = frozenset({
    BlockType.STATEMENT, BlockType.GOAL, BlockType.ENTITY,
    BlockType.CLAIM, BlockType.ACTION,
})
SUBJECT_OPERATIONS: FrozenSet[str] = frozenset({"identify_subjects"})


def subject_operation_issues(data: dict) -> List[str]:
    """Validate the all-or-nothing typed operation on a statement subject."""
    operation = data.get("subjectOperation")
    reference = data.get("subjectStatementRef")
    issues: List[str] = []
    if bool(operation) != bool(reference):
        issues.append("subop= and subref= must be supplied together")
    if operation and operation not in SUBJECT_OPERATIONS:
        issues.append("subop= must be identify_subjects")
    subject = str(data.get("subject") or "")
    if re.search(r"^\s*identifying\b.*\b(?:that|which)\b", subject, re.IGNORECASE):
        issues.append("sub= hides a relative assertion; use an atomic row and subop=/subref=")
    return issues


def allowed_kinds(block_type: str) -> Dict[str, str]:
    """JSON-поле → kind (для парсера/валидатора)."""
    return {spec.json_field: spec.kind for spec in DSL_FIELDS.get(block_type, {}).values()}


_COMMON_MAP_DSL_KEYS: FrozenSet[str] = frozenset()


def render_field_docs(block_type: str, *, include_common: bool = False) -> str:
    """Компактная строка-документация полей для LLM-промпта.

    Вывод намеренно содержит только DSL-ключи, которые разрешено писать
    модели. Внутренние JSON-поля хранилища в промпт не попадают.
    """
    parts = []
    for key, spec in DSL_FIELDS.get(block_type, {}).items():
        if key in _COMMON_MAP_DSL_KEYS and not include_common:
            continue
        kind = {"str": "plain", "int": "int", "float": "number",
                "bool": "bool", "ref": "ref", "refs": "refs",
                "strs": "list", "ref_groups": "ref-groups"}[spec.kind]
        required_mark = "(required)" if spec.required else ""
        description = spec.description
        if spec.choices:
            choices = "|".join(spec.choices)
            description = f"{description}; allowed: {choices}" if description else f"allowed: {choices}"
        parts.append(f"{key}=<{kind}>{required_mark} ({description})")
    return " ".join(parts)


def render_common_map_field_docs() -> str:
    """Compatibility helper; map transitions are not model-generated fields."""
    return ""


def render_type_doc() -> str:
    """Полная справка «TYPE KEY -> fields» для LLM-промпта прямой типизации."""
    lines: List[str] = []
    for block_type in BlockType.ALL_TYPES:
        docs = render_field_docs(block_type)
        lines.append(f"  {block_type}: {docs}")
    return "\n".join(lines)


def referenced_tags(block_type: str, data: dict) -> List[str]:
    """Collect all B-tags referenced by the typed fields of a structural row.

    References validate provenance and are interpreted by typed transition and
    evidence-ownership rules in the deterministic knowledge-map builder.
    """
    from .dsl_tags import iter_tags
    tags: List[str] = []
    for key, spec in DSL_FIELDS.get(block_type, {}).items():
        if spec.kind not in ("ref", "refs", "ref_groups"):
            continue
        value = data.get(spec.json_field)
        if value is None:
            continue
        if spec.kind == "ref_groups":
            tags.extend(tag for group in value for tag in group)
        else:
            tags.extend(iter_tags(value))
    return tags
