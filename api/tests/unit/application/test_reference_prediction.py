"""Автоматические контрольные задачи для семантики и символьных шаблонов."""
import copy
import json

import pytest

from domain.article_maps import ArticleMapError
from domain.reference_prediction import (
    Atom, Corpus, Occurrence, canonicalize, evaluate, fit_aliases, learn_rules, merge_corpora, predict, source_priority,
)


SCOPE = json.dumps({"conditions": [], "modality": None, "quantifier": None,
                    "qualifiers": [], "temporal_context": None}, sort_keys=True)


def occurrence(source, node, predicate, subject, *, scope=SCOPE, negated=False):
    return Occurrence(source, node, f"{subject} {predicate}", {"unit_ids": ["U1"]},
                      Atom(predicate, "assertion", (("subject", subject),), scope, negated))


def training(multi=False):
    items, edges = [], set()
    for source, subject in (("one", "mice"), ("two", "rats")):
        items += [occurrence(source, "A", "eligible", subject), occurrence(source, "C", "enrolled", subject)]
        edges.add(((source, "A"), (source, "C")))
        if multi:
            items.append(occurrence(source, "B", "consented", subject))
            edges.add(((source, "B"), (source, "C")))
    items.append(occurrence("three", "A", "eligible", "hamsters"))
    if multi:
        items.append(occurrence("three", "B", "consented", "hamsters"))
    return Corpus(items, edges)


def graph(concept="Mice", alias=None):
    return {"schema_version": 5, "concepts": [{"id": "C1", "display_text": concept, "aliases": alias or []}],
            "nodes": [{"id": "N1", "display_text": "Mice are eligible", "kind": "assertion",
                       "provenance": {"unit_ids": ["U1"]}, "semantic": {
                           "predicate": "eligible", "roles": [{"role": "subject", "concept_id": "C1", "node_id": None}],
                           "inputs": [], "quantifier": None, "modality": None, "negated": False,
                           "conditions": [], "temporal_context": None, "qualifiers": {"attributes": []}}}], "edges": []}


@pytest.mark.parametrize("graph_mode", [False, True])
@pytest.mark.parametrize("multi", [False, True])
def test_generates_novel_range_restricted_prediction(graph_mode, multi):
    corpus = training(multi)
    rules, _ = learn_rules(corpus, graph_mode=graph_mode)
    predictions, _ = predict(corpus, rules)
    expected = occurrence("target", "N", "enrolled", "hamsters")
    assert expected.atom.key in {p["id"] for p in predictions}
    assert all(p["status"] == "statistical_hypothesis" for p in predictions)
    assert all(p["support"] >= 2 and p["premises"] for p in predictions)
    assert evaluate(predictions, Corpus([expected], set()))["matched"] >= 1


def test_multiple_inputs_are_required_and_not_dropped():
    corpus = training(True)
    corpus.occurrences = [o for o in corpus.occurrences if not (o.source_id == "three" and o.node_id == "B")]
    rules, _ = learn_rules(corpus, graph_mode=True)
    predictions, _ = predict(corpus, rules)
    assert occurrence("target", "N", "enrolled", "hamsters").atom.key not in {p["id"] for p in predictions}


def test_template_examples_follow_the_canonical_premise_order():
    corpus = training(True)
    lookup = {(o.source_id, o.node_id): o for o in corpus.occurrences}
    for rule in learn_rules(corpus, graph_mode=True)[0]:
        for example in rule.examples:
            predicates = [lookup[(example["source_id"], node_id)].atom.predicate for node_id in example["premises"]]
            assert predicates == [atom.predicate for atom in rule.body]


def test_unreferenced_dictionary_entries_do_not_enter_training_aliases():
    value = graph()
    value["concepts"].append({"id": "C2", "display_text": "Unused participant", "aliases": ["Noise"]})
    aliases = fit_aliases([value])
    assert "unused participant" not in aliases and "noise" not in aliases


def test_does_not_invent_unbound_participant():
    corpus = training()
    corpus.occurrences = [o if o.node_id != "C" else occurrence(o.source_id, "C", "enrolled", "unknown")
                          for o in corpus.occurrences]
    rules, _ = learn_rules(corpus, graph_mode=True)
    assert not rules


def test_does_not_claim_association_transitivity_as_logic():
    items = [occurrence("one", "A", "associated_with", "a"), occurrence("one", "B", "associated_with", "b")]
    rules, _ = learn_rules(Corpus(items, set()), graph_mode=True)
    assert not rules


def test_graph_preserves_direction_and_requires_internal_premise_edges():
    corpus = training(True)
    for source in ("one", "two"):
        corpus.edges.add(((source, "A"), (source, "B")))
    rules, _ = learn_rules(corpus, graph_mode=True)
    predicted, _ = predict(corpus, rules)
    wanted = occurrence("target", "N", "enrolled", "hamsters").atom.key
    assert wanted not in {p["id"] for p in predicted}
    corpus.edges.add((("three", "B"), ("three", "A")))
    assert wanted not in {p["id"] for p in predict(corpus, rules)[0]}
    corpus.edges.add((("three", "A"), ("three", "B")))
    assert wanted in {p["id"] for p in predict(corpus, rules)[0]}


