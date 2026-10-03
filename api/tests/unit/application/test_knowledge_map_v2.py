import re
from pathlib import Path

import pytest

from knowledge_contracts.block_dsl import MAP_EVIDENCE_TYPES, MAP_NODE_TYPES
from knowledge_contracts.block_types import ALL_TYPES, BlockType
from knowledge_contracts.validation import ValidationError, validate_map
from knowledge_pipeline.dsl_rows import parse_dsl_rows
from knowledge_pipeline.knowledge_map_builder import _assign_ranks, build_knowledge_map
from knowledge_pipeline.knowledge_map_rules import (
    ALLOWED_TRANSITIONS, MAP_ANCHOR_FIELDS, MAP_ROW_ROLES,
)


def _blocks(dsl: str) -> list[dict]:
    units = sorted(set(re.findall(r"\bunit=(S[1-9][0-9]*)", dsl)),
                   key=lambda value: int(value[1:]))
    rows = parse_dsl_rows(dsl, units)
    return [
        {
            "instanceId": f"row-{row['tag']}",
            "schemaVersion": 2,
            "blockType": row["blockType"],
            "data": row["data"],
            "order": index,
        }
        for index, row in enumerate(rows)
    ]


def test_all_types_have_deterministic_roles_anchor_fields_and_explicit_transition_registry():
    evidence_types = set(MAP_EVIDENCE_TYPES)
    assert set(MAP_NODE_TYPES) | evidence_types == set(ALL_TYPES)
    assert set(MAP_NODE_TYPES).isdisjoint(evidence_types)
    assert set(MAP_ROW_ROLES) == set(MAP_ANCHOR_FIELDS) == set(ALL_TYPES)
    assert all(role in {"node", "evidence"} for role in MAP_ROW_ROLES.values())
    assert {kind for kind, role in MAP_ROW_ROLES.items() if role == "node"} == set(MAP_NODE_TYPES)
    assert set(ALLOWED_TRANSITIONS) == set(ALL_TYPES)
    assert all(not sources or target in MAP_NODE_TYPES
               for target, sources in ALLOWED_TRANSITIONS.items())
    assert all(source in MAP_NODE_TYPES for sources in ALLOWED_TRANSITIONS.values()
               for source in sources)
    blocks = []
    for index, block_type in enumerate(ALL_TYPES, start=1):
        tag = f"B{index}"
        data = {"tag": tag}
        if block_type == BlockType.RELATION:
            data.update(source="Source", target="Target", relationType="causes")
        blocks.append({
            "instanceId": f"row-{tag}", "schemaVersion": 2,
            "blockType": block_type, "data": data, "order": index,
        })
    graph = build_knowledge_map(blocks)
    assert {node["block_type"] for node in graph["nodes"]} == set(MAP_NODE_TYPES)
    assert {item["block_type"] for item in graph["evidence"]} == evidence_types

    row = parse_dsl_rows(
        "B T54 B1 | sub=scientist | pred=does | obj=work | "
        "req=[B2,B3] | anyreq=[[B4,B5],[B6]] | unit=S1",
        ["S1"],
    )[0]
    assert "requiresRefs" not in row["data"]
    assert "requiresAnyOfRefs" not in row["data"]


def test_untagged_metadata_is_preserved_as_evidence():
    blocks = [{
        "instanceId": "metadata-row", "schemaVersion": 2,
        "blockType": BlockType.METADATA, "data": {"title": "Article title"}, "order": 0,
    }, *_blocks("B T54 B1 | sub=scientist | pred=does | obj=work | unit=S1")]
    blocks[1]["order"] = 1

    graph = build_knowledge_map(blocks)

    assert len(graph["nodes"]) == 1
    assert graph["evidence"] == [{
        "id": "metadata-row", "block_type": BlockType.METADATA,
        "tag": None, "order": 0, "owner_id": None,
        "owner_resolution": "unattached", "display_text": "title: Article title",
    }]


def test_historical_requirement_fields_are_discarded_and_do_not_affect_new_map():
    blocks = _blocks("\n".join([
        "B T54 B1 | sub=scientist | pred=does | obj=first | req=[B2] | unit=S1",
        "B T54 B2 | sub=scientist | pred=does | obj=second | req=[B1] | unit=S1",
    ]))
    graph = build_knowledge_map(blocks)
    assert graph["schema_version"] == 3
    assert graph["edges"] == []

    blocks[0]["data"]["requiresRefs"] = ["B2"]
    blocks[1]["data"]["requiresAnyOfRefs"] = [["B1"]]
    rebuilt = build_knowledge_map(blocks)
    assert rebuilt["edges"] == []
    assert all("requiresRefs" not in node["properties"]
               and "requiresAnyOfRefs" not in node["properties"]
               for node in rebuilt["nodes"])


