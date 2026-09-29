"""Explicit read adapters for legacy statement consumers (never identity inference).

Variant A rows are typed directly: ``statement``/``entity``/``claim``/``action``
carry plain-text subject/predicate/object (with negation/epistemicStatus/context),
so the classic editor view is a thin projection of the structural rows.
"""
from __future__ import annotations
from knowledge_contracts.block_types import BlockType
from .pipeline import knowledge_map


def statements(blocks, resolve_refs=True):
    del resolve_refs
    graph = knowledge_map(blocks)
    names = {n["id"]: n["display_text"] for n in graph["nodes"]}
    result = []
    for block in blocks:
        if block["blockType"] not in (BlockType.STATEMENT, BlockType.ENTITY,
                                      BlockType.CLAIM, BlockType.ACTION):
            continue
        data = block["data"]
        if block["blockType"] == BlockType.CLAIM:
            subject, predicate, objective = (data.get("claimSubject", ""),
                                             data.get("claimPredicate", ""),
                                             data.get("claimObject", ""))
        else:
            subject, predicate, objective = (data.get("subject", ""),
                                             data.get("predicate", ""),
                                             data.get("object", ""))
        result.append({
            "id": block["instanceId"], "subject_text": subject,
            "predicate": predicate, "object_text": objective,
            "subject_type": "statement" if data.get("subjectStatementRef") else "concept",
            "object_type": "concept",
            "subject": subject, "object": objective,
            "subject_operation": data.get("subjectOperation"),
            "subject_statement_ref": data.get("subjectStatementRef"),
            "predicate_id": "", "sourceBlockId": block["instanceId"],
            "sourceBlockType": block["blockType"], "type": "EXTRACTED",
            "schemaVersion": 2, "status": "declared", "arity": 2,
            "negated": bool(data.get("negated", False)),
            "modality": data.get("epistemicStatus", "asserted"),
            "context": data.get("context", ""),
            "provenance": data.get("provenance"),
            "display_text": names.get(block["instanceId"], ""),
        })
    return result
