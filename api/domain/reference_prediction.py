"""Чистые модели и символьный прогноз по самостоятельным знаниям схемы 5."""
from __future__ import annotations

import itertools
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Iterable

from domain.article_maps import fingerprint, require

VERSION = "1.2"
PREDICATE_ALIASES = {
    "is associated with": "associated_with", "was associated with": "associated_with",
    "are associated with": "associated_with", "were associated with": "associated_with",
    "correlates with": "correlated_with", "is correlated with": "correlated_with",
    "is a": "is_a", "is an": "is_a",
    "increases": "increases", "increased": "increases",
    "decreases": "decreases", "decreased": "decreases",
}


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def normalized_value(value):
    if isinstance(value, str):
        return normalize(value)
    if isinstance(value, list):
        return [normalized_value(v) for v in value]
    if isinstance(value, dict):
        return {k: normalized_value(v) for k, v in sorted(value.items())}
    return value


@dataclass(frozen=True)
class Atom:
    predicate: str
    kind: str
    roles: tuple[tuple[str, str], ...]
    scope: str
    negated: bool

    @property
    def key(self) -> str:
        return fingerprint(asdict(self))

    @property
    def core(self) -> str:
        return fingerprint({"predicate": self.predicate, "roles": self.roles})


@dataclass(frozen=True)
class Occurrence:
    source_id: str
    node_id: str
    display_text: str
    provenance: dict
    atom: Atom


@dataclass
class Corpus:
    occurrences: list[Occurrence]
    edges: set[tuple[tuple[str, str], tuple[str, str]]]
    diagnostics: dict = field(default_factory=dict)

    def assert_isolated(self, target_ids: set[str]) -> None:
        require(not ({o.source_id for o in self.occurrences} & target_ids),
                "Target article leaked into the prediction corpus")


def fit_aliases(graphs: Iterable[dict]) -> dict[str, str]:
    """Объединяет только явно объявленные эквивалентности обучающих источников."""
    parent = {}
    records = []
    for graph in graphs:
        used = {role["concept_id"] for node in graph["nodes"] for role in node["semantic"]["roles"]
                if role["concept_id"] is not None}
        records.extend(concept for concept in graph["concepts"] if concept["id"] in used)
    main_labels = {normalize(c["display_text"]) for c in records}
    alias_claims = defaultdict(set)
    for concept in records:
        for alias in concept["aliases"]:
            alias_claims[normalize(alias)].add(normalize(concept["display_text"]))

    def find(x):
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    for label in sorted(main_labels):
        find(label)
    for alias, labels in sorted(alias_claims.items()):
        # Общая неоднозначная аббревиатура сама по себе не делает понятия одинаковыми.
        if len(labels) == 1 and alias in main_labels:
            root_a, root_b = find(next(iter(labels))), find(alias)
            parent[max(root_a, root_b)] = min(root_a, root_b)
    result = {name: find(name) for name in sorted(main_labels)}
    for alias, labels in sorted(alias_claims.items()):
        if len(labels) == 1:
            result[alias] = find(next(iter(labels)))
    return result