def test_research_route_uses_type_rules_and_typed_references_without_requirements():
    blocks = _blocks("\n".join([
        "B T7 B1 | hyp=Treatment improves memory | unit=S1",
        "B T11 B2 | design=randomized study | hyps=[B1] | unit=S1",
        "B T14 B3 | name=memory experiment | steps=[B4] | findings=[B5] | unit=S1",
        "B T56 B4 | name=measure memory | unit=S1",
        "B T57 B5 | param=memory score | exp=B3 | unit=S1",
        "B T42 B6 | claims=[treatment improves memory] | unit=S1",
    ]))
    graph = build_knowledge_map(blocks)
    by_tag = {node["tag"]: node for node in graph["nodes"]}
    pairs = {(edge["source"], edge["target"]) for edge in graph["edges"]}
    assert pairs == {
        (by_tag["B1"]["id"], by_tag["B2"]["id"]),
        (by_tag["B2"]["id"], by_tag["B3"]["id"]),
        (by_tag["B3"]["id"], by_tag["B4"]["id"]),
        (by_tag["B3"]["id"], by_tag["B5"]["id"]),
        (by_tag["B4"]["id"], by_tag["B5"]["id"]),
        (by_tag["B5"]["id"], by_tag["B6"]["id"]),
    }
    assert by_tag["B1"]["rank"] < by_tag["B2"]["rank"] < by_tag["B3"]["rank"]
    assert all(set(edge) == {"source", "target", "evidence"} for edge in graph["edges"])


def test_method_chain_stops_at_experiment_and_restarts_at_next_method():
    blocks = _blocks("\n".join([
        "B T21 B1 | meth=assay method | unit=S1",
        "B T57 B2 | param=memory score | unit=S1",
        "B T36 B3 | sum=memory score increased | unit=S1",
        "B T14 B4 | name=second experiment | unit=S1",
        "B T57 B5 | param=attention score | exp=B4 | unit=S1",
        "B T21 B6 | meth=follow-up method | unit=S1",
        "B T36 B7 | sum=attention score was stable | unit=S1",
    ]))
    graph = build_knowledge_map(blocks)
    by_tag = {node["tag"]: node["id"] for node in graph["nodes"]}
    pairs = {(edge["source"], edge["target"]) for edge in graph["edges"]}
    assert (by_tag["B1"], by_tag["B2"]) in pairs
    assert (by_tag["B1"], by_tag["B3"]) in pairs
    assert (by_tag["B1"], by_tag["B5"]) not in pairs
    assert (by_tag["B6"], by_tag["B7"]) in pairs


def test_goal_is_to_the_right_of_exactly_matching_action_even_if_mentioned_first():
    blocks = _blocks("\n".join([
        "B T2 B1 | sub=researcher | pred=achieves | obj=improve memory | unit=S1",
        "B T54 B2 | sub=researcher | pred=improves | obj=improve memory | unit=S1",
    ]))
    graph = build_knowledge_map(blocks)
    by_tag = {node["tag"]: node for node in graph["nodes"]}
    assert [(edge["source"], edge["target"]) for edge in graph["edges"]] == [
        (by_tag["B2"]["id"], by_tag["B1"]["id"]),
    ]
    assert by_tag["B2"]["rank"] < by_tag["B1"]["rank"]

    ambiguous_blocks = _blocks("\n".join([
        "B T2 B1 | sub=researcher | pred=achieves | obj=improve memory | unit=S1",
        "B T54 B2 | sub=researcher | pred=improves | obj=improve memory | unit=S1",
        "B T54 B3 | sub=team | pred=improves | obj=improve memory | unit=S1",
    ]))
    assert build_knowledge_map(ambiguous_blocks)["edges"] == []


