"""Проверки глубины знаний, отдельных ролей и достоверного контракта зависимостей."""
import copy
import json

import pytest
from jsonschema import Draft202012Validator

from domain.article_maps import ArticleMapError, prepare_source
from domain.knowledge_map import apply_dependency_review, dependency_review_view, knowledge_text_keys, model_contract, parse_knowledge_map, validate_knowledge_map
from domain.knowledge_map_schema import dependency_review_json_schema, extraction_map_json_schema, knowledge_map_json_schema

TEXT = ("# Example\n\nThe method averages two readings. The study applied this method to baseline readings. "
        "The resulting mean was 20. The authors used this result to conclude Q, subject to limitation L. "
        "Some results may not generalize beyond six months.\n\n## References\n\nIgnored citation.")


def knowledge_node(identifier, text, kind="assertion", concept="C1"):
    return {"id": identifier, "kind": kind, "display_text": text, "aliases": [],
            "semantic": {"predicate": "states", "roles": [
                {"role": "subject", "concept_id": concept, "node_id": None}],
                "inputs": [], "quantifier": None, "modality": None, "negated": False,
                "conditions": [], "temporal_context": None, "qualifiers": {"attributes": []}},
            "provenance": {"unit_ids": ["U2"]}}


def knowledge_graph():
    return {"schema_version": 5, "concepts": [
        {"id": "C1", "display_text": "Study", "aliases": ["Investigation"], "provenance": {"unit_ids": ["U2"]}}],
        "nodes": [knowledge_node("M", "The method averages two readings", "method"),
                  knowledge_node("O", "The study applied the averaging method to baseline readings", "operation"),
                  knowledge_node("R", "The resulting mean was 20", "result"),
                  knowledge_node("Q", "The authors concluded Q, subject to limitation L", "conclusion")],
        "edges": []}


def review_dependencies(nodes=None):
    return {"dependencies": [reviewed_input(parent, child, usage, reason, nodes)
        for parent, child, usage, reason in [
            ("M", "O", "method", "The reported operation applies the stated averaging method."),
            ("O", "R", "result", "The source reports this mean as the result of the operation."),
            ("R", "Q", "evidence", "The authors use the reported mean to substantiate the qualified conclusion.")]]}


def reviewed_input(parent, child, usage="evidence", reason="The source uses this knowledge.", nodes=None):
    keys = knowledge_text_keys(nodes or knowledge_graph()["nodes"])
    return {"source": keys[parent], "target": keys[child], "usage": usage, "reason": reason, "unit_ids": ["U2"]}


def target_key(identifier, nodes=None):
    return knowledge_text_keys(nodes or knowledge_graph()["nodes"])[identifier]


def reference(identifier, nodes=None):
    node = next(n for n in (nodes or knowledge_graph()["nodes"]) if n["id"] == identifier)
    return {"node_id": node["id"], "display_text": node["display_text"]}


def validated():
    return validate_knowledge_map(knowledge_graph(), prepare_source("article", TEXT))


def test_roles_are_not_edges_and_dictionary_is_not_visible_inventory():
    graph = validated()
    assert graph["edges"] == []
    assert [n["rank"] for n in graph["nodes"]] == [0, 0, 0, 0]
    assert graph["analysis"]["depth"] == 1
    assert "C1" not in graph["reading_order"]
    assert graph["concepts"][0]["provenance"]["source_spans"]


def test_unused_grounded_dictionary_entry_is_diagnostic_and_not_a_dag_node():
    value = knowledge_graph()
    value["concepts"].append({"id": "C2", "display_text": "Baseline readings", "aliases": [],
                              "provenance": {"unit_ids": ["U2"]}})
    graph = validate_knowledge_map(value, prepare_source("article", TEXT))
    assert graph["analysis"]["unused_concept_ids"] == ["C2"]
    assert "C2" not in graph["reading_order"] and not graph["edges"]
    value["concepts"][-1]["provenance"]["unit_ids"] = ["missing"]
    with pytest.raises(ArticleMapError):
        validate_knowledge_map(value, prepare_source("article", TEXT))


