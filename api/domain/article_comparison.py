"""Детерминированное сравнение знаний схемы 6 без модельных вызовов."""
from __future__ import annotations

import math
from collections import Counter

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import normalize_map, VERSION as NORMALIZER_VERSION, DICTIONARY_SHA256, DICTIONARY

VERSION = "article-comparator-5"
RRF_CONSTANT = 60
MODES = ("text", "semantic", "hybrid")


def overlap(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a or b else 0.0


def compare_statements(a, b, left, right):
    predicate = a["predicate"] == b["predicate"]
    roles = overlap([fingerprint(r) for r in a["roles"]], [fingerprint(r) for r in b["roles"]])
    differences = []
    for name in ("predicate", "roles"):
        if a[name] != b[name]:
            differences.append({"field": name, "left": a[name], "right": b[name]})
    for name in ("negated", "scope", "attributes"):
        if a[name] != b[name]:
            differences.append({"field": name, "left": a[name], "right": b[name]})
    for name in ("kind", "action_status"):
        if left[name] != right[name]:
            differences.append({"field": name, "left": left[name], "right": right[name]})
    for name in ("quantifier", "modality", "time", "study_group", "conditions"):
        if a["scope"].get(name) != b["scope"].get(name):
            differences.append({"field": name, "left": a["scope"].get(name), "right": b["scope"].get(name)})
    dimensions_a = {x["unit"] for x in a["attributes"] if x["unit"] is not None}
    dimensions_b = {x["unit"] for x in b["attributes"] if x["unit"] is not None}
    if dimensions_a != dimensions_b:
        differences.append({"field": "units", "left": sorted(dimensions_a), "right": sorted(dimensions_b)})
    complete_roles = bool(a["roles"]) and a["roles"] == b["roles"]
    same_scope = a["scope"] == b["scope"] and not (a["unknown_context"] or b["unknown_context"])
    same_attrs = a["attributes"] == b["attributes"]
    contradiction = (predicate and complete_roles and same_scope and same_attrs
                     and a["negated"] != b["negated"] and left["kind"] == right["kind"]
                     and left["action_status"] == right["action_status"])
    equivalent = predicate and complete_roles and same_scope and not differences
    uncertain = a["unknown_context"] or b["unknown_context"]
    compatible = not differences and not uncertain
    score = (0.45 * predicate + 0.35 * roles + 0.10 * same_scope + 0.10 * same_attrs)
    if not predicate:
        score = min(score, 0.35)
    if not predicate and roles == 0:
        # Пустые одинаковые qualifiers не являются положительным свидетельством сходства.
        score = 0.0
    if contradiction:
        relation = "contradiction"
    elif equivalent:
        relation = "equivalent"
    elif predicate and roles > 0:
        relation = "partial"
    elif predicate:
        relation = "template"
    elif roles > 0:
        relation = "topical"
    else:
        relation = "insufficient"
    if uncertain:
        differences.append({"field": "unknown_context", "left": a["unknown_context"], "right": b["unknown_context"]})
    shared_attributes = [x for x in a["attributes"] if x in b["attributes"]] if predicate else []
    return {"left_statement": a["id"], "right_statement": b["id"], "score": round(score, 6),
            "shared_attributes": shared_attributes,
            "relation": relation, "compatible": compatible, "differences": differences}


def maximum_alignment(matrix):
    """Взвешенное взаимно однозначное сопоставление (венгерский алгоритм)."""
    if not matrix or not matrix[0]:
        return []
    flipped = len(matrix) > len(matrix[0])
    values = list(map(list, zip(*matrix))) if flipped else matrix
    n, m = len(values), len(values[0])
    u, v, p, way = [0.] * (n + 1), [0.] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minimum, used = [float("inf")] * (m + 1), [False] * (m + 1)
        while True:
            used[j0], i0, delta, j1 = True, p[j0], float("inf"), 0
            for j in range(1, m + 1):
                if not used[j]:
                    cost = -values[i0 - 1][j - 1] - u[i0] - v[j]
                    if cost < minimum[j]:
                        minimum[j], way[j] = cost, j0
                    if minimum[j] < delta:
                        delta, j1 = minimum[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0], j0 = p[j1], j1
    pairs = [(p[j] - 1, j - 1) for j in range(1, m + 1) if p[j]]
    return sorted((j, i) if flipped else (i, j) for i, j in pairs)


def compare_knowledge(left, right):
    matrix = [[compare_statements(a, b, left, right) for b in right["statements"]] for a in left["statements"]]
    matches = [matrix[i][j] for i, j in maximum_alignment([[c["score"] for c in row] for row in matrix])]
    relations = sorted({c["relation"] for c in matches})
    same_logic = left["logic"] == right["logic"]
    equivalent = (same_logic and len(left["statements"]) == len(right["statements"])
                  and all(c["relation"] == "equivalent" for c in matches))
    if "equivalent" in relations and not equivalent:
        relations = sorted((set(relations) - {"equivalent"}) | {"partial"})
    usable = [c for c in matches if c["relation"] in ("equivalent", "partial") and c["compatible"]]
    score = sum(c["score"] for c in matches) / max(len(left["statements"]), len(right["statements"]))
    template = overlap([s["predicate"] for s in left["statements"]], [s["predicate"] for s in right["statements"]])
    chain = overlap([fingerprint(g) for g in left.get("chain_signature", [])],
                    [fingerprint(g) for g in right.get("chain_signature", [])])
    return {"relations": ["equivalent"] if equivalent else relations, "statement_matches": matches,
            "logic_difference": None if same_logic else [left["logic"], right["logic"]],
            "coverage_left": len(usable) / len(left["statements"]), "coverage_right": len(usable) / len(right["statements"]),
            "semantic_score": round(score, 6), "template_score": round(template, 6),
            "dag_shape_score": chain, "dag_shape_note": "Three-level predicate/premise-group signatures; alternative groups retained; not factual equivalence"}


class BM25:
    def __init__(self, documents):
        self.documents = [Counter(d) for d in documents]
        self.lengths = [len(d) for d in documents]
        self.average = sum(self.lengths) / len(documents) if documents else 1
        df = Counter(t for doc in self.documents for t in doc)
        self.idf = {t: math.log(1 + (len(documents) - count + .5) / (count + .5)) for t, count in df.items()}

    def score(self, query, index):
        doc, length = self.documents[index], self.lengths[index]
        return sum(self.idf.get(t, 0) * doc.get(t, 0) * 2.2 /
                   (doc.get(t, 0) + 1.2 * (.25 + .75 * length / (self.average or 1))) for t in set(query))


def rank_pairs(pairs, key):
    ordered = sorted(pairs, key=lambda p: (-p[key], p["right_article_id"], p["right_knowledge_id"]))
    for i, pair in enumerate(ordered, 1):
        # Ранг соответствует фактическому месту в выдаче, включая стабильный порядок равных оценок.
        pair[key.replace("_score", "_rank")] = i if pair[key] > 0 else None
    return ordered


def compare_corpus(target, sources):
    require(bool(sources), "At least one explicit source run is required")
    left = normalize_map(target)
    right = [k for source in sources for k in normalize_map(source)]
    search = BM25([k["tokens"] for k in right])
    pairs = []
    for knowledge in left:
        row = []
        for index, candidate in enumerate(right):
            pair = {"left_knowledge_id": knowledge["id"], "right_knowledge_id": candidate["id"],
                    "right_article_id": candidate["article_id"], "right_run_id": candidate["run_id"],
                    "left_provenance": knowledge["provenance"], "right_provenance": candidate["provenance"],
                    "text_score": round(search.score(knowledge["tokens"], index), 8),
                    **compare_knowledge(knowledge, candidate)}
            pair["pair_id"] = fingerprint([target["run_id"], knowledge["id"], candidate["run_id"], candidate["id"]])
            row.append(pair)
        rank_pairs(row, "text_score")
        rank_pairs(row, "semantic_score")
        for pair in row:
            pair["hybrid_score"] = sum(1 / (RRF_CONSTANT + pair[f"{m}_rank"])
                                       for m in ("text", "semantic") if pair[f"{m}_rank"] is not None)
        rank_pairs(row, "hybrid_score")
        pairs.extend(row)
    return {"normalizer_version": NORMALIZER_VERSION, "dictionary_sha256": DICTIONARY_SHA256,
            "comparator_version": VERSION, "rrf_constant": RRF_CONSTANT, "modes": list(MODES),
            "target_knowledge_count": len(left), "source_knowledge_count": len(right), "pair_count": len(pairs),
            "pairs": pairs, "normalization": {"dictionary": DICTIONARY, "target": left, "sources": right},
            "model_calls": 0, "expert_validated": False, "needs_expert_review": True}