def canonicalize(source_id: str, graph: dict, aliases: dict[str, str]) -> Corpus:
    """Проекция готовой карты: не извлекает текст и не создаёт структурных строк."""
    require(graph.get("schema_version") == 5, "Prediction requires direct knowledge-map schema 5")
    concepts = {c["id"]: c for c in graph["concepts"]}
    nodes = {n["id"]: n for n in graph["nodes"]}
    occurrences, unresolved = [], 0
    for node in graph["nodes"]:
        sem = node["semantic"]
        roles = []
        for role in sem["roles"]:
            if role["concept_id"] is not None:
                term = normalize(concepts[role["concept_id"]]["display_text"])
                term = aliases.get(term, term)
            else:
                # Ссылку на знание сохраняем отдельным типом, не подменяем понятием.
                term = "knowledge:" + normalize(nodes[role["node_id"]]["display_text"])
                unresolved += 1
            roles.append((normalize(role["role"]), term))
        predicate = normalize(sem["predicate"])
        qualifiers = sorted((normalized_value(a) for a in sem["qualifiers"]["attributes"]),
                            key=lambda a: json.dumps(a, sort_keys=True))
        scope = json.dumps({"quantifier": normalized_value(sem["quantifier"]),
                            "modality": normalized_value(sem["modality"]),
                            "conditions": sorted(normalized_value(sem["conditions"])),
                            "temporal_context": normalized_value(sem["temporal_context"]),
                            "qualifiers": qualifiers}, sort_keys=True, ensure_ascii=False)
        past_without_time = sem["temporal_context"] is None and (
            predicate.startswith(("was ", "were ")) or predicate in {"increased", "decreased"})
        if predicate in {"is", "are"} and any(role == "class" for role, _ in roles):
            canonical_predicate = "is_a"
        else:
            canonical_predicate = predicate if past_without_time else PREDICATE_ALIASES.get(predicate, predicate)
        atom = Atom(canonical_predicate, node["kind"],
                    tuple(sorted(roles)), scope, sem["negated"])
        occurrences.append(Occurrence(source_id, node["id"], node["display_text"],
                                      node["provenance"], atom))
    edges = {((source_id, e["source"]), (source_id, e["target"])) for e in graph["edges"]}
    return Corpus(occurrences, edges, {"knowledge_role_references": unresolved,
                                     "unregistered_predicates": sorted({o.atom.predicate for o in occurrences
                                                                       if o.atom.predicate not in PREDICATE_ALIASES.values()})})


def merge_corpora(corpora: Iterable[Corpus]) -> Corpus:
    corpora = list(corpora)
    return Corpus([o for c in corpora for o in c.occurrences],
                  set().union(*(c.edges for c in corpora)),
                  {"sources": [c.diagnostics for c in corpora]})


def _constant(term: str) -> bool:
    # Числа и ссылки на знания не обобщаются в свободные участники.
    return bool(re.search(r"\d", term)) or term.startswith("knowledge:")


def _template(premises: tuple[Occurrence, ...], head: Occurrence, edges, graph_mode):
    variants = []
    for ordered in itertools.permutations(premises):
        variables = {}

        def abstract(atom, allow_new):
            roles = []
            for role, term in atom.roles:
                if _constant(term):
                    mapped = "=" + term
                else:
                    if term not in variables:
                        if not allow_new:
                            return None
                        variables[term] = "$" + str(len(variables))
                    mapped = variables[term]
                roles.append((role, mapped))
            return Atom(atom.predicate, atom.kind, tuple(roles), atom.scope, atom.negated)

        body = tuple(abstract(o.atom, True) for o in ordered)
        conclusion = abstract(head.atom, False)
        if conclusion is None:
            continue
        internal = tuple((i, j) for i, a in enumerate(ordered) for j, b in enumerate(ordered)
                         if graph_mode and ((a.source_id, a.node_id), (b.source_id, b.node_id)) in edges)
        value = {"body": [asdict(a) for a in body], "head": asdict(conclusion),
                 "body_edges": internal, "mode": "graph" if graph_mode else "semantic"}
        variants.append((json.dumps(value, sort_keys=True), body, conclusion, internal, ordered))
    return min(variants, key=lambda v: v[0]) if variants else None


@dataclass
class Rule:
    id: str
    body: tuple[Atom, ...]
    head: Atom
    body_edges: tuple[tuple[int, int], ...]
    support_sources: set[str]
    examples: list[dict]
    mode: str

    def to_dict(self):
        return {"id": self.id, "body": [asdict(a) for a in self.body], "head": asdict(self.head),
                "body_edges": list(self.body_edges), "support_sources": sorted(self.support_sources),
                "support": len(self.support_sources), "examples": self.examples,
                "mode": self.mode, "status": "statistical_hypothesis"}


