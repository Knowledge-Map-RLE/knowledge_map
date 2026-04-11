"""
Layer: Application (Use Cases)
Package: application.actions.auto_review
Responsibility: Автоматическое ревью pending LEADS_TO рёбер.

Классифицирует рёбра как confirmed/rejected на основе:
- био-домена глаголов (BIO_VERBS vs META_VERBS)
- наличия маркеров биологического домена в фразах
- абстрактности общих сущностей (ABSTRACT_ENTITY_TOKENS)
- тавтоличности src≈tgt фраз
- confidence score

Allowed imports: domain, application.ports, re, dataclasses
Forbidden imports: fastapi, neomodel, grpc, adapters, infrastructure, web
"""
from __future__ import annotations

import logging
import re as _re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

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
    "upregulate", "downregulate", "demethylate", "deacetylate", "sumoylate",
    "nitrosylate", "glycosylate",
    # cell/tissue-level
    "apoptose", "proliferate", "differentiate", "migrate", "infiltrate",
    "survive", "die", "necrose", "senesce",
    # disease-specific
    "misfold", "fibrilize", "deposit", "spread",
    "infect", "replicate", "transmit",
    # additional biological
    "yield", "influence", "contribute", "require",
    "identify", "facilitate", "initiate",
    "counteract", "affect", "remove", "detect",
    "maintain", "drive", "stop", "turn", "further",
    # gerund/participle roots
    "causing", "producing", "triggering", "facilitating", "inducing",
    "disrupting", "affecting", "counteracting", "modulating", "inhibiting",
    "activating", "promoting", "generating", "recruiting", "releasing",
    "removing", "detecting", "maintaining", "driving", "restoring",
    # additional
    "deregulate", "dysregulate", "sensitize", "desensitize", "potentiate",
    "propagate", "excite", "depolarize", "hyperpolarize",
    # transport/structural
    "carry", "transfer", "transport", "deliver",
    # therapeutic actions
    "substitute", "replace", "supplement",
    # cellular acquisition
    "acquire",
    # cell biology: attraction, sustainment, rewiring
    "attract", "sustain", "rewire", "re-wire",
    "harbor", "harbore", "enable", "undergo", "exhibit",
    "participate", "coordinate",
    "integrate", "converge", "diverge", "amplify",
    "elongate", "shorten", "extend", "expand", "contract",
    "swell", "shrink", "lyse", "permeabilize",
    # ДОБАВЛЕНО: ключевые bio-глаголы для РПЖ
    "dephosphorylate", "deubiquitinate",
    "desumoylate",
    "transcribe", "translate", "splice",
    "secrete", "internalize", "endocytose", "exocytose",
    "senesce", "quiesce", "rejuvenate",
    "repair", "regenerate",
    "metabolize", "catabolize", "anabolize",
    "phagocytose", "engulf",
    "cross", "penetrate", "diffuse",
    "confer", "govern", "determine", "dictate",
    "buffer", "scavenge", "chelate",
    "replenish", "deplete",
    "resensitize",
    "abrogate",
}

META_VERBS = {
    # meta-commentary / writing about science
    "suggest", "indicate", "show", "demonstrate", "report", "describe",
    "discuss", "review", "summarize", "conclude", "propose", "hypothesize",
    "argue", "note", "observe", "find", "found", "present", "provide",
    "examine", "investigate", "analyze", "study", "test", "measure",
    "evaluate", "assess", "compare", "consider", "highlight", "emphasize",
    "focus", "aim", "attempt", "try", "seek", "explore", "address",
    "approach", "define", "characterize", "classify",
    "categorize", "organize", "structure",
    "incorporate",
    "represent", "reflect", "illustrate", "exemplify",
    "validate", "confirm", "verify", "support", "challenge",
    # movement/abstract
    "bring", "take", "give", "get", "go", "come", "make", "use",
    "adopt", "apply", "employ",
    "broaden", "narrow", "limit",
    "understand", "explain", "clarify", "elucidate", "reveal",
    "uncover", "discover", "identify_meta",
    "hasten", "facilitate_meta", "enable_meta",
    # abstract systems
    "monitor", "control", "manage",
    "encourage",
    # replication/repetition verbs (methodology)
    "replicate", "reproduce", "repeat",
    "confirm_meta", "duplicate",
    # collection/data verbs
    "collect", "gather", "record", "document", "capture", "store",
    "retrieve", "extract_meta", "obtain", "acquire_meta",
    # comparison/assessment verbs
    "rank", "score_verb",
    "benchmark", "calibrate",
    # reporting/publication
    "publish", "present_meta", "submit", "write", "read",
    "cite", "reference",
}

