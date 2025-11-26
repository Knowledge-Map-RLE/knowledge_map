"""
Linguistic markers for different dependency types
"""

# Временные маркеры
TEMPORAL_MARKERS = {
    'BEFORE': [
        r'\b(before|prior to|preceding|earlier)\b',
        r'\b(then|subsequently|following|next|after that|later)\b',
        r'\b(first|initially|at first).*(then|later|after)\b',
        r'\b(precedes?|comes? before)\b',
        r'\b(leads? up to|builds? up to)\b',
    ],
    'AFTER': [
        r'\b(after|following|upon|once)\b',
        r'\b(when|as soon as|immediately after)\b',
        r'\b(subsequent to|in the wake of)\b',
        r'\b(in response to)\b',
    ],
    'DURING': [
        r'\b(during|while|throughout|in the course of)\b',
        r'\b(simultaneously|at the same time|concurrently)\b',
        r'\b(in parallel with|alongside)\b',
    ]
}

# Причинные маркеры
CAUSAL_MARKERS = {
    'CAUSES': [
        r'\b(causes?|leads? to|results? in|produces?)\b',
        r'\b(triggers?|induces?|generates?|brings? about)\b',
        r'\b(consequently|therefore|thus|hence|as a result)\b',
        r'\b(because of|due to|owing to)\b',
        r'\b(thereby|thus)\s+\w+ing\b',
        r'\b(giving rise to|contributes? to|promotes?)\b',
        r'\b(is instrumental in|plays? a (?:key |major )?role in)\b',
        r'\b(accounts? for|explains?|underlies?)\b',
        r'\b(stems? from|arises? from|originates? from)\b',
        r'\b(can lead to|may lead to|might lead to)\b',
        # Биомедицинские:
        r'\b(?:is |are )?involved in\b',
        r'\b(?:is |are )?responsible for\b',
        r'\b(?:is |are )?implicated in\b',
        r'\b(?:the )?loss of\b',
        r'\b(?:the )?death of\b',
        r'\b(?:the )?formation of\b',
        r'\b(?:the )?aggregation of\b',
        r'\b(?:the )?dysfunction of\b',
        r'\b(?:the )?degeneration of\b',
        # Косвенные каузальные маркеры:
        r'\b(in turn)\b',
        r'\b(thereby contributing to)\b',
        r'\b(which (?:can |may |might )?have)\b',
        r'\b(having .* consequences? (?:such as|including))\b',
        # Биологические процессы:
        r'\b(?:is |are )?(?:an? )?inhibitor of\b',
        r'\b(?:is |are )?(?:an? )?activator of\b',
        r'\b(activates?|activate)\b',
        r'\b(stabilizes?|stabilizing)\b',
        r'\b(increases? the (?:risk|susceptibility|production))\b',
        r'\b(contributes? to the)\b',
        r'\b(?:through|via) (?:the )?(?:production|release|activation) of\b',
        # Механизмы с "by":
        r'\bby\s+(?:stabilizing|promoting|activating|inhibiting|binding|sequestering)\b',
        r'\bby\s+\w+ing\s+\w+\b',
    ],
    'PREVENTS': [
        r'\b(prevents?|inhibits?|blocks?|suppresses?)\b',
        r'\b(avoids?|stops?|impedes?|hinders?)\b',
        r'\b(counteracts?|opposes?)\b',
        r'\b(protects? against|guards? against)\b',
        r'\b(disrupts?|interferes? with)\b',
        r'\b(reduces?|decreases?|diminishes?)\b',
        # Биомедицинские:
        r'\b(?:is |are )?protective against\b',
        r'\b(?:prevents? the onset of)\b',
        r'\b(?:is |are )?lacking\b',
        r'\b(markedly inhibits?)\b',
    ],
    'ENABLES': [
        r'\b(enables?|allows?|permits?|facilitates?)\b',
        r'\b(makes? possible|makes? it possible)\b',
        r'\b(promotes?|supports?|helps?)\b',
        r'\b(enhances?|augments?)\b',
        r'\b(is sufficient to)\b',
        r'\b(able to)\b',
    ]
}

# Условные маркеры
CONDITIONAL_MARKERS = {
    'REQUIRES': [
        r'\b(requires?|needs?|depends? on|relies? on)\b',
        r'\b(is required for|is necessary for|is needed to)\b',
        r'\b(is essential for|necessitates?)\b',
        r'\b(controlled (?:via|by)|regulated by|mediated by)\b',
        r'\b(dependent upon|contingent upon)\b',
        r'\b(in cases? of|in the presence of)\b',
        r'\b(when|if|provided that)\b',
    ]
}

# Целевые маркеры
PURPOSE_MARKERS = {
    'PURPOSE': [
        r'\b(to|in order to|for the purpose of)\b',
        r'\b(aiming to|with the goal of|with the aim of)\b',
        r'\b(so that|such that)\b',
        r'\b(intended to|designed to)\b',
        r'\b(in an effort to|in an attempt to)\b',
    ]
}

# Механистические маркеры
MECHANISM_MARKERS = {
    'VIA_MECHANISM': [
        r'\b(by|via|through)\s+\w+ing\b',
        r'\bby means of\b',
        r'\bmediated by\b',
    ]
}

# Корреляционные маркеры
CORRELATION_MARKERS = {
    'CORRELATES': [
        r'\b(correlates? with|is correlated with)\b',
        r'\b(is associated with|is linked to)\b',
        r'\b(relates? to|is related to)\b',
        r'\b(coincides? with|accompanies?)\b',
        # Биомедицинские:
        r'\b(?:is |are )?characterized by\b',
        r'\b(?:presents? (?:as|with))\b',
        r'\b(?:shows?|showing)\b',
    ]
}

# Маркеры отношений "часть-целое"
PART_OF_MARKERS = {
    'PART_OF': [
        r'\b(?:is )?(?:a |an )?(?:part|component|region|area|section|segment|portion|division) of\b',
        r'\b(?:is )?(?:located |found |situated )?(?:in|within|inside)\b',
        r'\b(?:is )?(?:a |an )?(?:subregion|subdivision|subsection) of\b',
        r'\b(?:is )?(?:contained )?(?:in|within)\b',
        r'\b(?:belongs? to|is part of)\b',
        r'\bcomprises?\b',
        r'\bconsists? of\b',
        r'\b(?:is )?(?:a |an )?(?:member|element) of\b',
        # Биомедицинские:
        r'\b(?:in|within) the (?:brain|CNS|system|pathway|structure)\b',
        r'\bof the (?:brain|CNS|system|pathway|cell|neuron)\b',
    ]
}

# Маркеры параллельности
PARALLEL_MARKERS = [
    r'\b(simultaneously|at the same time|concurrently|in parallel)\b',
    r'\b(meanwhile|while|as)\b',
    r'\b(both .* and|as well as|along with|together with)\b'
]

# Приоритеты типов зависимостей (для разрешения конфликтов)
PRIORITY = {
    'CAUSES': 5,
    'PREVENTS': 5,
    'ENABLES': 4,
    'VIA_MECHANISM': 4,
    'PART_OF': 3,
    'REQUIRES': 3,
    'TEMPORAL_BEFORE': 2,
    'TEMPORAL_AFTER': 2,
    'CORRELATES': 2,
    'PURPOSE': 1,
}