def test_operation_result_and_conclusion_form_four_layers_without_inventing_nodes():
    source = prepare_source("article", TEXT)
    before = validated()
    after = apply_dependency_review(json.dumps(review_dependencies()), before, source)
    assert [n["rank"] for n in after["nodes"]] == [0, 1, 2, 3]
    assert after["analysis"] == {"depth": 4, "layer_counts": {"0": 1, "1": 1, "2": 1, "3": 1},
                                 "knowledge_input_count": 3, "concept_count": 1, "operation_count": 1}
    assert [n["display_text"] for n in after["nodes"]] == [n["display_text"] for n in before["nodes"]]
    assert after["concepts"] == before["concepts"]
    assert before["edges"] == []
    assert validate_knowledge_map(model_contract(after), source) == after


def test_multiple_inputs_and_existing_edges_are_reviewed_as_complete_set():
    source = prepare_source("article", TEXT)
    extracted = knowledge_graph()
    extracted["nodes"].append(knowledge_node("B", "The averaging operation used baseline readings", "observation"))
    review = review_dependencies(extracted["nodes"])
    review["dependencies"].append(reviewed_input("B", "O", "data",
        "The source identifies baseline readings as the operation's input data.", extracted["nodes"]))
    graph = apply_dependency_review(json.dumps(review), validate_knowledge_map(extracted, source), source)
    assert len(next(n for n in graph["nodes"] if n["id"] == "O")["semantic"]["inputs"]) == 2
    replacement = apply_dependency_review(json.dumps({"dependencies": []}), graph, source)
    assert replacement["edges"] == []
    assert all(not n["semantic"]["inputs"] for n in replacement["nodes"])


def test_dependency_groups_preserve_future_inputs_and_combine_into_same_dag():
    source, graph = prepare_source("article", TEXT), validated()
    records = review_dependencies()["dependencies"]
    for child, record in (("Q", records[2]), ("O", records[0]), ("R", records[1])):
        graph = apply_dependency_review(json.dumps({"dependencies": [record]}), graph, source,
                                        target_keys=[target_key(child)])
    whole = apply_dependency_review(json.dumps(review_dependencies()), validated(), source)
    assert {(edge["source"], edge["target"]) for edge in graph["edges"]} == {
        (edge["source"], edge["target"]) for edge in whole["edges"]}
    assert {key: value for key, value in graph.items() if key != "edges"} == {
        key: value for key, value in whole.items() if key != "edges"}


def test_dependency_group_cannot_replace_inputs_or_emit_outside_target_scope():
    source, graph = prepare_source("article", TEXT), validated()
    record = review_dependencies()["dependencies"][0]
    raw = json.dumps({"dependencies": [record]})
    with pytest.raises(ArticleMapError, match="outside its batch"):
        apply_dependency_review(raw, graph, source, target_keys=[target_key("Q")])
    accepted = apply_dependency_review(raw, graph, source, target_keys=[target_key("O")])
    with pytest.raises(ArticleMapError, match="replace accepted"):
        apply_dependency_review('{"dependencies":[]}', accepted, source, target_keys=[target_key("O")])


def test_cycle_between_groups_is_rejected_without_changing_accepted_graph():
    source = prepare_source("article", TEXT)
    graph = apply_dependency_review(json.dumps(review_dependencies()), validated(), source)
    before = copy.deepcopy(graph)
    with pytest.raises(ArticleMapError, match="cycle"):
        apply_dependency_review(json.dumps({"dependencies": [reviewed_input("Q", "M")]}), graph,
                                source, target_keys=[target_key("M")])
    assert graph == before


@pytest.mark.parametrize("scope", [[], ["unknown"], ["T1", "T1"]])
def test_invalid_group_scope_is_rejected(scope):
    with pytest.raises(ArticleMapError):
        apply_dependency_review('{"dependencies":[]}', validated(), prepare_source("article", TEXT),
                                target_keys=scope)


def test_group_schema_limits_only_targets_and_keeps_all_sources():
    nodes = knowledge_graph()["nodes"]
    keys = knowledge_text_keys(nodes)
    schema = dependency_review_json_schema(nodes, [keys["Q"]])
    validator = Draft202012Validator(schema)
    validator.validate({"dependencies": [reviewed_input("M", "Q")]})
    assert not validator.is_valid({"dependencies": [reviewed_input("Q", "M")]})
    assert not validator.is_valid({"dependencies": [reviewed_input("Q", "Q")]})
    for source in ("M", "O", "R"):
        validator.validate({"dependencies": [reviewed_input(source, "Q")]})