ABSTRACT_ENTITY_TOKENS = {
    'neuron', 'neurons', 'cell', 'cells', 'protein', 'proteins',
    'gene', 'genes', 'pathway', 'pathways', 'disease', 'diseases',
    'process', 'processes', 'role', 'roles', 'function', 'functions',
    'mechanism', 'mechanisms', 'effect', 'effects', 'level', 'levels',
    'activity', 'activities', 'signal', 'signals',
    'factor', 'factors', 'type', 'types', 'form', 'forms',
    'feature', 'features', 'aspect', 'aspects', 'part', 'parts',
    'stage', 'stages', 'phase', 'phases', 'step', 'steps',
    'way', 'ways', 'result', 'results', 'outcome', 'outcomes',
    'change', 'changes', 'loss', 'losses', 'damage', 'damages',
    'production', 'accumulation', 'aggregation',
    'information', 'text', 'people',
    'view', 'approach', 'concept', 'idea', 'theory', 'framework',
    'evidence', 'finding', 'findings', 'observation', 'observations',
    'control', 'feedback', 'loop', 'cycle', 'cascade', 'interaction',
    'environment', 'condition', 'conditions',
    'symptom', 'symptoms', 'sign', 'signs',
    'patient', 'patients', 'subject', 'subjects',
    'risk', 'rate', 'study', 'trial',
    'group', 'groups', 'sample', 'cohort', 'population', 'populations',
    'measure', 'measures', 'assessment',
    'quality', 'performance', 'improvement', 'management',
    'skill', 'skills', 'training', 'program', 'protocol',
    'need', 'needs', 'barrier', 'barriers', 'strategy', 'strategies',
    'impact', 'influence', 'association', 'correlation', 'relationship',
    'analysis', 'report', 'survey', 'questionnaire',
    'participant', 'participants', 'adult', 'adults', 'person', 'persons',
    'age', 'sex', 'gender', 'year', 'years', 'month', 'months',
    'number', 'proportion', 'percentage', 'prevalence', 'incidence',
    'index', 'score', 'ratio', 'value', 'values', 'range',
    'term', 'terms', 'word', 'words', 'item', 'items',
    'table', 'figure', 'chart', 'method', 'methods',
    'functional', 'cognitive', 'biological', 'molecular', 'cellular',
    'clinical', 'physical', 'mental', 'social', 'emotional', 'behavioral',
    'metabolic', 'structural', 'immune', 'genetic', 'epigenetic',
    'surgical', 'medical', 'therapeutic', 'diagnostic', 'preventive',
    'postoperative', 'preoperative', 'perioperative',
    'caregiver', 'caregivers', 'nurse', 'nurses', 'physician', 'physicians',
    'provider', 'providers', 'clinician', 'clinicians', 'worker', 'workers',
    'community', 'communities', 'unit', 'units', 'team', 'teams',
    'hospital', 'hospitals', 'clinic', 'clinics', 'facility', 'facilities',
    'vitamin', 'vitamins', 'supplement', 'supplements', 'nutrient', 'nutrients',
    'inappropriate', 'appropriate', 'unnecessary',
    'effective', 'ineffective', 'significant', 'relevant', 'important',
    'specific', 'general', 'common', 'typical', 'normal', 'abnormal',
    'learning', 'mobility', 'stability', 'complexity', 'diversity',
    'integrity', 'sensitivity', 'specificity', 'accuracy', 'efficiency',
    'homeostasis', 'balance', 'regulation', 'expression', 'formation',
    'older', 'elderly', 'among', 'within', 'across', 'between',
    'hospitalized', 'frail', 'disabled', 'independent',
    'living', 'daily', 'activity', 'activities',
    'connections', 'connection',
    'stress', 'wellbeing', 'anxiety', 'depression', 'distress',
    'burden', 'strain', 'demand', 'demands',
    'supply', 'cost', 'costs', 'access', 'service', 'services',
    'work', 'works',
    'sleep', 'bone', 'frailty', 'lifespan', 'longevity', 'aging', 'ageing',
    'fitness', 'strength', 'muscle', 'brain', 'heart', 'lung', 'liver',
    'blood', 'plasma', 'serum', 'urine', 'tissue', 'tissues',
    'diagnosis', 'detection', 'screening', 'monitoring', 'prevention',
    'identification', 'stratification', 'evaluation', 'assessment',
    'validation', 'investigation', 'estimation', 'prediction', 'discrimination',
    'engagement', 'inclusion', 'welfare', 'natural', 'space', 'spaces',
    'human', 'animals', 'mice', 'mouse', 'rats', 'model',
    'carbon', 'emissions', 'volatile', 'yield', 'yields',
    'wrinkles', 'roughness', 'viscosity', 'composite',
    'loss', 'impairment', 'impairments', 'independence', 'autonomy',
    'progression', 'onset', 'trajectory', 'trajectories', 'duration',
    'research', 'analyses', 'comparison', 'comparisons',
    'inference', 'interpretability', 'reliability', 'validity',
    'capacity', 'capabilities',
    'equity', 'inequality',
    'renal', 'surface', 'surfaces', 'material', 'materials',
    'transfer', 'transfers', 'water', 'dietary', 'calling', 'load', 'sway',
    'upright', 'polymer', 'polymers', 'charging', 'grid', 'grids',
    'recovery', 'rehabilitation',
    'technology', 'technologies', 'support', 'supports',
    'episode', 'episodes', 'substance', 'substances', 'comfort',
    'use', 'usage', 'technique', 'techniques',
    'efficacy', 'outcomes', 'benefit', 'benefits',
    'readmission', 'readmissions', 'hospitalization', 'hospitalizations',
    'mortality', 'morbidity', 'survival', 'recurrence',
    'endurance', 'tolerance', 'reserve', 'output',
    'filling', 'pressure', 'pressures', 'volume', 'volumes',
    'behavior', 'behaviors', 'behaviour', 'behaviours', 'attitude', 'attitudes',
    'adherence', 'compliance',
    'pattern', 'patterns', 'marker', 'markers', 'indicator', 'indicators',
    'rise', 'decrease', 'increase', 'reduction', 'elevation', 'improvement',
    'deterioration', 'worsening',
    'function', 'functions', 'dysfunction', 'dysfunctions',
    'neural', 'neuronal', 'neuroscience', 'neurogenesis', 'neurodegeneration',
    'neurological', 'neuroinflammation',
    'proliferation', 'differentiation', 'migration', 'invasion',
    'adaptation', 'adaptations',
    'lymphatic', 'lymph', 'lymphocyte', 'lymphocytes',
    'viability',
    'events', 'variant', 'variants', 'regions', 'segment', 'segments',
    'reads', 'coverage', 'sequencing', 'alignment', 'mapping',
    'callers', 'haplotype', 'haplotypes',
    'thermal', 'wear', 'crack', 'cracks', 'grain', 'grains',
    'roughening', 'stiffness',
    'family', 'families', 'meaning', 'purpose', 'coherence',
    'questions', 'answers', 'knowledge', 'understanding',
    'offspring', 'children', 'parents',
    'eating', 'nutrition', 'nutritional', 'dietary',
    'fixation', 'implant', 'implants',
    'driving', 'cessation',
    'infection', 'infections', 'immunity', 'immunological',
    'sweat', 'sodium', 'electrolyte', 'electrolytes',
    'breast', 'cancer', 'tumor', 'tumour', 'cancers',
    'climate', 'decarbonisation', 'emergency',
    'statistics', 'estimates', 'models',
    'long-term', 'short-term', 'chronic', 'acute',
    'environmental', 'different', 'optimal',
    'polymerization', 'resin', 'crystallinity', 'hardness',
    'monomer', 'monomers',
    'temperature', 'electron', 'electrons', 'current', 'voltage',
    'flow', 'flux', 'resistance',
    'mechanical', 'elastic',
    'photocatalyst', 'photocatalytic', 'pollutant', 'pollutants',
    'catalytic', 'catalyst', 'catalysts', 'substrate', 'substrates',
    'battery', 'lithium', 'discharge', 'charge',
    'crystalline',
    'interface', 'interfaces', 'coating', 'coatings',
    'insp6', 'phytase', 'phytate', 'hens',
    'bovine', 'cows', 'poultry',
    'omega-3', 'pufa',
    'fermentation', 'extract', 'extracts',
    'activation',
    'prognosis', 'carcinogenesis', 'carcinoma',
    'coordination', 'configuration', 'architecture',
    'postharvest', 'vase', 'flower', 'flowers',
    'allele', 'alleles', 'band', 'bands', 'primer', 'primers',
    'amplicon', 'amplicons', 'genotype', 'genotypes', 'founder',
    'transgenic', 'heterozygous', 'homozygous',
    'vascular', 'cardiovascular', 'arterial', 'venous', 'aortic',
    'forelimb', 'hindlimb', 'limb', 'limbs', 'spine', 'spinal',
    'intraocular', 'ocular', 'retinal', 'corneal',
    'stroke', 'atrophy', 'fibrosis', 'necrosis', 'infarction',
    'embolism', 'thrombosis', 'hemorrhage',
    'memory', 'cognition', 'attention', 'executive',
    'oscillations', 'spindle', 'spindles',
    'lean', 'adipose', 'adiposity',
    'impedance', 'electrochemical', 'kinetics',
    'electrode', 'electrodes', 'anodic', 'cathodic',
    'mast', 'granulocyte', 'granulocytes', 'basophil', 'basophils',
    'trauma', 'traumatic', 'adverse', 'resilience',
    'unrest', 'violence', 'displacement',
    'permeability', 'motility', 'contractility',
    'arthroplasty', 'osteotomy', 'reconstruction', 'prosthesis',
    'meniscal', 'rotator', 'cuff', 'ligament', 'tendon',
}

