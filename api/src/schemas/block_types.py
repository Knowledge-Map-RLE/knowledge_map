"""Канонический реестр типов структурных строк (блоков) Карты Знаний.

Обозначения типов соответствуют пункту «Обозначение» в Спецификации.md.
Числовые коды 1..59 были заменены на строковые обозначения
(например T4 DIRECT_TRIPLET → "statement").

Единый источник истины для Python-схем, сервисов, LLM-промптов и миграций.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List, Tuple


class BlockType:
    """Строковые обозначения структурных строк по Спецификации.md."""

    METADATA = "metadata"
    GOAL = "goal"
    TEXT = "text"
    STATEMENT = "statement"
    HYPOTHESIS = "hypothesis"
    PREREQUISITE = "prerequisite"
    EXPECTATIONS = "expectations"
    RESEARCH_DESIGN = "research_design"
    MATERIAL = "material"
    METHOD = "method"
    EXPERIMENT = "experiment"
    INCLUSION_EXCLUSION_CRITERIA = "inclusion_exclusion_criteria"
    BIOLOGICAL_MECHANISM = "biological_mechanism"
    IMPACT_GOAL = "impact_goal"
    INTERVENTION = "intervention"
    ANIMAL_MODEL = "animal_model"
    ANIMAL_GROUP = "animal_group"
    ENTITY = "entity"
    DEFINITION = "definition"
    ASSUMPTIONS = "assumptions"
    SAMPLE_SIZE = "sample_size"
    DATA_SOURCE = "data_source"
    PROBABILITY_VALUE = "probability_value"
    VARIANCE = "variance"
    EFFECT_SIZE = "effect_size"
    STATISTICAL_POWER = "statistical_power"
    CONFIDENCE_INTERVAL = "confidence_interval"
    MAGNITUDE_VALUE = "magnitude_value"
    FORMULA = "formula"
    CAUSAL_GRAPH = "causal_graph"
    IDENTIFIABILITY_CRITERIA = "identifiability_criteria"
    RESULT = "result"
    STATISTICAL_PROCESSING = "statistical_processing"
    CLAIM = "claim"
    LIMITATIONS = "limitations"
    SIDE_FINDINGS = "side_findings"
    SIDE_EFFECTS = "side_effects"
    POST_CLAIMS = "post_claims"
    OPEN_QUESTIONS = "open_questions"
    NOVELTY = "novelty"
    VERSIONS = "versions"
    FUTURE_RESEARCH_SUGGESTIONS = "future_research_suggestions"
    REFERENCE = "reference"
    LINK_WITH_AGING = "link_with_aging"
    IMAGE = "image"
    CODE = "code"
    FUNDING = "funding"
    INTEREST_CONFLICT = "interest_conflict"
    SCIENTIFIC_KNOWLEDGE_VALUE = "scientific_knowledge_value"
    ACTION = "action"
    EXPERIMENT_STEP = "experiment_step"
    FINDING = "finding"
    RELATION = "relation"
    TEMPORAL_RELATION = "temporal_relation"

    # Типы, у которых есть sequence (контейнеры для statement-триплетов).
    CONTAINER_TYPES: FrozenSet[str] = frozenset({
        HYPOTHESIS,
        BIOLOGICAL_MECHANISM,
        ENTITY,
        DEFINITION,
        STATISTICAL_PROCESSING,
        CLAIM,
        LIMITATIONS,
        SIDE_FINDINGS,
        NOVELTY,
        FUTURE_RESEARCH_SUGGESTIONS,
        REFERENCE,
        EXPERIMENT_STEP,
        FINDING,
    })

    # Все типы в порядке следования Спецификации.md.
    ALL_TYPES: Tuple[str, ...] = (
        METADATA,
        GOAL,
        TEXT,
        STATEMENT,
        HYPOTHESIS,
        PREREQUISITE,
        EXPECTATIONS,
        RESEARCH_DESIGN,
        MATERIAL,
        METHOD,
        EXPERIMENT,
        INCLUSION_EXCLUSION_CRITERIA,
        BIOLOGICAL_MECHANISM,
        IMPACT_GOAL,
        INTERVENTION,
        ANIMAL_MODEL,
        ANIMAL_GROUP,
        ENTITY,
        DEFINITION,
        ASSUMPTIONS,
        SAMPLE_SIZE,
        DATA_SOURCE,
        PROBABILITY_VALUE,
        VARIANCE,
        EFFECT_SIZE,
        STATISTICAL_POWER,
        CONFIDENCE_INTERVAL,
        MAGNITUDE_VALUE,
        FORMULA,
        CAUSAL_GRAPH,
        IDENTIFIABILITY_CRITERIA,
        RESULT,
        STATISTICAL_PROCESSING,
        CLAIM,
        LIMITATIONS,
        SIDE_FINDINGS,
        SIDE_EFFECTS,
        POST_CLAIMS,
        OPEN_QUESTIONS,
        NOVELTY,
        VERSIONS,
        FUTURE_RESEARCH_SUGGESTIONS,
        REFERENCE,
        LINK_WITH_AGING,
        IMAGE,
        CODE,
        FUNDING,
        INTEREST_CONFLICT,
        SCIENTIFIC_KNOWLEDGE_VALUE,
        ACTION,
        EXPERIMENT_STEP,
        FINDING,
        RELATION,
        TEMPORAL_RELATION,
    )

    ALL_TYPES_SET: FrozenSet[str] = frozenset(ALL_TYPES)

    # Типы, помеченные в Спецификации как «только 1 структурная строка на статью».
    SINGLETON_TYPES: FrozenSet[str] = frozenset({METADATA})


# Module-level алиасы (для идиоматичных импортов без обращения к классу).
ALL_TYPES: Tuple[str, ...] = BlockType.ALL_TYPES
ALL_TYPES_SET: FrozenSet[str] = BlockType.ALL_TYPES_SET


# Обозначения: RU-название (для UI и промптов).
BLOCK_TYPE_NAMES: Dict[str, str] = {
    BlockType.METADATA: "Метаданные",
    BlockType.GOAL: "Цель исследования",
    BlockType.TEXT: "Свободный текст",
    BlockType.STATEMENT: "Универсальное утверждение (триплет)",
    BlockType.HYPOTHESIS: "Гипотеза",
    BlockType.PREREQUISITE: "Предпосылки",
    BlockType.EXPECTATIONS: "Ожидания",
    BlockType.RESEARCH_DESIGN: "Дизайн исследования",
    BlockType.MATERIAL: "Материал",
    BlockType.METHOD: "Метод, логика исследователя",
    BlockType.EXPERIMENT: "Эксперимент",
    BlockType.INCLUSION_EXCLUSION_CRITERIA: "Критерии включения и исключения",
    BlockType.BIOLOGICAL_MECHANISM: "Биологический механизм",
    BlockType.IMPACT_GOAL: "Цель воздействия",
    BlockType.INTERVENTION: "Интервенция",
    BlockType.ANIMAL_MODEL: "Животная модель",
    BlockType.ANIMAL_GROUP: "Группа животных",
    BlockType.ENTITY: "Сущность",
    BlockType.DEFINITION: "Определение понятия",
    BlockType.ASSUMPTIONS: "Предположения",
    BlockType.SAMPLE_SIZE: "Размер выборки",
    BlockType.DATA_SOURCE: "Источник данных",
    BlockType.PROBABILITY_VALUE: "p-value",
    BlockType.VARIANCE: "Дисперсия",
    BlockType.EFFECT_SIZE: "Размер эффекта",
    BlockType.STATISTICAL_POWER: "Статистическая мощность",
    BlockType.CONFIDENCE_INTERVAL: "Доверительный интервал",
    BlockType.MAGNITUDE_VALUE: "Числа с названиями и величинами",
    BlockType.FORMULA: "Формула",
    BlockType.CAUSAL_GRAPH: "Каузальный граф (DAG)",
    BlockType.IDENTIFIABILITY_CRITERIA: "Критерии идентифицируемости Перла",
    BlockType.RESULT: "Результат (таблицы данных)",
    BlockType.STATISTICAL_PROCESSING: "Статистическая обработка",
    BlockType.CLAIM: "Утверждение",
    BlockType.LIMITATIONS: "Ограничения исследования",
    BlockType.SIDE_FINDINGS: "Побочные выводы и гипотезы",
    BlockType.SIDE_EFFECTS: "Сопутствующие эффекты",
    BlockType.POST_CLAIMS: "Утверждения после исследования",
    BlockType.OPEN_QUESTIONS: "Открытые вопросы",
    BlockType.NOVELTY: "Новизна",
    BlockType.VERSIONS: "Версии",
    BlockType.FUTURE_RESEARCH_SUGGESTIONS: "Предложения для будущих исследований",
    BlockType.REFERENCE: "Связь с предыдущими исследованиями",
    BlockType.LINK_WITH_AGING: "Связь со старением",
    BlockType.IMAGE: "Изображение",
    BlockType.CODE: "Код",
    BlockType.FUNDING: "Источник финансирования",
    BlockType.INTEREST_CONFLICT: "Конфликт интересов",
    BlockType.SCIENTIFIC_KNOWLEDGE_VALUE: "Информационная ценность знаний",
    BlockType.ACTION: "Действие",
    BlockType.EXPERIMENT_STEP: "Шаг эксперимента",
    BlockType.FINDING: "Результат (находка)",
    BlockType.RELATION: "Причинно-следственная связь",
    BlockType.TEMPORAL_RELATION: "Временная последовательность",
}

# Карта миграции: старый числовой код (1..59) → строка-обозначение.
LEGACY_INT_TO_KEY: Dict[int, str] = {
    1: BlockType.METADATA,
    2: BlockType.GOAL,
    3: BlockType.TEXT,
    4: BlockType.STATEMENT,
    5: BlockType.RESEARCH_DESIGN,          # T5 Первичная конечная точка → research_design
    6: BlockType.RESEARCH_DESIGN,          # T6 Вторичные конечные точки → research_design
    7: BlockType.HYPOTHESIS,
    8: BlockType.PREREQUISITE,
    9: BlockType.EXPECTATIONS,
    10: BlockType.PREREQUISITE,            # T10 Знания-зависимости → prerequisite
    11: BlockType.RESEARCH_DESIGN,
    12: BlockType.MATERIAL,
    13: BlockType.METHOD,
    14: BlockType.EXPERIMENT,
    15: BlockType.INCLUSION_EXCLUSION_CRITERIA,
    16: BlockType.BIOLOGICAL_MECHANISM,
    17: BlockType.IMPACT_GOAL,
    18: BlockType.INTERVENTION,
    19: BlockType.ANIMAL_MODEL,
    20: BlockType.POST_CLAIMS,             # T20 Заключения → post_claims
    21: BlockType.METHOD,                  # T21 Логика исследователя → method
    22: BlockType.ENTITY,
    23: BlockType.DEFINITION,
    24: BlockType.ASSUMPTIONS,
    25: BlockType.SAMPLE_SIZE,
    26: BlockType.DATA_SOURCE,
    27: BlockType.PROBABILITY_VALUE,
    28: BlockType.VARIANCE,
    29: BlockType.EFFECT_SIZE,
    30: BlockType.STATISTICAL_POWER,
    31: BlockType.CONFIDENCE_INTERVAL,
    32: BlockType.MAGNITUDE_VALUE,
    33: BlockType.FORMULA,
    34: BlockType.CAUSAL_GRAPH,
    35: BlockType.IDENTIFIABILITY_CRITERIA,
    36: BlockType.RESULT,
    37: BlockType.STATISTICAL_PROCESSING,
    38: BlockType.CLAIM,
    39: BlockType.LIMITATIONS,
    40: BlockType.SIDE_FINDINGS,
    41: BlockType.SIDE_EFFECTS,
    42: BlockType.POST_CLAIMS,
    43: BlockType.OPEN_QUESTIONS,
    44: BlockType.NOVELTY,
    45: BlockType.VERSIONS,
    46: BlockType.FUTURE_RESEARCH_SUGGESTIONS,
    47: BlockType.REFERENCE,
    48: BlockType.LINK_WITH_AGING,
    49: BlockType.IMAGE,
    50: BlockType.CODE,
    51: BlockType.FUNDING,
    52: BlockType.INTEREST_CONFLICT,
    53: BlockType.SCIENTIFIC_KNOWLEDGE_VALUE,
    54: BlockType.ACTION,
    55: BlockType.ANIMAL_GROUP,
    56: BlockType.EXPERIMENT_STEP,
    57: BlockType.FINDING,
    58: BlockType.RELATION,
    59: BlockType.TEMPORAL_RELATION,
}

KEY_TO_LEGACY_INT: Dict[str, int] = {
    key: value for value, key in LEGACY_INT_TO_KEY.items()
}


def coerce_block_type(value) -> str:
    """Приводит произвольное значение blockType к строке-обозначению.

    Понимает старые числовые коды (1..59), существующие строки-обозначения и
    неизвестные значения → "" (чтобы не падало при legacy-данных).
    """
    if isinstance(value, str):
        stripped = value.strip()
        if stripped in BlockType.ALL_TYPES_SET:
            return stripped
        # legacy-строки вида "T4", "4"
        if stripped.isdigit():
            return LEGACY_INT_TO_KEY.get(int(stripped), "")
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return LEGACY_INT_TO_KEY.get(value, "")
    return ""