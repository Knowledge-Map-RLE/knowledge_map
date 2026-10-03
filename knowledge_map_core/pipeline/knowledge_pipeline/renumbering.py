"""Deterministic renumbering of batch-local DSL tags into a global sequence.

Each batched LLM call emits rows with local tags B1..Bn. The parser guarantees
uniqueness inside one call but not across calls, so every batch is renumbered
into a single global tag space with a running offset. References that the model
expressed against local tags are rewritten to the same global tags. The whole
procedure is pure and deterministic given the batch partition and model output.
"""
from __future__ import annotations

import re

from knowledge_contracts.block_dsl import DSL_FIELDS

_LOCAL_TAG_RE = re.compile(r"^B([1-9][0-9]*)$")

_JSON_FIELD_KINDS = {
    spec.json_field: spec.kind
    for fields in DSL_FIELDS.values()
    for spec in fields.values()
}


def _renumber_tag(local: str, mapping: dict[str, str]) -> str:
    return mapping.get(local, local)


def remap_local_tags(rows: list[dict], offset: int) -> list[dict]:
    """Rewrite each row's tag to ``B<offset + position>`` and fix its ref-kind fields.

    ``rows`` is the parse output of one batch (``data`` carries ``tag`` and DSL
    fields in JSON shape). Global tags are assigned by row position, so numbers
    stay consecutive across the article regardless of which local numbers the
    model chose, and references map through the same deterministic rule.
    """
    local_tags = [row["data"].get("tag") for row in rows if row["data"].get("tag")]
    mapping = {local: f"B{offset + position}" for position, local in enumerate(local_tags)}
    renumbered = []
    for row in rows:
        data = dict(row["data"])
        local_tag = data.get("tag")
        if local_tag:
            data["tag"] = _renumber_tag(local_tag, mapping)
        for key, kind in _JSON_FIELD_KINDS.items():
            if key not in data:
                continue
            if kind == "ref":
                data[key] = _renumber_tag(data[key], mapping)
            elif kind == "refs" and isinstance(data[key], list):
                data[key] = [_renumber_tag(item, mapping) for item in data[key]]
            elif kind == "ref_groups" and isinstance(data[key], list):
                data[key] = [[_renumber_tag(item, mapping) for item in group]
                             for group in data[key]]
        renumbered.append({**row, "tag": data.get("tag"), "data": data})
    return renumbered
