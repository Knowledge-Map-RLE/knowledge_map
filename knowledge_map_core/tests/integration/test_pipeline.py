"""
Integration tests using real sentences from scientific articles.
Tests the full pipeline: sentence → DependencyTree → RuleEngine → statements.
"""

from src.extractor.engine import RuleEngine
from src.extractor.context import ExtractionContext
from src.extractor.rules import ALL_RULES


def test_copular_from_article():
    sentence = "PD is an age-related multifactorial disease."
    tree = _mock_dep_tree_copular_complex()
    engine = RuleEngine(ALL_RULES)
    ctx = ExtractionContext(sentence_text=sentence)
    statements = engine.process_sentence(tree, ctx)
    assert len(statements) >= 1


def test_coordination_from_article():
    sentence = "PD research has generated a rich and complex body of knowledge."
    tree = _mock_dep_tree_coordination()
    engine = RuleEngine(ALL_RULES)
    ctx = ExtractionContext(sentence_text=sentence)
    statements = engine.process_sentence(tree, ctx)
    coord_statements = [s for s in statements if s.predicate == "property"]
    assert len(coord_statements) >= 2


def test_passive_from_article():
    sentence = "PD is influenced by both genetic and environmental factors."
    tree = _mock_dep_tree_passive()
    engine = RuleEngine(ALL_RULES)
    ctx = ExtractionContext(sentence_text=sentence)
    statements = engine.process_sentence(tree, ctx)
    assert len(statements) >= 1


def test_multiple_rules_on_complex_sentence():
    sentence = (
        "Since the discovery of dopamine as a neurotransmitter in the 1950s, "
        "Parkinson's disease (PD) research has generated a rich and complex "
        "body of knowledge, revealing PD to be an age-related multifactorial "
        "disease, influenced by both genetic and environmental factors."
    )
    tree = _mock_dep_tree_complex()
    engine = RuleEngine(ALL_RULES)
    ctx = ExtractionContext(sentence_text=sentence)
    statements = engine.process_sentence(tree, ctx)
    assert len(statements) >= 1


def test_causal_from_article():
    sentence = "Mitochondrial dysfunction causes oxidative stress."
    tree = _mock_dep_tree_causal()
    engine = RuleEngine(ALL_RULES)
    ctx = ExtractionContext(sentence_text=sentence)
    statements = engine.process_sentence(tree, ctx)
    assert len(statements) >= 1


def test_negation_from_article():
    sentence = "Lewy bodies are typically not present in affected carriers."
    tree = _mock_dep_tree_negation()
    engine = RuleEngine(ALL_RULES)
    ctx = ExtractionContext(sentence_text=sentence)
    statements = engine.process_sentence(tree, ctx)
    assert len(statements) >= 1


def test_active_voice_from_article():
    sentence = "Genetic factors influence Parkinson's disease."
    tree = _mock_dep_tree_active()
    engine = RuleEngine(ALL_RULES)
    ctx = ExtractionContext(sentence_text=sentence)
    statements = engine.process_sentence(tree, ctx)
    assert len(statements) >= 1


def test_relative_clause():
    sentence = "PD, which is age-related, affects the elderly."
    tree = _mock_dep_tree_relcl()
    engine = RuleEngine(ALL_RULES)
    ctx = ExtractionContext(sentence_text=sentence)
    statements = engine.process_sentence(tree, ctx)
    assert len(statements) >= 1


def _make_tok(idx, text, lemma, pos, tag, dep, head):
    from src.parser.dep_tree import TokenInfo
    return TokenInfo(idx=idx, text=text, lemma=lemma, pos=pos, tag=tag, dep=dep, head_idx=head)


def _make_tree(tokens, deps):
    for dep in deps:
        dependent_idx, head_idx, rel = dep
        for t in tokens:
            if t.idx == dependent_idx:
                t.dep = rel
                t.head_idx = head_idx
                break
    from src.parser.dep_tree import DependencyTree
    return DependencyTree(tokens=tokens)


def _mock_dep_tree_copular_complex():
    tokens = [
        _make_tok(0, "PD", "PD", "NOUN", "NN", "nsubj", 2),
        _make_tok(1, "is", "be", "AUX", "VBZ", "cop", 2),
        _make_tok(2, "disease", "disease", "NOUN", "NN", "ROOT", 2),
        _make_tok(3, "an", "an", "DET", "DT", "det", 2),
        _make_tok(4, "age-related", "age-related", "ADJ", "JJ", "amod", 2),
        _make_tok(5, "multifactorial", "multifactorial", "ADJ", "JJ", "amod", 2),
    ]
    deps = [(0, 2, "nsubj"), (1, 2, "cop"), (3, 2, "det"), (4, 2, "amod"), (5, 2, "amod")]
    return _make_tree(tokens, deps)