def test_group_schema_forbids_all_self_loops_without_enum_explosion():
    nodes = [{"id": f"N{i}", "display_text": f"Claim {i:03d}"} for i in range(1, 237)]
    keys = list(knowledge_text_keys(nodes).values())
    schema = dependency_review_json_schema(nodes, keys[:40])
    validator = Draft202012Validator(schema)
    for target in keys[:40]:
        validator.validate({"dependencies": [{"target": target, "source": "T236", "usage": "data",
                                               "reason": "The target uses the source.", "unit_ids": ["U1"]}]})
        assert not validator.is_valid({"dependencies": [{"target": target, "source": target, "usage": "data",
                                                         "reason": "The target uses itself.", "unit_ids": ["U1"]}]})
    assert schema["$defs"]["usage"]["enum"] == sorted({"definition", "premise", "evidence", "method", "data", "condition", "result"})
    assert len(schema["$defs"]["input"]["anyOf"]) == 40
    assert len(json.dumps(schema).encode()) < 70000
    assert not any(f'"{name}"' in json.dumps(schema) for name in ("not", "if", "then", "allOf"))


def test_single_block_group_schema_requires_no_self_loop_or_placeholder():
    schema = dependency_review_json_schema([{"id": "N1", "display_text": "The observation was recorded"}], ["T1"])
    validator = Draft202012Validator(schema)
    validator.validate({"dependencies": []})
    assert not validator.is_valid({"dependencies": ["T1"]})


def test_group_schema_forbids_back_edges_to_existing_descendants():
    nodes = knowledge_graph()["nodes"]
    keys = knowledge_text_keys(nodes)
    prior = [reviewed_input("M", "O"), reviewed_input("O", "R")]
    validator = Draft202012Validator(dependency_review_json_schema(nodes, [keys["M"]], prior))
    for parent in ("M", "O", "R"):
        assert not validator.is_valid({"dependencies": [reviewed_input(parent, "M")]})
    validator.validate({"dependencies": [reviewed_input("Q", "M")]})


def test_feedback_in_participant_references_does_not_create_a_dependency_cycle():
    candidate = knowledge_graph()
    candidate["nodes"][0]["semantic"]["roles"].append({"role": "effect", "concept_id": None, "node_id": "O"})
    candidate["nodes"][1]["semantic"]["roles"].append({"role": "cause", "concept_id": None, "node_id": "M"})
    assert validate_knowledge_map(candidate, prepare_source("article", TEXT))["edges"] == []


def test_negation_quantifiers_modality_numbers_and_time_are_preserved():
    candidate = knowledge_graph()
    node = candidate["nodes"][-1]
    node["display_text"] = "Some results may not generalize beyond six months"
    node["semantic"].update(quantifier="some", modality="may", negated=True,
                            temporal_context="beyond six months", conditions=["within the study context"],
                            qualifiers={"attributes": [{"name": "duration", "value": 6, "unit": "months"},
                                                       {"name": "mean", "value": 20, "unit": None}]})
    graph = validate_knowledge_map(candidate, prepare_source("article", TEXT))
    assert graph["nodes"][-1]["semantic"] == node["semantic"]
    assert graph["concepts"][0]["aliases"] == ["Investigation"]


@pytest.mark.parametrize("mutation", [
    lambda g: g["nodes"][0].update(kind="concept"),
    lambda g: g["nodes"][0]["semantic"].update(predicate=None),
    lambda g: g["nodes"][0]["semantic"].update(qualifiers={"months": 6}),
    lambda g: g["nodes"][0]["semantic"].update(qualifiers={"attributes": [{"name": "months", "value": {}, "unit": None}]}),
    lambda g: g["nodes"][0]["semantic"].update(qualifiers={"attributes": [{"name": "months", "value": float("inf"), "unit": None}]}),
    lambda g: g["nodes"][0]["semantic"].update(qualifiers={"attributes": [{"name": "months", "value": 6, "unit": None}] * 2}),
    lambda g: g["nodes"][0]["semantic"]["roles"][0].update(concept_id="unknown"),
    lambda g: g["nodes"][0]["semantic"]["roles"][0].update(node_id="O"),
    lambda g: g["nodes"][0]["semantic"]["roles"][0].update(concept_id=None),
    lambda g: g["nodes"][0]["provenance"].update(unit_ids=["U999"]),
    lambda g: g["nodes"][1].update(display_text=g["nodes"][0]["display_text"]),
    lambda g: g["edges"].append({"source": "C1", "target": "M"}),
    lambda g: g["edges"].append({"source": "M", "target": "O"}),
])
def test_reject_invalid_knowledge_or_unjustified_edges(mutation):
    candidate = knowledge_graph()
    mutation(candidate)
    with pytest.raises(ArticleMapError):
        validate_knowledge_map(candidate, prepare_source("article", TEXT))