BIO_DOMAIN_TOKENS = {
    'mrna', 'rrna', 'cdna', 'sirna', 'mirna', 'lncrna', 'dna', 'rna',
    'protein', 'proteins', 'peptide', 'peptides', 'enzyme', 'enzymes',
    'receptor', 'receptors', 'ligand', 'ligands',
    'kinase', 'kinases', 'phosphatase', 'phosphatases',
    'transcription', 'translation', 'promoter', 'promoters',
    'chromosome', 'chromosomes', 'genome', 'genomics',
    'mutation', 'mutations', 'polymorphism', 'snp', 'snps',
    'exon', 'intron', 'allele', 'alleles',
    'cell', 'cells', 'neuron', 'neurons', 'mitochondria', 'mitochondrial',
    'nucleus', 'cytoplasm', 'membrane', 'membranes',
    'apoptosis', 'autophagy', 'mitophagy', 'senescence',
    'proliferation', 'differentiation', 'migration',
    'stem', 'progenitor', 'fibroblast', 'macrophage', 'macrophages',
    'lymphocyte', 'lymphocytes', 'neutrophil', 'neutrophils',
    'platelet', 'platelets', 'erythrocyte', 'erythrocytes',
    'cytokine', 'cytokines', 'chemokine', 'chemokines',
    'interleukin', 'interferon', 'tumor',
    'tnf', 'nfkb', 'mapk', 'pi3k', 'akt', 'mtor', 'stat',
    'wnt', 'notch', 'hedgehog', 'tgf',
    'ros', 'oxidative', 'antioxidant',
    'atp', 'nadh', 'nadph',
    'glucose', 'insulin', 'glucagon', 'cortisol',
    'dopamine', 'serotonin', 'norepinephrine', 'acetylcholine',
    'amyloid', 'tau', 'synuclein', 'huntingtin',
    'collagen', 'fibrin', 'actin', 'tubulin',
    'inflammatory', 'inflammation', 'neuroinflammation',
    'ischemia', 'hypoxia', 'angiogenesis',
    'cholesterol', 'lipid', 'lipids', 'triglyceride', 'triglycerides',
    'hormone', 'hormones', 'estrogen', 'testosterone', 'progesterone',
    'apoptotic', 'necrotic', 'fibrotic',
    'pathogen', 'pathogens', 'bacteria', 'viral', 'virus',
    'antibody', 'antibodies', 'antigen', 'antigens', 'vaccine', 'vaccines',
    'drug', 'drugs', 'pharmacological', 'therapeutic',
    'inhibitor', 'inhibitors', 'agonist', 'antagonist',
    'expression', 'upregulating', 'downregulating', 'overexpressing',
    'knockdown', 'knockout', 'silencing', 'overexpression',
    'proplatelet', 'megakaryocyte', 'megakaryocytes', 'hematopoiesis',
    'hematopoietic', 'erythropoiesis', 'thrombopoiesis',
    'vasculogenesis',
    'placenta', 'placental', 'fetal', 'embryo', 'embryonic',
    'ovarian', 'uterine', 'endometrial', 'follicular',
    'oocyte', 'sperm', 'spermatogenesis',
    'efferocytosis', 'phagocytosis', 'opsonization',
    'complement', 'innate', 'adaptive',
    'muscle', 'muscles', 'myosin', 'sarcomere', 'sarcopenia',
    'bone', 'bones', 'osteoblast', 'osteoclast', 'chondrocyte',
    'glenohumeral', 'deltoid',
    'cartilage', 'synovial',
    'mertk', 'tyro3', 'neuropeptide', 'neurotransmitter',
    'angiotensin', 'renin', 'aldosterone', 'bradykinin',
    'at1r', 'at2r', 'ace2',
    'liver', 'kidney', 'lungs', 'heart', 'brain', 'spleen',
    'colon', 'intestine', 'gut', 'pancreas', 'thyroid',
    'adipose', 'endothelial', 'epithelial',
    'aging', 'ageing', 'longevity', 'lifespan', 'healthspan', 'senescent',
    'telomere', 'telomeres', 'telomerase', 'epigenetic', 'epigenetics',
    'methylation', 'acetylation', 'histone', 'chromatin',
    'proteostasis', 'proteome', 'proteasome', 'ubiquitin',
    'nad', 'sirtuin', 'sirtuins', 'ampk', 'igf', 'rapamycin',
    'sasp', 'senolytic', 'senolytics', 'inflammaging',
    'dmp', 'dmps', 'cpg', 'methylome',
    'rna-seq', 'rnaseq', 'scrnaseq', 'scrna',
    'gwas', 'loci', 'locus',
    'transcriptome', 'proteome', 'metabolome', 'microbiome',
    'pathway', 'pathways', 'network', 'networks',
    'biomarker', 'biomarkers', 'signature', 'signatures',
    'classifier', 'classification', 'clustering', 'imputation',
    'survival', 'prognosis', 'prognostic',
    'patient', 'patients', 'cohort', 'cohorts', 'sample', 'samples',
    'diagnosis', 'diagnostic', 'treatment', 'therapy',
    'cancer', 'carcinoma', 'metastasis',
    'disease', 'syndrome', 'disorder', 'condition',
    'trial', 'dose', 'dosage', 'toxicity',
    'mouse', 'mice', 'rat', 'zebrafish', 'drosophila', 'yeast',
    'worm', 'caenorhabditis', 'c. elegans',
    'hela', 'hek', 'jurkat', 'mcf', 'huvec', 'ipsc',
    'western', 'elisa', 'pcr', 'flow', 'facs', 'immunofluorescence',
    'immunohistochemistry', 'microscopy', 'imaging', 'staining',
}

