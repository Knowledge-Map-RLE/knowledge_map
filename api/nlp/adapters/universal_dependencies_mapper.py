"""
Universal Dependencies mapping tables.

This module provides comprehensive mappings from various NLP tool tagsets
to Universal Dependencies v2 standard.

Sources:
- https://universaldependencies.org/u/pos/
- https://universaldependencies.org/u/dep/
- spaCy, NLTK, Stanford, UDPipe documentation
"""

from typing import Dict, Set


class UniversalDependenciesMapper:
    """
    Centralized mapping tables for converting various tagsets to UD format.
    """

    # ============================================================================
    # Penn Treebank POS tags → Universal Dependencies POS tags
    # Used by: NLTK, Stanford Parser
    # ============================================================================

    PTB_TO_UD_POS: Dict[str, str] = {
        # Nouns
        'NN': 'NOUN',       # noun, singular or mass
        'NNS': 'NOUN',      # noun, plural
        'NNP': 'PROPN',     # proper noun, singular
        'NNPS': 'PROPN',    # proper noun, plural

        # Verbs
        'VB': 'VERB',       # verb, base form
        'VBD': 'VERB',      # verb, past tense
        'VBG': 'VERB',      # verb, gerund/present participle
        'VBN': 'VERB',      # verb, past participle
        'VBP': 'VERB',      # verb, non-3rd person singular present
        'VBZ': 'VERB',      # verb, 3rd person singular present

        # Adjectives
        'JJ': 'ADJ',        # adjective
        'JJR': 'ADJ',       # adjective, comparative
        'JJS': 'ADJ',       # adjective, superlative

        # Adverbs
        'RB': 'ADV',        # adverb
        'RBR': 'ADV',       # adverb, comparative
        'RBS': 'ADV',       # adverb, superlative
        'WRB': 'ADV',       # wh-adverb

        # Pronouns
        'PRP': 'PRON',      # personal pronoun
        'PRP$': 'DET',      # possessive pronoun (treated as determiner in UD)
        'WP': 'PRON',       # wh-pronoun
        'WP$': 'DET',       # possessive wh-pronoun

        # Determiners
        'DT': 'DET',        # determiner
        'WDT': 'DET',       # wh-determiner
        'PDT': 'DET',       # predeterminer

        # Numbers
        'CD': 'NUM',        # cardinal number

        # Prepositions/Postpositions
        'IN': 'ADP',        # preposition or subordinating conjunction
        'TO': 'PART',       # to (infinitive marker)

        # Conjunctions
        'CC': 'CCONJ',      # coordinating conjunction
        # IN above can also be SCONJ in context

        # Particles
        'RP': 'PART',       # particle
        'POS': 'PART',      # possessive ending

        # Modals
        'MD': 'AUX',        # modal

        # Existential there
        'EX': 'PRON',       # existential there

        # Symbols and punctuation
        'SYM': 'SYM',       # symbol
        '.': 'PUNCT',       # punctuation
        ',': 'PUNCT',
        ':': 'PUNCT',
        '(': 'PUNCT',
        ')': 'PUNCT',
        '``': 'PUNCT',
        "''": 'PUNCT',
        '#': 'SYM',
        '$': 'SYM',

        # Others
        'FW': 'X',          # foreign word
        'LS': 'X',          # list item marker
        'UH': 'INTJ',       # interjection
    }

    # ============================================================================
    # Stanford Dependencies → Universal Dependencies relations
    # ============================================================================

    STANFORD_TO_UD_DEP: Dict[str, str] = {
        # Core arguments
        'nsubj': 'nsubj',           # nominal subject
        'nsubjpass': 'nsubj:pass',  # passive nominal subject
        'dobj': 'obj',              # direct object
        'iobj': 'iobj',             # indirect object
        'csubj': 'csubj',           # clausal subject
        'csubjpass': 'csubj:pass',  # passive clausal subject
        'ccomp': 'ccomp',           # clausal complement
        'xcomp': 'xcomp',           # open clausal complement

        # Non-core dependents
        'obl': 'obl',               # oblique nominal
        'vocative': 'vocative',     # vocative
        'expl': 'expl',             # expletive
        'dislocated': 'dislocated', # dislocated elements
        'advcl': 'advcl',           # adverbial clause modifier
        'advmod': 'advmod',         # adverbial modifier
        'discourse': 'discourse',   # discourse element
        'aux': 'aux',               # auxiliary
        'auxpass': 'aux:pass',      # passive auxiliary
        'cop': 'cop',               # copula
        'mark': 'mark',             # marker

        # Nominal dependents
        'nmod': 'nmod',             # nominal modifier
        'appos': 'appos',           # appositional modifier
        'nummod': 'nummod',         # numeric modifier
        'acl': 'acl',               # clausal modifier of noun
        'amod': 'amod',             # adjectival modifier
        'det': 'det',               # determiner
        'clf': 'clf',               # classifier
        'case': 'case',             # case marking

        # Coordination
        'conj': 'conj',             # conjunct
        'cc': 'cc',                 # coordinating conjunction
        'cc:preconj': 'cc:preconj', # preconjunct

        # MWE and other
        'fixed': 'fixed',           # fixed multiword expression
        'flat': 'flat',             # flat multiword expression
        'compound': 'compound',     # compound
        'list': 'list',             # list
        'parataxis': 'parataxis',   # parataxis
        'orphan': 'orphan',         # orphan
        'goeswith': 'goeswith',     # goes with
        'reparandum': 'reparandum', # reparandum

        # Loose
        'punct': 'punct',           # punctuation
        'root': 'root',             # root
        'dep': 'dep',               # unspecified dependency

        # Preposition-specific
        'prep': 'case',             # prepositional modifier → case
        'pobj': 'obl',              # object of preposition → oblique
        'pcomp': 'xcomp',           # prepositional complement

        # Modifier-specific
        'nn': 'compound',           # noun compound modifier
        'poss': 'nmod:poss',        # possession modifier
        'possessive': 'case',       # possessive clitic
        'number': 'nummod',         # number compound modifier

        # Other Stanford-specific
        'agent': 'obl:agent',       # agent
        'neg': 'advmod',            # negation modifier
        'tmod': 'obl:tmod',         # temporal modifier
        'npadvmod': 'obl:npmod',    # noun phrase adverbial modifier
        'predet': 'det:predet',     # predeterminer
        'preconj': 'cc:preconj',    # preconjunct
        'quantmod': 'advmod',       # quantifier modifier
        'rcmod': 'acl:relcl',       # relative clause modifier
        'partmod': 'acl',           # participial modifier
        'infmod': 'acl',            # infinitival modifier
        'acomp': 'xcomp',           # adjectival complement
        'prt': 'compound:prt',      # phrasal verb particle
        'mwe': 'fixed',             # multi-word expression
        'ref': 'ref',               # referent
    }

    # ============================================================================
    # spaCy fine-grained tags → UD morphological features
    # ============================================================================

    @staticmethod
    def spacy_tag_to_morph(tag: str, pos: str) -> Dict[str, str]:
        """
        Convert spaCy fine-grained tag to UD morphological features.

        Args:
            tag: spaCy tag (e.g., 'VBZ', 'NNS')
            pos: UD POS tag

        Returns:
            Dictionary of morphological features
        """
        morph = {}

        # Verbs
        if pos == 'VERB':
            if tag == 'VB':
                morph['VerbForm'] = 'Inf'
            elif tag == 'VBD':
                morph['Tense'] = 'Past'
                morph['VerbForm'] = 'Fin'
            elif tag == 'VBG':
                morph['Aspect'] = 'Prog'
                morph['Tense'] = 'Pres'
                morph['VerbForm'] = 'Part'
            elif tag == 'VBN':
                morph['Aspect'] = 'Perf'
                morph['Tense'] = 'Past'
                morph['VerbForm'] = 'Part'
            elif tag == 'VBP':
                morph['Tense'] = 'Pres'
                morph['VerbForm'] = 'Fin'
            elif tag == 'VBZ':
                morph['Number'] = 'Sing'
                morph['Person'] = '3'
                morph['Tense'] = 'Pres'
                morph['VerbForm'] = 'Fin'

        # Nouns
        elif pos == 'NOUN' or pos == 'PROPN':
            if tag.endswith('S'):  # NNS, NNPS
                morph['Number'] = 'Plur'
            else:
                morph['Number'] = 'Sing'

        # Adjectives
        elif pos == 'ADJ':
            if tag == 'JJR':
                morph['Degree'] = 'Cmp'
            elif tag == 'JJS':
                morph['Degree'] = 'Sup'
            else:
                morph['Degree'] = 'Pos'

        # Adverbs
        elif pos == 'ADV':
            if tag == 'RBR':
                morph['Degree'] = 'Cmp'
            elif tag == 'RBS':
                morph['Degree'] = 'Sup'

        # Pronouns
        elif pos == 'PRON':
            if tag == 'PRP':
                morph['PronType'] = 'Prs'
            elif tag == 'WP':
                morph['PronType'] = 'Int'

        return morph

    # ============================================================================
    # Named Entity types mapping
    # ============================================================================

    # spaCy NER types (already fairly standard)
    SPACY_NER_TYPES: Set[str] = {
        'PERSON', 'NORP', 'FAC', 'ORG', 'GPE', 'LOC', 'PRODUCT',
        'EVENT', 'WORK_OF_ART', 'LAW', 'LANGUAGE', 'DATE', 'TIME',
        'PERCENT', 'MONEY', 'QUANTITY', 'ORDINAL', 'CARDINAL',
    }

    # OntoNotes → Standard mapping
    ONTONOTES_TO_STANDARD: Dict[str, str] = {
        'NORP': 'GROUP',           # Nationalities, religious/political groups
        'FAC': 'FACILITY',
        'GPE': 'LOCATION',         # Geo-political entity
        'LOC': 'LOCATION',
        'WORK_OF_ART': 'WORK',
        'LANGUAGE': 'LANG',
    }

    # BioBERT/SciBERT entity types (biomedical)
    BIOMEDICAL_ENTITY_TYPES: Set[str] = {
        'GENE', 'PROTEIN', 'DISEASE', 'CHEMICAL', 'SPECIES',
        'CELL_LINE', 'CELL_TYPE', 'DNA', 'RNA', 'ENZYME',
    }

    # ============================================================================
    # Semantic Role Labels (PropBank/FrameNet)
    # ============================================================================

    PROPBANK_CORE_ROLES = ['ARG0', 'ARG1', 'ARG2', 'ARG3', 'ARG4', 'ARG5']

    PROPBANK_MODIFIER_ROLES = [
        'ARGM-ADJ', 'ARGM-ADV', 'ARGM-CAU', 'ARGM-DIR', 'ARGM-DIS',
        'ARGM-EXT', 'ARGM-GOL', 'ARGM-LOC', 'ARGM-MNR', 'ARGM-MOD',
        'ARGM-NEG', 'ARGM-PRD', 'ARGM-PRP', 'ARGM-TMP',
    ]

    PROPBANK_ROLE_DESCRIPTIONS: Dict[str, str] = {
        'ARG0': 'Agent/Causer',
        'ARG1': 'Patient/Theme',
        'ARG2': 'Instrument/Benefactive/Attribute',
        'ARG3': 'Starting point/Benefactive',
        'ARG4': 'Ending point',
        'ARGM-ADJ': 'Adjectival',
        'ARGM-ADV': 'General Adverbial',
        'ARGM-CAU': 'Cause',
        'ARGM-DIR': 'Direction',
        'ARGM-DIS': 'Discourse connective',
        'ARGM-EXT': 'Extent',
        'ARGM-GOL': 'Goal',
        'ARGM-LOC': 'Location',
        'ARGM-MNR': 'Manner',
        'ARGM-MOD': 'Modal',
        'ARGM-NEG': 'Negation',
        'ARGM-PRD': 'Predication',
        'ARGM-PRP': 'Purpose',
        'ARGM-TMP': 'Temporal',
    }

    # ============================================================================
    # Discourse Relations (RST)
    # ============================================================================

    RST_RELATIONS = [
        # Elaboration
        'ELABORATION', 'EXAMPLE', 'DEFINITION',

        # Attribution
        'ATTRIBUTION', 'QUOTATION',

        # Comparison
        'COMPARISON', 'CONTRAST', 'ANALOGY',

        # Cause
        'CAUSE', 'RESULT', 'CONSEQUENCE', 'PURPOSE',

        # Condition
        'CONDITION', 'OTHERWISE',

        # Temporal
        'TEMPORAL-BEFORE', 'TEMPORAL-AFTER', 'TEMPORAL-SAME-TIME',

        # Topic
        'TOPIC-SHIFT', 'TOPIC-COMMENT',

        # Joint
        'JOINT', 'LIST', 'DISJUNCTION',

        # Background
        'BACKGROUND', 'CIRCUMSTANCE',

        # Evaluation
        'EVALUATION', 'INTERPRETATION', 'CONCLUSION',

        # Manner/Means
        'MANNER', 'MEANS',

        # Summary
        'SUMMARY', 'RESTATEMENT',

        # Enablement
        'ENABLEMENT',
    ]

    # ============================================================================
    # Helper methods
    # ============================================================================

    @classmethod
    def is_valid_ud_pos(cls, pos: str) -> bool:
        """Check if a POS tag is valid UD."""
        valid_tags = {
            'ADJ', 'ADP', 'ADV', 'AUX', 'CCONJ', 'DET', 'INTJ',
            'NOUN', 'NUM', 'PART', 'PRON', 'PROPN', 'PUNCT',
            'SCONJ', 'SYM', 'VERB', 'X'
        }
        return pos in valid_tags

    @classmethod
    def is_valid_ud_relation(cls, rel: str) -> bool:
        """Check if a dependency relation is valid UD."""
        # Basic check - should contain only lowercase letters, colons
        return rel.replace(':', '').replace('_', '').isalpha() and rel.islower()

    @classmethod
    def get_pos_category(cls, pos: str) -> str:
        """
        Get broad category for a UD POS tag.

        Returns: 'open-class', 'closed-class', 'other'
        """
        open_class = {'NOUN', 'VERB', 'ADJ', 'ADV', 'PROPN'}
        closed_class = {'ADP', 'AUX', 'CCONJ', 'DET', 'NUM', 'PART', 'PRON', 'SCONJ'}

        if pos in open_class:
            return 'open-class'
        elif pos in closed_class:
            return 'closed-class'
        else:
            return 'other'