def _mock_dep_tree_coordination():
    tokens = [
        _make_tok(0, "rich", "rich", "ADJ", "JJ", "amod", 3),
        _make_tok(1, "and", "and", "CCONJ", "CC", "cc", 0),
        _make_tok(2, "complex", "complex", "ADJ", "JJ", "conj", 0),
        _make_tok(3, "body", "body", "NOUN", "NN", "ROOT", 3),
        _make_tok(4, "of", "of", "ADP", "IN", "prep", 3),
        _make_tok(5, "knowledge", "knowledge", "NOUN", "NN", "pobj", 4),
    ]
    deps = [(0, 3, "amod"), (1, 0, "cc"), (2, 0, "conj"), (4, 3, "prep"), (5, 4, "pobj")]
    return _make_tree(tokens, deps)


def _mock_dep_tree_passive():
    tokens = [
        _make_tok(0, "PD", "PD", "NOUN", "NN", "nsubj:pass", 2),
        _make_tok(1, "is", "be", "AUX", "VBZ", "aux:pass", 2),
        _make_tok(2, "influenced", "influence", "VERB", "VBN", "ROOT", 2),
        _make_tok(3, "by", "by", "ADP", "IN", "case", 4),
        _make_tok(4, "factors", "factor", "NOUN", "NNS", "obl", 2),
        _make_tok(5, "both", "both", "CCONJ", "CC", "cc:preconj", 4),
        _make_tok(6, "genetic", "genetic", "ADJ", "JJ", "amod", 4),
        _make_tok(7, "and", "and", "CCONJ", "CC", "cc", 6),
        _make_tok(8, "environmental", "environmental", "ADJ", "JJ", "conj", 6),
    ]
    deps = [(0, 2, "nsubj:pass"), (1, 2, "aux:pass"), (3, 4, "case"), (4, 2, "obl"),
            (5, 4, "cc:preconj"), (6, 4, "amod"), (7, 6, "cc"), (8, 6, "conj")]
    return _make_tree(tokens, deps)


def _mock_dep_tree_causal():
    tokens = [
        _make_tok(0, "Mitochondrial", "mitochondrial", "ADJ", "JJ", "amod", 1),
        _make_tok(1, "dysfunction", "dysfunction", "NOUN", "NN", "nsubj", 2),
        _make_tok(2, "causes", "cause", "VERB", "VBZ", "ROOT", 2),
        _make_tok(3, "oxidative", "oxidative", "ADJ", "JJ", "amod", 4),
        _make_tok(4, "stress", "stress", "NOUN", "NN", "obj", 2),
    ]
    deps = [(0, 1, "amod"), (1, 2, "nsubj"), (3, 4, "amod"), (4, 2, "obj")]
    return _make_tree(tokens, deps)


def _mock_dep_tree_negation():
    tokens = [
        _make_tok(0, "Lewy", "Lewy", "PROPN", "NNP", "compound", 1),
        _make_tok(1, "bodies", "body", "NOUN", "NNS", "nsubj", 4),
        _make_tok(2, "are", "be", "AUX", "VBP", "aux", 4),
        _make_tok(3, "typically", "typically", "ADV", "RB", "advmod", 4),
        _make_tok(4, "not", "not", "PART", "RB", "neg", 5),
        _make_tok(5, "present", "present", "ADJ", "JJ", "ROOT", 5),
        _make_tok(6, "in", "in", "ADP", "IN", "prep", 5),
        _make_tok(7, "carriers", "carrier", "NOUN", "NNS", "pobj", 6),
    ]
    deps = [(0, 1, "compound"), (1, 5, "nsubj"), (2, 5, "cop"), (3, 5, "advmod"),
            (4, 5, "neg"), (6, 5, "prep"), (7, 6, "pobj")]
    return _make_tree(tokens, deps)


def _mock_dep_tree_active():
    tokens = [
        _make_tok(0, "Genetic", "genetic", "ADJ", "JJ", "amod", 1),
        _make_tok(1, "factors", "factor", "NOUN", "NNS", "nsubj", 2),
        _make_tok(2, "influence", "influence", "VERB", "VBP", "ROOT", 2),
        _make_tok(3, "Parkinson", "Parkinson", "PROPN", "NNP", "compound", 4),
        _make_tok(4, "disease", "disease", "NOUN", "NN", "obj", 2),
    ]
    deps = [(0, 1, "amod"), (1, 2, "nsubj"), (3, 4, "compound"), (4, 2, "obj")]
    return _make_tree(tokens, deps)