@pytest.mark.parametrize("mutation", [
    lambda r: r["dependencies"].append(reviewed_input("Q", "M")),
    lambda r: r["dependencies"][0].update(target="unknown"),
    lambda r: r["dependencies"][0].update(source="unknown"),
    lambda r: r["dependencies"][0].update(source="C1"),
    lambda r: r["dependencies"][0].update(source=target_key("O")),
    lambda r: r["dependencies"][0].pop("target"),
    lambda r: r["dependencies"].append({}),
    lambda r: r["dependencies"][0].update(source="T999"),
    lambda r: r["dependencies"][0].update(target_text_key="T999"),
    lambda r: r["dependencies"][0].update(unit_ids=["U999"]),
    lambda r: r["dependencies"][0].update(unit_ids=["U1"]),
    lambda r: r["dependencies"][0].update(reason=""),
    lambda r: r["dependencies"][0].update(usage="causes"),
    lambda r: r["dependencies"][0].update(usage="action"),
])
def test_reject_invalid_review_as_a_whole(mutation):
    review = review_dependencies()
    mutation(review)
    with pytest.raises(ArticleMapError):
        apply_dependency_review(json.dumps(review), validated(), prepare_source("article", TEXT))


@pytest.mark.parametrize("duplicate", ["pair", "json_key"])
def test_duplicate_pair_keys_are_rejected_without_repair(duplicate):
    first = json.dumps(reviewed_input("M", "O"))
    if duplicate == "pair":
        second = json.dumps(reviewed_input("M", "O", reason="The same pair described again."))
        raw = '{"dependencies":[' + first + ',' + second + ']}'
    else:
        repeated = first[:-1] + ',"target":' + json.dumps(target_key("O")) + '}'
        raw = '{"dependencies":[' + repeated + ']}'
    before = validated()
    with pytest.raises(ArticleMapError, match="Duplicate"):
        apply_dependency_review(raw, before, prepare_source("article", TEXT))
    assert before["edges"] == []


@pytest.mark.parametrize("count", [1, 2, 3])
def test_individual_measurements_feed_aggregate_without_mirrored_inputs(count):
    text = "# Studies\n\n" + " ".join(f"Study {i} measured {i + 10}." for i in range(count))
    text += " The review pooled these individual measurements."
    candidate = knowledge_graph()
    candidate["nodes"] = [knowledge_node(f"D{i}", f"Study {i} measured {i + 10}", "observation")
                          for i in range(count)]
    candidate["nodes"].append(knowledge_node("S", "The review pooled these individual measurements", "result"))
    source = prepare_source("article", text)
    before = validate_knowledge_map(candidate, source)
    keys = knowledge_text_keys(candidate["nodes"])
    review = {"dependencies": [{"source": keys[f"D{i}"], "target": keys["S"], "usage": "data",
         "reason": f"The pooled result uses the measurement from study {i}.", "unit_ids": ["U2"]}
         for i in range(count)]}
    result = apply_dependency_review(json.dumps(review), before, source)
    assert result["edges"] == [{"source": f"D{i}", "target": "S"} for i in range(count)]
    assert [node["rank"] for node in result["nodes"]] == [0] * count + [1]
    review["dependencies"].append({"source": keys["S"], "target": keys["D0"], "usage": "data",
         "reason": "The pooled result uses the measurement from study 0.", "unit_ids": ["U2"]})
    with pytest.raises(ArticleMapError, match="cycle"):
        apply_dependency_review(json.dumps(review), before, source)
    assert not before["edges"]