BIO_PREFIXES = (
    'phospho', 'glyco', 'neuro', 'immuno', 'cardio',
    'hepato', 'nephro', 'pulmo', 'osteo', 'hemato',
    'carcino', 'apopto', 'autoph', 'cytoki', 'interleu',
    'myocard', 'angiog', 'lympho', 'fibro', 'adipo',
    'erythro', 'leuko', 'thromb', 'coagul', 'platele',
    'synapt', 'axon', 'dendri', 'myelon', 'glial',
)

_HTML_RE = _re.compile(r'<[a-zA-Z/]|</|<table|<tr\b|<td\b|<th\b|<img\b|<figure|<figcaption')
_CYRILLIC_RE = _re.compile(r'[А-Яа-яЁё]')


# ─── helpers ──────────────────────────────────────────────────────────────────

def _normalize_verb(word: str) -> str:
    w = word.lower()
    if w.endswith('ing'):
        stem = w[:-3]
        if stem + 'e' in BIO_VERBS or stem + 'e' in META_VERBS:
            return stem + 'e'
        if len(stem) >= 2 and stem[-1] == stem[-2]:
            shorter = stem[:-1]
            if shorter in BIO_VERBS or shorter in META_VERBS:
                return shorter
        if stem in BIO_VERBS or stem in META_VERBS:
            return stem
        return stem + 'e'
    if w.endswith('en'):
        stem = w[:-2]
        if stem + 'e' in BIO_VERBS or stem + 'e' in META_VERBS:
            return stem + 'e'
        if stem in BIO_VERBS or stem in META_VERBS:
            return stem
        return stem + 'e'
    if w.endswith('ed'):
        stem = w[:-2]
        if stem.endswith('e'):
            return stem
        if stem + 'e' in BIO_VERBS or stem + 'e' in META_VERBS:
            return stem + 'e'
        if len(stem) >= 2 and stem[-1] == stem[-2]:
            return stem[:-1]
        return stem
    if w.endswith('s') and not w.endswith('ss') and len(w) > 3:
        return w[:-1]
    return w