def _mock_dep_tree_relcl():
    tokens = [
        _make_tok(0, "PD", "PD", "NOUN", "NN", "nsubj", 6),
        _make_tok(1, ",", ",", "PUNCT", ",", "punct", 0),
        _make_tok(2, "which", "which", "PRON", "WP", "nsubj", 4),
        _make_tok(3, "is", "be", "AUX", "VBZ", "cop", 4),
        _make_tok(4, "age-related", "age-related", "ADJ", "JJ", "relcl", 6),
        _make_tok(5, ",", ",", "PUNCT", ",", "punct", 0),
        _make_tok(6, "affects", "affect", "VERB", "VBZ", "ROOT", 6),
        _make_tok(7, "the", "the", "DET", "DT", "det", 8),
        _make_tok(8, "elderly", "elderly", "ADJ", "JJ", "obj", 6),
    ]
    deps = [(0, 6, "nsubj"), (1, 0, "punct"), (2, 4, "nsubj"), (3, 4, "cop"),
            (4, 6, "relcl"), (5, 0, "punct"), (7, 8, "det"), (8, 6, "obj")]
    return _make_tree(tokens, deps)


def _mock_dep_tree_complex():
    tokens = [
        _make_tok(0, "Since", "since", "ADP", "IN", "mark", 2),
        _make_tok(1, "the", "the", "DET", "DT", "det", 2),
        _make_tok(2, "discovery", "discovery", "NOUN", "NN", "obl", 18),
        _make_tok(3, "of", "of", "ADP", "IN", "case", 4),
        _make_tok(4, "dopamine", "dopamine", "NOUN", "NN", "nmod", 2),
        _make_tok(5, "as", "as", "ADP", "IN", "case", 6),
        _make_tok(6, "neurotransmitter", "neurotransmitter", "NOUN", "NN", "nmod", 2),
        _make_tok(7, "a", "a", "DET", "DT", "det", 6),
        _make_tok(8, "in", "in", "ADP", "IN", "case", 9),
        _make_tok(9, "1950s", "1950s", "NOUN", "NN", "nmod", 2),
        _make_tok(10, "PD", "PD", "NOUN", "NN", "nmod", 11),
        _make_tok(11, "research", "research", "NOUN", "NN", "nsubj", 13),
        _make_tok(12, "has", "have", "AUX", "VBZ", "aux", 13),
        _make_tok(13, "generated", "generate", "VERB", "VBN", "ROOT", 13),
        _make_tok(14, "a", "a", "DET", "DT", "det", 15),
        _make_tok(15, "body", "body", "NOUN", "NN", "obj", 13),
        _make_tok(16, "of", "of", "ADP", "IN", "case", 17),
        _make_tok(17, "knowledge", "knowledge", "NOUN", "NN", "nmod", 15),
        _make_tok(18, ",", ",", "PUNCT", ",", "punct", 13),
        _make_tok(19, "revealing", "reveal", "VERB", "VBG", "advcl", 13),
        _make_tok(20, "PD", "PD", "NOUN", "NN", "obj", 19),
        _make_tok(21, "to", "to", "PART", "TO", "mark", 22),
        _make_tok(22, "be", "be", "AUX", "VB", "xcomp", 19),
        _make_tok(23, "a", "a", "DET", "DT", "det", 24),
        _make_tok(24, "disease", "disease", "NOUN", "NN", "attr", 22),
        _make_tok(25, "age-related", "age-related", "ADJ", "JJ", "amod", 24),
        _make_tok(26, "multifactorial", "multifactorial", "ADJ", "JJ", "amod", 24),
        _make_tok(27, ",", ",", "PUNCT", ",", "punct", 22),
        _make_tok(28, "influenced", "influence", "VERB", "VBN", "acl", 24),
        _make_tok(29, "by", "by", "ADP", "IN", "case", 30),
        _make_tok(30, "factors", "factor", "NOUN", "NNS", "obl", 28),
        _make_tok(31, "both", "both", "CCONJ", "CC", "cc:preconj", 30),
        _make_tok(32, "genetic", "genetic", "ADJ", "JJ", "amod", 30),
        _make_tok(33, "and", "and", "CCONJ", "CC", "cc", 32),
        _make_tok(34, "environmental", "environmental", "ADJ", "JJ", "conj", 32),
    ]
    deps = [
        (0, 2, "mark"), (1, 2, "det"), (3, 4, "case"), (4, 2, "nmod"),
        (5, 6, "case"), (6, 2, "nmod"), (7, 6, "det"), (8, 9, "case"),
        (9, 2, "nmod"), (10, 11, "nmod"), (11, 13, "nsubj"),
        (12, 13, "aux"), (14, 15, "det"), (15, 13, "obj"),
        (16, 17, "case"), (17, 15, "nmod"), (18, 13, "punct"),
        (19, 13, "advcl"), (20, 19, "obj"), (21, 22, "mark"),
        (22, 19, "xcomp"), (23, 24, "det"), (24, 22, "attr"),
        (25, 24, "amod"), (26, 24, "amod"), (27, 22, "punct"),
        (28, 24, "acl"), (29, 30, "case"), (30, 28, "obl"),
        (31, 30, "cc:preconj"), (32, 30, "amod"), (33, 32, "cc"),
        (34, 32, "conj"),
    ]
    return _make_tree(tokens, deps)