@pytest.mark.parametrize("wrapper", [[], {"outputs": []}, {"inputs": [], "outputs": []}])
def test_live_review_rejects_indexed_incoming_or_outgoing_contracts(wrapper):
    review = {"dependencies": {target_key("M"): wrapper}}
    assert not Draft202012Validator(dependency_review_json_schema(knowledge_graph()["nodes"])).is_valid(review)
    with pytest.raises(ArticleMapError, match="array"):
        apply_dependency_review(json.dumps(review), validated(), prepare_source("article", TEXT))


@pytest.mark.parametrize("raw", ['{"schema_version":5,', '```json\n{}\n```', '{"nodes":[],"nodes":[]}'])
def test_reject_incomplete_or_ambiguous_json(raw):
    with pytest.raises(ArticleMapError):
        parse_knowledge_map(raw, prepare_source("article", TEXT))


def test_supplied_schemas_match_domain_contracts():
    map_schema, review_schema = knowledge_map_json_schema(), dependency_review_json_schema(knowledge_graph()["nodes"])
    for schema in (map_schema, review_schema):
        Draft202012Validator.check_schema(schema)
    Draft202012Validator(map_schema).validate(knowledge_graph())
    Draft202012Validator(review_schema).validate(review_dependencies())
    candidate = knowledge_graph()
    candidate["nodes"][0]["semantic"]["predicate"] = None
    assert not Draft202012Validator(map_schema).is_valid(candidate)


def test_extraction_schema_excludes_dependencies_until_second_stage():
    validator = Draft202012Validator(extraction_map_json_schema())
    candidate = knowledge_graph()
    validator.validate(candidate)
    connected = model_contract(apply_dependency_review(json.dumps(review_dependencies()),
                                validate_knowledge_map(candidate, prepare_source("article", TEXT)),
                                prepare_source("article", TEXT)))
    assert not validator.is_valid(connected)
    Draft202012Validator(knowledge_map_json_schema()).validate(connected)


def test_current_schemas_are_closed_with_all_properties_required():
    def inspect(value):
        if isinstance(value, dict):
            if value.get("type") == "object":
                assert value["additionalProperties"] is False
                assert set(value["properties"]) == set(value["required"])
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)
    inspect(extraction_map_json_schema())
    inspect(dependency_review_json_schema(knowledge_graph()["nodes"]))


def test_bound_schema_requires_all_targets_and_restricts_usage_before_generation():
    validator = Draft202012Validator(dependency_review_json_schema(knowledge_graph()["nodes"]))
    review = review_dependencies()
    validator.validate(review)
    review["dependencies"][0]["usage"] = "action"
    assert not validator.is_valid(review)


@pytest.mark.parametrize("endpoint", ["source", "target"])
def test_strict_schema_rejects_node_identifiers_in_text_key_contract(endpoint):
    validator = Draft202012Validator(dependency_review_json_schema(knowledge_graph()["nodes"]))
    review = review_dependencies()
    review["dependencies"][0][endpoint] = "M"
    assert not validator.is_valid(review)
    review = review_dependencies()
    review["dependencies"][0].pop(endpoint)
    assert not validator.is_valid(review)


def test_directed_schema_rejects_unknown_keys_and_extra_payload_fields():
    validator = Draft202012Validator(dependency_review_json_schema(knowledge_graph()["nodes"]))
    review = review_dependencies()
    review["dependencies"][0]["invented"] = True
    assert not validator.is_valid(review)
    review = review_dependencies()
    review["unknown"] = []
    assert not validator.is_valid(review)


def test_dependency_evidence_can_include_additional_valid_article_context():
    source = prepare_source("article", TEXT.replace("\n\n## References",
        "\n\nThe study protocol specified the baseline readings used in the averaging operation.\n\n## References"))
    review = review_dependencies()
    review["dependencies"][0]["unit_ids"] = ["U2", "U3"]
    result = apply_dependency_review(json.dumps(review), validate_knowledge_map(knowledge_graph(), source), source)
    assert next(node for node in result["nodes"] if node["id"] == "O")["semantic"]["inputs"][0]["unit_ids"] == ["U2", "U3"]


