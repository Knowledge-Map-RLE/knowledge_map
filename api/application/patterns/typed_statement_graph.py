"""Typed assertion graphs: identity is a reference, display labels are not keys."""
from __future__ import annotations
import json

def typed_statement_graph(doc_id, statements, predicate_mode="raw", max_nodes=None):
    from .statement_graph import normalize_predicate
    nodes, edges, texts, raw = {}, [], {}, []
    for row in statements:
        data = row.get("semantic_data")
        if isinstance(data, str):
            data = json.loads(data)
        if not data:
            raise ValueError("Canonical pattern rows require semantic_data")
        entity_id = row["uid"]
        predicate = data.get("predicate")
        if predicate is None:
            nodes[entity_id] = "concept"
            texts[entity_id] = data["label"]
            continue
        nodes[entity_id] = "|".join(("ST", normalize_predicate(predicate["label"],predicate_mode),
            str(predicate["arity"]), str(data["negated"]), data["modality"]))
        texts[entity_id] = row.get("display_text") or predicate["label"]
        for role in ("subject","object"):
            term = data[role]
            if term is None:
                continue
            if term["kind"] == "literal":
                target = entity_id + ":" + role
                label = "literal|" + term.get("unit","")
                texts[target] = term["value"]
            else:
                target = term["id"]
                label = term["kind"]
            nodes.setdefault(target,label)
            edges.append({"from":entity_id,"to":target,"label":role})
        raw.append({"uid":entity_id,"predicate":predicate["label"],"semantic_data":data})
    original_count = len(nodes)
    if max_nodes and len(nodes) > max_nodes:
        degrees = dict.fromkeys(nodes,0)
        for edge in edges:
            degrees[edge["from"]] += 1
            degrees[edge["to"]] += 1
        keep = set(sorted(nodes,key=lambda n:(-degrees[n],n))[:max_nodes])
        nodes = {n:label for n,label in nodes.items() if n in keep}
        edges = [e for e in edges if e["from"] in keep and e["to"] in keep]
    return {"id":doc_id,"nodes":[{"id":n,"label":label} for n,label in nodes.items()],
        "edges":edges,"node_text":texts,"raw":raw,"count":len(raw),
        "coverage":{"total_nodes":original_count,"included_nodes":len(nodes)}}
