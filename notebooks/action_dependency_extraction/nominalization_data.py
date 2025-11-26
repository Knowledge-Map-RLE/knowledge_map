"""
Данные о номинализациях для биомедицинских текстов
"""

# Номинализации: существительные, образованные от глаголов
# Формат: базовая форма → список вариантов
NOMINALIZATIONS = {
    # Генетические/молекулярные процессы
    'mutation': ['mutation', 'mutations'],
    'duplication': ['duplication', 'duplications'],
    'deletion': ['deletion', 'deletions'],
    'insertion': ['insertion', 'insertions'],
    'substitution': ['substitution', 'substitutions'],
    'expression': ['expression', 'overexpression'],
    'regulation': ['regulation', 'deregulation'],
    'activation': ['activation'],
    'inhibition': ['inhibition'],
    'suppression': ['suppression'],
    'misfolding': ['misfolding'],

    # Клеточные процессы
    'aggregation': ['aggregation'],
    'accumulation': ['accumulation'],
    'formation': ['formation'],
    'degradation': ['degradation'],
    'degeneration': ['degeneration', 'neurodegeneration'],
    'dysfunction': ['dysfunction'],
    'damage': ['damage'],
    'loss': ['loss'],
    'death': ['death'],
    'survival': ['survival'],
    'clearance': ['clearance'],

    # Метаболические процессы
    'oxidation': ['oxidation'],
    'reduction': ['reduction'],
    'phosphorylation': ['phosphorylation'],
    'ubiquitination': ['ubiquitination'],
    'acetylation': ['acetylation'],
    'methylation': ['methylation'],
    'peroxidation': ['peroxidation'],

    # Транспорт и движение
    'transmission': ['transmission'],
    'transport': ['transport'],
    'trafficking': ['trafficking'],
    'spread': ['spread', 'spreading'],
    'propagation': ['propagation'],
    'translocation': ['translocation'],

    # Биомедицинские состояния
    'exposure': ['exposure'],
    'treatment': ['treatment'],
    'administration': ['administration'],
    'onset': ['onset'],
    'progression': ['progression'],
    'development': ['development'],
    'deficiency': ['deficiency'],

    # Иммунные процессы
    'inflammation': ['inflammation', 'neuroinflammation'],
    'activation': ['activation'],
    'response': ['response'],

    # Синаптические процессы
    'release': ['release'],
    'uptake': ['uptake'],
    'recycling': ['recycling'],
    'reuptake': ['reuptake'],

    # Общие процессы
    'increase': ['increase'],
    'decrease': ['decrease'],
    'change': ['change', 'changes'],
    'reduction': ['reduction'],

    # Патологические процессы (добавлено)
    'impairment': ['impairment'],
    'disruption': ['disruption'],
    'interference': ['interference'],
    'toxicity': ['toxicity', 'neurotoxicity'],
    'susceptibility': ['susceptibility'],
    'vulnerability': ['vulnerability'],

    # Биохимические процессы (добавлено)
    'binding': ['binding'],
    'interaction': ['interaction'],
    'production': ['production'],
    'synthesis': ['synthesis'],
    'catalysis': ['catalysis'],
    'reaction': ['reaction'],
}

# Создаём плоский список для быстрого поиска
NOMINALIZATION_SET = set()
NOMINALIZATION_TO_BASE = {}
for base, variants in NOMINALIZATIONS.items():
    for variant in variants:
        NOMINALIZATION_SET.add(variant)
        NOMINALIZATION_TO_BASE[variant] = base

# Ключевые биомедицинские сущности (не номинализации, но важны)
KEY_ENTITIES = {
    # Болезни
    'PD', 'IPD', 'parkinsonism', 'disease', 'syndrome',
    'Alzheimer', 'dementia',

    # Белки и гены
    'α-synuclein', 'a-synuclein', 'synuclein',
    'LRRK2', 'Parkin', 'PINK1', 'DJ-1', 'ATP13A2',

    # Клеточные структуры
    'neuron', 'neurons', 'microglia', 'astrocyte', 'astrocytes',
    'mitochondria', 'mitochondrion',
    'dopaminergic', 'DA',

    # Анатомия
    'substantia nigra', 'SN', 'striatum', 'brain',
    'CNS', 'enteric nervous system',

    # Патологические структуры
    'Lewy bodies', 'Lewy body', 'Lewy neurites',
    'oligomer', 'oligomers', 'fibril', 'fibrils',

    # Токсины
    'MPTP', 'rotenone', 'paraquat',

    # Биохимия
    'dopamine', 'ROS', 'ATP', 'calcium', 'iron',
    'oxygen', 'superoxide',
}