def extract_verb(phrase: str) -> str:
    if not phrase:
        return ""
    first = phrase.strip().split()[0].lower()
    return _normalize_verb(first)


def is_bio_verb(verb: str) -> bool:
    v = _normalize_verb(verb)
    return v in BIO_VERBS or v + 's' in BIO_VERBS or v + 'e' in BIO_VERBS or v + 'es' in BIO_VERBS


def is_meta_verb(verb: str) -> bool:
    v = _normalize_verb(verb)
    return v in META_VERBS or v + 's' in META_VERBS or v + 'e' in META_VERBS


def _has_bio_domain_token(phrase: str) -> bool:
    if not phrase:
        return False
    for w in phrase.lower().split():
        w = w.strip(".,;:()[]\"'`")
        if w.endswith("'s"):
            w = w[:-2]
        if w in BIO_DOMAIN_TOKENS:
            return True
        if len(w) >= 5 and any(w.startswith(p) for p in BIO_PREFIXES):
            return True
    return False


def _has_html_artifact(phrase: str) -> bool:
    return bool(_HTML_RE.search(phrase)) if phrase else False


def _has_cyrillic(phrase: str) -> bool:
    return bool(_CYRILLIC_RE.search(phrase)) if phrase else False


def _phrase_tokens(phrase: str) -> set:
    if not phrase:
        return set()
    tokens = set()
    for w in phrase.split():
        w = w.lower().strip('.,;:()[]')
        if len(w) <= 2:
            continue
        if w.endswith('ing') and len(w) > 5:
            w = w[:-3]
        elif w.endswith('ed') and len(w) > 4:
            w = w[:-2]
        elif w.endswith('s') and not w.endswith('ss') and len(w) > 4:
            w = w[:-1]
        tokens.add(w)
    return tokens