def learn_rules(corpus: Corpus, *, graph_mode: bool, min_support: int = 2,
                max_premises: int = 3, max_neighbors: int = 12) -> tuple[list[Rule], dict]:
    require(1 <= max_premises <= 3 and min_support >= 2, "Invalid symbolic learner limits")
    by_source = defaultdict(list)
    incoming = defaultdict(set)
    for occurrence in corpus.occurrences:
        by_source[occurrence.source_id].append(occurrence)
    for a, b in corpus.edges:
        incoming[b].add(a)
    grouped, skipped = {}, 0
    for source_id, occurrences in sorted(by_source.items()):
        for head in sorted(occurrences, key=lambda o: o.node_id):
            if graph_mode:
                parents = incoming[(source_id, head.node_id)]
                neighbors = tuple(o for o in occurrences if (o.source_id, o.node_id) in parents)
                # Не выдаём произвольное подмножество обязательных входов за полное основание.
                bodies = [neighbors] if 1 <= len(neighbors) <= max_premises else []
                skipped += int(len(neighbors) > max_premises)
            else:
                terms = {term for _, term in head.atom.roles if not _constant(term)}
                neighbors = sorted((o for o in occurrences if o.node_id != head.node_id
                                    and terms & {term for _, term in o.atom.roles}), key=lambda o: o.node_id)
                skipped += int(len(neighbors) > max_neighbors)
                neighbors = neighbors[:max_neighbors]
                bodies = itertools.chain.from_iterable(itertools.combinations(neighbors, count)
                                                        for count in range(1, min(max_premises, len(neighbors)) + 1))
            for premises in bodies:
                if any(o.atom.key == head.atom.key for o in premises):
                    continue
                variant = _template(tuple(premises), head, corpus.edges, graph_mode)
                if variant is None:
                    continue
                key, body, conclusion, internal, ordered = variant
                rule = grouped.setdefault(key, Rule(fingerprint(key), body, conclusion, internal,
                                                    set(), [], "graph" if graph_mode else "semantic"))
                rule.support_sources.add(source_id)
                if len(rule.examples) < 3:
                    rule.examples.append({"source_id": source_id, "premises": [o.node_id for o in ordered],
                                          "head": head.node_id})
    rules = sorted((r for r in grouped.values() if len(r.support_sources) >= min_support),
                   key=lambda r: (-len(r.support_sources), len(r.body), r.id))
    return rules, {"candidate_templates": len(grouped), "accepted_rules": len(rules),
                   "bounded_or_unsupported_neighborhoods": skipped, "min_support": min_support,
                   "max_premises": max_premises, "max_neighbors": max_neighbors}


def _bind(template: Atom, candidate: Atom, bindings: dict) -> dict | None:
    if (template.predicate, template.kind, template.scope, template.negated) != (
            candidate.predicate, candidate.kind, candidate.scope, candidate.negated):
        return None
    if [r for r, _ in template.roles] != [r for r, _ in candidate.roles]:
        return None
    bound = dict(bindings)
    for (_, variable), (_, term) in zip(template.roles, candidate.roles):
        if variable.startswith("="):
            if variable[1:] != term:
                return None
        elif variable in bound:
            if bound[variable] != term:
                return None
        else:
            bound[variable] = term
    return bound