@pytest.mark.parametrize("field,value", [("negated", True), ("quantifier", "some"), ("modality", "may"),
                                         ("temporal_context", "after six months"),
                                         ("conditions", ["in humans"]),
                                         ("qualifiers", {"attributes": [{"name": "n", "value": 12, "unit": None}]})])
def test_context_and_negation_change_identity(field, value):
    original = graph()
    changed = copy.deepcopy(original)
    changed["nodes"][0]["semantic"][field] = value
    aliases = fit_aliases([original])
    assert canonicalize("one", original, aliases).occurrences[0].atom.key != canonicalize("two", changed, aliases).occurrences[0].atom.key


def test_declared_synonyms_and_source_order_do_not_change_claim_identity():
    a, b = graph("Mice", ["Experimental mice"]), graph("Experimental mice")
    aliases = fit_aliases([a, b])
    assert aliases == fit_aliases([b, a])
    assert canonicalize("one", a, aliases).occurrences[0].atom.key == canonicalize("two", b, aliases).occurrences[0].atom.key


def test_generic_copula_is_not_reclassified_without_explicit_class_role():
    value = graph()
    value["nodes"][0]["semantic"]["predicate"] = "are"
    aliases = fit_aliases([value])
    assert canonicalize("one", value, aliases).occurrences[0].atom.predicate == "are"
    value["nodes"][0]["semantic"]["roles"].append({"role": "class", "concept_id": "C1", "node_id": None})
    assert canonicalize("one", value, aliases).occurrences[0].atom.predicate == "is_a"


def test_ambiguous_alias_does_not_merge_different_concepts():
    a, b = graph("Alzheimer disease", ["AD"]), graph("Anxiety and depression", ["AD"])
    aliases = fit_aliases([a, b])
    assert aliases["alzheimer disease"] != aliases["anxiety and depression"]
    assert "ad" not in aliases


def test_target_aliases_are_not_fitted_and_target_is_rejected_from_training():
    aliases = fit_aliases([graph("Mice")])
    assert "target-specific synonym" not in aliases
    with pytest.raises(ArticleMapError, match="leaked"):
        canonicalize("PMC10000452", graph(), aliases).assert_isolated({"PMC10000452"})


def test_missing_target_claim_is_unconfirmed_not_false():
    atom = occurrence("source", "N", "eligible", "mice").atom
    payload = {"id": atom.key, "atom": {"predicate": atom.predicate, "kind": atom.kind,
                                          "roles": atom.roles, "scope": atom.scope, "negated": atom.negated}}
    evaluation = evaluate([payload], Corpus([], set()))
    assert evaluation["details"][0]["status"] == "not_confirmed_by_target"
    assert evaluation["scientific_accuracy"] == "requires_review"
    assert evaluation["unique_target_atoms"] == 0
    assert evaluation["matched_target_atoms"] == 0


@pytest.mark.parametrize("restriction", ["all", "some", "may", "after treatment", "in humans"])
@pytest.mark.parametrize("graph_mode", [True, False])
def test_generated_hypotheses_do_not_apply_to_incompatible_premise_context(restriction, graph_mode):
    corpus = training()
    corpus.occurrences[-1] = occurrence("three", "A", "eligible", "hamsters", scope=restriction)
    rules, _ = learn_rules(corpus, graph_mode=graph_mode)
    wanted = occurrence("target", "N", "enrolled", "hamsters").atom.key
    assert wanted not in {p["id"] for p in predict(corpus, rules)[0]}


def test_explicit_negation_and_context_mismatch_are_distinct():
    positive = occurrence("source", "N", "eligible", "mice")
    payload = {"id": positive.atom.key, "atom": {
        "predicate": positive.atom.predicate, "kind": positive.atom.kind, "roles": positive.atom.roles,
        "scope": positive.atom.scope, "negated": False}}
    negative = occurrence("target", "N", "eligible", "mice", negated=True)
    assert evaluate([payload], Corpus([negative], set()))["details"][0]["status"] == "explicit_contradiction"
    other = occurrence("target", "N", "eligible", "mice", scope="different context")
    assert evaluate([payload], Corpus([other], set()))["details"][0]["status"] == "context_or_kind_mismatch"


def test_support_counts_sources_not_repeated_nodes():
    corpus = training()
    corpus.occurrences = [o for o in corpus.occurrences if o.source_id == "one"] * 3
    assert not learn_rules(corpus, graph_mode=True)[0]


def test_priority_is_frozen_from_titles_and_reference_number():
    refs = [{"number": 8, "title": "The Cretan Aging Cohort"}, {"number": 3, "title": "Cognitive impairment"},
            {"number": 1, "title": "Unrelated report"}]
    assert [r["number"] for r in sorted(refs, key=source_priority)] == [8, 3, 1]