def _is_tautological(src_phrase: str, tgt_phrase: str) -> bool:
    src_tok = _phrase_tokens(src_phrase)
    tgt_tok = _phrase_tokens(tgt_phrase)
    if not src_tok or not tgt_tok:
        return False
    intersection = len(src_tok & tgt_tok)
    union = len(src_tok | tgt_tok)
    if (intersection / union) >= 0.60:
        return True
    if len(src_tok) <= 8 and len(tgt_tok) <= 8 and intersection >= 3:
        return True
    return False


def shared_entity_is_abstract(evidence: list) -> bool:
    for ev in (evidence or []):
        if isinstance(ev, str) and ev.startswith('[shared:'):
            entity = ev[8:].rstrip(']').strip().lower()
            if entity in {'it', 'its', 'this', 'these', 'those', 'that', 'they', 'them',
                          'the', 'a', 'an', 'their', 'our', 'its'}:
                return True
            tokens = [t.strip('.,;:') for t in entity.split() if len(t.strip('.,;:')) >= 3]
            if not tokens:
                return True
            if all(t not in ABSTRACT_ENTITY_TOKENS for t in tokens):
                return False
            return True
    return False


def keyword_is_abstract(evidence: list) -> bool:
    for ev in (evidence or []):
        if isinstance(ev, str):
            for prefix in ('[keyword:', '[obj_obj:'):
                if ev.startswith(prefix):
                    kws = ev[len(prefix):].rstrip(']').strip().lower()
                    kw_list = [k.strip() for k in kws.split(',') if k.strip()]
                    if not kw_list:
                        return True
                    has_concrete = any(
                        k not in ABSTRACT_ENTITY_TOKENS and len(k) >= 4 and not k.isdigit()
                        for k in kw_list
                    )
                    if not has_concrete:
                        return True
    return False