def test_unique_exact_field_match_beats_nearest_predecessor_and_fallback_is_nearest():
    exact_blocks = _blocks("\n".join([
        "B T14 B1 | name=first experiment | outcome=[attention score] | unit=S1",
        "B T56 B2 | name=memory score | unit=S1",
        "B T14 B3 | name=nearest but unrelated experiment | unit=S1",
        "B T57 B4 | param=memory score | unit=S1",
    ]))
    exact_graph = build_knowledge_map(exact_blocks)
    exact_ids = {node["tag"]: node["id"] for node in exact_graph["nodes"]}
    exact_pairs = {(edge["source"], edge["target"]) for edge in exact_graph["edges"]}
    assert (exact_ids["B2"], exact_ids["B4"]) in exact_pairs
    assert (exact_ids["B3"], exact_ids["B4"]) not in exact_pairs

    fallback_blocks = _blocks("\n".join([
        "B T14 B1 | name=first experiment | outcome=[attention score] | unit=S1",
        "B T56 B2 | name=unrelated step | unit=S1",
        "B T14 B3 | name=nearest experiment | unit=S1",
        "B T57 B4 | param=memory score | unit=S1",
    ]))
    fallback_graph = build_knowledge_map(fallback_blocks)
    fallback_ids = {node["tag"]: node["id"] for node in fallback_graph["nodes"]}
    fallback_pairs = {(edge["source"], edge["target"])
                      for edge in fallback_graph["edges"]}
    assert (fallback_ids["B3"], fallback_ids["B4"]) in fallback_pairs
    assert (fallback_ids["B2"], fallback_ids["B4"]) not in fallback_pairs


def test_context_rows_are_evidence_and_unique_typed_refs_assign_owner():
    blocks = _blocks("\n".join([
        "B T57 B1 | param=memory score | pval=B2 | grp=[B3] | unit=S1",
        "B T27 B2 | p=0.04 | unit=S1",
        "B T55 B3 | name=control group | n=10 | unit=S1",
        "B T25 B4 | n=20 | unit=S1",
    ]))
    graph = build_knowledge_map(blocks)
    finding = next(node for node in graph["nodes"] if node["tag"] == "B1")
    evidence = {item["tag"]: item for item in graph["evidence"]}
    assert evidence["B2"]["owner_id"] == finding["id"]
    assert evidence["B3"]["owner_id"] == finding["id"]
    assert evidence["B4"]["owner_id"] is None
    assert evidence["B4"]["owner_resolution"] == "unattached"
    assert set(finding["evidence_refs"]) == {evidence["B2"]["id"], evidence["B3"]["id"]}


def test_experiment_group_refs_assign_context_evidence_to_the_experiment():
    blocks = _blocks("\n".join([
        "B T14 B1 | name=memory experiment | grp=[B2] | ctrl=[B3] | unit=S1",
        "B T55 B2 | name=treated group | n=10 | unit=S1",
        "B T55 B3 | name=control group | n=10 | unit=S1",
    ]))
    graph = build_knowledge_map(blocks)
    experiment = next(node for node in graph["nodes"] if node["tag"] == "B1")
    evidence = {item["tag"]: item for item in graph["evidence"]}
    assert evidence["B2"]["owner_id"] == experiment["id"]
    assert evidence["B3"]["owner_id"] == experiment["id"]
    assert set(experiment["evidence_refs"]) == {evidence["B2"]["id"], evidence["B3"]["id"]}


def test_ambiguous_evidence_owner_is_not_guessed_and_legacy_dependencies_are_ignored():
    blocks = _blocks("\n".join([
        "B T57 B1 | param=memory score | pval=B3 | unit=S1",
        "B T57 B2 | param=attention score | pval=B3 | unit=S1",
        "B T27 B3 | p=0.04 | unit=S1",
        "B T12 B4 | mats=sample | req=[B5] | unit=S1",
        "B T54 B5 | sub=scientist | pred=prepares | obj=sample | unit=S1",
    ]))
    graph = build_knowledge_map(blocks)
    evidence = {item["tag"]: item for item in graph["evidence"]}
    nodes = {item["tag"]: item for item in graph["nodes"]}
    assert evidence["B3"]["owner_id"] is None
    assert evidence["B3"]["owner_resolution"] == "ambiguous"
    assert "B4" in evidence and "B4" not in nodes
    assert graph["edges"] == []
    assert graph["reading_order"] == [block["instanceId"] for block in blocks]


def test_relation_and_temporal_rows_never_create_progression_edges():
    blocks = _blocks("\n".join([
        "B T54 B1 | sub=scientist | pred=collects | obj=data | unit=S1",
        "B T54 B2 | sub=scientist | pred=analyzes | obj=data | unit=S1",
        "B T58 B3 | srcRef=B2 | tgtRef=B1 | src=analysis | tgt=collection | rel=requires | unit=S1",
        "B T58 B4 | srcRef=B1 | tgtRef=B2 | src=collection | tgt=analysis | rel=causes | unit=S1",
        "B T59 B5 | earlier=collection | later=analysis | rel=precedes | unit=S1",
    ]))
    graph = build_knowledge_map(blocks)
    assert graph["edges"] == []
    assert {item["tag"] for item in graph["evidence"]} >= {"B3", "B4", "B5"}


