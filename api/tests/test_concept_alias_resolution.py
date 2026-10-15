from copy import deepcopy

import pytest

from domain.article_maps import ArticleMapError
from domain.concept_alias_resolution import derive_unambiguous_aliases, resolve_concept_label


def snapshot(concepts):
    return {
        "graph": {
            "schema_version": 6,
            "concepts": concepts,
            "knowledge": [{"semantic_frame": {"statements": [{"roles": [
                {"concept_id": concept["id"], "knowledge_id": None}
                for concept in concepts
            ]}]}}],
        }
    }


def test_explicit_unambiguous_alias_bridges_main_labels_across_maps():
    maps = [
        snapshot([{"id": "C1", "display_text": "glucose", "aliases": ["blood sugar"]}]),
        snapshot([{"id": "C2", "display_text": "blood sugar", "aliases": []}]),
    ]
    index = derive_unambiguous_aliases(maps)
    assert resolve_concept_label("glucose", index) == resolve_concept_label("blood sugar", index)
    assert index["merged_components"] == [["blood sugar", "glucose"]]


def test_ambiguous_alias_does_not_merge_distinct_concepts():
    maps = [
        snapshot([{"id": "C1", "display_text": "control group", "aliases": ["control"]}]),
        snapshot([{"id": "C2", "display_text": "control variable", "aliases": ["control"]}]),
        snapshot([{"id": "C3", "display_text": "control", "aliases": []}]),
    ]
    index = derive_unambiguous_aliases(maps)
    assert index["ambiguous_aliases"]["control"] == ["control group", "control variable"]
    assert len({resolve_concept_label(value, index) for value in
                ("control", "control group", "control variable")}) == 3


def test_unused_concept_alias_does_not_create_a_cross_map_bridge():
    one = snapshot([{"id": "C1", "display_text": "glucose", "aliases": ["blood sugar"]}])
    one["graph"]["knowledge"][0]["semantic_frame"]["statements"][0]["roles"] = []
    two = snapshot([{"id": "C2", "display_text": "blood sugar", "aliases": []}])
    index = derive_unambiguous_aliases([one, two])
    assert resolve_concept_label("glucose", index) != resolve_concept_label("blood sugar", index)


def test_unknown_concept_reference_fails_closed():
    item = snapshot([{"id": "C1", "display_text": "glucose", "aliases": []}])
    item["graph"]["knowledge"][0]["semantic_frame"]["statements"][0]["roles"][0]["concept_id"] = "missing"
    with pytest.raises(ArticleMapError):
        derive_unambiguous_aliases([item])


def test_inputs_are_not_mutated():
    maps = [snapshot([{"id": "C1", "display_text": "glucose", "aliases": ["blood sugar"]}]),
            snapshot([{"id": "C2", "display_text": "blood sugar", "aliases": []}])]
    before = deepcopy(maps)
    derive_unambiguous_aliases(maps)
    assert maps == before
