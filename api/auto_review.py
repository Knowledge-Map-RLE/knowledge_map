"""
Auto-review script for Action LEADS_TO edges.
Confirms edges where both verbs are biological mechanisms/results.
Rejects edges with meta-commentary verbs, abstract shared entities, etc.
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from neomodel import config, db

config.DATABASE_URL = 'bolt://neo4j:password@127.0.0.1:7687'

# ─── classification ───────────────────────────────────────────────────────────

BIO_VERBS = {
    # direct molecular mechanisms
    "inhibit", "activate", "phosphorylate", "bind", "regulate", "modulate",
    "catalyze", "ubiquitinate", "acetylate", "methylate", "cleave", "recruit",
    "sequester", "stabilize", "degrade", "translocate", "oligomerize",
    "aggregate", "fold", "interact", "associate", "localize", "polymerize",
    "dimerize", "hydrolyze", "oxidize", "reduce", "block", "suppress",
    "induce", "generate", "promote", "prevent", "protect", "damage",
    "cause", "produce", "enhance", "restore", "increase", "decrease",
    "improve", "attenuate", "ameliorate", "exacerbate", "accelerate",
    "delay", "arrest", "halt", "reverse", "mediate", "rescue",
    "release", "trigger", "signal", "express", "encode", "mutate",
    "impair", "disrupt", "form", "accumulate", "clear", "depolymerize",
    "upregulate", "downregulate", "methylate", "demethylate", "acetylate",
    "deacetylate", "sumoylate", "nitrosylate", "glycosylate",
    # cell/tissue-level
    "apoptose", "proliferate", "differentiate", "migrate", "infiltrate",
    "survive", "die", "necrose", "senesce",
    # disease-specific
    "aggregate", "misfold", "fibrilize", "deposit", "spread",
    "infect", "replicate", "transmit",
    # additional biological
    "yield", "reduce", "increase", "inhibit", "activate",
    "bind", "recruit", "release", "trigger", "cause", "promote",
    "prevent", "protect", "damage", "impair", "disrupt", "form",
    "accumulate", "clear", "mediate", "signal", "express",
    "encode", "mutate", "influence", "contribute", "require",
    "identify", "facilitate", "initiate", "induce", "produce",
    "counteract", "affect", "restore", "remove", "detect",
    "maintain", "drive", "stop", "turn", "further",
    # gerund/participle roots
    "causing", "producing", "triggering", "facilitating", "inducing",
    "disrupting", "affecting", "counteracting", "modulating", "inhibiting",
    "activating", "promoting", "generating", "recruiting", "releasing",
    "removing", "detecting", "maintaining", "driving", "restoring",
    # additional
    "deregulate", "dysregulate", "sensitize", "desensitize", "potentiate",
    "propagate", "transmit", "excite", "depolarize", "hyperpolarize",
    # transport/structural
    "carry", "transfer", "transport", "deliver",
    # therapeutic actions
    "substitute", "replace", "supplement",
    # cellular acquisition
    "acquire",
}

META_VERBS = {
    # meta-commentary / writing about science
    "suggest", "indicate", "show", "demonstrate", "report", "describe",
    "discuss", "review", "summarize", "conclude", "propose", "hypothesize",
    "argue", "note", "observe", "find", "found", "present", "provide",
    "examine", "investigate", "analyze", "study", "test", "measure",
    "evaluate", "assess", "compare", "consider", "highlight", "emphasize",
    "focus", "aim", "attempt", "try", "seek", "explore", "address",
    "approach", "develop", "build", "create", "design", "implement",
    "establish", "introduce", "define", "characterize", "classify",
    "categorize", "organize", "structure", "organize", "integrate",
    "incorporate", "include", "involve", "comprise", "consist", "contain",
    "represent", "reflect", "illustrate", "exemplify", "highlight",
    "demonstrate", "validate", "confirm", "verify", "support", "challenge",
    # movement/abstract
    "bring", "take", "give", "get", "go", "come", "make", "use",
    "adopt", "apply", "employ", "utilize", "leverage",
    "extend", "expand", "broaden", "narrow", "limit",
    "understand", "explain", "clarify", "elucidate", "reveal",
    "uncover", "discover", "identify_meta",
    "hasten", "facilitate_meta", "enable_meta",
    # abstract systems
    "monitor", "control", "manage", "coordinate",
    "encourage",   # "encourage peers" — social
    # replication/repetition verbs (methodology)
    "replicate", "reproduce", "repeat", "validate", "verify",
    "confirm_meta", "duplicate",
    # collection/data verbs
    "collect", "gather", "record", "document", "capture", "store",
    "retrieve", "extract_meta", "obtain", "acquire_meta",
    # comparison/assessment verbs
    "compare", "contrast", "rank", "rate", "score_verb",
    "benchmark", "calibrate",
    # reporting/publication
    "publish", "present_meta", "submit", "write", "read",
    "cite", "reference",
}

# Shared-entity markers that are too abstract to be meaningful
ABSTRACT_ENTITY_TOKENS = {
    'neuron', 'neurons', 'cell', 'cells', 'protein', 'proteins',
    'gene', 'genes', 'pathway', 'pathways', 'disease', 'diseases',
    'process', 'processes', 'role', 'roles', 'function', 'functions',
    'mechanism', 'mechanisms', 'effect', 'effects', 'level', 'levels',
    'activity', 'activities', 'signal', 'signals',
    # 'response'/'responses' removed — "microglial response", "immune response" are concrete
    'factor', 'factors', 'type', 'types', 'form', 'forms',
    'feature', 'features', 'aspect', 'aspects', 'part', 'parts',
    'stage', 'stages', 'phase', 'phases', 'step', 'steps',
    'way', 'ways', 'result', 'results', 'outcome', 'outcomes',
    'change', 'changes', 'loss', 'losses', 'damage', 'damages',
    'production', 'accumulation', 'aggregation',
    # 'release' removed — "neurotransmitter release" is concrete
    # 'response' removed — "microglial response" is concrete
    # abstract concepts added in last session
    'information', 'brain', 'body', 'system', 'systems', 'model', 'models',
    'data', 'context', 'scale', 'area', 'region', 'network', 'networks',
    'hallmark', 'hallmarks', 'principle', 'principles', 'aging', 'cancer',
    'life', 'text', 'people', 'growth', 'death',
    # additional common abstracts
    'view', 'approach', 'concept', 'idea', 'theory', 'framework',
    'evidence', 'finding', 'findings', 'observation', 'observations',
    'control', 'feedback', 'loop', 'cycle', 'cascade', 'interaction',
    'environment', 'condition', 'conditions',
    'symptom', 'symptoms', 'sign', 'signs',
    'patient', 'patients', 'subject', 'subjects',
    # clinical/epidemiological abstracts (from quality review)
    'care', 'health', 'risk', 'rate', 'score', 'test', 'study', 'trial',
    'group', 'groups', 'sample', 'cohort', 'population', 'populations',
    'treatment', 'treatments', 'intervention', 'interventions',
    'outcome', 'outcomes', 'measure', 'measures', 'assessment',
    'quality', 'performance', 'improvement', 'management',
    'skill', 'skills', 'training', 'program', 'protocol',
    'need', 'needs', 'barrier', 'barriers', 'strategy', 'strategies',
    # generic nouns (from obj_obj failures)
    'impact', 'influence', 'association', 'correlation', 'relationship',
    'analysis', 'review', 'report', 'survey', 'questionnaire',
    'participant', 'participants', 'adult', 'adults', 'person', 'persons',
    'age', 'sex', 'gender', 'year', 'years', 'month', 'months',
    'number', 'proportion', 'percentage', 'prevalence', 'incidence',
    'index', 'score', 'ratio', 'value', 'values', 'range',
    # structural/methodological from obj_obj noise
    'term', 'terms', 'word', 'words', 'item', 'items',
    'table', 'figure', 'chart', 'method', 'methods',
    # clinical-generic adjective-derived nouns (from quality review: obj_obj failures)
    'functional', 'cognitive', 'biological', 'molecular', 'cellular',
    'clinical', 'physical', 'mental', 'social', 'emotional', 'behavioral',
    'metabolic', 'structural', 'immune', 'genetic', 'epigenetic',
    'surgical', 'medical', 'therapeutic', 'diagnostic', 'preventive',
    'postoperative', 'preoperative', 'perioperative',
    # clinical actors/entities too generic
    'caregiver', 'caregivers', 'nurse', 'nurses', 'physician', 'physicians',
    'provider', 'providers', 'clinician', 'clinicians', 'worker', 'workers',
    'community', 'communities', 'unit', 'units', 'team', 'teams',
    'hospital', 'hospitals', 'clinic', 'clinics', 'facility', 'facilities',
    # supplements/vitamins used as generic tokens
    'vitamin', 'vitamins', 'supplement', 'supplements', 'nutrient', 'nutrients',
    # generic descriptors
    'inappropriate', 'appropriate', 'unnecessary', 'unnecessary',
    'effective', 'ineffective', 'significant', 'relevant', 'important',
    'specific', 'general', 'common', 'typical', 'normal', 'abnormal',
    # misc from observed failures
    'learning', 'mobility', 'stability', 'complexity', 'diversity',
    'integrity', 'sensitivity', 'specificity', 'accuracy', 'efficiency',
    'homeostasis', 'balance', 'regulation', 'expression', 'formation',
    # social/demographic tokens — too generic for edge evidence
    'older', 'elderly', 'among', 'within', 'across', 'between',
    'hospitalized', 'frail', 'disabled', 'independent', 'independent',
    'living', 'daily', 'activity', 'activities',
    # connections/relationships — abstract
    'connections', 'connection', 'relationship', 'relationships',
    'interaction', 'interactions', 'association', 'associations',
    # stress/wellbeing — clinical generic
    'stress', 'wellbeing', 'anxiety', 'depression', 'distress',
    'burden', 'strain', 'demand', 'demands',
    # identification/analysis methodology
    'demand', 'supply', 'cost', 'costs', 'access', 'service', 'services',
    # generic verbs-turned-nouns that appear as obj_obj
    'work', 'works',
    # bio/health terms too generic for meaningful obj_obj evidence
    'sleep', 'bone', 'frailty', 'lifespan', 'longevity', 'aging', 'ageing',
    'fitness', 'strength', 'muscle', 'brain', 'heart', 'lung', 'liver',
    'blood', 'plasma', 'serum', 'urine', 'tissue', 'tissues',
    # measurement-domain abstract nouns (from frailty/diagnostic articles)
    'diagnosis', 'detection', 'screening', 'monitoring', 'prevention',
    'identification', 'stratification', 'evaluation', 'assessment',
    # other common single-token obj_obj that proved too generic
    'validation', 'investigation', 'estimation', 'prediction', 'discrimination',
    'engagement', 'inclusion', 'welfare', 'natural', 'space', 'spaces',
    'human', 'animals', 'mice', 'mouse', 'rats', 'model',
    # carbon/ecology domain generics
    'carbon', 'emissions', 'volatile', 'yield', 'yields',
    # tautological obj_obj for dental/material articles
    'wrinkles', 'roughness', 'viscosity', 'composite',
    # social/geriatric abstracts causing tautological obj_obj
    'loss', 'impairment', 'impairments', 'independence', 'autonomy',
    'prevalence', 'incidence', 'burden', 'hearing', 'vision',
    # clinical trajectory abstracts
    'progression', 'onset', 'trajectory', 'trajectories', 'duration',
    # research/methodology abstracts
    'research', 'analysis', 'analyses', 'comparison', 'comparisons',
    'inference', 'interpretability', 'accuracy', 'reliability', 'validity',
    # demand/supply
    'demand', 'supply', 'cost', 'costs', 'capacity', 'capabilities',
    # generic social outcomes
    'equity', 'inequality', 'access', 'quality',
    # body/organ/physical generic (from obj_obj failures)
    'renal', 'surface', 'surfaces', 'exercise', 'material', 'materials',
    'transfer', 'transfers', 'water', 'dietary', 'diet', 'diets',
    'healthy', 'wound', 'wounds', 'healing', 'calling', 'load', 'sway',
    'upright', 'polymer', 'polymers', 'charging', 'grid', 'grids',
    'recovery', 'rehabilitation',
    # social/behavioral abstract
    'technology', 'technologies', 'support', 'supports',
    'episode', 'episodes', 'substance', 'substances', 'comfort',
    'use', 'usage', 'technique', 'techniques',
    # efficacy/performance (research outcome, not mechanistic)
    'efficacy', 'performance', 'outcomes', 'benefit', 'benefits',
    # clinical measurement generics
    'readmission', 'readmissions', 'hospitalization', 'hospitalizations',
    'mortality', 'morbidity', 'survival', 'recurrence',
    # physical fitness / cardiorespiratory measures
    'endurance', 'tolerance', 'capacity', 'reserve', 'output',
    'filling', 'pressure', 'pressures', 'volume', 'volumes',
    # social behavior
    'behavior', 'behaviors', 'behaviour', 'behaviours', 'attitude', 'attitudes',
    'adherence', 'compliance', 'engagement',
    # structural/research design
    'pathway', 'pathways', 'process', 'processes', 'mechanism', 'mechanisms',
    'pattern', 'patterns', 'marker', 'markers', 'indicator', 'indicators',
    # abstract direction/trajectory nouns
    'rise', 'decrease', 'increase', 'reduction', 'elevation', 'improvement',
    'deterioration', 'worsening',
    # domain-specific generics seen in failures
    'ageing', 'aging', 'lifespan', 'longevity', 'frailty',
    'function', 'functions', 'dysfunction', 'dysfunctions',
    # neural/neuro generics (too vague for obj_obj)
    'neural', 'neuronal', 'neuroscience', 'neurogenesis', 'neurodegeneration',
    'neurological', 'neuroinflammation',
    # bio-process generics (too broad — not specific enough without qualifier)
    'proliferation', 'differentiation', 'migration', 'invasion',
    'adaptation', 'adaptations',
    'lymphatic', 'lymph', 'lymphocyte', 'lymphocytes',
    'viability',
    # genomics/bioinformatics methodology tokens
    'events', 'variant', 'variants', 'regions', 'segment', 'segments',
    'reads', 'coverage', 'sequencing', 'alignment', 'mapping',
    'callers', 'haplotype', 'haplotypes',
    # materials science / engineering
    'thermal', 'wear', 'crack', 'cracks', 'grain', 'grains',
    'roughening', 'roughness', 'composite', 'torque', 'ripple',
    'stiffness',
    # social/behavioral generics
    'family', 'families', 'meaning', 'purpose', 'coherence',
    'questions', 'answers', 'knowledge', 'understanding',
    'offspring', 'children', 'parents',
    'eating', 'nutrition', 'nutritional', 'dietary',
    # clinical method generics
    'fixation', 'implant', 'implants',
    'driving', 'cessation',
    # infection/immunity generics too vague
    'infection', 'infections', 'immunity', 'immunological',
    # sweat/exercise physiology generics
    'sweat', 'sodium', 'electrolyte', 'electrolytes',
    # breast/cancer generics (without specific molecular context)
    'breast', 'cancer', 'tumor', 'tumour', 'cancers',
    # healthcare/administrative
    'climate', 'decarbonisation', 'emergency',
    # data/statistics generics
    'statistics', 'estimates', 'models', 'model',
    # temporal/duration descriptors (not bio-specific)
    'long-term', 'short-term', 'chronic', 'acute',
    # generic modifiers used as keywords
    'environmental', 'different', 'specific', 'optimal',
    # dental/polymer chemistry
    'polymerization', 'resin', 'crystallinity', 'hardness',
    'viscosity', 'monomer', 'monomers',
    # engineering/physics generics
    'temperature', 'electron', 'electrons', 'current', 'voltage',
    'flow', 'flux', 'pressure_phys', 'resistance',
    'mechanical', 'structural', 'elastic',
    # photocatalysis/chemistry
    'photocatalyst', 'photocatalytic', 'pollutant', 'pollutants',
    'catalytic', 'catalyst', 'catalysts', 'substrate', 'substrates',
    # battery/thermal engineering
    'thermal', 'battery', 'lithium', 'discharge', 'charge',
    'crystalline', 'composite',
    # material surface science
    'surface', 'interface', 'interfaces', 'coating', 'coatings',
    # agricultural/food/animal science (non-core bio)
    'insp6', 'phytase', 'phytate', 'hens',
    'bovine', 'cows', 'poultry',
    'omega-3', 'pufa',
    'fermentation', 'extract', 'extracts',
    # activation (too generic when used as sole keyword)
    'activation',
    # clinical outcomes that are too generic for keyword evidence
    'prognosis', 'outcomes', 'mortality', 'morbidity',
    'carcinogenesis', 'carcinoma',
    # coordination/structure generic
    'coordination', 'configuration', 'architecture',
    # postharvest/plant physiology generics
    'postharvest', 'vase', 'flower', 'flowers',
    # genotyping/mouse model methodology (used as identification, not mechanism)
    'allele', 'alleles', 'band', 'bands', 'primer', 'primers',
    'amplicon', 'amplicons', 'genotype', 'genotypes', 'founder',
    'transgenic', 'heterozygous', 'homozygous',
    # vascular/cardiovascular generics (too broad without molecular specificity)
    'vascular', 'cardiovascular', 'arterial', 'venous', 'aortic',
    # anatomy/organ region generics
    'forelimb', 'hindlimb', 'limb', 'limbs', 'spine', 'spinal',
    'intraocular', 'ocular', 'retinal', 'corneal',
    # disease outcome generics
    'stroke', 'atrophy', 'fibrosis', 'necrosis', 'infarction',
    'embolism', 'thrombosis', 'hemorrhage',
    # cognitive/neuropsych generics
    'memory', 'cognition', 'attention', 'executive',
    'oscillations', 'spindle', 'spindles',
    # body composition generics
    'lean', 'adipose', 'adiposity',
    # electrochemistry/physics (battery domain)
    'impedance', 'electrochemical', 'electrolyte', 'kinetics',
    'electrode', 'electrodes', 'anodic', 'cathodic',
    # mast/immune tissue types (too generic)
    'mast', 'granulocyte', 'granulocytes', 'basophil', 'basophils',
    # ACE/social trauma (non-bio evidence)
    'trauma', 'traumatic', 'adverse', 'resilience',
    'unrest', 'violence', 'displacement',
    # generic bio-process terms (already in set but ensure coverage)
    'permeability', 'motility', 'contractility',
    # surgical procedure generics
    'arthroplasty', 'osteotomy', 'reconstruction', 'prosthesis',
    'meniscal', 'rotator', 'cuff', 'ligament', 'tendon',
}


import re as _re

# Tokens that strongly indicate a biomedical context.
# Used to filter out marker-based edges from non-bio domains (materials, engineering, social science).
BIO_DOMAIN_TOKENS = {
    # molecular biology
    'mrna', 'rrna', 'cdna', 'sirna', 'mirna', 'lncrna', 'dna', 'rna',
    'protein', 'proteins', 'peptide', 'peptides', 'enzyme', 'enzymes',
    'receptor', 'receptors', 'ligand', 'ligands',
    'kinase', 'kinases', 'phosphatase', 'phosphatases',
    'transcription', 'translation', 'promoter', 'promoters',
    'chromosome', 'chromosomes', 'genome', 'genomics',
    'mutation', 'mutations', 'polymorphism', 'snp', 'snps',
    'exon', 'intron', 'allele', 'alleles',
    # cell biology
    'cell', 'cells', 'neuron', 'neurons', 'mitochondria', 'mitochondrial',
    'nucleus', 'cytoplasm', 'membrane', 'membranes',
    'apoptosis', 'autophagy', 'mitophagy', 'senescence',
    'proliferation', 'differentiation', 'migration',
    'stem', 'progenitor', 'fibroblast', 'macrophage', 'macrophages',
    'lymphocyte', 'lymphocytes', 'neutrophil', 'neutrophils',
    'platelet', 'platelets', 'erythrocyte', 'erythrocytes',
    # signaling molecules
    'cytokine', 'cytokines', 'chemokine', 'chemokines',
    'interleukin', 'interferon', 'tumor',
    'tnf', 'nfkb', 'mapk', 'pi3k', 'akt', 'mtor', 'stat',
    'wnt', 'notch', 'hedgehog', 'tgf',
    'ros', 'oxidative', 'antioxidant',
    'atp', 'nadh', 'nadph',
    # specific molecules (partial list — high specificity)
    'glucose', 'insulin', 'glucagon', 'cortisol',
    'dopamine', 'serotonin', 'norepinephrine', 'acetylcholine',
    'amyloid', 'tau', 'synuclein', 'huntingtin',
    'collagen', 'fibrin', 'actin', 'tubulin',
    # disease biomarkers
    'inflammatory', 'inflammation', 'neuroinflammation',
    'ischemia', 'hypoxia', 'angiogenesis',
    'cholesterol', 'lipid', 'lipids', 'triglyceride', 'triglycerides',
    'hormone', 'hormones', 'estrogen', 'testosterone', 'progesterone',
    # pathology
    'apoptotic', 'necrotic', 'fibrotic',
    'pathogen', 'pathogens', 'bacteria', 'viral', 'virus',
    'antibody', 'antibodies', 'antigen', 'antigens', 'vaccine', 'vaccines',
    # pharmacology
    'drug', 'drugs', 'pharmacological', 'therapeutic',
    'inhibitor', 'inhibitors', 'agonist', 'antagonist',
    # common expression patterns
    'expression', 'upregulating', 'downregulating', 'overexpressing',
    'knockdown', 'knockout', 'silencing', 'overexpression',
    # hematopoiesis specific
    'proplatelet', 'megakaryocyte', 'megakaryocytes', 'hematopoiesis',
    'hematopoietic', 'erythropoiesis', 'thrombopoiesis',
    # vascular/production
    'angiogenesis', 'vasculogenesis',
    # reproductive / developmental
    'placenta', 'placental', 'fetal', 'embryo', 'embryonic',
    'ovarian', 'uterine', 'endometrial', 'follicular',
    'oocyte', 'sperm', 'spermatogenesis',
    # immune / efferocytosis
    'efferocytosis', 'phagocytosis', 'opsonization',
    'complement', 'innate', 'adaptive',
    # musculoskeletal
    'muscle', 'muscles', 'myosin', 'sarcomere', 'sarcopenia',
    'bone', 'bones', 'osteoblast', 'osteoclast', 'chondrocyte',
    'glenohumeral', 'deltoid', 'tendon', 'ligament',
    'cartilage', 'synovial',
    # neuropeptides / receptors
    'mertk', 'tyro3', 'neuropeptide', 'neurotransmitter',
    # renin-angiotensin system
    'angiotensin', 'renin', 'aldosterone', 'bradykinin',
    'at1r', 'at2r', 'ace2',
    # general tissue/organ
    'liver', 'kidney', 'lungs', 'heart', 'brain', 'spleen',
    'colon', 'intestine', 'gut', 'pancreas', 'thyroid',
    'adipose', 'endothelial', 'epithelial',
}

# Non-bio domain tokens — presence in BOTH phrases suggests non-bio article
NON_BIO_DOMAIN_TOKENS = {
    # materials science / metallurgy
    'alloy', 'alloys', 'grain', 'grains', 'precipitate', 'precipitates',
    'dislocation', 'dislocations', 'fracture', 'fractures',
    'hardness', 'tensile', 'ductile', 'microstructure',
    'welding', 'annealing', 'quenching', 'tempering',
    # construction / civil engineering
    'asphalt', 'pavement', 'concrete', 'aggregate', 'bitumen',
    'foaming', 'polymer_asphalt',
    # electrochemistry / battery
    'electrode', 'electrolyte', 'impedance', 'capacitance',
    'lithium_battery', 'discharge_cycle', 'anode', 'cathode',
    # wood / acoustic
    'acoustic_wood', 'densification', 'lignin_wood', 'cellulose_wood',
    # social science / education
    'bibliometric', 'bibliometrics', 'academic', 'curriculum',
    'pedagogy', 'assessment_edu',
}


def _has_bio_domain_token(phrase: str) -> bool:
    """Return True if phrase contains at least one token from BIO_DOMAIN_TOKENS,
    or matches a known bio-domain prefix pattern."""
    if not phrase:
        return False
    for w in phrase.lower().split():
        w = w.strip(".,;:()[]\"'`")
        # strip possessive
        if w.endswith("'s"):
            w = w[:-2]
        if w in BIO_DOMAIN_TOKENS:
            return True
        # prefix match for bio terms
        if len(w) >= 5:
            BIO_PREFIXES = (
                'phospho', 'glyco', 'neuro', 'immuno', 'cardio',
                'hepato', 'nephro', 'pulmo', 'osteo', 'hemato',
                'carcino', 'apopto', 'autoph', 'cytoki', 'interleu',
                'myocard', 'angiog', 'lympho', 'fibro', 'adipo',
                'erythro', 'leuko', 'thromb', 'coagul', 'platele',
                'synapt', 'axon', 'dendri', 'myelon', 'glial',
            )
            if any(w.startswith(p) for p in BIO_PREFIXES):
                return True
    return False


def _normalize_verb(word: str) -> str:
    """Rough lemmatization: strip common suffixes to reach base form."""
    w = word.lower()
    # -ing: causing→cause, triggering→trigger, producing→produce
    if w.endswith('ing'):
        stem = w[:-3]
        # try stem + e: caus→cause, produc→produce, facilitat→facilitate
        if stem + 'e' in BIO_VERBS or stem + 'e' in META_VERBS:
            return stem + 'e'
        # double consonant: triggering→trigger (trigge→r→trigger)
        if len(stem) >= 2 and stem[-1] == stem[-2]:
            shorter = stem[:-1]
            if shorter in BIO_VERBS or shorter in META_VERBS:
                return shorter
        # stem itself: modulating→modulat→modulate (try +e)
        if stem in BIO_VERBS or stem in META_VERBS:
            return stem
        return stem + 'e'  # best guess
    # -en forms: driven→drive, broken→break, fallen→fall
    if w.endswith('en'):
        stem = w[:-2]
        if stem + 'e' in BIO_VERBS or stem + 'e' in META_VERBS:
            return stem + 'e'
        if stem in BIO_VERBS or stem in META_VERBS:
            return stem
        # driven→driv→drive
        return stem + 'e'
    # -ed: facilitated→facilitate, triggered→trigger, modeled→model
    if w.endswith('ed'):
        stem = w[:-2]
        if stem.endswith('e'):
            return stem
        if stem + 'e' in BIO_VERBS or stem + 'e' in META_VERBS:
            return stem + 'e'
        if len(stem) >= 2 and stem[-1] == stem[-2]:
            return stem[:-1]
        return stem
    # -s: facilitates→facilitate, inhibits→inhibit
    if w.endswith('s') and not w.endswith('ss') and len(w) > 3:
        return w[:-1]
    return w


def extract_verb(phrase: str) -> str:
    """Extract first word and normalize to lemma approximation."""
    if not phrase:
        return ""
    first = phrase.strip().split()[0].lower()
    return _normalize_verb(first)


def is_bio_verb(verb: str) -> bool:
    v = _normalize_verb(verb)
    return (v in BIO_VERBS or v + 's' in BIO_VERBS or v + 'e' in BIO_VERBS
            or v + 'es' in BIO_VERBS)


def is_meta_verb(verb: str) -> bool:
    v = _normalize_verb(verb)
    return (v in META_VERBS or v + 's' in META_VERBS or v + 'e' in META_VERBS)


def shared_entity_is_abstract(evidence: list) -> bool:
    """Check if shared entity in evidence is too abstract."""
    for ev in (evidence or []):
        if ev.startswith('[shared:'):
            entity = ev[8:].rstrip(']').strip().lower()
            # Check if entity is or contains abstract tokens
            tokens = entity.split()
            for t in tokens:
                t_clean = t.strip('.,;:')
                if t_clean in ABSTRACT_ENTITY_TOKENS:
                    return True
            # Short entities (1-2 words) that are pronouns or articles only
            if entity in {'it', 'its', 'this', 'these', 'those', 'that', 'they', 'them',
                          'the', 'a', 'an', 'their', 'our', 'its'}:
                return True
    return False


def keyword_is_abstract(evidence: list) -> bool:
    """Check if keyword/obj_obj overlap evidence is too abstract.

    Rejects if there is NO concrete (non-abstract, ≥4-char) token in the overlap.
    This is stricter than the old 'all abstract' rule and catches single-word
    matches like [obj_obj:care], [keyword:health] etc.
    """
    for ev in (evidence or []):
        for prefix in ('[keyword:', '[obj_obj:'):
            if ev.startswith(prefix):
                kws = ev[len(prefix):].rstrip(']').strip().lower()
                kw_list = [k.strip() for k in kws.split(',') if k.strip()]
                if not kw_list:
                    return True
                # Reject unless at least one token is concrete:
                # - not in ABSTRACT_ENTITY_TOKENS
                # - length >= 4 (filters out 'or', 'its', etc.)
                # - not a pure number
                has_concrete = any(
                    k not in ABSTRACT_ENTITY_TOKENS
                    and len(k) >= 4
                    and not k.isdigit()
                    for k in kw_list
                )
                if not has_concrete:
                    return True
    return False


def _phrase_tokens(phrase: str) -> set:
    """Return lowercase stemmed word tokens, stripping punctuation.
    Strips -ing/-ed/-s to catch near-duplicate phrasal variants.
    """
    if not phrase:
        return set()
    tokens = set()
    for w in phrase.split():
        w = w.lower().strip('.,;:()[]')
        if len(w) <= 2:
            continue
        # light stemming: strip -ing, -ed, -s to reduce inflectional variants
        if w.endswith('ing') and len(w) > 5:
            w = w[:-3]
        elif w.endswith('ed') and len(w) > 4:
            w = w[:-2]
        elif w.endswith('s') and not w.endswith('ss') and len(w) > 4:
            w = w[:-1]
        tokens.add(w)
    return tokens


def _is_tautological(src_phrase: str, tgt_phrase: str) -> bool:
    """Reject if src and tgt are near-duplicate phrases.

    Uses Jaccard >= 0.60 for general case, and a stricter absolute-overlap
    check for short phrases: if both phrases are ≤8 tokens and share ≥3
    content words, treat as tautological (catches near-synonymous rewrites).
    """
    src_tok = _phrase_tokens(src_phrase)
    tgt_tok = _phrase_tokens(tgt_phrase)
    if not src_tok or not tgt_tok:
        return False
    intersection = len(src_tok & tgt_tok)
    union = len(src_tok | tgt_tok)
    if (intersection / union) >= 0.60:
        return True
    # Short-phrase absolute overlap: ≤8 tokens each, share ≥3 content words
    if len(src_tok) <= 8 and len(tgt_tok) <= 8 and intersection >= 3:
        return True
    return False


_HTML_RE = _re.compile(r'<[a-zA-Z/]|</|<table|<tr\b|<td\b|<th\b|<img\b|<figure|<figcaption')
_CYRILLIC_RE = _re.compile(r'[А-Яа-яЁё]')


def _has_html_artifact(phrase: str) -> bool:
    """Reject if phrase contains HTML tags (markdown artifact)."""
    if not phrase:
        return False
    return bool(_HTML_RE.search(phrase))


def _has_cyrillic(phrase: str) -> bool:
    """Reject if phrase contains Cyrillic characters (metadata leak)."""
    if not phrase:
        return False
    return bool(_CYRILLIC_RE.search(phrase))


def should_confirm(src_phrase: str, tgt_phrase: str, relation: str,
                   confidence: float, evidence: list) -> tuple[bool, str]:
    src_verb = extract_verb(src_phrase)
    tgt_verb = extract_verb(tgt_phrase)

    # Reject HTML artifacts (markdown parsing noise)
    if _has_html_artifact(src_phrase) or _has_html_artifact(tgt_phrase):
        return False, "html artifact in phrase"

    # Reject Cyrillic text (metadata/author-name leak into full_phrase)
    if _has_cyrillic(src_phrase) or _has_cyrillic(tgt_phrase):
        return False, "cyrillic text in phrase (metadata leak)"

    # Reject if neither phrase contains a bio-domain token (non-biomedical article)
    if not _has_bio_domain_token(src_phrase) and not _has_bio_domain_token(tgt_phrase):
        return False, "no bio domain token in either phrase (non-bio article)"

    # Reject tautological edges (src ≈ tgt paraphrase)
    if _is_tautological(src_phrase, tgt_phrase):
        return False, "tautological src≈tgt phrases"

    # Reject if either verb is meta-commentary
    if is_meta_verb(src_verb):
        return False, f"meta src verb: {src_verb}"
    if is_meta_verb(tgt_verb):
        return False, f"meta tgt verb: {tgt_verb}"

    # Reject if shared entity is abstract
    if shared_entity_is_abstract(evidence):
        return False, f"abstract shared entity: {evidence}"

    # Reject if keyword overlap is abstract
    if keyword_is_abstract(evidence):
        return False, f"abstract keyword: {evidence}"

    # Reject if [subject:] evidence contains only abstract tokens
    for ev in (evidence or []):
        if ev.startswith('[subject:'):
            subj = ev[9:].rstrip(']').strip().lower()
            tokens = [t.strip() for t in subj.split(',') if t.strip()]
            if tokens and all(t in ABSTRACT_ENTITY_TOKENS or len(t) <= 3 for t in tokens):
                return False, f"abstract subject evidence: {ev}"

    # Reject if low confidence and neither verb is bio
    if confidence < 0.6 and not is_bio_verb(src_verb) and not is_bio_verb(tgt_verb):
        return False, f"low conf + non-bio verbs: {src_verb}, {tgt_verb}"

    # Reject sequential edges where neither verb is bio
    if relation == 'sequential' and not is_bio_verb(src_verb) and not is_bio_verb(tgt_verb):
        return False, f"sequential non-bio: {src_verb}, {tgt_verb}"

    src_bio = is_bio_verb(src_verb)
    tgt_bio = is_bio_verb(tgt_verb)

    # Same generic verb (cause→cause, require→require) without a real causal marker → reject
    # EXCEPT if shared subject is a concrete biological entity (gene/protein name)
    _GENERIC_BIO = {'cause', 'require', 'share', 'identify', 'contribute', 'involve'}
    if src_verb == tgt_verb and src_verb in _GENERIC_BIO:
        has_real_marker = any(ev and not ev.startswith('[') for ev in (evidence or []))
        if not has_real_marker:
            # Allow if shared subject is concrete (not abstract, not "mutations"/"cells")
            has_concrete_subject = False
            for ev in (evidence or []):
                if ev.startswith('[subject:'):
                    subj = ev[9:].rstrip(']').strip().lower()
                    tokens = subj.split(',')
                    if all(t.strip() not in ABSTRACT_ENTITY_TOKENS and t.strip() not in
                           {'mutation', 'mutations', 'variant', 'variants', 'change', 'changes',
                            'cell', 'cells', 'factor', 'factors', 'gene', 'genes',
                            'protein', 'proteins', 'pathway', 'pathways'}
                           for t in tokens if t.strip()):
                        has_concrete_subject = True
            # Also allow cause→cause via obj_obj if objects are different specific entities
            has_obj_obj_evidence = any('[obj_obj:' in str(ev) for ev in (evidence or []))
            if has_obj_obj_evidence and not keyword_is_abstract(evidence):
                has_concrete_subject = True
            if not has_concrete_subject:
                return False, f"same generic verb without marker: {src_verb}"

    # Confirm marker-based edges with at least one bio verb
    # AND at least one phrase must contain a bio-domain token (prevents non-bio domain leakage)
    has_marker = any(ev and not ev.startswith('[') for ev in (evidence or []))
    if has_marker:
        if src_bio or tgt_bio:
            src_bio_domain = _has_bio_domain_token(src_phrase)
            tgt_bio_domain = _has_bio_domain_token(tgt_phrase)
            if src_bio_domain or tgt_bio_domain:
                return True, "marker + bio verb + bio domain token"
            return False, "marker + bio verb but no bio domain token (non-bio article)"
        return False, f"marker but non-bio verbs: {src_verb}, {tgt_verb}"

    # Shared-entity edges: require both bio verbs
    has_shared = any('[shared:' in str(ev) for ev in (evidence or []))
    if has_shared:
        if src_bio and tgt_bio:
            return True, "shared entity + both bio verbs"
        return False, f"shared entity but non-bio: {src_verb}, {tgt_verb}"

    # Keyword overlap: require both bio verbs
    has_keyword = any('[keyword:' in str(ev) for ev in (evidence or []))
    if has_keyword:
        if src_bio and tgt_bio:
            return True, "keyword + both bio verbs"
        return False, f"keyword but non-bio: {src_verb}, {tgt_verb}"

    # Obj→obj overlap: require both bio verbs AND confidence >= 0.65
    # (weakest structural evidence — high false positive rate at 0.58)
    has_obj_obj = any('[obj_obj:' in str(ev) for ev in (evidence or []))
    if has_obj_obj:
        if src_bio and tgt_bio and confidence >= 0.65:
            return True, "obj_obj + both bio verbs + conf>=0.65"
        return False, f"obj_obj but non-bio or low-conf: {src_verb}, {tgt_verb}, conf={confidence}"

    # Shared subject: require both bio verbs AND confidence >= 0.65
    # (weakest evidence type — many false positives at low confidence)
    has_subject = any('[subject:' in str(ev) for ev in (evidence or []))
    if has_subject:
        if src_bio and tgt_bio and confidence >= 0.65:
            return True, "shared subject + both bio verbs"
        return False, f"shared subject but non-bio or low-conf: {src_verb}, {tgt_verb}"

    # Default: confirm if both bio verbs (any confidence)
    if src_bio and tgt_bio:
        return True, f"both bio verbs: {src_verb} + {tgt_verb}"

    return False, f"no clear positive signal: {src_verb}({'bio' if src_bio else 'meta'}), {tgt_verb}({'bio' if tgt_bio else 'meta'})"


def run(doc_id: str, dry_run: bool = False, quiet: bool = False) -> dict:
    results, _ = db.cypher_query('''
        MATCH (s:Action {doc_id: $doc_id})-[r:LEADS_TO {status: "pending"}]->(t:Action)
        RETURN s.uid, t.uid, s.full_phrase, t.full_phrase,
               r.relation_subtype, r.confidence, r.evidence
    ''', {'doc_id': doc_id})

    confirmed = []
    rejected = []

    for row in results:
        src_uid, tgt_uid, src_phrase, tgt_phrase, relation, confidence, evidence = row
        confidence = confidence or 0.0
        evidence = list(evidence) if evidence else []

        ok, reason = should_confirm(src_phrase, tgt_phrase, relation, confidence, evidence)

        src_short = (src_phrase or '')[:45]
        tgt_short = (tgt_phrase or '')[:45]

        if ok:
            confirmed.append((src_uid, tgt_uid, relation, src_short, tgt_short, reason))
        else:
            rejected.append((src_uid, tgt_uid, relation, src_short, tgt_short, reason))

    total = len(confirmed) + len(rejected)
    prec = len(confirmed) / total * 100 if total else 0

    if not quiet:
        print(f"\n{'DRY RUN — ' if dry_run else ''}Results for doc {doc_id}:")
        print(f"  Confirmed: {len(confirmed)}")
        print(f"  Rejected:  {len(rejected)}")
        print(f"  Precision: {prec:.0f}%\n")

    if not dry_run:
        if confirmed:
            db.cypher_query('''
                UNWIND $pairs AS p
                MATCH (s:Action {uid: p.src})-[r:LEADS_TO {relation_subtype: p.rel}]->(t:Action {uid: p.tgt})
                SET r.status = "confirmed"
            ''', {'pairs': [{'src': su, 'tgt': tu, 'rel': rel} for su, tu, rel, *_ in confirmed]})

        if rejected:
            db.cypher_query('''
                UNWIND $pairs AS p
                MATCH (s:Action {uid: p.src})-[r:LEADS_TO {relation_subtype: p.rel}]->(t:Action {uid: p.tgt})
                SET r.status = "rejected"
            ''', {'pairs': [{'src': su, 'tgt': tu, 'rel': rel} for su, tu, rel, *_ in rejected]})

        if not quiet:
            print("  Status updated in Neo4j.")

    if not quiet:
        print("\n=== CONFIRMED ===")
        for _, _, rel, src, tgt, reason in confirmed:
            print(f"  [{rel}] {src} --> {tgt}  ({reason})")

        print("\n=== REJECTED ===")
        for _, _, rel, src, tgt, reason in rejected:
            print(f"  [{rel}] {src} --> {tgt}  ({reason})")

    return {"confirmed": len(confirmed), "rejected": len(rejected)}


if __name__ == '__main__':
    DOC_ID = '886f1448799d4aba1076c65e059a3d58'
    DRY_RUN = '--dry' in sys.argv
    run(DOC_ID, dry_run=DRY_RUN)