@pytest.mark.parametrize(
    "left_label,source_text,expected_edges",
    [
        ("Alpha", "alpha", 0),
        ("Alpha Beta", "Alpha", 0),
        ("Alpha", "Alpha", 0),
    ],
)
def test_text_endpoint_resolution_is_exact_and_requires_unique_match(
    left_label: str, source_text: str, expected_edges: int,
):
    duplicate = "B T22 B3 | sub=Alpha | pred=is_a | obj=protein | unit=S1\n" if expected_edges == 0 and left_label == "Alpha" else ""
    blocks = _blocks("\n".join([
        f"B T22 B1 | sub={left_label} | pred=is_a | obj=protein | unit=S1",
        "B T22 B2 | sub=Beta | pred=is_a | obj=protein | unit=S1",
        duplicate.rstrip(),
        f"B T58 B4 | src={source_text} | tgt=Beta | rel=requires | unit=S1",
    ]))
    graph = build_knowledge_map(blocks)
    assert len(graph["edges"]) == expected_edges


def test_cycle_is_rejected_and_legacy_map_payload_remains_readable():
    cyclic_nodes = [
        {"id": "a", "order": 0, "tag": "B1"},
        {"id": "b", "order": 1, "tag": "B2"},
    ]
    with pytest.raises(ValidationError, match="cycle"):
        _assign_ranks(cyclic_nodes, [{"source": "a", "target": "b"},
                                    {"source": "b", "target": "a"}])

    plain_blocks = _blocks("\n".join([
        "B T54 B1 | sub=scientist | pred=collects | obj=data | unit=S1",
        "B T54 B2 | sub=scientist | pred=analyzes | obj=data | unit=S1",
    ]))
    v2_graph = build_knowledge_map(plain_blocks)
    v2_graph["schema_version"] = 2
    source_id, target_id = (block["instanceId"] for block in plain_blocks)
    group_id = f"all:{target_id}"
    v2_graph["requirement_groups"] = [{
        "id": group_id, "target": target_id, "mode": "all",
    }]
    v2_graph["edges"] = [{
        "source": source_id, "target": target_id, "group_id": group_id,
        "evidence": [{"structural_id": target_id, "field": "requiresRefs"}],
    }]
    next(node for node in v2_graph["nodes"] if node["id"] == target_id)["rank"] = 1
    validate_map(v2_graph, plain_blocks)
    legacy_graph = {
        "nodes": [{"id": row["instanceId"], "structural_id": row["instanceId"],
                   "block_type": row["blockType"], "display_text": "legacy action"}
                  for row in plain_blocks],
        "semantic_edges": [], "dependency_edges": [],
    }
    validate_map(legacy_graph, plain_blocks)


def test_first_two_gold_cases_follow_local_method_chains_without_invented_edges():
    root = Path(__file__).resolve().parents[4]
    cases = ["pmc10000452", "pmc10000584"]
    for case in cases:
        dsl_path = root / "eval" / "article_pipeline_gold" / "cases" / case / "gold.dsl"
        dsl = dsl_path.read_text(encoding="utf-8")
        blocks = _blocks(dsl)
        graph = build_knowledge_map(blocks)
        expected_method_edges = set()
        ordered = sorted(blocks, key=lambda block: block["order"])
        for index, block in enumerate(ordered):
            if block["blockType"] != BlockType.METHOD:
                continue
            for candidate in ordered[index + 1:]:
                if candidate["blockType"] in (BlockType.METHOD, BlockType.EXPERIMENT):
                    break
                if candidate["blockType"] in (BlockType.FINDING, BlockType.RESULT):
                    expected_method_edges.add((block["instanceId"], candidate["instanceId"]))
        actual_edges = {(edge["source"], edge["target"]) for edge in graph["edges"]}
        block_by_id = {block["instanceId"]: block for block in blocks}
        assert expected_method_edges <= actual_edges
        method_output_edges = {
            (edge["source"], edge["target"])
            for edge in graph["edges"]
            if block_by_id[edge["source"]]["blockType"] == BlockType.METHOD
            and block_by_id[edge["target"]]["blockType"] in (BlockType.FINDING, BlockType.RESULT)
        }
        assert method_output_edges == expected_method_edges
        allowed_pairs = {
            (source_type, target_type)
            for target_type, source_types in ALLOWED_TRANSITIONS.items()
            for source_type in source_types
        }
        assert all((
            block_by_id[source]["blockType"],
            block_by_id[target]["blockType"],
        ) in allowed_pairs for source, target in actual_edges)
        assert all(set(edge) == {"source", "target", "evidence"} for edge in graph["edges"])
        assert len(graph["nodes"]) + len(graph["evidence"]) == len(blocks)
