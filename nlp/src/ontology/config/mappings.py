"""
Маппинги для преобразования синтаксических структур в онтологические связи
"""

# Маппинг синтаксических зависимостей на отношения
DEPENDENCY_MAPPING = {
    "nsubj": "nsubj_of",
    "nsubjpass": "nsubjpass_of",
    "dobj": "obj_of",
    "obj": "obj_of",
    "amod": "amod_of",
    "advmod": "advmod_of",
    "advcl": "advcl_of",
    "acl": "acl_of",
    "xcomp": "xcomp_of",
    "ccomp": "ccomp_of",
    "nmod": "nmod_of",
    "pobj": "pobj_of",
    "conj": "conj_of",
    "appos": "appos_of",
}

# Зависимости которые нужно пропускать при поиске head
SKIP_DEPENDENCIES = {"prep", "case", "mark"}

# Маппинг глаголов на семантические отношения
ACTION_VERB_MAPPING = {
    "generate": {
        "semantic": "generated",
        "passive_swap": False
    },
    "create": {
        "semantic": "created",
        "passive_swap": False
    },
    "reveal": {
        "semantic": "reveals",
        "passive_swap": False
    },
    "show": {
        "semantic": "shows",
        "passive_swap": False
    },
    "influence": {
        "semantic": "influences",
        "passive_swap": False,
        "inverse": ["influenced_by", "influenced_by_what"]
    },
    "affect": {
        "semantic": "affects",
        "passive_swap": False
    },
    "increase": {
        "semantic": "increases",
        "passive_swap": True,  # В пассиве: объект увеличивает субъект
        "passive_relations": ["increased_by", "by_what"]
    }
}

# Маппинг предлогов на временные/пространственные отношения
PREPOSITION_MAPPING = {
    "in": {
        "temporal": "happened_in",
        "spatial": None,
        "question": "when"
    },
    "since": {
        "temporal": "started_after",
        "question": "since_when",
        "additional": ["when"]
    },
    "during": {
        "temporal": "happened_during",
        "question": "when"
    },
    "between": {
        "spatial": ["happens_between", "occurs_in", "where"],
        "additional": ["nmod_of"],
        "inverse": True
    }
}