def test_additional_article_context_cannot_replace_all_endpoint_anchors():
    source = prepare_source("article", TEXT.replace("\n\n## References",
        "\n\nThe study protocol specified the baseline readings used in the averaging operation.\n\n## References"))
    review = review_dependencies()
    review["dependencies"][0]["unit_ids"] = ["U3"]
    with pytest.raises(ArticleMapError, match="endpoint provenance"):
        apply_dependency_review(json.dumps(review), validate_knowledge_map(knowledge_graph(), source), source)


def test_text_keys_are_short_unique_and_independent_of_node_order():
    nodes = knowledge_graph()["nodes"]
    keys = knowledge_text_keys(nodes)
    assert keys == knowledge_text_keys(list(reversed(nodes)))
    assert len(set(keys.values())) == len(nodes)
    assert all(len(key) < 8 for key in keys.values())


def test_dependency_view_attaches_identity_keys_and_preserves_all_knowledge():
    before = validated()
    snapshot = copy.deepcopy(before)
    view = dependency_review_view(before)
    keys = knowledge_text_keys(before["nodes"])
    assert knowledge_text_keys(view["nodes"]) == {key: key for key in keys.values()}
    for original, working in zip(before["nodes"], view["nodes"]):
        assert working["id"] == keys[original["id"]]
        assert working["display_text"] == original["display_text"]
        assert working["aliases"] == original["aliases"]
        assert working["provenance"] == {"unit_ids": original["provenance"]["unit_ids"]}
        assert working["semantic"]["roles"][0]["concept_id"] == "C:" + original["semantic"]["roles"][0]["concept_id"]
        assert {k: v for k, v in working["semantic"].items() if k != "roles"} == {
            k: v for k, v in original["semantic"].items() if k != "roles"}
    assert before == snapshot
    validate_knowledge_map(view, prepare_source("article", TEXT))


def test_dependency_view_preserves_block_roles_and_roundtrips_edges_to_stored_ids():
    source = prepare_source("article", TEXT)
    candidate = knowledge_graph()
    candidate["nodes"][0]["semantic"]["roles"].append({"role": "operation", "concept_id": None, "node_id": "O"})
    original = validate_knowledge_map(candidate, source)
    working = validate_knowledge_map(dependency_review_view(original), source)
    keys = knowledge_text_keys(original["nodes"])
    assert working["nodes"][0]["semantic"]["roles"][-1]["node_id"] == keys["O"]
    raw = json.dumps(review_dependencies())
    stored_result = apply_dependency_review(raw, original, source)
    working_result = apply_dependency_review(raw, working, source)
    inverse = {key: identifier for identifier, key in keys.items()}
    assert stored_result["edges"] == [{"source": inverse[e["source"]], "target": inverse[e["target"]]}
                                     for e in working_result["edges"]]
    assert stored_result["nodes"][0]["id"] == "M"
    assert stored_result["nodes"][0]["semantic"]["roles"][-1]["node_id"] == "O"


def test_dependency_view_keeps_dictionary_and_knowledge_namespaces_disjoint():
    candidate = knowledge_graph()
    candidate["concepts"][0]["id"] = "T1"
    for node in candidate["nodes"]:
        node["semantic"]["roles"][0]["concept_id"] = "T1"
    working = validate_knowledge_map(dependency_review_view(validate_knowledge_map(
        candidate, prepare_source("article", TEXT))), prepare_source("article", TEXT))
    assert working["concepts"][0]["id"] == "C:T1"
    assert "T1" in {node["id"] for node in working["nodes"]}


def test_strict_dependency_schema_uses_shared_references_and_no_unsupported_composition():
    nodes = [{"id": f"N{index}", "display_text": f"Claim {index}"} for index in range(1, 501)]
    schema = dependency_review_json_schema(nodes)
    assert schema["properties"]["dependencies"] == {"type": "array", "items": {"$ref": "#/$defs/input"}}
    assert len(schema["$defs"]) == 2
    assert len(schema["$defs"]["source_reference"]["enum"]) == 500
    assert schema["$defs"]["input"]["properties"]["source"] == schema["$defs"]["input"]["properties"]["target"]
    assert len(json.dumps(schema).encode()) < 12000
    assert not any(f'"{keyword}"' in json.dumps(schema) for keyword in
                   ("allOf", "propertyNames", "minProperties", "patternProperties"))
    Draft202012Validator(schema).validate({"dependencies": []})