# ─── classification ───────────────────────────────────────────────────────────

def should_confirm(
    src_phrase: str, tgt_phrase: str, relation: str,
    confidence: float, evidence: list, doc_is_bio: bool = False,
) -> tuple[bool, str]:
    src_verb = extract_verb(src_phrase)
    tgt_verb = extract_verb(tgt_phrase)

    if _has_html_artifact(src_phrase) or _has_html_artifact(tgt_phrase):
        return False, "html artifact in phrase"
    if _has_cyrillic(src_phrase) or _has_cyrillic(tgt_phrase):
        return False, "cyrillic text in phrase (metadata leak)"
    if not doc_is_bio and not _has_bio_domain_token(src_phrase) and not _has_bio_domain_token(tgt_phrase):
        return False, "no bio domain token in either phrase (non-bio article)"
    if _is_tautological(src_phrase, tgt_phrase):
        return False, "tautological src≈tgt phrases"

    if is_meta_verb(src_verb) and not is_bio_verb(src_verb):
        return False, f"meta src verb: {src_verb}"
    if is_meta_verb(tgt_verb) and not is_bio_verb(tgt_verb):
        return False, f"meta tgt verb: {tgt_verb}"
    if shared_entity_is_abstract(evidence):
        return False, f"abstract shared entity"
    if keyword_is_abstract(evidence):
        return False, f"abstract keyword"

    for ev in (evidence or []):
        if isinstance(ev, str) and ev.startswith('[subject:'):
            subj = ev[9:].rstrip(']').strip().lower()
            tokens = [t.strip() for t in subj.split(',') if t.strip()]
            if tokens and all(t in ABSTRACT_ENTITY_TOKENS or len(t) <= 3 for t in tokens):
                return False, f"abstract subject evidence"

    if confidence < 0.6 and not is_bio_verb(src_verb) and not is_bio_verb(tgt_verb):
        return False, f"low conf + non-bio verbs"
    if relation == 'sequential' and not is_bio_verb(src_verb) and not is_bio_verb(tgt_verb):
        return False, f"sequential non-bio"

    _GENERIC_BIO = {'cause', 'require', 'share', 'identify', 'contribute', 'involve'}
    if src_verb == tgt_verb and src_verb in _GENERIC_BIO:
        has_real_marker = any(isinstance(ev, str) and ev and not ev.startswith('[') for ev in (evidence or []))
        if not has_real_marker:
            has_obj_obj_evidence = any(isinstance(ev, str) and '[obj_obj:' in ev for ev in (evidence or []))
            if has_obj_obj_evidence and not keyword_is_abstract(evidence):
                return True, "obj_obj evidence with non-abstract keywords"
            return False, f"same generic verb without marker: {src_verb}"

    has_marker = any(isinstance(ev, str) and ev and not ev.startswith('[') for ev in (evidence or []))
    if has_marker:
        if is_bio_verb(src_verb) or is_bio_verb(tgt_verb):
            if _has_bio_domain_token(src_phrase) or _has_bio_domain_token(tgt_phrase):
                return True, "marker + bio verb + bio domain token"
            return False, "marker + bio verb but no bio domain token"
        return False, f"marker but non-bio verbs"

    src_bio_domain = _has_bio_domain_token(src_phrase)
    tgt_bio_domain = _has_bio_domain_token(tgt_phrase)
    has_bio_domain = src_bio_domain or tgt_bio_domain
    src_bio = is_bio_verb(src_verb)
    tgt_bio = is_bio_verb(tgt_verb)

    has_shared = any(isinstance(ev, str) and '[shared:' in ev for ev in (evidence or []))
    if has_shared:
        if src_bio and tgt_bio:
            return True, "shared entity + both bio verbs"
        if (src_bio or tgt_bio) and has_bio_domain and confidence >= 0.55:
            return True, "shared entity + one bio verb + bio domain"
        return False, f"shared entity but non-bio"

    has_keyword = any(isinstance(ev, str) and '[keyword:' in ev for ev in (evidence or []))
    if has_keyword:
        if src_bio and tgt_bio:
            return True, "keyword + both bio verbs"
        if (src_bio or tgt_bio) and has_bio_domain and confidence >= 0.55:
            return True, "keyword + one bio verb + bio domain"
        return False, f"keyword but non-bio"

    has_obj_obj = any(isinstance(ev, str) and '[obj_obj:' in ev for ev in (evidence or []))
    if has_obj_obj:
        if src_bio and tgt_bio and confidence >= 0.55:
            return True, "obj_obj + both bio verbs"
        if (src_bio or tgt_bio) and has_bio_domain and confidence >= 0.65:
            return True, "obj_obj + one bio verb + bio domain"
        return False, f"obj_obj but non-bio or low-conf"

    has_subject = any(isinstance(ev, str) and '[subject:' in ev for ev in (evidence or []))
    if has_subject:
        if src_bio and tgt_bio and confidence >= 0.55:
            return True, "shared subject + both bio verbs"
        if (src_bio or tgt_bio) and has_bio_domain and confidence >= 0.65:
            return True, "shared subject + one bio verb + bio domain"
        return False, f"shared subject but non-bio or low-conf"

    if src_bio and tgt_bio:
        return True, f"both bio verbs: {src_verb} + {tgt_verb}"

    return False, f"no clear positive signal: {src_verb}({'bio' if src_bio else 'meta'}), {tgt_verb}({'bio' if tgt_bio else 'meta'})"


