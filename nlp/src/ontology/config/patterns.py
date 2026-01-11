"""
Конфигурация паттернов для распознавания составных терминов
"""

# Составные термины с точными шаблонами
COMPOUND_PATTERNS = {
    # Формат: "pattern_name": {
    #   "trigger": лемма или текст триггера,
    #   "search": [(relation, lemma/pos, distance), ...],
    #   "concept_name": имя концепта,
    #   "label": читаемая метка
    # }
    
    "body_of_knowledge": {
        "trigger": "body",
        "search": [
            ("prep", "of", 1),
            ("pobj", "knowledge", 2)
        ],
        "concept_name": "body_of_knowledge",
        "label": "body of knowledge",
        "tokens_to_map": ["trigger", "prep", "pobj"],
        "exclude_from_separate": ["pobj"]  # knowledge создаётся отдельно
    },
    
    "genetic_factors": {
        "trigger": "factor",
        "search": [("amod", "genetic", 1)],
        "concept_name": "genetic_factors",
        "label": "genetic factors",
        "tokens_to_map": ["trigger", "amod"]
    },
    
    "environmental_factors": {
        "trigger": "factor",
        "search": [("amod", "environmental", 1)],
        "concept_name": "environmental_factors",
        "label": "environmental factors",
        "tokens_to_map": ["trigger", "amod"]
    },
}

# Именованные сущности (NER) с преобразованием
NER_PATTERNS = {
    "Parkinsons_disease": {
        "text_contains": ["parkinson", "disease"],
        "max_distance": 3,
        "concept_name": "Parkinsons_disease",
        "label": "Parkinson's disease"
    }
}

# Специальные токены (аббревиатуры, даты)
SPECIAL_TOKENS = {
    "PD": {
        "match": lambda token: token.text == "PD",
        "concept_name": "PD",
        "label": "PD"
    },
    "1950s": {
        "match": lambda token: "1950" in token.text,
        "concept_name": "1950s",
        "label": "1950s"
    },
    "age_related": {
        "match": lambda token: "age-related" in token.text.lower(),
        "concept_name": "age_related",
        "label": "age-related"
    }
}

# Термины с сохранением конкретной формы (не лемматизируем)
PRESERVE_FORM = {
    "systems": "systems",
    "knowledge": "knowledge"
}