def predict(corpus: Corpus, rules: list[Rule], *, limit: int = 20,
            max_matches_per_rule: int = 1000) -> tuple[list[dict], dict]:
    known = {o.atom.key for o in corpus.occurrences}
    index = defaultdict(list)
    for o in sorted(corpus.occurrences, key=lambda o: (o.source_id, o.node_id)):
        index[(o.atom.predicate, o.atom.kind, o.atom.scope, o.atom.negated)].append(o)
    candidates, bounded = {}, 0
    for rule in rules:
        matches = 0

        def visit(position, bindings, premises):
            nonlocal matches, bounded
            if matches >= max_matches_per_rule:
                bounded += 1
                return
            if position == len(rule.body):
                matches += 1
                if any(((premises[a].source_id, premises[a].node_id),
                        (premises[b].source_id, premises[b].node_id)) not in corpus.edges
                       for a, b in rule.body_edges):
                    return
                atom = Atom(rule.head.predicate, rule.head.kind,
                            tuple(sorted((role, term[1:] if term.startswith("=") else bindings[term])
                                         for role, term in rule.head.roles)), rule.head.scope, rule.head.negated)
                if atom.key in known:
                    return
                item = {"id": atom.key, "atom": asdict(atom), "status": "statistical_hypothesis",
                        "rule_id": rule.id, "support": len(rule.support_sources),
                        "support_sources": sorted(rule.support_sources),
                        "premises": [{"source_id": o.source_id, "node_id": o.node_id,
                                      "display_text": o.display_text, "provenance": o.provenance}
                                     for o in premises]}
                existing = candidates.get(atom.key)
                if existing is None or item["support"] > existing["support"]:
                    candidates[atom.key] = item
                return
            template = rule.body[position]
            for candidate in index[(template.predicate, template.kind, template.scope, template.negated)]:
                if candidate in premises:
                    continue
                bound = _bind(template, candidate.atom, bindings)
                if bound is not None:
                    visit(position + 1, bound, [*premises, candidate])
                if matches >= max_matches_per_rule:
                    break

        visit(0, {}, [])
    ranked = sorted(candidates.values(), key=lambda p: (-p["support"], len(p["premises"]), p["id"]))
    return ranked[:limit], {"novel_candidates": len(ranked), "returned": min(limit, len(ranked)),
                            "bounded_matches": bounded, "max_matches_per_rule": max_matches_per_rule}


def evaluate(predictions: list[dict], target: Corpus) -> dict:
    exact, cores = defaultdict(list), defaultdict(list)
    for o in target.occurrences:
        exact[o.atom.key].append(o)
        cores[o.atom.core].append(o)
    results = []
    for prediction in predictions:
        payload = prediction["atom"]
        atom = Atom(payload["predicate"], payload["kind"], tuple(tuple(r) for r in payload["roles"]),
                    payload["scope"], payload["negated"])
        matches = exact.get(atom.key, [])
        related = cores.get(atom.core, [])
        compatible = [o for o in related if o.atom.scope == atom.scope and o.atom.kind == atom.kind]
        if matches:
            status = "matched"
        elif any(o.atom.negated != atom.negated for o in compatible):
            status = "explicit_contradiction"
        elif related:
            status = "context_or_kind_mismatch"
        else:
            status = "not_confirmed_by_target"
        results.append({"prediction_id": prediction["id"], "status": status,
                        "target_nodes": [o.node_id for o in (matches or related)]})
    matched = sum(r["status"] == "matched" for r in results)
    statuses = {status: sum(r["status"] == status for r in results) for status in (
        "matched", "explicit_contradiction", "context_or_kind_mismatch", "not_confirmed_by_target")}
    matched_target = len({prediction["id"] for prediction in predictions if prediction["id"] in exact})
    return {"predictions": len(results), "matched": matched,
            "match_fraction": matched / len(results) if results else None,
            "status_counts": statuses, "unique_target_atoms": len(exact), "matched_target_atoms": matched_target,
            "target_coverage": matched_target / len(exact) if exact else None,
            "scientific_accuracy": "requires_review", "details": results}


def source_priority(reference: dict) -> tuple[int, int]:
    title = normalize(reference.get("title") or reference.get("citation") or "")
    citation = normalize(reference.get("citation") or title)
    cohort_authors = sum(name in citation for name in ("basta", "simos", "vgontzas"))
    if "cretan aging cohort" in title or "cretan ageing cohort" in title or cohort_authors >= 2:
        group = 0
    elif any(term in title for term in ("cognitiv", "dementia", "alzheimer", "longitudinal", "heliad")):
        group = 1
    else:
        group = 2
    return group, reference["number"]
