"""
Правила для автоматического создания онтологических связей
"""

# Правила для IS_A отношений
IS_A_RULES = [
    {
        "pattern": "X_as_Y",  # "dopamine as a neurotransmitter"
        "syntax": {"dep": "pobj", "prep": "as"},
        "relations": ["IS_A", "what_is_it"]
    },
    {
        "pattern": "subclass",
        "pairs": [
            ("dopamine", "neurotransmitter"),
            ("Parkinsons_disease", "disease")
        ]
    }
]

# Правила для PART_OF отношений
PART_OF_RULES = [
    {
        "pattern": "X_of_Y",  # "complexity of disease"
        "syntax": {"dep": "pobj", "prep": "of"},
        "conditions": lambda head: head.lemma_ in ["complexity", "knowledge", "factor"],
        "relations": ["PART_OF", "of_what"]
    },
    {
        "pattern": "predefined_pairs",
        "pairs": [
            ("knowledge", "body_of_knowledge"),
            ("genetic_factors", "factors"),
            ("environmental_factors", "factors"),
            ("complexity", "disease"),
            ("progression", "pathogenesis"),
            ("pathogenesis", "disease")
        ]
    }
]

# Правила для HAS_PROPERTY отношений
HAS_PROPERTY_RULES = [
    {
        "pattern": "amod",
        "syntax": {"pos": "ADJ", "dep": "amod"},
        "relations": ["HAS_PROPERTY", "what_kind"],
        "inverse": "amod_of"
    },
    {
        "pattern": "predefined_properties",
        "pairs": [
            ("body_of_knowledge", ["rich", "complex"]),
            ("disease", ["age_related", "multifactorial"]),
            ("complexity", ["tremendous"]),
            ("progression", ["nonlinear"]),
            ("systems", ["molecular", "cellular", "organic"])
        ]
    }
]

# Правила для аббревиатур
ABBREVIATION_RULES = [
    {
        "pattern": "appos",
        "syntax": {"dep": "appos"},
        "relation": "IS_ABBREVIATION_OF",
        "shorter_first": True
    },
    {
        "pattern": "predefined",
        "pairs": [("PD", "Parkinsons_disease")]
    }
]

# Правила для HAS_TOPIC / HAS_OBJECT
TOPIC_OBJECT_RULES = [
    {
        "pattern": "research_of",
        "trigger_lemmas": ["research", "study"],
        "syntax": {"prep": "of"},
        "relation": ["HAS_TOPIC", "of_what_disease", "focuses_on", "topic_of"]
    },
    {
        "pattern": "discovery_of",
        "trigger_lemmas": ["discovery"],
        "syntax": {"prep": "of"},
        "relation": ["HAS_OBJECT", "what_discovered"]
    }
]

# Специфичные семантические связи для доменных концептов
DOMAIN_SEMANTIC_RULES = {
    "research": {
        "relations": [
            ("research", "generated", "body_of_knowledge"),
            ("research", "started_after", "discovery"),
            ("research", "since_when", "discovery")
        ]
    },
    "body_of_knowledge": {
        "relations": [
            ("body_of_knowledge", "reveals", "PD"),
            ("body_of_knowledge", "supports_classification", "disease"),
            ("body_of_knowledge", "consists_of", "knowledge"),
            ("body_of_knowledge", "characterized_by", "rich"),
            ("body_of_knowledge", "characterized_by", "complex"),
            ("body_of_knowledge", "what_reveals", "reveal")
        ]
    },
    "genetic_factors": {
        "relations": [
            ("genetic_factors", "influences", "disease"),
            ("disease", "influenced_by", "genetic_factors"),
            ("disease", "influenced_by_what", "genetic_factors")
        ]
    },
    "environmental_factors": {
        "relations": [
            ("environmental_factors", "influences", "disease"),
            ("disease", "influenced_by", "environmental_factors"),
            ("disease", "influenced_by_what", "environmental_factors")
        ]
    },
    "PD": {
        "relations": [
            ("PD", "classified_as", "age_related"),
            ("PD", "classified_as", "multifactorial"),
            ("PD", "nsubj_of", "disease"),
            ("PD", "what_is_pd", "disease")
        ]
    },
    "discovery": {
        "relations": [
            ("discovery", "when", "1950s"),
            ("discovery", "happened_in", "1950s"),
            ("1950s", "nmod_of", "discovery"),
            ("discovery", "HAS_OBJECT", "dopamine"),
            ("discovery", "what_discovered", "dopamine"),
            ("discovery", "advcl_of", "generate")
        ]
    },
    "dopamine": {
        "relations": [
            ("dopamine", "IS_A", "neurotransmitter"),
            ("dopamine", "what_is_it", "neurotransmitter"),
            ("dopamine", "functions_as", "neurotransmitter"),
            ("neurotransmitter", "nmod_of", "dopamine"),
            ("dopamine", "nmod_of", "discovery")
        ]
    },
    "disease": {
        "relations": [
            ("disease", "HAS_PROPERTY", "age_related"),
            ("disease", "what_kind", "age_related"),
            ("age_related", "amod_of", "disease"),
            ("disease", "xcomp_of", "reveal"),
            ("disease", "has_complexity", "complexity"),
            ("disease", "nmod_of", "complexity")
        ]
    },
    "complex": {
        "relations": [
            ("complex", "amod_of", "body_of_knowledge"),
            ("body_of_knowledge", "HAS_PROPERTY", "complex"),
            ("body_of_knowledge", "what_kind", "complex")
        ]
    },
    "factors": {
        "relations": [
            ("factors", "obl_agent_of", "influence"),
            ("genetic_factors", "conj_of", "environmental_factors"),
            ("environmental_factors", "conj_of", "genetic_factors")
        ]
    },
    "reveal": {
        "relations": [
            ("reveal", "acl_of", "body_of_knowledge")
        ]
    },
    "pathogenesis": {
        "relations": [
            ("pathogenesis", "progresses_through", "systems")
        ]
    },
    "systems": {
        "conj_rules": [
            ("molecular", "cellular"),
            ("cellular", "organic")
        ]
    }
}