# ─── Use Case ─────────────────────────────────────────────────────────────────

@dataclass
class AutoReviewResult:
    confirmed: int = 0
    rejected: int = 0
    total: int = 0
    confirmed_edges: List[Dict[str, Any]] = field(default_factory=list)
    rejected_edges: List[Dict[str, Any]] = field(default_factory=list)


async def auto_review_pending_edges(
    doc_id: str,
    action_repo: Any,
    dry_run: bool = False,
) -> AutoReviewResult:
    """
    Автоматически ревьюит все pending LEADS_TO рёбра документа.

    1. Загружает pending edges из репозитория.
    2. Классифицирует каждое ребро через should_confirm().
    3. Если dry_run=False — обновляет статусы в репозитории.
    4. Возвращает результат с деталями.
    """
    pending = action_repo.get_pending_for_document(doc_id)
    if not pending:
        return AutoReviewResult(total=0)

    confirmed_edges: List[Dict[str, Any]] = []
    rejected_edges: List[Dict[str, Any]] = []

    for edge in pending:
        src_phrase = edge.get("src_phrase") or edge.get("src_text") or ""
        tgt_phrase = edge.get("tgt_phrase") or edge.get("tgt_text") or ""
        relation = edge.get("relation_subtype", "")
        confidence = edge.get("confidence", 0.0)
        evidence = edge.get("evidence") or []

        ok, reason = should_confirm(src_phrase, tgt_phrase, relation, confidence, evidence)

        edge_info = {
            "src_uid": edge["src_uid"],
            "tgt_uid": edge["tgt_uid"],
            "src_phrase": src_phrase,
            "tgt_phrase": tgt_phrase,
            "relation_subtype": relation,
            "confidence": confidence,
            "reason": reason,
        }

        if ok:
            confirmed_edges.append(edge_info)
        else:
            rejected_edges.append(edge_info)

    # Update statuses in repository
    if not dry_run:
        for edge_info in confirmed_edges:
            try:
                action_repo.update_edge_status(
                    edge_info["src_uid"], edge_info["tgt_uid"],
                    edge_info["relation_subtype"], "confirmed",
                )
            except Exception as e:
                logger.warning(f"Failed to confirm edge {edge_info['src_uid'][:8]}: {e}")

        for edge_info in rejected_edges:
            try:
                action_repo.update_edge_status(
                    edge_info["src_uid"], edge_info["tgt_uid"],
                    edge_info["relation_subtype"], "rejected",
                )
            except Exception as e:
                logger.warning(f"Failed to reject edge {edge_info['src_uid'][:8]}: {e}")

    return AutoReviewResult(
        confirmed=len(confirmed_edges),
        rejected=len(rejected_edges),
        total=len(confirmed_edges) + len(rejected_edges),
        confirmed_edges=confirmed_edges,
        rejected_edges=rejected_edges,
    )
