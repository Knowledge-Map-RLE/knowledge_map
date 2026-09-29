import copy
import json
import re
import pytest
from knowledge_pipeline.pipeline import (
    ArticlePipeline, materialize_rows, source_revision, source_units, linguistic_profile,
)
from knowledge_pipeline.dsl_rows import parse_dsl_rows
from knowledge_pipeline.knowledge_map_builder import build_knowledge_map
from knowledge_pipeline.quality_metrics import evaluate_article_transformation
from knowledge_pipeline.caption_units import caption_unit_ids
from knowledge_contracts.validation import (ValidationError, validate_linguistic,
                                            validate_map, validate_structural)
from knowledge_pipeline.semantic_extraction import extract_structural_rows
from infrastructure.article_pipeline import SemanticGateway

TEXT = "Clusterin may inhibit inflammation. Aged mice do not show fibrosis."
TEXT_WITH_PVALUE = "Clusterin may inhibit inflammation. Aged mice do not show fibrosis (p = 0.014)."

DSL = "\n".join([
    "B T1 B1 | doi=10.1 | title=Clusterin regulates inflammaging | authors=[A, B] | year=2024 | unit=S1",
    "B T4 B2 | sub=Clusterin | pred=inhibits | obj=inflammaging | unit=S1",
    "B T22 B9 | sub=inflammaging | pred=is_a | obj=condition | unit=S1",
    "B T4 B4 | sub=aged mice | pred=show | obj=fibrosis | neg=true | unit=S2",
    "B T57 B5 | param=clusterin levels | dir=decreased | grp=[B2] | unit=S2",
    "B T58 B6 | src=Clusterin | tgt=inflammaging | srcRef=B2 | tgtRef=B9 | rel=supports | conf=medium | unit=S1",
    "B T59 B7 | earlier=step A | later=step B | unit=S2",
    "B T27 B8 | p=0.014 | unit=S2",
])

def document(text):
    spans = []
    start = 0
    for boundary in re.finditer(r"(?<!\d)[.!?]+", text):
        spans.append((start, boundary.end()))
        start = boundary.end()
    if start < len(text) or not spans:
        spans.append((start, len(text)))
    return {"text": text, "sentences": [
        {"idx": index, "start_char": start, "end_char": end,
         "tokens": [{"idx": i, "text": m.group(),
                     "start_char": start + m.start(), "end_char": start + m.end()}
                    for i, m in enumerate(re.finditer(r"\w+|[^\w\s]", text[start:end]))],
         "dependencies": [], "phrases": []}
        for index, (start, end) in enumerate(spans)]}

class FakeNLP:
    async def __call__(self, text):
        return document(text)

class FakeLLM:
    def __init__(self, dsl=DSL, calls=None):
        self.dsl, self.calls = dsl, calls
    async def __call__(self, system, user):
        if self.calls is not None:
            self.calls.append(user)
        assert "SOURCE_UNITS" in user and "text=" in user
        return self.dsl


@pytest.mark.asyncio
async def test_semantic_gateway_returns_raw_dsl_from_sse(monkeypatch):
    captured: dict = {}
    first_tokens: list[float] = []
    dsl = "B T4 B1 | sub=Clusterin | pred=inhibits | obj=inflammaging | unit=S1"
    events = [
        'data: {"choices":[{"delta":{"content":"' + dsl + '"},"finish_reason":null}]}',
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"completion_tokens":12}}',
        "data: [DONE]",
    ]

    class FakeResponse:
        status_code = 200

        async def aread(self):
            return b""

        async def aiter_lines(self):
            for event in events:
                yield event

    class FakeStreamContext:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *_):
            return False

    class FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        def stream(self, method, url, json):
            captured.update(method=method, url=url, body=json)
            return FakeStreamContext()

    monkeypatch.setattr("infrastructure.article_pipeline.httpx.AsyncClient", lambda **_: FakeHttpClient())
    gateway = SemanticGateway(on_first_token=first_tokens.append)
    assert await gateway("DSL only", "article") == dsl
    assert captured["method"] == "POST"
    assert captured["body"]["stream"] is True
    assert captured["body"]["max_completion_tokens"] == gateway.max_tokens
    assert "max_tokens" not in captured["body"]
    assert "reasoning_effort" not in captured["body"]
    assert captured["body"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert gateway.last_call["finish_reason"] == "stop"
    assert gateway.provider == "openai"
    assert gateway.last_call["reasoning_effort"] == "max"
    assert len(first_tokens) == 1
    assert gateway.last_call["time_to_first_token_seconds"] == first_tokens[0]


@pytest.mark.asyncio
async def test_semantic_gateway_reduces_output_budget_to_fit_context(monkeypatch):
    captured = {}
    dsl = "B T4 B1 | sub=Clusterin | pred=inhibits | obj=inflammation | unit=S1"
    events = [
        'data: {"choices":[{"delta":{"content":"' + dsl + '"},"finish_reason":null}]}',
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
        "data: [DONE]",
    ]

    class FakeResponse:
        status_code = 200

        async def aread(self):
            return b""

        async def aiter_lines(self):
            for event in events:
                yield event

    class FakeStreamContext:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *_):
            return False

    class FakeHttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        def stream(self, method, url, json):
            captured["body"] = json
            return FakeStreamContext()

    monkeypatch.setattr(
        "infrastructure.article_pipeline.httpx.AsyncClient",
        lambda **_: FakeHttpClient(),
    )
    gateway = SemanticGateway()
    gateway.context_length = 26000
    gateway.max_tokens = 3072

    system = "S" * 33849
    user = "U" * 7510
    assert await gateway(system, user) == dsl

    body = captured["body"]
    estimated_input_tokens = (
        len(json.dumps(body, ensure_ascii=False).encode("utf-8")) + 1024 + 1
    ) // 2
    assert 512 <= body["max_completion_tokens"] < gateway.max_tokens
    assert estimated_input_tokens + body["max_completion_tokens"] + 2048 <= gateway.context_length
    assert gateway.last_call["max_completion_tokens"] == body["max_completion_tokens"]

def build_blocks(dsl=DSL):
    source = source_revision("article", TEXT)
    profile = linguistic_profile(source, document(TEXT))
    rows = parse_dsl_rows(dsl, [u["id"] for u in source_units(profile, TEXT)])
    return source, profile, materialize_rows(rows, source, profile)

def tags(blocks):
    return {b["data"]["tag"]: b["instanceId"] for b in blocks}


def test_nested_importance_is_typed_action_on_atomic_statement():
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path
    from knowledge_pipeline.compat import statements
    from knowledge_pipeline.semantic_extraction import _row_validation_issues

    text = ("Identifying modifiable factors that may predict long-term cognitive "
            "decline is critical.")
    dsl = "\n".join([
        "B T4 B1 | sub=modifiable factors | pred=may_predict | "
        "obj=long-term cognitive decline | unit=S1",
        "B T4 B2 | sub=identifying modifiable factors | subop=identify_subjects | "
        "subref=B1 | pred=is | obj=critical | unit=S1",
    ])
    source = source_revision("nested", text)
    profile = linguistic_profile(source, document(text))
    rows = parse_dsl_rows(dsl, ["S1"])
    assert _row_validation_issues(rows) == []
    blocks = materialize_rows(rows, source, profile)
    by_tag = tags(blocks)
    assert blocks[1]["data"]["subjectStatementRef"] == by_tag["B1"]
    assert blocks[1]["data"]["subject"] == "identifying modifiable factors"
    graph = build_knowledge_map(blocks)
    assert graph["dependency_edges"] == []
    assert graph["semantic_edges"] == [{
        "source": by_tag["B1"], "target": by_tag["B2"],
        "relation": "subject_operation:identify_subjects", "relation_tag": "B2",
        "block": by_tag["B2"], "resolution": "ref",
    }]
    projected = statements(blocks)
    assert projected[1]["subject_type"] == "statement"
    assert projected[1]["subject_statement_ref"] == by_tag["B1"]
    assert projected[1]["subject_operation"] == "identify_subjects"

    root = Path(__file__).resolve().parents[4]
    module_spec = spec_from_file_location(
        "article_pipeline_live_nested_serializer", root / "eval" / "run_article_pipeline_live.py")
    serializer = module_from_spec(module_spec)
    module_spec.loader.exec_module(serializer)
    serialized = serializer._serialize_dsl(blocks)
    assert "subref=B1" in serialized
    assert by_tag["B1"] not in serialized
    assert parse_dsl_rows(serialized, ["S1"]) == rows


def test_nested_importance_cannot_hide_prediction_inside_sub():
    from knowledge_pipeline.semantic_extraction import _row_validation_issues

    rows = parse_dsl_rows(
        "B T4 B1 | sub=Identifying modifiable factors that may predict decline "
        "| pred=is | obj=critical | unit=S1", ["S1"],
    )
    issues = _row_validation_issues(rows)
    assert len(issues) == 1
    assert "sub= hides a relative assertion" in issues[0][1]


@pytest.mark.parametrize("fields,expected", [
    ("subop=identify_subjects", "subop= and subref= must be supplied together"),
    ("subref=B1", "subop= and subref= must be supplied together"),
    ("subop=guess | subref=B1", "subop= must be identify_subjects"),
    ("subop=identify_subjects | subref=B99", "subref= must cite an existing direct assertion B-tag"),
    ("subop=identify_subjects | subref=B2", "subref= cannot cite its own row"),
])
def test_typed_subject_operation_rejects_invalid_rows(fields, expected):
    from knowledge_pipeline.semantic_extraction import _row_validation_issues

    dsl = "\n".join([
        "B T4 B1 | sub=factors | pred=may_predict | obj=decline | unit=S1",
        f"B T4 B2 | sub=identifying factors | {fields} | pred=is | obj=critical | unit=S1",
    ])
    rows = parse_dsl_rows(dsl, ["S1"])
    assert expected in " ".join(message for _, message in _row_validation_issues(rows))


def test_typed_subject_reference_cannot_target_container_block():
    text = "Identifying modifiable factors is critical."
    source = source_revision("nested", text)
    profile = linguistic_profile(source, document(text))
    rows = parse_dsl_rows("\n".join([
        "B T21 B1 | meth=identifying factors | unit=S1",
        "B T4 B2 | sub=identifying factors | subop=identify_subjects | subref=B1 "
        "| pred=is | obj=critical | unit=S1",
    ]), ["S1"])
    with pytest.raises(ValidationError, match="one direct assertion"):
        materialize_rows(rows, source, profile)


def test_typed_subject_reference_rejects_noncanonical_tag_and_cycles():
    with pytest.raises(ValidationError, match="subref= must be exactly one B-tag"):
        parse_dsl_rows(
            "B T4 B1 | sub=identifying factors | subop=identify_subjects | "
            "subref=see B2 | pred=is | obj=critical | unit=S1", ["S1"],
        )

    text = "Identifying factors is important."
    source = source_revision("cycle", text)
    profile = linguistic_profile(source, document(text))
    rows = parse_dsl_rows("\n".join([
        "B T4 B1 | sub=identifying factors | subop=identify_subjects | "
        "subref=B2 | pred=is | obj=important | unit=S1",
        "B T4 B2 | sub=identifying factors | subop=identify_subjects | "
        "subref=B1 | pred=is | obj=important | unit=S1",
    ]), ["S1"])
    with pytest.raises(ValidationError, match="Cycle in subject statement references"):
        materialize_rows(rows, source, profile)

@pytest.mark.asyncio
async def test_pipeline_stage_order_and_artifacts():
    stages = []
    async def checkpoint(result): stages.append(result["stage"])
    result = await ArticlePipeline(FakeNLP(), FakeLLM()).run(
        "article", TEXT_WITH_PVALUE, checkpoint)
    assert stages == ["source", "linguistic", "linguistic_profile", "structural", "complete"]
    assert result["status"] == "completed"
    assert result["coverage"]["token_preservation"] == 1
    assert result["validation"] == {"linguistic": "passed", "structural": "passed",
                                    "map": "passed", "semantic_fidelity": 0.285714}
    assert result["quality_metrics"]["version"] == 5
    assert result["quality_metrics"]["gates"]["passed"] is True
    assert len(result["blocks"]) == 7
    graph = result["graph"]
    assert len(graph["nodes"]) == 7
    relation_block = next(
        block for block in result["blocks"] if block["blockType"] == "relation"
    )
    by_tag = tags(result["blocks"])
    edge = graph["semantic_edges"][0]
    assert {edge["source"], edge["target"]} == {
        by_tag[relation_block["data"]["sourceRef"]],
        by_tag[relation_block["data"]["targetRef"]],
    }
    assert edge["relation"] == "supports" and edge["resolution"] == "ref"

@pytest.mark.asyncio
async def test_source_corruption_rejected():
    source, profile, _ = build_blocks()
    source["text"] += " "
    with pytest.raises(ValidationError, match="checksum"):
        validate_linguistic(profile, source)

@pytest.mark.asyncio
async def test_missing_token_rejected_by_coverage():
    source, profile, _ = build_blocks()
    profile["tokens"].pop()
    with pytest.raises(ValidationError, match="Uncovered"):
        validate_linguistic(profile, source)

@pytest.mark.asyncio
async def test_structural_span_must_stay_inside_its_unit_sentence():
    source, profile, blocks = build_blocks()
    blocks[0]["data"]["provenance"]["source_spans"][0]["start"] = -5
    with pytest.raises(ValidationError, match="source span"):
        validate_structural(blocks, source, profile["sentences"])

@pytest.mark.asyncio
async def test_structural_unit_mismatch_rejected():
    source, profile, blocks = build_blocks()
    blocks[-1]["data"]["provenance"]["unit_ids"] = ["S1"]
    with pytest.raises(ValidationError, match="provenance unit mismatch"):
        validate_structural(blocks, source, profile["sentences"])

@pytest.mark.asyncio
async def test_invalid_model_dsl_never_reaches_structural_stage():
    stages = []
    async def checkpoint(result): stages.append(result["stage"])
    bad = DSL.replace("B T58 B6", "B T99 B6")
    with pytest.raises(ValidationError):
        await ArticlePipeline(FakeNLP(), FakeLLM(bad)).run("article", TEXT, checkpoint)
    assert "structural" not in stages

@pytest.mark.asyncio
async def test_model_hostiles_never_materialize():
    request = {"source": TEXT, "source_units": [{"id": "S1", "text": TEXT}]}
    with pytest.raises(ValidationError):
        await extract_structural_rows(FakeLLM("not dsl"), request, ["S1"])
    duplicate = DSL.replace("\nB T4 B4", "\nB T4 B2", 1)
    with pytest.raises(ValidationError, match="still invalid after 3 corrections"):
        await extract_structural_rows(FakeLLM(duplicate), request, ["S1", "S2"])

@pytest.mark.asyncio
async def test_prefix_index_header_is_normalized_to_code_major():
    dsl = "\n".join([
        "B1 T1 B1 | doi=10.1 | title=Metadata row | unit=S1",
        "B2 T4 B2 | sub=Clusterin | pred=inhibits | obj=inflammaging | unit=S1",
        "B3 T4 B3 | sub=aged mice | pred=show | obj=fibrosis | unit=S2",
    ])
    rows = parse_dsl_rows(dsl, ["S1", "S2"])
    assert [(r["tag"], r["blockType"]) for r in rows] == [
        ("B1", "metadata"), ("B2", "statement"), ("B3", "statement")]
    assert rows[0]["data"]["title"] == "Metadata row"
    assert "_extra" not in rows[0]["data"] and "_extra" not in rows[1]["data"]

@pytest.mark.asyncio
async def test_prompt_version_is_current():
    from knowledge_pipeline.prompts import PROMPT_VERSION
    assert PROMPT_VERSION == "147"


def test_prompt_audits_all_predicates_and_source_unit_identity():
    from knowledge_pipeline.prompts import DSL_SYSTEM

    assert "Inventory every source-expressed predication in grammatical order" in DSL_SYSTEM
    assert "Treat every S<n> as an independent evidence boundary" in DSL_SYSTEM
    assert "it must not supply a separate claim" in DSL_SYSTEM
    assert "do not truncate restrictive" in " ".join(DSL_SYSTEM.split())
    assert "attach it to the correct assertion" in " ".join(DSL_SYSTEM.split())


def test_prompt_preserves_active_argument_direction_and_shared_scope():
    from knowledge_pipeline.prompts import DSL_SYSTEM

    assert "the row must not say the reverse" in DSL_SYSTEM
    assert "Coordination words such as “and” or “or” are not predicates" in DSL_SYSTEM
    assert "Carry shared heads/modifiers only where grammar licenses them" in " ".join(DSL_SYSTEM.split())
    assert "use T4 only as the last resort" in DSL_SYSTEM
    assert "preserve each feedback-named target exactly once" in " ".join(DSL_SYSTEM.split())
    assert "in source order" in " ".join(DSL_SYSTEM.split())


def test_prompt_requires_claim_inventory_and_role_faithful_audit():
    from knowledge_pipeline.prompts import DSL_SYSTEM
    from knowledge_pipeline.semantic_extraction import SEMANTIC_AUDIT_TEMPLATE

    system = " ".join(DSL_SYSTEM.split())
    audit = " ".join(SEMANTIC_AUDIT_TEMPLATE.split())
    assert "matrix/root" in system
    assert "the row must not say the reverse" in system
    assert "source-stated assessment or measurement (what was done) is T21" in system
    assert "reported empirical finding (what was observed) is T36" in system
    assert "Classify by the proposition's role, not by a measurement verb alone" in system
    assert "preserve the source proposition's own subject and predicate" in system
    assert "unless the source explicitly asserts that reporting relation" in system
    assert "Never infer a procedure from a mentioned characteristic" in system
    assert "Do not infer epistemic labels" in system
    assert "preserve that complete argument" in system
    assert "reconstruct the source proposition inventory" in audit
    assert "Correct semantic errors even when the DSL" in audit


def test_prompt_covers_nonfinite_matrix_claims_lists_and_document_metadiscourse():
    from knowledge_pipeline.prompts import DSL_SYSTEM
    from knowledge_pipeline.semantic_extraction import (
        CORRECTION_TEMPLATE, SEMANTIC_AUDIT_TEMPLATE,
    )

    assert "matrix/root" in " ".join(DSL_SYSTEM.split())
    normalized = [
        " ".join(prompt.split())
        for prompt in (DSL_SYSTEM, CORRECTION_TEMPLATE, SEMANTIC_AUDIT_TEMPLATE)
    ]
    assert "non-finite" in normalized[0]
    assert "coordinated" in normalized[0]
    assert "metadiscourse" in normalized[0]
    assert "governing predicate" in normalized[2]
    assert "proposition inventory" in normalized[2]
    assert "first source-order item" in normalized[1]
    assert "every distinct finite claim" not in DSL_SYSTEM


def test_prompt_distinguishes_design_timepoints_from_participant_counts():
    from knowledge_pipeline.prompts import DSL_SYSTEM
    from knowledge_pipeline.semantic_extraction import SEMANTIC_AUDIT_TEMPLATE

    system = " ".join(DSL_SYSTEM.split())
    assert "Numeric-coverage feedback signals only a missing number" in system
    audit = " ".join(SEMANTIC_AUDIT_TEMPLATE.split())
    assert "T25 only for explicit participant or experimental-unit counts" in audit
    assert "Do not duplicate a factual sentence as T3" in system
    assert "Ground every T1 value only in the source unit named by that row's `unit=`" in system
    assert "every T1 field against its own source unit" in audit


def test_prompt_binds_optional_fields_to_source_units_and_field_meanings():
    from knowledge_pipeline.prompts import DSL_SYSTEM
    from knowledge_pipeline.semantic_extraction import (
        SEMANTIC_AUDIT_TEMPLATE, TARGETED_REPAIR_TEMPLATE,
    )

    system = " ".join(DSL_SYSTEM.split())
    repair = " ".join(TARGETED_REPAIR_TEMPLATE.split())
    audit = " ".join(SEMANTIC_AUDIT_TEMPLATE.split())
    assert "Every field, including optional fields" in system
    assert "primary=` and `secondary=` are only explicitly designated endpoints" in system
    assert "Do not add a parallel T4/T2 row" in system
    assert "A phase/timepoint alone is not a method" in system
    assert "count row's `unit=` must be the source unit that states that number" in system
    assert "Put all source-named methods for that target in its row" in system
    assert "preserve its measured target rather than substituting the participants" in system
    assert "meth=assessed TARGET | meas=METHOD (TIME)" in system
    assert "meth=measured TARGET in TIME" in system
    assert "repeat a source-shared subject in" in system
    assert "Omit optional `results=` when it merely repeats" in system
    assert "one T21 row per measured target" in audit
    assert "complete T36 findings" in audit


def test_t11_optional_values_must_be_explicit_and_not_inferred_from_silence():
    from knowledge_pipeline.semantic_extraction import _t11_optional_field_issues

    source = "Participants were recruited from a community-dwelling cohort."
    unit = {"id": "S1", "text": source}
    invalid = parse_dsl_rows(
        "B T11 B1 | design=Participants were recruited from a community cohort "
        "| type=research_design | rand=false | blind=false "
        "| primary=[baseline assessments] | secondary=[follow-up] "
        "| concl=[S12] | unit=S1",
        ["S1"],
    )

    issues = _t11_optional_field_issues(invalid, [unit])
    message = " ".join(text for _, text in issues)
    assert "not the generic DSL/design type" in message
    assert "silence is not false" in message
    assert "explicitly designated" in message
    assert "not an ID or label" in message

    valid = parse_dsl_rows(
        "B T11 B1 | design=Participants were recruited from a community cohort "
        "| unit=S1",
        ["S1"],
    )
    assert _t11_optional_field_issues(valid, [unit]) == []


def test_result_summary_must_retain_its_source_subject_and_object():
    from knowledge_pipeline.semantic_extraction import _result_summary_issues

    source = "Individuals completed evaluation."
    unit = {"id": "S1", "text": source, "start": 0, "end": len(source)}
    profile = _dependency_profile(source, [
        ("completed", "Individuals", "nsubj"),
        ("completed", "evaluation", "dobj"),
    ])
    incomplete = parse_dsl_rows(
        "B T36 B1 | sum=completed evaluation | results=[individuals] | unit=S1",
        ["S1"],
    )
    issues = _result_summary_issues(incomplete, [unit], profile)
    assert len(issues) == 1
    assert "source subject 'Individuals'" in issues[0][1]
    assert "not in optional results=" in issues[0][1]

    complete = parse_dsl_rows(
        "B T36 B1 | sum=Individuals completed evaluation | unit=S1",
        ["S1"],
    )
    assert _result_summary_issues(complete, [unit], profile) == []


def test_open_label_is_explicit_evidence_of_no_blinding():
    from knowledge_pipeline.semantic_extraction import _t11_optional_field_issues

    source = "The study used an open-label design."
    unit = {"id": "S1", "text": source}
    row = parse_dsl_rows(
        "B T11 B1 | design=The study used an open-label design "
        "| blind=false | unit=S1",
        ["S1"],
    )
    assert _t11_optional_field_issues(row, [unit]) == []


def test_t21_measurement_method_keeps_each_source_timing_attached():
    from knowledge_pipeline.semantic_extraction import _t21_measurement_field_issues

    source = (
        "Objective sleep was assessed using actigraphy (Phase II and III) and "
        "home polysomnography (Phase III)."
    )
    unit = {"id": "S1", "text": source}
    missing_timings = parse_dsl_rows(
        "B T21 B1 | meth=assessed objective sleep "
        "| meas=[actigraphy;home polysomnography] | unit=S1",
        ["S1"],
    )
    issues = _t21_measurement_field_issues(missing_timings, [unit])
    assert len(issues) == 1
    assert "Phase II and III" in issues[0][1]
    assert "Phase III" in issues[0][1]
    assert "meas=actigraphy (Phase II and III)" in issues[0][1]

    timepoints_only = parse_dsl_rows(
        "B T21 B1 | meth=measured inflammation markers "
        "| meas=[both phases] | unit=S1",
        ["S1"],
    )
    timepoint_issues = _t21_measurement_field_issues(
        timepoints_only,
        [{"id": "S1", "text": "Markers were measured in both phases."}],
    )
    assert "a phase/timepoint alone is not a method" in " ".join(
        message for _, message in timepoint_issues
    )

    complete = parse_dsl_rows(
        "B T21 B1 | meth=assessed objective sleep "
        "| meas=[actigraphy (Phase II and III);home polysomnography (Phase III)] "
        "| unit=S1",
        ["S1"],
    )
    assert _t21_measurement_field_issues(complete, [unit]) == []


def test_t21_generation_and_repair_rules_agree_on_method_timing():
    from knowledge_pipeline.prompts import DSL_SYSTEM
    from knowledge_pipeline.semantic_extraction import TARGETED_REPAIR_TEMPLATE

    system = " ".join(DSL_SYSTEM.split())
    repair = " ".join(TARGETED_REPAIR_TEMPLATE.split())
    assert "Attach each stated timing to the method it qualifies" in system
    assert "exactly one row for each listed target" in repair
    assert "phase/timepoint alone is not a method" in system
    assert "If no method is named, omit `meas=`" in repair
    assert "If no method/instrument is named, omit `meas=`" in system
    assert "Never write `meas=[TIME]`" in system and repair
    assert "Timing belongs in `meth=`, not `meas=`" not in repair


def test_t21_does_not_combine_coordinated_measurement_targets():
    from knowledge_pipeline.semantic_extraction import _t21_measurement_field_issues

    source = "Inflammation markers and stress hormones were measured in both phases."
    unit = {"id": "S1", "text": source, "start": 0, "end": len(source)}
    profile = _dependency_profile(source, [
        ("measured", "markers", "nsubjpass"),
        ("markers", "Inflammation", "compound"),
        ("markers", "hormones", "conj"),
        ("hormones", "stress", "compound"),
    ])
    row = parse_dsl_rows(
        "B T21 B1 | meth=measured inflammation markers and stress hormones "
        "| meas=[both phases] | unit=S1",
        ["S1"],
    )
    messages = " ".join(
        message for _, message in _t21_measurement_field_issues(
            row, [unit], profile,
        )
    )
    assert "a phase/timepoint alone is not a method" in messages
    assert "meth= combines independently measured source targets" in messages
    assert "Inflammation markers" in messages
    assert "stress hormones" in messages


def test_t21_requires_a_row_for_each_source_stated_measurement_target():
    from knowledge_pipeline.semantic_extraction import _t21_measurement_field_issues

    source = "Inflammation markers and stress hormones were measured in both phases."
    unit = {"id": "S1", "text": source, "start": 0, "end": len(source)}
    profile = _dependency_profile(source, [
        ("measured", "markers", "nsubjpass"),
        ("markers", "Inflammation", "compound"),
        ("markers", "hormones", "conj"),
        ("hormones", "stress", "compound"),
    ])
    one_target_only = parse_dsl_rows(
        "B T21 B1 | meth=measured inflammation markers in both phases | unit=S1",
        ["S1"],
    )

    messages = " ".join(
        message for _, message in _t21_measurement_field_issues(
            one_target_only, [unit], profile,
        )
    )

    assert "omits source-stated measurement target(s)" in messages
    assert "stress hormones" in messages


def test_t21_requires_timing_only_for_the_method_in_each_row():
    from knowledge_pipeline.semantic_extraction import _t21_measurement_field_issues

    source = (
        "Objective sleep was assessed based on actigraphy (Phase II and III) and "
        "home polysomnography (Phase III)."
    )
    unit = {"id": "S1", "text": source}
    separate_methods = parse_dsl_rows("\n".join([
        "B T21 B1 | meth=assessed based on actigraphy "
        "| meas=actigraphy (Phase II and III) | unit=S1",
        "B T21 B2 | meth=assessed based on home polysomnography "
        "| meas=home polysomnography (Phase III) | unit=S1",
    ]), ["S1"])

    assert _t21_measurement_field_issues(separate_methods, [unit]) == []


def test_t21_does_not_put_measured_targets_in_meas_field():
    from knowledge_pipeline.semantic_extraction import _t21_measurement_field_issues

    source = "Inflammation markers and stress hormones were measured in both phases."
    unit = {"id": "S1", "text": source, "start": 0, "end": len(source)}
    profile = _dependency_profile(source, [
        ("measured", "markers", "nsubjpass"),
        ("markers", "Inflammation", "compound"),
        ("markers", "hormones", "conj"),
        ("hormones", "stress", "compound"),
    ])
    row = parse_dsl_rows(
        "B T21 B1 | meth=measured inflammation markers and stress hormones "
        "| meas=[inflammation markers;stress hormones] | unit=S1",
        ["S1"],
    )

    messages = " ".join(
        message for _, message in _t21_measurement_field_issues(
            row, [unit], profile,
        )
    )
    assert "meas= names a source measurement target, not a method or instrument" in messages


def test_measurement_procedure_in_t36_is_retyped_as_t21():
    from knowledge_pipeline.semantic_extraction import (
        _accepted_targeted_rows, _measurement_claim_type_issues,
    )

    source = "Sleep was assessed using actigraphy."
    unit = {"id": "S1", "text": source, "start": 0, "end": len(source)}
    profile = _dependency_profile(source, [
        ("assessed", "Sleep", "nsubjpass"),
    ])
    current = parse_dsl_rows(
        "B T36 B1 | sum=Sleep was assessed using actigraphy | unit=S1",
        ["S1"],
    )
    issues = _measurement_claim_type_issues(current, [unit], profile)
    assert len(issues) == 1
    assert "represent it as T21 method" in issues[0][1]

    patch = parse_dsl_rows(
        "B T21 B1 | meth=Sleep was assessed using actigraphy "
        "| meas=actigraphy | unit=S1",
        ["S1"],
    )
    accepted, errors = _accepted_targeted_rows(
        patch, current, issues, [], [], [], source_units=[unit],
        linguistic_profile=profile,
    )

    assert errors == []
    assert [(row["tag"], row["blockType"]) for row in accepted] == [
        ("B1", "method"),
    ]


@pytest.mark.parametrize(("source", "predicate", "target", "summary"), [
    ("Group differences were detected at follow-up.", "detected", "differences",
     "Group differences were detected at follow-up"),
    ("A mean change was estimated at follow-up.", "estimated", "change",
     "A mean change was estimated at follow-up"),
])
def test_ambiguous_finding_verbs_are_not_forced_to_t21(source, predicate, target, summary):
    from knowledge_pipeline.semantic_extraction import (
        _measurement_claim_type_issues, _source_measurement_target_phrases,
    )

    unit = {"id": "S1", "text": source, "start": 0, "end": len(source)}
    profile = _dependency_profile(source, [
        (predicate, target, "nsubjpass"),
    ])
    row = parse_dsl_rows(f"B T36 B1 | sum={summary} | unit=S1", ["S1"])

    assert _measurement_claim_type_issues(row, [unit], profile) == []
    assert _source_measurement_target_phrases([unit], profile) == {}


def test_targeted_feedback_names_mandatory_t21_replacement_tags():
    from knowledge_pipeline.semantic_extraction import _targeted_repair_prompt

    source = "Sleep was assessed using actigraphy."
    unit = {"id": "S1", "text": source}
    dsl = "B T36 B1 | sum=Sleep was assessed using actigraphy | unit=S1"
    rows = parse_dsl_rows(dsl, ["S1"])
    issue = (rows[0], "source-stated measurement operation is a procedure; "
             "represent it as T21 method with meth= and any explicitly stated "
             "instrument in meas=")

    prompt = _targeted_repair_prompt(
        [unit], [], rows, [issue], [], [], [], {"B1": dsl}, "", None,
    )

    assert "MANDATORY TYPE REPLACEMENT for B1" in prompt
    assert "keep each exact tag and unit, replace its old type with T21 method" in prompt
    assert "Required DSL keys [meth=]" in prompt
    assert "do not reuse a replacement tag" in prompt
    assert "If no method is named, omit `meas=`" in " ".join(prompt.split())
    assert "exactly one row for each listed target" in " ".join(prompt.split())


def test_targeted_feedback_lists_each_omitted_t21_target_as_an_addition():
    from knowledge_pipeline.semantic_extraction import _targeted_repair_prompt

    source = "Sleep was assessed using actigraphy; stress markers were measured."
    unit = {"id": "S1", "text": source}
    dsl = "B T21 B1 | meth=Sleep was assessed | meas=actigraphy | unit=S1"
    rows = parse_dsl_rows(dsl, ["S1"])
    issue = (
        rows[0],
        "Row B1 (method) omits source-stated measurement target(s) 'stress markers'; "
        "add a separate T21 row for each omitted target, with the source-stated "
        "operation and timing",
    )

    prompt = _targeted_repair_prompt(
        [unit], [], rows, [issue], [], [], [], {"B1": dsl}, "", None,
    )

    assert "REQUIRED_T21_TARGET_ADDITIONS" in prompt
    assert "B1 unit=S1: 'stress markers'" in prompt
    assert "exactly one T21 row per listed target" in prompt


def test_coordinated_result_rows_repeat_the_source_shared_subject():
    from knowledge_pipeline.semantic_extraction import _result_summary_issues

    source = "Participants were older and predisposed."
    unit = {"id": "S1", "text": source, "start": 0, "end": len(source)}
    profile = _dependency_profile(source, [
        ("older", "Participants", "nsubj"),
        ("older", "predisposed", "conj"),
    ])
    for token in profile["tokens"]:
        if token["text"].casefold() in {"older", "predisposed"}:
            token["pos"] = "ADJ"
    fragment = parse_dsl_rows(
        "B T36 B1 | sum=predisposed | unit=S1", ["S1"],
    )
    issues = _result_summary_issues(fragment, [unit], profile)
    assert len(issues) == 1
    assert "shared source subject 'Participants'" in issues[0][1]

    combined = parse_dsl_rows(
        "B T36 B1 | sum=Participants were older and predisposed | unit=S1",
        ["S1"],
    )
    combined_issues = _result_summary_issues(combined, [unit], profile)
    assert any("split them into separate atomic T36 rows" in message
               for _, message in combined_issues)

    complete = parse_dsl_rows("\n".join([
        "B T36 B1 | sum=Participants were older | unit=S1",
        "B T36 B2 | sum=Participants were predisposed | unit=S1",
    ]), ["S1"])
    assert _result_summary_issues(complete, [unit], profile) == []

    distinct_subject_source = "Participants were impaired and controls were diagnosed."
    distinct_unit = {
        "id": "S2", "text": distinct_subject_source,
        "start": 0, "end": len(distinct_subject_source),
    }
    distinct_profile = _dependency_profile(distinct_subject_source, [
        ("impaired", "Participants", "nsubj"),
        ("impaired", "diagnosed", "conj"),
        ("diagnosed", "controls", "nsubj"),
    ])
    locally_subjected = parse_dsl_rows(
        "B T36 B1 | sum=controls were diagnosed | unit=S2", ["S2"],
    )
    assert _result_summary_issues(
        locally_subjected, [distinct_unit], distinct_profile,
    ) == []


def test_result_summary_splits_assertions_with_distinct_source_subjects():
    from knowledge_pipeline.semantic_extraction import _result_summary_issues

    source = "Alpha improved and Beta declined."
    unit = {"id": "S1", "text": source, "start": 0, "end": len(source)}
    profile = _dependency_profile(source, [
        ("improved", "Alpha", "nsubj"),
        ("declined", "Beta", "nsubj"),
    ])
    combined = parse_dsl_rows(
        "B T36 B1 | sum=Alpha improved and Beta declined | unit=S1", ["S1"],
    )

    issues = _result_summary_issues(combined, [unit], profile)

    assert len(issues) == 1
    assert "separate source assertions with distinct subjects" in issues[0][1]
    assert "'Alpha' → improved" in issues[0][1]
    assert "'Beta' → declined" in issues[0][1]


def test_result_summary_does_not_split_embedded_or_temporal_clauses():
    from knowledge_pipeline.semantic_extraction import _result_summary_issues

    examples = [
        (
            "There was a non significant tendency for followed-up persons to "
            "have achieved more years of education (p = 0.059).",
            [
                ("was", "tendency", "nsubj"),
                ("achieved", "persons", "nsubj"),
                ("tendency", "achieved", "xcomp"),
            ],
        ),
        (
            "A gradual decrease in these cells was observed as age increased.",
            [
                ("observed", "decrease", "nsubjpass"),
                ("increased", "age", "nsubj"),
                ("observed", "increased", "advcl"),
            ],
        ),
    ]

    for source, relations in examples:
        unit = {"id": "S1", "text": source, "start": 0, "end": len(source)}
        profile = _dependency_profile(source, relations)
        rows = parse_dsl_rows(
            f"B T36 B1 | sum={source} | unit=S1", ["S1"],
        )

        assert _result_summary_issues(rows, [unit], profile) == []


def test_result_summary_accepts_one_member_of_a_coordinated_source_argument():
    from knowledge_pipeline.semantic_extraction import _result_summary_issues

    source = "Brain abnormalities and decreased brain weight were observed."
    unit = {"id": "S1", "text": source, "start": 0, "end": len(source)}
    profile = _dependency_profile(source, [
        ("observed", "abnormalities", "nsubjpass"),
        ("abnormalities", "weight", "conj"),
    ])
    rows = parse_dsl_rows(
        "B T36 B1 | sum=Decreased brain weight was observed | unit=S1",
        ["S1"],
    )

    assert _result_summary_issues(rows, [unit], profile) == []


def test_result_summary_does_not_treat_coordinated_attributive_adjectives_as_predicates():
    from knowledge_pipeline.semantic_extraction import _result_summary_issues

    source = "Altered glial and neuronal protein expression was observed."
    unit = {"id": "S1", "text": source, "start": 0, "end": len(source)}
    profile = _dependency_profile(source, [
        ("observed", "expression", "nsubjpass"),
        ("expression", "glial", "amod"),
        ("glial", "neuronal", "conj"),
    ])
    for token in profile["tokens"]:
        if token["text"].casefold() in {"glial", "neuronal"}:
            token["pos"] = "ADJ"
    rows = parse_dsl_rows(
        f"B T36 B1 | sum={source} | unit=S1", ["S1"],
    )

    assert _result_summary_issues(rows, [unit], profile) == []


def test_decimal_source_statistic_is_not_retained_as_t25_sample_size():
    from knowledge_pipeline.semantic_extraction import (
        _remove_decimal_statistics_from_sample_size,
    )

    source = "Participants had mean age 75.03 years; the subgroup included 12 people."
    unit = {"id": "S1", "text": source}
    rows = parse_dsl_rows("\n".join([
        "B T25 B1 | n=75.03 | unit=S1",
        "B T25 B2 | n=12 | unit=S1",
    ]), ["S1"])
    lines = {"B1": "B T25 B1 | n=75.03 | unit=S1", "B2": "B T25 B2 | n=12 | unit=S1"}
    filtered, _, removed = _remove_decimal_statistics_from_sample_size(
        rows, lines, [unit],
    )
    assert [row["tag"] for row in filtered] == ["B2"]
    assert removed == ["B1"]
    assert set(lines) == {"B2"}


def test_result_statistics_require_typed_rows_even_when_sum_contains_values():
    from knowledge_pipeline.semantic_extraction import (
        _accepted_targeted_rows, _typed_result_statistic_issues,
    )

    source = "Participants were older (mean age = 75.03 years, SD = 6.34)."
    unit = {"id": "S1", "text": source}
    result = parse_dsl_rows(
        "B T36 B1 | sum=Participants were older, mean age 75.03 years, "
        "SD 6.34 | unit=S1",
        ["S1"],
    )
    issues = _typed_result_statistic_issues(result, [unit])
    assert len(issues) == 1
    assert "T32 magnitude_value row with nums=" in issues[0][1]
    assert "T28 variance row with var=" in issues[0][1]

    patch = parse_dsl_rows("\n".join([
        "B T36 B1 | sum=Participants were older (mean age = 75.03 years, "
        "SD = 6.34) | unit=S1",
        "B T32 B2 | nums=[mean age 75.03 years] | unit=S1",
        "B T28 B3 | var=SD 6.34 | unit=S1",
    ]), ["S1"])
    accepted, errors = _accepted_targeted_rows(
        patch, result, issues, [], [], [], source_units=[unit],
    )
    assert errors == []
    assert [row["blockType"] for row in accepted] == [
        "result", "magnitude_value", "variance",
    ]


def test_numeric_repair_preserves_an_already_valid_typed_value_row():
    from knowledge_pipeline.semantic_extraction import (
        _accepted_targeted_rows, _typed_result_statistic_issues,
    )

    source = "Participants were older (mean age = 75.03 years, SD = 6.34)."
    unit = {"id": "S1", "text": source}
    current = parse_dsl_rows("\n".join([
        "B T36 B1 | sum=Participants were older | unit=S1",
        "B T28 B2 | var=SD = 6.34 | unit=S1",
    ]), ["S1"])
    row_issues = _typed_result_statistic_issues(current, [unit])
    patch = parse_dsl_rows("\n".join([
        "B T36 B1 | sum=Participants were older | unit=S1",
        "B T32 B2 | nums=[mean age 75.03 years] | unit=S1",
    ]), ["S1"])

    accepted, errors = _accepted_targeted_rows(
        patch, current, row_issues, [], [], [], source_units=[unit],
        missing_numeric_units={"S1": ["75.03"]},
    )

    assert errors == []
    assert [(row["tag"], row["blockType"]) for row in accepted] == [
        ("B1", "result"), ("B3", "magnitude_value"),
    ]
    assert (current[1]["tag"], current[1]["blockType"]) == ("B2", "variance")


def test_production_prompts_contain_no_article_specific_science_examples():
    from knowledge_pipeline.prompts import DSL_SYSTEM
    from knowledge_pipeline.semantic_extraction import (
        CORRECTION_TEMPLATE, SEMANTIC_AUDIT_TEMPLATE, TARGETED_REPAIR_TEMPLATE,
    )

    prompt_text = " ".join("\n".join((
        DSL_SYSTEM, CORRECTION_TEMPLATE, TARGETED_REPAIR_TEMPLATE,
        SEMANTIC_AUDIT_TEMPLATE,
    )).split()).casefold()
    assert "same-unit items" in prompt_text
    assert "first source-order item" in prompt_text
    assert not any(term.casefold() in prompt_text for term in (
        "cretan aging cohort", "apoe", "mci", "cni", "actigraphy",
        "psychotropic medication", "long-term cognitive decline",
    ))


def test_source_pvalue_extraction_preserves_each_value_and_inequality():
    from knowledge_pipeline.semantic_extraction import _reported_p_values

    assert _reported_p_values(
        "The groups differed (p = 0.4, 0.9 and 0.1); p < 0.001."
    ) == ["0.4", "0.9", "0.1", "<0.001"]


def test_typed_pvalue_coverage_requires_probability_value_rows():
    from knowledge_pipeline.semantic_extraction import _missing_probability_values

    source_units = [{"id": "S1", "text": "The result was significant (p = 0.059)."}]
    statement_only = parse_dsl_rows(
        "B T4 B1 | sub=result | pred=was | obj=significant | unit=S1", ["S1"]
    )
    assert _missing_probability_values(statement_only, source_units) == {"S1": ["0.059"]}

    complete = parse_dsl_rows("\n".join([
        "B T4 B1 | sub=result | pred=was | obj=significant | unit=S1",
        "B T27 B2 | p=0.059 | unit=S1",
    ]), ["S1"])
    assert _missing_probability_values(complete, source_units) == {}

    inequality = parse_dsl_rows("B T27 B3 | p=<0.05 | unit=S1", ["S1"])[0]
    assert inequality["data"]["pValue"] == "<0.05"


def test_epistemic_status_is_validated_from_the_dsl_field_catalog():
    from knowledge_pipeline.semantic_extraction import _row_validation_issues
    from knowledge_contracts.block_dsl import render_field_docs

    valid = parse_dsl_rows(
        "B T4 B1 | sub=aging | pred=affects | obj=health "
        "| epi=background_claim | unit=S1", ["S1"],
    )
    invalid = parse_dsl_rows(
        "B T4 B1 | sub=aging | pred=affects | obj=health "
        "| epi=research_goal | unit=S1", ["S1"],
    )

    assert _row_validation_issues(valid) == []
    assert "epi= must be one of" in _row_validation_issues(invalid)[0][1]
    assert "allowed: direct_statement|observation|" in render_field_docs("statement")


def test_numeric_coverage_preserves_source_values_but_ignores_numeric_citations():
    from knowledge_pipeline.semantic_extraction import _missing_source_numeric_mentions

    source_units = [{
        "id": "S1",
        "text": (
            "Participants had a mean age of 75.03 years (SD 6.34; n=1,000), "
            "and follow-up continued to 2050; Smith et al. (2020) [12, 14-16]."
        ),
    }]
    incomplete = parse_dsl_rows(
        "B T4 B1 | sub=participants | pred=had | "
        "obj=mean age 75 years; SD 6.3; n 999 | unit=S1",
        ["S1"],
    )
    assert _missing_source_numeric_mentions(incomplete, source_units) == {
        "S1": ["75.03", "6.34", "1,000", "2050"]
    }

    complete = parse_dsl_rows(
        "B T4 B1 | sub=participants | pred=had | "
        "obj=mean age 75.030 years; SD 6.340; n 1000; follow-up through 2050 "
        "| unit=S1",
        ["S1"],
    )
    assert _missing_source_numeric_mentions(complete, source_units) == {}


def test_result_summary_does_not_treat_inline_citation_as_source_argument():
    from knowledge_pipeline.semantic_extraction import _result_summary_issues

    source = (
        "A small group of POMC neurons expresses the glutamate vesicular "
        "transporter (VGLUT-2) [121]."
    )
    token_matches = list(re.finditer(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*|[^\w\s]", source))
    tokens = []
    token_ids = {}
    for index, match in enumerate(token_matches, 1):
        value = match.group()
        token_id = f"t{index}"
        token_ids[value.casefold()] = token_id
        tokens.append({
            "id": token_id,
            "sentence_id": "sent1",
            "text": value,
            "lemma": "express" if value.casefold() == "expresses" else value.casefold(),
            "pos": "VERB" if value.casefold() == "expresses" else "NOUN",
            "start": match.start(),
            "end": match.end(),
        })
    profile = {
        "tokens": tokens,
        "dependencies": [
            {"source": token_ids["expresses"], "target": token_ids["group"],
             "relation": "nsubj"},
            {"source": token_ids["expresses"], "target": token_ids["vglut-2"],
             "relation": "obj"},
            {"source": token_ids["expresses"], "target": token_ids["121"],
             "relation": "obj"},
        ],
    }
    units = [{"id": "S1", "text": source, "start": 0, "end": len(source)}]
    rows = parse_dsl_rows(
        "B T36 B1 | sum=A small group of POMC neurons expresses the glutamate "
        "vesicular transporter (VGLUT-2). | unit=S1",
        ["S1"],
    )

    assert _result_summary_issues(rows, units, profile) == []


@pytest.mark.asyncio
async def test_numeric_coverage_repair_replaces_the_source_unit_row():
    request = {
        "source_units": [{"id": "S1", "text": "The mean age was 75.03 years."}],
    }

    class NumericRepairLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, _system, user):
            self.calls.append(user)
            if len(self.calls) == 1:
                return (
                    "B T4 B1 | sub=mean age | pred=was | obj=75 years | unit=S1"
                )
            return (
                "B T4 B1 | sub=mean age | pred=was | obj=75.03 years | unit=S1"
            )

    llm = NumericRepairLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1"])

    assert step["retries"] == 1
    assert rows[0]["data"]["object"] == "75.03 years"
    assert "Replace only these existing tags: B1" in llm.calls[1]
    assert "MISSING_NUMERIC_MENTIONS" in llm.calls[1]
    assert "same number attached to another unit does not satisfy this entry" in llm.calls[1]


def test_initial_unreported_and_duplicate_pvalues_are_discarded():
    from knowledge_pipeline.semantic_extraction import (
        _filter_unreported_probability_rows, _missing_probability_values,
    )

    source_units = [{"id": "S1", "text": "The result was significant (p = 0.059)."}]
    dsl = "\n".join([
        "B T4 B1 | sub=result | pred=was | obj=significant | unit=S1",
        "B T27 B2 | p=0.059 | unit=S1",
        "B T27 B3 | p=0.059 | unit=S1",
        "B T27 B4 | p=<0.05 | unit=S1",
    ])
    rows = parse_dsl_rows(dsl, ["S1"])
    current_dsl = {f"B{index}": line for index, line in enumerate(dsl.splitlines(), 1)}

    filtered, kept_dsl = _filter_unreported_probability_rows(rows, current_dsl, source_units)

    assert [row["tag"] for row in filtered] == ["B1", "B2"]
    assert set(kept_dsl) == {"B1", "B2"}
    assert _missing_probability_values(filtered, source_units) == {}


def test_source_grounded_repair_splits_relative_copula_into_object():
    from knowledge_pipeline.semantic_extraction import (
        _row_validation_issues, _source_grounded_repair,
    )

    source = "Neurospheres (NS) that are smaller in size."
    row = parse_dsl_rows(
        "B T4 B1 | sub=Neurospheres (NS) | pred=are_smaller_in_size | obj= | unit=S1",
        ["S1"],
    )[0]
    assert _row_validation_issues([row])
    repaired = _source_grounded_repair(row, source, has_semantic_sibling=False)
    assert repaired == (
        "B T4 B1 | sub=Neurospheres (NS) | pred=are | "
        "obj=smaller in size | unit=S1"
    )


@pytest.mark.asyncio
async def test_fronted_time_is_not_mistaken_for_observed_nominal_outcome():
    source = (
        "After three weeks of a three-month period of IF, an elevated NSC "
        "proliferation in the rats and mice dentate gyrus was observed [152,153]."
    )
    request = {"source_units": [{"id": "S1", "text": source}]}

    class MisparsedObservedResultLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return (
                "B T4 B1 | sub=After three weeks of a three-month period of IF "
                "| pred=was_observed_to | obj=an elevated NSC proliferation in "
                "the rats and mice dentate gyrus | unit=S1"
            )

    rows, step = await extract_structural_rows(
        MisparsedObservedResultLLM(), request, ["S1"],
    )

    assert step["retries"] == 0
    assert len(rows) == 1
    assert rows[0]["blockType"] == "result"
    assert rows[0]["data"]["resultsSummary"] == (
        "an elevated NSC proliferation in the rats and mice dentate gyrus "
        "was observed [152,153]"
    )


@pytest.mark.asyncio
async def test_source_grounded_repairs_split_known_shared_subject_clauses():
    sources = [
        (
            "\n\nAs a prodromal stage of dementia pathology, MCI constitutes a "
            "critical “window” for early intervention, and consequently, several "
            "studies have focused on identifying modifiable risk factors for "
            "cognitive deterioration."
        ),
        (
            "\n\nOther biomarkers (including genetic factors, pro-inflammatory "
            "cytokines and stress hormones) contribute to disease progression and "
            "differentiate between clinical categories (MCI, dementia)."
        ),
    ]


    request = {"source_units": [
        {"id": f"S{index}", "text": source}
        for index, source in enumerate(sources, 1)
    ]}

    class MergedClauseLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return "\n".join([
                "B T4 B1 | sub=As a prodromal stage of dementia pathology MCI "
                "constitutes a critical window for early intervention | "
                "pred=and_consequently_several_studies_have_focused_on_identifying "
                "| obj= | unit=S1",
                "B T4 B2 | sub=Other biomarkers including genetic factors "
                "pro-inflammatory cytokines and stress hormones | "
                "pred=contribute_to_disease_progression_and_differentiate_between "
                "| obj= | unit=S2",
            ])

    rows, step = await extract_structural_rows(
        MergedClauseLLM(), request, ["S1", "S2"],
    )

    assert step["retries"] == 0
    assert [(row["data"]["subject"], row["data"]["predicate"],
             row["data"]["object"], row["data"].get("context")) for row in rows
            if row["blockType"] == "statement"] == [
        ("MCI", "constitutes", "a critical “window” for early intervention",
         "As a prodromal stage of dementia pathology"),
        ("several studies", "have_focused_on",
         "identifying modifiable risk factors for cognitive deterioration",
         "consequently"),
        ("Other biomarkers (including genetic factors, pro-inflammatory cytokines and stress hormones)",
         "contribute_to", "disease progression", None),
        ("Other biomarkers (including genetic factors, pro-inflammatory cytokines and stress hormones)",
         "differentiate_between", "clinical categories (MCI, dementia)", None),
    ]


def test_labeled_article_header_becomes_source_grounded_metadata_row():
    from knowledge_pipeline.semantic_extraction import _apply_metadata_fragment_repairs

    source = (
        "# Cretan Aging Cohort-Phase III: Methodology and Descriptive "
        "Characteristics\n\n**Авторы:** Basta Maria, Skourti Eleni\n\n"
        "**Журнал:** Healthcare (2023)\n"
    )
    dsl = "B T36 B1 | sum=" + source.replace("\n", r"\n") + " | unit=S1"
    rows = parse_dsl_rows(dsl, ["S1"])
    current_dsl = {"B1": dsl}

    repaired, repaired_dsl, changed = _apply_metadata_fragment_repairs(
        rows, current_dsl, [{"id": "S1", "text": source}],
    )

    assert changed == ["B1"]
    assert len(repaired) == 1 and repaired[0]["blockType"] == "metadata"
    assert repaired[0]["data"]["title"] == (
        "Cretan Aging Cohort-Phase III: Methodology and Descriptive Characteristics"
    )
    assert repaired[0]["data"]["authors"] == ["Basta Maria", "Skourti Eleni"]
    assert repaired[0]["data"]["journal"] == "Healthcare"
    assert repaired[0]["data"]["publication_date"] == "2023"
    assert "title=" in repaired_dsl["B1"] and "year=2023" in repaired_dsl["B1"]


def test_metadata_without_evidence_in_its_source_unit_is_removed_only():
    from knowledge_pipeline.semantic_extraction import _apply_metadata_fragment_repairs

    source = "Participants were recruited from a community cohort."
    dsl = "\n".join([
        "B T1 B1 | title=Invented article title | authors=[Invented Author] | "
        "doi=10.1234/invented | unit=S1",
        "B T11 B2 | design=Participants were recruited from a community cohort "
        "| unit=S1",
    ])
    rows = parse_dsl_rows(dsl, ["S1"])
    current_dsl = {row["tag"]: line for row, line in zip(rows, dsl.splitlines(), strict=True)}

    repaired, repaired_dsl, changed = _apply_metadata_fragment_repairs(
        rows, current_dsl, [{"id": "S1", "text": source}],
    )

    assert [(row["tag"], row["blockType"]) for row in repaired] == [
        ("B2", "research_design"),
    ]
    assert "B1" not in repaired_dsl
    assert repaired_dsl["B2"].startswith("B T11 B2 |")
    assert changed == ["B1"]


def test_mixed_article_header_metadata_keeps_scientific_claims_in_same_unit():
    from knowledge_pipeline.semantic_extraction import _apply_metadata_fragment_repairs

    source = (
        "# Neural Stem Cells and Aging\n\n"
        "**Авторы:** Plakkot Bhuvana, Di Agostino Ashley\n"
        "**Журнал:** Cells (2023)\n"
        "**DOI:** 10.3390/cells12050769\n\n"
        "## Abstract\n"
        "The hypothalamus controls homeostatic processes."
    )
    dsl = "\n".join([
        "B T4 B1 | sub=the hypothalamus | pred=controls "
        "| obj=homeostatic processes | unit=S1",
        "B T4 B2 | sub=Authors | pred=are | obj=Plakkot Bhuvana "
        "| unit=S1",
        "B T4 B3 | sub=Journal | pred=is | obj=Cells (2023) | unit=S1",
        "B T3 B4 | content=DOI | unit=S1",
    ])
    rows = parse_dsl_rows(dsl, ["S1"])
    current_dsl = {row["tag"]: line for row, line in zip(rows, dsl.splitlines())}

    repaired, repaired_dsl, changed = _apply_metadata_fragment_repairs(
        rows, current_dsl, [{"id": "S1", "text": source}],
    )

    metadata = next(row for row in repaired if row["blockType"] == "metadata")
    claim = next(row for row in repaired if row["blockType"] == "statement")
    assert metadata["data"]["authors"] == ["Plakkot Bhuvana", "Di Agostino Ashley"]
    assert metadata["data"]["journal"] == "Cells"
    assert metadata["data"]["publication_date"] == "2023"
    assert metadata["data"]["doi"] == "10.3390/cells12050769"
    assert claim["data"]["subject"] == "the hypothalamus"
    assert claim["data"]["object"] == "homeostatic processes"
    assert len([row for row in repaired if row["blockType"] == "metadata"]) == 1
    assert not any(row["data"].get("subject") in {"Authors", "Journal"} for row in repaired)
    assert all(tag in repaired_dsl for tag in {row["tag"] for row in repaired})
    assert changed


@pytest.mark.asyncio
async def test_source_exact_copula_repairs_importance_and_fronted_qualifier():
    source_units = [
        {"id": "S7", "text": "Identifying modifiable factors is critical."},
        {"id": "S50", "text": (
            "However, to our knowledge, up to now, this is the first longitudinal "
            "cohort study conducted in Greece and among few worldwide."
        )},
    ]
    initial = "\n".join([
        "B T3 B1 | content=Identifying modifiable factors "
        "is critical. | unit=S7",
        "B T4 B2 | sub=However_to_our_knowledge_up_to_now_this_is_the_first_"
        "longitudinal_cohort_study_conducted_in_Greece_and_among_few_worldwide "
        "| pred=is_the_first_longitudinal_cohort_study_conducted_in_Greece "
        "| unit=S50",
    ])

    rows, step = await extract_structural_rows(
        FakeLLM(initial), {"source_units": source_units}, ["S7", "S50"],
    )

    assert step["retries"] == 0
    assert [(row["blockType"], row["data"]["unit"]) for row in rows] == [
        ("statement", "S7"), ("statement", "S50"),
    ]
    assert rows[0]["data"]["predicate"] == "is"
    assert rows[0]["data"]["object"] == "critical"
    assert rows[1]["data"]["subject"] == "this"
    assert rows[1]["data"]["predicate"] == "is"
    assert rows[1]["data"]["object"].startswith("the first longitudinal cohort study")
    assert rows[1]["data"]["context"] == "However, to our knowledge, up to now"


@pytest.mark.asyncio
async def test_uncertainty_and_objectless_discovery_are_repaired_from_exact_source():
    source_units = [
        {"id": "S6", "text": (
            "Various studies have substantiated the chances of obesity inducing "
            "accelerated aging."
        )},
        {"id": "S13", "text": (
            "In recent times, a third NSC pool, hypothalamic neural stem cells "
            "(htNSCs), were discovered [4,5,6]."
        )},
    ]
    initial = "\n".join([
        "B T4 B1 | sub=obesity | pred=induces_accelerated_aging | obj= | unit=S6",
        "B T4 B2 | sub=a_third_NSC_pool_hypothalamic_neural_stem_cells_htNSCs "
        "| pred=were_discovered | obj= | unit=S13",
    ])

    rows, step = await extract_structural_rows(
        FakeLLM(initial), {"source_units": source_units}, ["S6", "S13"],
    )

    assert step["retries"] == 0
    assert rows[0]["blockType"] == "statement"
    assert rows[0]["data"]["subject"] == "Various studies"
    assert rows[0]["data"]["predicate"] == "have_substantiated"
    assert rows[0]["data"]["object"] == (
        "the chances of obesity inducing accelerated aging"
    )
    assert rows[1]["blockType"] == "result"
    assert rows[1]["data"]["resultsSummary"] == source_units[1]["text"]


@pytest.mark.asyncio
async def test_raw_figure_markup_is_removed_from_semantic_rows():
    source = (
        "<figure>\n  <figcaption><strong>Figure 1</strong> Flow diagram of "
        "Phases I, II & III of the Cretan Aging Cohort study."
        "</figcaption>\n</figure>"
    )
    request = {"source_units": [{"id": "S1", "text": source}],
               "caption_unit_ids": ["S1"]}

    class MarkupLeakingCaptionLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return "\n".join([
                "B T4 B1 | sub=Flow diagram | pred=depicts | "
                "obj=Phases I, II & III of the Cretan Aging Cohort study | unit=S1",
                r"B T36 B2 | sum=<figure>\n <figcaption><strong>Figure 1</strong> "
                r"Flow diagram of Phases I, II & III of the Cretan Aging Cohort "
                r"study.</figcaption>\n</figure> | unit=S1",
            ])

    rows, step = await extract_structural_rows(
        MarkupLeakingCaptionLLM(), request, ["S1"],
    )

    assert step["retries"] == 0
    assert [row["blockType"] for row in rows] == ["statement", "image"]
    semantic_rows = [row for row in rows if row["blockType"] not in {"image", "text"}]
    assert len(semantic_rows) == 1
    assert "<figure>" not in str(semantic_rows[0]["data"])


@pytest.mark.asyncio
async def test_nonassertional_html_caption_gets_plain_context_when_model_echoes_markup():
    source = (
        "<figure>\n<figcaption><strong>Figure 1</strong> Flow diagram of "
        "Phases I, II & III of the Cretan Aging Cohort study."
        "</figcaption>\n</figure>"
    )
    request = {"source_units": [{"id": "S1", "text": source}],
               "caption_unit_ids": ["S1"]}

    class MarkupOnlyCaptionLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return (
                r"B T36 B1 | sum=<figure>\n<figcaption><strong>Figure 1</strong> "
                r"Flow diagram of Phases I, II & III of the Cretan Aging Cohort "
                r"study.</figcaption>\n</figure> | unit=S1"
            )

    rows, step = await extract_structural_rows(
        MarkupOnlyCaptionLLM(), request, ["S1"],
    )

    assert step["retries"] == 0
    assert [(row["blockType"], row["data"]["unit"]) for row in rows] == [
        ("text", "S1"), ("image", "S1"),
    ]
    assert rows[0]["data"]["content"] == (
        "Figure 1 Flow diagram of Phases I, II & III of the Cretan Aging Cohort study."
    )
    assert "<figure>" not in rows[0]["data"]["content"]


@pytest.mark.asyncio
async def test_split_html_caption_opening_fragment_gets_plain_context_row():
    source = (
        "<figure>\n<figcaption><strong>Figure 1</strong> Flow diagram of "
        "Phases I, II & III of the Cretan Aging Cohort study."
    )
    request = {"source_units": [{"id": "S1", "text": source}],
               "caption_unit_ids": ["S1"]}

    class SplitMarkupCaptionLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return (
                r"B T36 B1 | sum=<figure>\n<figcaption><strong>Figure 1</strong> "
                r"Flow diagram of Phases I, II & III of the Cretan Aging Cohort study. "
                r"| unit=S1"
            )

    rows, step = await extract_structural_rows(
        SplitMarkupCaptionLLM(), request, ["S1"],
    )

    assert step["retries"] == 0
    assert [(row["blockType"], row["data"]["unit"]) for row in rows] == [
        ("text", "S1"), ("image", "S1"),
    ]
    assert rows[0]["data"]["content"] == (
        "Figure 1 Flow diagram of Phases I, II & III of the Cretan Aging Cohort study."
    )
    assert "<figcaption>" not in rows[0]["data"]["content"]


@pytest.mark.asyncio
async def test_split_html_caption_opening_fragment_gets_plain_context_row():
    source = (
        "<figure>\n<figcaption><strong>Figure 1</strong> Flow diagram of "
        "Phases I, II & III of the Cretan Aging Cohort study."
    )
    request = {"source_units": [{"id": "S1", "text": source}],
               "caption_unit_ids": ["S1"]}

    class SplitMarkupCaptionLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return (
                r"B T36 B1 | sum=<figure>\n<figcaption><strong>Figure 1</strong> "
                r"Flow diagram of Phases I, II & III of the Cretan Aging Cohort study. "
                r"| unit=S1"
            )

    rows, step = await extract_structural_rows(
        SplitMarkupCaptionLLM(), request, ["S1"],
    )

    assert step["retries"] == 0
    assert [(row["blockType"], row["data"]["unit"]) for row in rows] == [
        ("text", "S1"), ("image", "S1"),
    ]
    assert rows[0]["data"]["content"] == (
        "Figure 1 Flow diagram of Phases I, II & III of the Cretan Aging Cohort study."
    )
    assert "<figcaption>" not in rows[0]["data"]["content"]


def test_based_on_difficulty_repairs_rationale_as_copula_and_solution_relative():
    from knowledge_pipeline.prompts import DSL_SYSTEM
    from knowledge_pipeline.semantic_extraction import _source_grounded_repair

    source = (
        "Based on the difficulty in accessing the brain to collect tissues for "
        "processing from live animals, using induced pluripotent stem cell (iPSC) "
        "technology is a solution that could produce in vitro NSCs or neurons "
        "for transplantation."
    )
    main_clause, relative_clause = parse_dsl_rows("\n".join([
        "B T4 B6 | sub=accessing_the_brain_to_collect_tissues_for_processing_from_live_animals "
        "| pred=is_difficult | obj= | neg=true | epi=background_claim | unit=S237",
        "B T4 B7 | sub=induced_pluripotent_stem_cell_iPSC "
        "| pred=technology_is_a_solution_that_could_produce "
        "| obj=in_vitro_NSCs_or_neurons_for_transplantation "
        "| neg=false | epi=future_proposal | unit=S237",
    ]), ["S237"])

    assert _source_grounded_repair(
        main_clause, source, has_semantic_sibling=True,
    ) == (
        "B T4 B6 | sub=using induced pluripotent stem cell (iPSC) technology "
        "| pred=is | obj=a solution | neg=false | epi=background_claim "
        "| ctx=Based on the difficulty in accessing the brain to collect tissues "
        "for processing from live animals | unit=S237"
    )
    assert _source_grounded_repair(
        relative_clause, source, has_semantic_sibling=True,
    ) == (
        "B T4 B7 | sub=using induced pluripotent stem cell (iPSC) technology "
        "| pred=is | obj=a solution | neg=false | epi=future_proposal "
        "| ctx=Based on the difficulty in accessing the brain to collect tissues "
        "for processing from live animals | unit=S237"
    )
    assert "put the stated complement in `obj=`" in DSL_SYSTEM
    assert "the row must not say the reverse" in DSL_SYSTEM

    qwen_solution_row = parse_dsl_rows(
        "B T4 B9 | sub=using_induced_pluripotent_stem_cell_iPSC_technology "
        "| pred=is_a_solution "
        "| obj=that_could_produce_in_vitro_NS_Cs_or_neurons_for_transplantation "
        "| ctx=based_on_the_difficulty_in_accessing_the_brain | unit=S237",
        ["S237"],
    )[0]
    assert _source_grounded_repair(
        qwen_solution_row, source, has_semantic_sibling=True,
    ) == (
        "B T4 B9 | sub=using induced pluripotent stem cell (iPSC) technology "
        "| pred=is | obj=a solution | neg=false | ctx=Based on the difficulty "
        "in accessing the brain to collect tissues for processing from live animals "
        "| unit=S237"
    )

    from knowledge_pipeline.semantic_extraction import (
        _apply_exact_source_grounded_repairs, _row_validation_issues,
    )
    current_line = "\n".join([
        "B T4 B1 | sub=using induced pluripotent stem cell iPSC technology "
        "| pred=is_a_solution "
        "| obj=that could produce in vitro NSCs or neurons for transplantation "
        "| neg=false | epi=future_proposal "
        "| ctx=based on the difficulty in accessing the brain | unit=S237",
        "B T4 B2 | sub=the difficulty in accessing the brain to collect tissues "
        "for processing from live animals | pred=justifies_the_use_of "
        "| obj=iPSC technology for producing in vitro NSs or neurons | unit=S237",
    ])
    actual_row = parse_dsl_rows(current_line, ["S237"])
    repaired_rows, repaired_dsl, repaired_tags = _apply_exact_source_grounded_repairs(
        actual_row,
        {row["tag"]: line for row, line in zip(
            actual_row, current_line.splitlines(), strict=True,
        )},
        _row_validation_issues(actual_row),
        [{"id": "S237", "text": source}], ["S237"], [], set(),
    )
    assert [row["data"]["tag"] for row in repaired_rows] == ["B1", "B2"]
    assert repaired_rows[0]["data"]["predicate"] == "is"
    assert repaired_rows[1]["data"]["subject"] == "a solution"
    assert repaired_rows[1]["data"]["predicate"] == "could_produce"
    assert repaired_rows[1]["data"]["object"] == "in vitro NSCs or neurons for transplantation"
    assert repaired_dsl["B2"] == (
        "B T4 B2 | sub=a solution | pred=could_produce "
        "| obj=in vitro NSCs or neurons for transplantation | neg=false "
        "| epi=future_proposal | unit=S237"
    )
    assert repaired_tags == ["B1", "B2"]


def test_partial_relative_revelation_object_is_rebuilt_from_source_roles():
    from knowledge_pipeline.prompts import DSL_SYSTEM
    from knowledge_pipeline.semantic_extraction import _source_grounded_repair

    source = (
        "It is inferred from this that obesity plays a role in SNA inhibition and "
        "it is due to tonic activity of NPY, which further reveals an elevated "
        "α-MSH excitation [132]."
    )
    row = parse_dsl_rows(
        "B T4 B1 | sub=α-MSH excitation | pred=further_reveals | obj=elevated "
        "| neg=false | epi=inferred | ctx=due to tonic activity of NPY | unit=S166",
        ["S166"],
    )[0]

    assert _source_grounded_repair(row, source, has_semantic_sibling=True) == (
        "B T4 B1 | sub=tonic activity of NPY | pred=further_reveals "
        "| obj=an elevated α-MSH excitation | neg=false | epi=inferred | unit=S166"
    )
    assert "or a missing argument" in " ".join(DSL_SYSTEM.split())


def test_source_grounded_repair_keeps_observation_and_drops_neighbor_context():
    from knowledge_pipeline.semantic_extraction import _source_grounded_repair

    source = (
        "Neural precursors giving rise to different neurons were observed to have "
        "POMC gene expression [43]."
    )
    row = parse_dsl_rows(
        "B T4 B5 | sub=neural precursors | pred=had_POMC_gene_expression | obj= "
        "| neg=false | epi=observation | ctx=long term HFD feeding | unit=S48",
        ["S48"],
    )[0]
    repaired = _source_grounded_repair(row, source, has_semantic_sibling=True)
    assert repaired == (
        "B T4 B5 | sub=neural precursors | pred=were_observed_to_have "
        "| obj=POMC gene expression | neg=false | epi=observation | unit=S48"
    )

    relative_clause = parse_dsl_rows(
        "B T4 B4 | sub=neural precursors | pred=giving_rise_to "
        "| obj=different neurons | ctx=long term HFD feeding | unit=S48",
        ["S48"],
    )[0]
    assert _source_grounded_repair(
        relative_clause, source, has_semantic_sibling=True,
    ) == (
        "B T4 B4 | sub=neural precursors | pred=giving_rise_to "
        "| obj=different neurons | unit=S48"
    )


def test_source_grounded_repair_splits_observed_increase_and_relative_expectation():
    from knowledge_pipeline.semantic_extraction import _source_grounded_repair

    source = (
        "At follow-up, we noted a significant increase in the number of major "
        "medical morbidities, which is expected with advancing age."
    )
    observed = parse_dsl_rows(
        "B T4 B4 | sub=the number of major medical morbidities "
        "| pred=increased_significantly | obj= | neg=false "
        "| epi=experimental_result | ctx=aging | unit=S185",
        ["S185"],
    )[0]
    assert _source_grounded_repair(observed, source, True) == (
        "B T4 B4 | sub=we | pred=noted "
        "| obj=a significant increase in the number of major medical morbidities "
        "| neg=false | epi=experimental_result | ctx=At follow-up | unit=S185"
    )

    expected = parse_dsl_rows(
        "B T4 B5 | sub=the increase in the number of major medical morbidities "
        "| pred=is_expected_with | obj=advancing age | neg=false "
        "| epi=author_interpretation | ctx=aging | unit=S185",
        ["S185"],
    )[0]
    assert _source_grounded_repair(expected, source, True) == (
        "B T4 B5 | sub=a significant increase in the number of major medical morbidities "
        "| pred=is | obj=expected with advancing age | neg=false "
        "| epi=author_interpretation | unit=S185"
    )


def test_source_grounded_repair_rebuilds_coordinated_detected_changes():
    from knowledge_pipeline.semantic_extraction import (
        _apply_exact_source_grounded_repairs, _row_validation_issues,
        _source_grounded_repair,
    )

    source = (
        "Also, at follow-up, we detected a significant increase in self-reported anxiety "
        "symptoms along with a substantial rise in psychotropic medication use and "
        "incidence of major medical morbidities."
    )
    rows = parse_dsl_rows("\n".join([
        "B T4 B1 | sub=we | pred=detected | "
        "obj=a significant increase in self-reported anxiety symptoms | "
        "ctx=along with a substantial rise in psychotropic medication use and "
        "incidence of major medical morbidities | unit=S16",
        "B T4 B2 | sub=self-reported anxiety symptoms | pred=increased | obj= "
        "| sig=significant | unit=S16",
        "B T4 B3 | sub=psychotropic medication use | pred=rose | obj=substantial "
        "| sig=substantial | unit=S16",
        "B T4 B4 | sub=incidence of major medical morbidities | pred=increased | obj= "
        "| sig=substantial | unit=S16",
    ]), ["S16"])

    assert _source_grounded_repair(rows[1], source, True) == (
        "B T4 B2 | sub=we | pred=detected | "
        "obj=a significant increase in self-reported anxiety symptoms "
        "| ctx=at follow-up | unit=S16"
    )
    repaired, dsl, changed = _apply_exact_source_grounded_repairs(
        rows, {row["tag"]: "" for row in rows}, _row_validation_issues(rows),
        [{"id": "S16", "text": source}], ["S16"], [], set(),
    )
    assert [row["tag"] for row in repaired] == ["B1", "B3", "B4"]
    assert [row["data"]["object"] for row in repaired] == [
        "a significant increase in self-reported anxiety symptoms",
        "a substantial rise in psychotropic medication use",
        "a substantial rise in incidence of major medical morbidities",
    ]
    assert "B2" not in dsl
    assert set(changed) >= {"B1", "B2", "B3", "B4"}


def test_source_grounded_repair_keeps_ambiguous_role_as_copular_claim():
    from knowledge_pipeline.semantic_extraction import _source_grounded_repair

    source = (
        "These neurons are in arcuate nucleus (ArcN), which projects to various sites "
        "in the hypothalamus, including the PVN, and regulates autonomic activity; "
        "however, the role of PVN MC3/4 is ambiguous."
    )
    row = parse_dsl_rows(
        "B T4 B9 | sub=PVN MC3/4 | pred=has_ambiguous_role | obj= | unit=S156",
        ["S156"],
    )[0]

    assert _source_grounded_repair(row, source, has_semantic_sibling=True) == (
        "B T4 B9 | sub=the role of PVN MC3/4 | pred=is | obj=ambiguous | unit=S156"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("model_row", [
    "B T3 B1 | content=As life expectancy increases, cognitive impairment becomes "
    "an inextricable facet of aging. | unit=S18",
    "B T36 B1 | sum=As life expectancy increases, cognitive impairment becomes "
    "an inextricable facet of aging. | unit=S18",
])
async def test_heading_plus_copular_claim_is_repaired_without_model_retry(model_row):
    source = (
        "## 1. Introduction\n"
        "As life expectancy increases, cognitive impairment becomes an inextricable facet of aging."
    )
    llm = FakeLLM(model_row, calls=[])
    rows, _ = await extract_structural_rows(
        llm, {"source_units": [{"id": "S18", "text": source}]}, ["S18"],
    )

    assert len(llm.calls) == 1
    assert [(row["blockType"], row["data"].get("content"), row["data"].get("subject"))
            for row in rows] == [
        ("text", "## 1. Introduction", None),
        ("statement", None, "cognitive impairment"),
    ]
    statement = rows[1]["data"]
    assert statement["predicate"] == "becomes"
    assert statement["object"] == "an inextricable facet of aging"
    assert statement["context"] == "as life expectancy increases"


def test_targeted_pvalue_repair_rejects_values_not_reported_by_source():
    from knowledge_pipeline.semantic_extraction import (
        _accepted_targeted_rows, _row_validation_issues,
    )

    source_units = [{"id": "S1", "text": "The result was significant (p = 0.059)."}]
    original = parse_dsl_rows(
        "B T4 B1 | sub=result | pred=was | obj=significant | p=0.059 | unit=S1",
        ["S1"],
    )
    patch_rows = parse_dsl_rows("\n".join([
        "B T4 B1 | sub=result | pred=was | obj=significant | unit=S1",
        "B T27 B2 | p=0.058 | unit=S1",
    ]), ["S1"])
    accepted, errors = _accepted_targeted_rows(
        patch_rows, original, _row_validation_issues(original), [], [], [],
        source_units=source_units,
        missing_pvalue_units={"S1": ["0.059"]},
    )

    assert [row["tag"] for row in accepted] == ["B1"]
    assert any("not reported in source unit S1" in error for error in errors)
    assert any("did not add typed p-values for S1: p=0.059" in error for error in errors)


def test_targeted_pvalue_repair_renumbers_reused_tags_and_preserves_every_value():
    from knowledge_pipeline.semantic_extraction import _accepted_targeted_rows

    source = (
        "The diagnosis frequency did not vary significantly (p = 0.6 and p = 0.2); "
        "a separate result was reported (p < 0.001)."
    )
    rows = parse_dsl_rows(
        "B T4 B11 | sub=participants | pred=reported | obj=results | unit=S167",
        ["S167"],
    )
    patch_rows = parse_dsl_rows("\n".join([
        "B T27 B7 | p=<0.001 | unit=S167",
        "B T27 B8 | p=0.6 | unit=S167",
        "B T27 B9 | p=0.2 | unit=S167",
    ]), ["S167"])

    accepted, errors = _accepted_targeted_rows(
        patch_rows, rows, [], [], [], [], source_units=[{"id": "S167", "text": source}],
        missing_pvalue_units={"S167": ["<0.001", "0.6", "0.2"]},
    )

    assert not errors
    assert [row["tag"] for row in accepted] == ["B12", "B13", "B14"]
    assert [row["data"]["tag"] for row in accepted] == ["B12", "B13", "B14"]
    assert [row["data"]["pValue"] for row in accepted] == ["<0.001", 0.6, 0.2]


def test_targeted_objectless_result_retype_is_accepted_and_reported_for_review():
    from knowledge_pipeline.semantic_extraction import (
        _accepted_targeted_rows, _row_validation_issues,
    )

    source = (
        "Anxiety symptoms increased, although the frequency of anxiety diagnosis "
        "did not vary significantly (p = 0.6)."
    )
    original = parse_dsl_rows("\n".join([
        "B T4 B1 | sub=participants | pred=reported | obj=increased anxiety symptoms | unit=S1",
        "B T4 B2 | sub=the frequency of anxiety diagnosis | "
        "pred=did_not_vary_significantly | obj= | unit=S1",
    ]), ["S1"])
    clause_row = parse_dsl_rows(
        "B T36 B2 | sum=the frequency of anxiety diagnosis did not vary significantly | unit=S1",
        ["S1"],
    )
    whole_unit_row = parse_dsl_rows(
        "B T36 B2 | sum=" + source + " | unit=S1", ["S1"],
    )
    issues = _row_validation_issues(original)
    reviewed = []

    accepted_clause, clause_errors = _accepted_targeted_rows(
        clause_row, original, issues, [], [], [],
        source_units=[{"id": "S1", "text": source}],
        reviewed_objectless_retypes=reviewed,
    )
    accepted_whole, whole_errors = _accepted_targeted_rows(
        whole_unit_row, original, issues, [], [], [],
        source_units=[{"id": "S1", "text": source}],
        reviewed_objectless_retypes=reviewed,
    )

    assert [row["blockType"] for row in accepted_clause] == ["result"]
    assert not clause_errors
    assert [row["blockType"] for row in accepted_whole] == ["result"]
    assert not whole_errors
    assert reviewed == [
        ("S1", "B2", "the frequency of anxiety diagnosis did not vary significantly"),
        ("S1", "B2", source),
    ]

    empty_summary = parse_dsl_rows(
        "B T36 B2 | sum= | unit=S1", ["S1"],
    )
    accepted_empty, empty_errors = _accepted_targeted_rows(
        empty_summary, original, issues, [], [], [],
        source_units=[{"id": "S1", "text": source}],
    )
    assert accepted_empty == []
    assert any("lacks required fields: sum" in error for error in empty_errors)


def test_semantic_audit_cannot_undo_repaired_objectless_t4_result():
    from knowledge_pipeline.semantic_extraction import (
        _preserve_objectless_result_retypes,
    )

    summary = "The pathway became active after treatment."
    candidate = parse_dsl_rows(
        "B T36 B2 | sum=" + summary + " | unit=S1", ["S1"],
    )
    audited = parse_dsl_rows(
        "B T4 B2 | sub=The pathway | pred=became_active "
        "| obj=the pathway | ctx=after treatment | unit=S1",
        ["S1"],
    )

    preserved, units = _preserve_objectless_result_retypes(
        audited, candidate, [("S1", "B2", summary)],
    )

    assert units == ["S1"]
    assert [(row["tag"], row["blockType"], row["data"].get("resultsSummary"))
            for row in preserved] == [("B2", "result", summary)]


def test_pipeline_keeps_objectless_retype_review_warning_after_final_diagnostics():
    finding = {
        "severity": "warning", "code": "objectless_t4_retyped",
        "unit": "S1", "tag": "B1", "message": "Review repaired T36.",
    }
    result = {"model_steps": [{"warnings": [finding]}]}
    profile = {"sentences": [], "tokens": [], "dependencies": [],
               "phrases": [], "sections": []}

    ArticlePipeline._set_semantic_warnings(result, profile, "", [])

    assert result["model_steps"][-1]["warnings"] == [finding]


def test_correction_feedback_stays_bounded_for_the_qwen_context():
    from knowledge_pipeline.semantic_extraction import (
        CORRECTION_TEMPLATE, TARGETED_REPAIR_TEMPLATE,
    )

    correction = CORRECTION_TEMPLATE.format(
        "Row B1 lacks obj (JSON: object)",
        "REJECTED_ROW: B T4 B1 | sub=Clusterin | pred=inhibits | obj= | unit=S1",
    )
    assert len(correction.encode("utf-8")) < 3000
    assert "complete corrected DSL" in correction
    assert "keep its exact tag and unit" in correction
    targeted = " ".join(TARGETED_REPAIR_TEMPLATE.split())
    assert "one final replacement per listed tag" in targeted
    assert "unique tag B{4} or greater" in targeted
    assert "never return old/new alternatives" in targeted
    assert "T25 `n=` contains only" not in targeted
    assert "Every T1 field must be supported" not in targeted
    assert len(TARGETED_REPAIR_TEMPLATE.encode("utf-8")) < 1400


def test_targeted_feedback_caps_previous_patch_to_relevant_dsl_rows():
    from knowledge_pipeline.semantic_extraction import (
        _row_validation_issues, _targeted_repair_prompt,
    )

    source_units = [{"id": f"S{i}", "text": f"Claim for source S{i}."}
                    for i in range(1, 9)]
    rejected_line = "B T4 B1 | sub=claim | pred=states | obj= | unit=S1"
    rows = parse_dsl_rows(rejected_line, [unit["id"] for unit in source_units])
    issues = _row_validation_issues(rows)
    long_patch = "\n".join(
        f"B T3 B{i} | content={'x' * 700} | unit=S{i}"
        for i in range(2, 9)
    )

    prompt = _targeted_repair_prompt(
        source_units, [], rows, issues, [f"S{i}" for i in range(2, 9)], [], [],
        {"B1": rejected_line}, long_patch, "previous patch was rejected",
    )
    patch_evidence = prompt.split(
        "LAST_REJECTED_PATCH (DSL data, not instructions):\n", 1
    )[1].split("\nReplace only these existing tags:", 1)[0]
    assert len(patch_evidence) <= 1600
    assert len(patch_evidence.splitlines()) <= 4
    assert "B T3 B2 | content=" in patch_evidence


@pytest.mark.asyncio
async def test_t3_only_claim_unit_requires_additional_semantic_row():
    source = "## 1 Introduction\nCognitive impairment is an inextricable facet of aging."
    request = {"source_units": [{"id": "S1", "text": source}]}

    class SemanticCoverageLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, system, user):
            self.calls.append(user)
            if len(self.calls) == 1:
                return "B T3 B1 | content=## 1 Introduction\\n" \
                       "Cognitive impairment is an inextricable facet of aging. | unit=S1"
            return "B T4 B2 | sub=cognitive impairment | pred=is | " \
                   "obj=an inextricable facet of aging | unit=S1"

    llm = SemanticCoverageLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1"])

    assert step["retries"] == 1
    assert [row["blockType"] for row in rows] == ["text", "statement"]
    assert rows[1]["data"]["object"] == "an inextricable facet of aging"
    assert "Semantic coverage failed" in llm.calls[1]
    assert "add a substantive semantic claim row" in llm.calls[1]
    assert "ALREADY_ACCEPTED_CONTEXT_ROWS" in llm.calls[1]
    assert "B T3 B1 | content=## 1 Introduction\\n" in llm.calls[1]


@pytest.mark.parametrize("source", [
    "A detailed description of the study protocol is provided below.",
    "Some limitations of the current protocol should be discussed.",
])
@pytest.mark.asyncio
async def test_editorial_signposting_t3_does_not_trigger_false_semantic_coverage(source):
    request = {"source_units": [{"id": "S1", "text": source}]}

    class EditorialContextLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return "B T3 B1 | content=" + source + " | unit=S1"

    rows, step = await extract_structural_rows(EditorialContextLLM(), request, ["S1"])

    assert step["retries"] == 0
    assert len(rows) == 1
    assert rows[0]["blockType"] == "text"
    assert rows[0]["data"]["content"] == source


@pytest.mark.asyncio
async def test_context_rejected_correction_preserves_dsl_for_error_artifact():
    from knowledge_pipeline.semantic_extraction import DslExtractionError

    request = {"source_units": [{"id": "S1", "text": "Clusterin inhibits inflammation."}]}
    invalid = "B T4 B1 | sub=Clusterin | pred=inhibits | obj= | unit=S1"

    class ContextFailingLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, system, user):
            self.calls.append(user)
            if len(self.calls) < 3:
                return invalid
            raise ValidationError("Full article and schema exceed the configured context budget")

    llm = ContextFailingLLM()
    with pytest.raises(DslExtractionError) as raised:
        await extract_structural_rows(llm, request, ["S1"])

    assert len(raised.value.rejected_dsl) == 2
    assert all(invalid in rejected for rejected in raised.value.rejected_dsl)


def test_prompt_catalog_exposes_only_dsl_keys():
    from knowledge_contracts.block_dsl import DSL_FIELDS, render_field_docs
    from knowledge_contracts.block_types import ALL_TYPES, KEY_TO_LEGACY_INT
    from knowledge_pipeline.prompts import DSL_SYSTEM, type_doc_with_codes

    catalog = type_doc_with_codes()
    prompt = DSL_SYSTEM % catalog
    statement_line = next(line for line in catalog.splitlines() if " T4 statement:" in line)
    assert "sub=<plain>" in statement_line
    assert "subop=<plain>" in statement_line
    assert "subref=<ref>" in statement_line
    assert "pred=<plain>" in statement_line
    assert "obj=<plain>" in statement_line
    assert "object=" not in statement_line
    assert len(prompt) < 37_000
    for block_type in ALL_TYPES:
        code = KEY_TO_LEGACY_INT[block_type]
        line = next(row for row in catalog.splitlines()
                    if f" T{code} {block_type}:" in row)
        assert render_field_docs(block_type) in line
        for dsl_key in DSL_FIELDS[block_type]:
            assert f"{dsl_key}=" in line
    assert "SOURCE-UNIT EVIDENCE AND COVERAGE" in prompt
    assert "INPUT LEDGER" in prompt and "Follow UNIT_ORDER" in prompt
    assert "Treat every S<n> as an independent evidence boundary" in prompt
    assert "it must not supply a separate claim" in prompt
    assert "suffix is repeated on every row, not once for the batch" in prompt
    assert "spaces alone never separate fields" in prompt
    assert "Each type permits only its catalogued keys" in prompt
    assert "use T4 only as the last resort" in prompt
    assert "Never output T49" in prompt
    assert "A T3 row may" in prompt and "accompany semantic rows" in prompt
    assert "The word “significant” alone is not a numeric p-value" in prompt
    assert "Inventory every source-expressed predication in grammatical order" in prompt
    assert "A heading never supplies the subject" in prompt
    assert "the row must not say the reverse" in prompt
    assert "T36 is only for reported findings" in " ".join(prompt.split())
    assert "Caption: never copy HTML or emit T49; pipeline creates it." in prompt
    assert "BEGIN_FIELD_CATALOG" in prompt
    assert not any(term in prompt for term in (
        "Ki67", "BrdU-labeled", "Nrf2", "SOD2", "GnRH secretion",
        "Such factors", "fasted animals",
    ))
    method_code = KEY_TO_LEGACY_INT["method"]
    expectations_code = KEY_TO_LEGACY_INT["expectations"]
    assert method_code == 21 and expectations_code == 9
    assert f"T{method_code} method" in prompt
    assert f"T{expectations_code} expectations" in prompt
    assert "Use the exact DSL keys" in prompt
    assert "srcs=" in prompt and "unit=S<n>" in prompt

    lines = set(catalog.splitlines())
    for block_type in ALL_TYPES:
        expected = f"  T{KEY_TO_LEGACY_INT[block_type]} {block_type}: {render_field_docs(block_type)}"
        assert expected in lines
        for dsl_key in DSL_FIELDS[block_type]:
            assert f"{dsl_key}=<" in expected
def test_prompt_catalog_covers_every_structural_type_in_specification():
    from pathlib import Path
    from knowledge_contracts.block_types import ALL_TYPES
    from knowledge_pipeline.prompts import type_doc_with_codes

    specification = Path(__file__).resolve().parents[4] / "Спецификация.md"
    spec_types = set(re.findall(
        r"Обозн\w*ение\s*:\s*`([^`]+)`",
        specification.read_text(encoding="utf-8"),
    ))
    catalog_types = {
        match.group(1)
        for line in type_doc_with_codes().splitlines()
        if (match := re.match(r"\s*T\d+\s+([a-z_]+):", line))
    }
    assert spec_types == set(ALL_TYPES) == catalog_types


def _coordination_profile(source):
    tokens = []
    token_ids = {}
    for index, match in enumerate(re.finditer(r"[A-Za-z]+", source), 1):
        token_id = f"t{index}"
        word = match.group()
        token_ids[word.casefold()] = token_id
        tokens.append({
            "id": token_id, "sentence_id": "sent1", "text": word,
            "lemma": word.casefold().rstrip("s"), "pos": "VERB" if word.casefold() == "include" else "NOUN",
            "start": match.start(), "end": match.end(),
        })
    relations = [
        ("include", "Factors", "nsubj"),
        ("include", "quality", "obj"),
        ("quality", "sleep", "compound"),
        ("quality", "quantity", "conj"),
    ]
    dependencies = [
        {"source": token_ids[head.casefold()], "target": token_ids[dependent.casefold()],
         "relation": relation}
        for head, dependent, relation in relations
    ]
    return {"tokens": tokens, "dependencies": dependencies}


def _dependency_profile(source, relations):
    tokens = []
    token_ids = {}
    for index, match in enumerate(re.finditer(r"[A-Za-z]+", source), 1):
        token_id = f"t{index}"
        word = match.group()
        token_ids[word.casefold()] = token_id
        tokens.append({
            "id": token_id, "sentence_id": "sent1", "text": word,
            "lemma": word.casefold().rstrip("s"), "pos": "NOUN",
            "start": match.start(), "end": match.end(),
        })
    dependencies = [
        {"source": token_ids[head.casefold()], "target": token_ids[dependent.casefold()],
         "relation": relation}
        for head, dependent, relation in relations
    ]
    return {"tokens": tokens, "dependencies": dependencies}


def test_dependency_semantic_gate_detects_reversed_roles_and_collapsed_list():
    from knowledge_pipeline.semantic_extraction import _dependency_semantic_issues

    source = "Factors may include sleep quality and quantity."
    profile = _coordination_profile(source)
    units = [{"id": "S1", "text": source, "start": 0, "end": len(source)}]
    rows = parse_dsl_rows(
        "B T4 B1 | sub=sleep quality and quantity | pred=includes | "
        "obj=factors | unit=S1",
        ["S1"],
    )

    issues, additions = _dependency_semantic_issues(rows, units, profile)

    assert len(issues) == 1
    assert "roles reverse the source dependency frame" in issues[0][1]
    assert "collapses 2 coordinated source object targets" in issues[0][1]
    assert additions == ["S1"]


def test_dependency_semantic_gate_rejects_coordinated_targets_out_of_source_order():
    from knowledge_pipeline.semantic_extraction import _dependency_semantic_issues

    source = "Factors may include sleep quality and quantity."
    profile = _coordination_profile(source)
    units = [{"id": "S1", "text": source, "start": 0, "end": len(source)}]
    out_of_order = parse_dsl_rows("\n".join([
        "B T4 B1 | sub=factors | pred=may_include | obj=sleep quantity | unit=S1",
        "B T4 B2 | sub=factors | pred=may_include | obj=sleep quality | unit=S1",
    ]), ["S1"])

    issues, additions = _dependency_semantic_issues(out_of_order, units, profile)

    assert [row["tag"] for row, _ in issues] == ["B1", "B2"]
    assert all("out of source order" in message for _, message in issues)
    assert all("required order is 'sleep quality'; 'sleep quantity'" in message
               for _, message in issues)
    assert additions == []

    ordered = parse_dsl_rows("\n".join([
        "B T4 B1 | sub=factors | pred=may_include | obj=sleep quality | unit=S1",
        "B T4 B2 | sub=factors | pred=may_include | obj=sleep quantity | unit=S1",
    ]), ["S1"])
    ordered_issues, ordered_additions = _dependency_semantic_issues(
        ordered, units, profile,
    )
    assert ordered_issues == []
    assert ordered_additions == []


@pytest.mark.asyncio
async def test_dependency_semantic_gate_repairs_a_reversed_collapsed_list():
    source = "Factors may include sleep quality and quantity."
    profile = _coordination_profile(source)
    initial = (
        "B T4 B1 | sub=sleep quality and quantity | pred=includes | "
        "obj=factors | unit=S1"
    )
    corrected = "\n".join([
        "B T4 B1 | sub=factors | pred=include | obj=sleep quality | unit=S1",
        "B T4 B2 | sub=factors | pred=include | obj=quantity | unit=S1",
    ])

    class RepairingLLM:
        def __init__(self):
            self.responses = [initial, corrected]
            self.calls = []

        async def __call__(self, system, user):
            self.calls.append(user)
            return self.responses.pop(0)

    llm = RepairingLLM()
    rows, _ = await extract_structural_rows(
        llm,
        {"source_units": [{"id": "S1", "text": source,
                           "start": 0, "end": len(source)}],
         "linguistic_profile": profile},
        ["S1"],
    )

    assert len(llm.calls) == 2
    assert "roles reverse the source dependency frame" in llm.calls[1]
    assert "collapses 2 coordinated source object targets" in llm.calls[1]
    assert [(row["data"]["subject"], row["data"]["predicate"],
             row["data"]["object"]) for row in rows] == [
        ("factors", "include", "sleep quality"),
        ("factors", "include", "quantity"),
    ]


def test_dependency_semantic_gate_resolves_relative_subject_to_antecedent():
    from knowledge_pipeline.semantic_extraction import _dependency_semantic_issues

    source = "Identifying modifiable factors that may predict decline is critical."
    profile = _dependency_profile(source, [
        ("factors", "predict", "acl:relcl"),
        ("predict", "that", "nsubj"),
        ("predict", "decline", "dobj"),
    ])
    units = [{"id": "S1", "text": source, "start": 0, "end": len(source)}]
    reversed_row = parse_dsl_rows(
        "B T4 B1 | sub=decline | pred=predicts | obj=factors | unit=S1",
        ["S1"],
    )
    correct_row = parse_dsl_rows(
        "B T4 B1 | sub=factors | pred=predicts | obj=decline | unit=S1",
        ["S1"],
    )

    issues, _ = _dependency_semantic_issues(reversed_row, units, profile)
    assert len(issues) == 1
    assert "roles reverse the source dependency frame" in issues[0][1]
    assert "sub=factors" in issues[0][1]
    assert "obj=decline" in issues[0][1]
    assert _dependency_semantic_issues(correct_row, units, profile) == ([], [])


def test_dependency_semantic_gate_requires_a_separate_matrix_copular_claim():
    from knowledge_pipeline.semantic_extraction import _dependency_semantic_issues

    source = "Identifying modifiable factors that may predict decline is critical."
    profile = _dependency_profile(source, [
        ("factors", "modifiable", "amod"),
        ("Identifying", "factors", "dobj"),
        ("factors", "predict", "acl:relcl"),
        ("predict", "that", "nsubj"),
        ("predict", "decline", "dobj"),
        ("predict", "may", "aux"),
        ("critical", "Identifying", "csubj"),
        ("critical", "is", "cop"),
    ])
    units = [{"id": "S1", "text": source, "start": 0, "end": len(source)}]
    embedded_only = parse_dsl_rows(
        "B T4 B1 | sub=modifiable factors | pred=may predict | "
        "obj=decline | unit=S1",
        ["S1"],
    )
    complete = parse_dsl_rows("\n".join([
        "B T4 B1 | sub=Identifying modifiable factors | pred=is | "
        "obj=critical | unit=S1",
        "B T4 B2 | sub=modifiable factors | pred=may predict | "
        "obj=decline | unit=S1",
    ]), ["S1"])

    issues, additional_units = _dependency_semantic_issues(
        embedded_only, units, profile
    )
    assert additional_units == ["S1"]
    assert len(issues) == 1
    assert "missing separate matrix copular assertion" in issues[0][1]
    assert "full clause subject includes 'Identifying modifiable factors'" in issues[0][1]
    assert "sub='Identifying modifiable factors'" in issues[0][1]
    assert "pred=is" in issues[0][1]
    assert "obj='critical'" in issues[0][1]
    assert _dependency_semantic_issues(complete, units, profile) == ([], [])


def test_dependency_semantic_gate_rejects_incomplete_or_misattributed_matrix_subject():
    from knowledge_pipeline.semantic_extraction import _dependency_semantic_issues

    source = "Identifying modifiable factors that may predict decline is critical."
    profile = _dependency_profile(source, [
        ("factors", "modifiable", "amod"),
        ("Identifying", "factors", "dobj"),
        ("factors", "predict", "acl:relcl"),
        ("predict", "that", "nsubj"),
        ("predict", "decline", "dobj"),
        ("predict", "may", "aux"),
        ("critical", "Identifying", "csubj"),
        ("critical", "is", "cop"),
    ])
    units = [{"id": "S1", "text": source, "start": 0, "end": len(source)}]
    rows = parse_dsl_rows("\n".join([
        "B T4 B1 | sub=modifiable factors | pred=may predict | "
        "obj=decline | unit=S1",
        "B T4 B2 | sub=Identifying | pred=is | obj=critical | unit=S1",
        "B T4 B3 | sub=decline | pred=is | obj=critical | unit=S1",
    ]), ["S1"])

    issues, additions = _dependency_semantic_issues(rows, units, profile)
    by_tag = {row["tag"]: message for row, message in issues}
    assert additions == ["S1"]
    assert "misassigned or incomplete matrix copular subject" in by_tag["B2"]
    assert "Identifying modifiable factors" in by_tag["B2"]
    assert "misassigned or incomplete matrix copular subject" in by_tag["B3"]
    assert "sub='decline'" in by_tag["B3"]


def test_dependency_semantic_gate_names_shared_heads_in_collapsed_targets():
    from knowledge_pipeline.semantic_extraction import _dependency_semantic_issues

    source = "Factors may include poor sleep quality and quantity."
    profile = _dependency_profile(source, [
        ("include", "factors", "nsubj"),
        ("include", "may", "aux"),
        ("include", "quality", "dobj"),
        ("quality", "poor", "amod"),
        ("quality", "sleep", "compound"),
        ("quality", "quantity", "conj"),
    ])
    units = [{"id": "S1", "text": source, "start": 0, "end": len(source)}]
    collapsed = parse_dsl_rows(
        "B T4 B1 | sub=factors | pred=may include | "
        "obj=poor sleep quality and quantity | unit=S1",
        ["S1"],
    )
    corrected = parse_dsl_rows("\n".join([
        "B T4 B1 | sub=factors | pred=may include | obj=poor sleep quality | unit=S1",
        "B T4 B2 | sub=factors | pred=may include | obj=sleep quantity | unit=S1",
    ]), ["S1"])

    issues, additions = _dependency_semantic_issues(collapsed, units, profile)
    assert additions == ["S1"]
    assert "'poor sleep quality'; 'sleep quantity'" in issues[0][1]
    assert _dependency_semantic_issues(corrected, units, profile) == ([], [])


def test_dependency_semantic_gate_does_not_carry_compounds_across_list_boundaries():
    from knowledge_pipeline.semantic_extraction import _dependency_semantic_issues

    source = (
        "Factors may include poor sleep quality and quantity, sleep-related breathing "
        "disorders, inflammatory cytokines and stress hormones, as well as mental health problems."
    )
    profile = _dependency_profile(source, [
        ("include", "factors", "nsubj"),
        ("include", "may", "aux"),
        ("include", "quality", "dobj"),
        ("quality", "poor", "amod"),
        ("quality", "sleep", "compound"),
        ("quality", "quantity", "conj"),
        ("quality", "disorders", "conj"),
        ("disorders", "breathing", "compound"),
        ("disorders", "related", "compound"),
        ("disorders", "cytokines", "conj"),
        ("cytokines", "inflammatory", "amod"),
        ("cytokines", "hormones", "conj"),
        ("hormones", "stress", "compound"),
        ("disorders", "problems", "conj"),
        ("problems", "mental", "compound"),
        ("problems", "health", "compound"),
    ])
    for comma_number, position in enumerate(
        [match.start() for match in re.finditer(",", source)], start=1
    ):
        profile["tokens"].append({
            "id": f"comma{comma_number}", "sentence_id": "sent1", "text": ",",
            "lemma": ",", "pos": "PUNCT", "is_punct": True,
            "start": position, "end": position + 1,
        })
    units = [{"id": "S1", "text": source, "start": 0, "end": len(source)}]
    collapsed = parse_dsl_rows(
        "B T4 B1 | sub=factors | pred=may include | "
        "obj=inflammatory cytokines and stress hormones | unit=S1",
        ["S1"],
    )

    issues, _ = _dependency_semantic_issues(collapsed, units, profile)
    assert "'inflammatory cytokines'; 'stress hormones'" in issues[0][1]
    assert "sleep inflammatory" not in issues[0][1]


def test_dependency_semantic_gate_requires_source_modality():
    from knowledge_pipeline.semantic_extraction import _dependency_semantic_issues

    source = "Factors may include sleep quality."
    profile = _dependency_profile(source, [
        ("include", "factors", "nsubj"),
        ("include", "quality", "dobj"),
        ("quality", "sleep", "compound"),
        ("include", "may", "aux"),
    ])
    units = [{"id": "S1", "text": source, "start": 0, "end": len(source)}]
    omitted = parse_dsl_rows(
        "B T4 B1 | sub=factors | pred=include | obj=sleep quality | unit=S1",
        ["S1"],
    )
    retained = parse_dsl_rows(
        "B T4 B1 | sub=factors | pred=may include | obj=sleep quality | unit=S1",
        ["S1"],
    )

    issues, _ = _dependency_semantic_issues(omitted, units, profile)
    assert len(issues) == 1
    assert "omits source modality 'may'" in issues[0][1]
    assert "pred=may include" in issues[0][1]
    assert _dependency_semantic_issues(retained, units, profile) == ([], [])


def test_dependency_semantic_gate_preserves_nmod_population_and_condition_qualifiers():
    from knowledge_pipeline.semantic_extraction import _dependency_semantic_issues

    source = "Factors may predict decline in the elderly with adequate daily functionality."
    profile = _dependency_profile(source, [
        ("predict", "factors", "nsubj"),
        ("predict", "may", "aux"),
        ("predict", "decline", "dobj"),
        ("decline", "elderly", "nmod"),
        ("elderly", "in", "case"),
        ("elderly", "the", "det"),
        ("decline", "functionality", "nmod"),
        ("functionality", "with", "case"),
        ("functionality", "adequate", "amod"),
        ("functionality", "daily", "amod"),
    ])
    units = [{"id": "S1", "text": source, "start": 0, "end": len(source)}]
    omitted = parse_dsl_rows(
        "B T4 B1 | sub=factors | pred=may predict | obj=decline | unit=S1",
        ["S1"],
    )
    retained = parse_dsl_rows(
        "B T4 B1 | sub=factors | pred=may predict | obj=decline | "
        "ctx=the elderly with adequate daily functionality | unit=S1",
        ["S1"],
    )

    issues, additions = _dependency_semantic_issues(omitted, units, profile)
    assert additions == []
    assert len(issues) == 1
    assert "omits source-dependent nominal phrase 'in the elderly'" in issues[0][1]
    assert "omits source-dependent nominal phrase 'with adequate daily functionality'" in issues[0][1]
    assert "obj= or ctx=" in issues[0][1]
    assert _dependency_semantic_issues(retained, units, profile) == ([], [])


def test_dependency_semantic_gate_ignores_nonessential_such_modifier():
    from knowledge_pipeline.semantic_extraction import _dependency_semantic_issues

    source = "Such factors include sleep quality."
    profile = _dependency_profile(source, [
        ("include", "factors", "nsubj"),
        ("factors", "Such", "amod"),
        ("include", "quality", "dobj"),
        ("quality", "sleep", "compound"),
    ])
    units = [{"id": "S1", "text": source, "start": 0, "end": len(source)}]
    rows = parse_dsl_rows(
        "B T4 B1 | sub=factors | pred=include | obj=sleep quality | unit=S1",
        ["S1"],
    )

    assert _dependency_semantic_issues(rows, units, profile) == ([], [])


def test_document_reporting_sentence_is_preserved_as_t3():
    from knowledge_pipeline.semantic_extraction import _add_pipeline_rows

    source = "This work reports the study methodology and follow-up schedule."
    rows = _add_pipeline_rows(
        [], [], [], [{"id": "S1", "text": source}], ["S1"],
    )

    assert len(rows) == 1
    assert rows[0]["blockType"] == "text"
    assert rows[0]["data"]["content"] == source


def test_exact_t3_document_signpost_covers_nonassertional_unit_only():
    from knowledge_pipeline.dsl_rows import parse_dsl_rows
    from knowledge_pipeline.semantic_extraction import _semantic_coverage_missing_units

    source = "This work reports the study methodology and follow-up schedule."
    unit = {"id": "S1", "text": source, "start": 0, "end": len(source)}
    signpost_profile = _dependency_profile(source, [
        ("reports", "work", "nsubj"),
        ("reports", "methodology", "dobj"),
    ])
    signpost_row = parse_dsl_rows(
        "B T3 B1 | content=" + source + " | unit=S1", ["S1"],
    )

    assert _semantic_coverage_missing_units(
        signpost_row, [unit], linguistic_profile=signpost_profile,
    ) == []

    factual_source = "This work reports that participants improved."
    factual_unit = {
        "id": "S1", "text": factual_source,
        "start": 0, "end": len(factual_source),
    }
    factual_profile = _dependency_profile(factual_source, [
        ("reports", "work", "nsubj"),
        ("reports", "improved", "ccomp"),
        ("improved", "participants", "nsubj"),
    ])
    factual_t3 = parse_dsl_rows(
        "B T3 B1 | content=" + factual_source + " | unit=S1", ["S1"],
    )

    assert _semantic_coverage_missing_units(
        factual_t3, [factual_unit], linguistic_profile=factual_profile,
    ) == ["S1"]


def test_sample_size_row_does_not_cover_reported_cohort_disposition():
    from knowledge_pipeline.semantic_extraction import (
        _accepted_targeted_rows, _semantic_coverage_missing_units,
    )

    source = "In total, 151 individuals completed the Phase III evaluation."
    unit = {"id": "S1", "text": source, "start": 0, "end": len(source)}
    count_only = parse_dsl_rows(
        "B T25 B1 | n=151 | unit=S1", ["S1"],
    )
    assert _semantic_coverage_missing_units(count_only, [unit]) == ["S1"]
    count_patch = parse_dsl_rows("B T25 B2 | n=151 | unit=S1", ["S1"])
    accepted, errors = _accepted_targeted_rows(
        count_patch, count_only, [], [], ["S1"], [], source_units=[unit],
    )
    assert accepted == []
    assert any("not a context or typed-value row" in error for error in errors)

    standalone_count = "In total, 151 individuals."
    standalone_unit = {
        "id": "S1", "text": standalone_count,
        "start": 0, "end": len(standalone_count),
    }
    standalone_row = parse_dsl_rows(
        "B T25 B1 | n=151 | unit=S1", ["S1"],
    )
    assert _semantic_coverage_missing_units(standalone_row, [standalone_unit]) == []


@pytest.mark.asyncio
async def test_counted_event_requires_integer_sample_size_and_separate_claim_row():
    from knowledge_pipeline.semantic_extraction import _row_validation_issues

    source = "In total, 151 individuals completed the Phase III evaluation."
    request = {"source_units": [{"id": "S1", "text": source}]}
    malformed_count = (
        "B T25 B1 | n=151 individuals completed the Phase III evaluation | unit=S1"
    )
    corrected = "\n".join([
        "B T25 B1 | n=151 | unit=S1",
        "B T36 B2 | sum=151 individuals completed the Phase III evaluation | unit=S1",
    ])

    class CountedEventRepairLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, _system, user):
            self.calls.append(user)
            return malformed_count if len(self.calls) == 1 else corrected

    malformed_rows = parse_dsl_rows(malformed_count, ["S1"])
    assert any("n= must contain only a nonnegative integer" in message
               for _, message in _row_validation_issues(malformed_rows))

    llm = CountedEventRepairLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1"])

    assert step["retries"] == 1
    assert {row["blockType"] for row in rows} == {"sample_size", "result"}
    assert next(row for row in rows if row["blockType"] == "sample_size")["data"][
        "sampleSize"
    ] == "151"
    assert next(row for row in rows if row["blockType"] == "result")["data"][
        "resultsSummary"
    ] == "151 individuals completed the Phase III evaluation"
    repair_prompt = " ".join(llm.calls[1].split())
    assert "typed-value rows" in repair_prompt
    assert "cannot express an explicit proposition" in repair_prompt
    assert "n=151 individuals completed the Phase III evaluation" in repair_prompt


@pytest.mark.asyncio
async def test_targeted_semantic_repair_keeps_count_supplemental_and_adds_result():
    source = "In total, 151 individuals completed the Phase III evaluation."
    request = {"source_units": [{"id": "S1", "text": source}]}
    count_only = "B T25 B1 | n=151 | unit=S1"
    result_claim = (
        "B T36 B2 | sum=In total, 151 individuals completed the Phase III evaluation. "
        "| unit=S1"
    )

    class TypedValueCoverageLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, _system, user):
            self.calls.append(user)
            return count_only if len(self.calls) == 1 else result_claim

    llm = TypedValueCoverageLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1"])

    assert step["retries"] == 1
    assert [(row["blockType"], row["tag"]) for row in rows] == [
        ("sample_size", "B1"), ("result", "B2"),
    ]
    repair_prompt = llm.calls[1]
    assert "ALREADY_ACCEPTED_TYPED_VALUE_ROWS" in repair_prompt
    assert "they do not express the source claim" in repair_prompt
    assert "ALREADY_ACCEPTED_SIBLINGS" not in repair_prompt


def test_dependency_semantic_gate_rejects_document_reporting_as_a_claim():
    from knowledge_pipeline.semantic_extraction import _dependency_semantic_issues

    source = "This work reports the study methodology and follow-up schedule."
    profile = _dependency_profile(source, [
        ("reports", "work", "nsubj"),
        ("reports", "methodology", "dobj"),
    ])
    units = [{"id": "S1", "text": source, "start": 0, "end": len(source)}]
    rows = parse_dsl_rows(
        "B T4 B1 | sub=This work | pred=reports | obj=study methodology | unit=S1",
        ["S1"],
    )

    issues, _ = _dependency_semantic_issues(rows, units, profile)
    assert len(issues) == 1
    assert "document-level reporting signpost" in issues[0][1]
    assert "T3 content=" in issues[0][1]


def test_dsl_audit_flags_snake_case_and_underrepresented_compound_claims():
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path
    from knowledge_pipeline.dsl_rows import parse_dsl_rows

    root = Path(__file__).resolve().parents[4]
    module_spec = spec_from_file_location(
        "article_pipeline_gold_audit", root / "eval" / "validate_article_pipeline_gold.py")
    audit = module_from_spec(module_spec)
    module_spec.loader.exec_module(audit)
    source = (
        "Other biomarkers contribute to disease progression and differentiate "
        "between clinical categories (MCI, dementia)."
    )
    rows = parse_dsl_rows(
        "B T4 B1 | sub=other_biomarkers | pred=contribute_to | "
        "obj=disease_progression_and_differentiate_between_clinical_categories | unit=S1",
        ["S1"],
    )

    spacing_findings = audit._semantic_findings(rows, {"S1": source})
    coverage_findings = audit._semantic_coverage_warnings(rows, {"S1": source})

    assert "# DSL_SPACING_WARN row=B1 unit=S1 fields=obj,sub" in spacing_findings
    assert any(finding.startswith("# COMPOUND_CLAIM_REVIEW unit=S1")
               for finding in coverage_findings)


def test_source_units_are_escaped_and_caption_units_are_marked():
    from knowledge_pipeline.prompts import render_source_units

    rendered = render_source_units(
        [{"id": "S1", "text": "line 1|line 2\nline 3\\tail"},
         {"id": "S2", "text": "\n\n"}],
        ["S1"],
    )

    assert "S1 | emit_required=true | caption_required=true | text=line 1\\|line 2\\nline 3\\\\tail" in rendered
    assert "S2 | emit_required=true | text=\\n\\n" in rendered
    assert "UNIT_ORDER: S1,S2" in rendered
    assert "MANDATORY_CAPTION_UNITS: S1" in rendered


def test_model_source_unit_ids_are_removed_only_from_optional_reference_fields():
    from knowledge_contracts.block_dsl import DSL_FIELDS
    from knowledge_pipeline.semantic_extraction import _remove_invalid_source_only_references

    assert all(not spec.required for fields in DSL_FIELDS.values()
               for spec in fields.values() if spec.kind in {"ref", "refs"})
    model_dsl = (
        "B T4 B1 | sub=NSCs | pred=are | obj=multipotent | "
        "srcs=[S9] | unit=S1\n"
        "B T4 B2 | sub=NSCs | pred=generate | obj=neurons\\|glia | "
        "srcs=[B1] | unit=S1"
    )

    normalized = _remove_invalid_source_only_references(model_dsl)
    assert "srcs=[S9]" not in normalized
    assert "srcs=[B1]" in normalized
    rows = parse_dsl_rows(normalized, ["S1"])
    assert "sourceRefs" not in rows[0]["data"]
    assert rows[1]["data"]["sourceRefs"] == ["B1"]
    assert rows[1]["data"]["object"] == "neurons|glia"

    with pytest.raises(ValidationError, match="Reference list has no B<tag>"):
        parse_dsl_rows(model_dsl, ["S1"])


@pytest.mark.asyncio
async def test_caption_units_are_explicitly_provided_to_the_model():
    request = {"source": TEXT, "source_units": [{"id": "S1", "text": TEXT}],
               "caption_unit_ids": ["S1"]}
    calls = []
    system_prompts = []

    class CaptionLLM(FakeLLM):
        async def __call__(self, system, user):
            calls.append(user)
            system_prompts.append(system)
            return "B T4 B1 | sub=Clusterin | pred=inhibits | obj=inflammation | unit=S1"

    rows, _ = await extract_structural_rows(CaptionLLM(), request, ["S1"])
    assert [row["blockType"] for row in rows] == ["statement", "image"]
    assert rows[1]["data"]["caption"] == TEXT
    assert "MANDATORY_CAPTION_UNITS: S1" in calls[0]
    assert "T49 yourself" in system_prompts[0]


@pytest.mark.asyncio
async def test_pipeline_caption_row_roundtrips_pipes_and_newlines_in_dsl():
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    module_spec = spec_from_file_location(
        "article_pipeline_live_serializer", root / "eval" / "run_article_pipeline_live.py")
    serializer = module_from_spec(module_spec)
    module_spec.loader.exec_module(serializer)
    caption = "Figure 1: A | B\nSecond line."
    request = {"source_units": [{"id": "S1", "text": caption}],
               "caption_unit_ids": ["S1"]}

    class ContextOnlyCaptionLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return "B T3 B1 | content=figure caption context | unit=S1"

    rows, _ = await extract_structural_rows(ContextOnlyCaptionLLM(), request, ["S1"])
    serialized = serializer._serialize_dsl(rows)
    reparsed = parse_dsl_rows(serialized, ["S1"])
    image = next(row for row in reparsed if row["blockType"] == "image")

    assert r"caption=Figure 1: A \| B\nSecond line." in serialized
    assert image["data"]["caption"] == caption


def test_live_eval_artifacts_are_atomic_collision_free_and_preflighted(tmp_path):
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    module_spec = spec_from_file_location(
        "article_pipeline_live_artifact_writer", root / "eval" / "run_article_pipeline_live.py")
    writer = module_from_spec(module_spec)
    module_spec.loader.exec_module(writer)

    target = tmp_path / f"run-v{writer.PROMPT_VERSION}.dsl"
    writer._write_text_atomic(target, "B T4 B1 | sub=cohort | pred=included | obj=10 people | unit=S1\n")
    assert target.read_text(encoding="utf-8").startswith("B T4 B1")
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        f"run-v{writer.PROMPT_VERSION}.dsl"]

    next_output = writer._run_artifact_path(tmp_path, "run")
    assert next_output.name == f"run-v{writer.PROMPT_VERSION}-2.dsl"
    next_output.touch()
    assert writer._run_artifact_path(tmp_path, "run").name == f"run-v{writer.PROMPT_VERSION}-3.dsl"

    case_dir = tmp_path / "case"
    case_dir.mkdir()
    writer.CORPUS = tmp_path
    writer._ensure_case_output_writable([{"path": "case"}])
    assert list(case_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_missing_source_coverage_is_corrected_and_caption_is_pipeline_generated():
    request = {"source": TEXT,
               "source_units": [{"id": "S1", "text": "The cohort included 151 participants."},
                                {"id": "S2", "text": "Figure 1: result shown."}],
               "caption_unit_ids": ["S2"]}

    class RepairCoverageLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, system, user):
            self.calls.append(user)
            if len(self.calls) == 1:
                return "B T4 B1 | sub=the cohort | pred=included | obj=151 participants | unit=S1"
            return "B T4 B2 | sub=Figure 1 | pred=shows | obj=result | unit=S2"

    llm = RepairCoverageLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1", "S2"])
    assert step["retries"] == 1
    assert [(row["blockType"], row["data"]["unit"]) for row in rows] == [
        ("statement", "S1"), ("statement", "S2"), ("image", "S2")]
    assert rows[0]["data"]["subject"] == "the cohort"
    assert "Replace only these existing tags: none" in llm.calls[1]
    assert "Add rows for these missing source units: S2" in llm.calls[1]
    assert "Return only replacement/addition DSL rows" in llm.calls[1]
    assert "missing source-unit rows: S2" in llm.calls[1]
    assert "MISSING_SOURCE_UNITS" in llm.calls[1]
    assert "S2 | emit_required=true | caption_required=true | text=Figure 1: result shown." in llm.calls[0]
    assert "missing mandatory T49 caption rows" not in llm.calls[1]


@pytest.mark.asyncio
async def test_whitespace_units_are_added_as_verbatim_text_rows_without_model_output():
    request = {"source": "\n\nThe cohort included 151 participants.",
               "source_units": [{"id": "S1", "text": "\n\n"},
                                {"id": "S2", "text": "The cohort included 151 participants."}]}

    class NonBlankOnlyLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, system, user):
            self.calls.append(user)
            return "B T4 B1 | sub=the cohort | pred=included | obj=151 participants | unit=S2"

    llm = NonBlankOnlyLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1", "S2"])
    assert "S1 | emit_required=true" not in llm.calls[0]
    assert [row["data"]["unit"] for row in rows] == ["S1", "S2"]
    assert [row["data"]["tag"] for row in rows] == ["B1", "B2"]
    assert rows[0]["blockType"] == "text" and "content" not in rows[0]["data"]
    assert step["retries"] == 0


@pytest.mark.asyncio
async def test_copular_statement_correction_puts_complement_in_object():
    from knowledge_pipeline.prompts import DSL_SYSTEM

    request = {"source_units": [{
        "id": "S1",
        "text": "Findings regarding sleep duration and cognitive impairment are rather controversial.",
    }]}

    class CopulaLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, system, user):
            self.calls.append(user)
            return ("B T4 B1 | sub=findings regarding sleep duration and cognitive impairment "
                    "| pred=are_rather_controversial | obj= | unit=S1")

    llm = CopulaLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1"])
    assert step["retries"] == 0
    assert len(llm.calls) == 1
    assert rows[0]["data"]["predicate"] == "are"
    assert rows[0]["data"]["object"] == "rather controversial"
    assert "in copular T4 claims" in DSL_SYSTEM and "complement in `obj=`" in DSL_SYSTEM
    assert "grammatical subject of the same clause" in DSL_SYSTEM


@pytest.mark.asyncio
async def test_targeted_repair_preserves_valid_rows_and_replaces_only_defective_tag():
    request = {"source_units": [
        {"id": "S1", "text": "Clusterin inhibits inflammation."},
        {"id": "S2", "text": "Sleep quality predicts cognition."},
    ]}
    accepted = "B T4 B1 | sub=Clusterin | pred=inhibits | obj=inflammation | unit=S1"
    rejected = "B T4 B2 | sub=sleep quality | pred=predicts | obj= | unit=S2"

    class TargetedRepairLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, system, user):
            self.calls.append(user)
            if len(self.calls) == 1:
                return "\n".join((accepted, rejected))
            return "B T4 B2 | sub=sleep quality | pred=predicts | obj=cognition | unit=S2"

    llm = TargetedRepairLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1", "S2"])

    assert step["retries"] == 1
    assert [(row["tag"], row["data"]["unit"], row["data"].get("subject"),
             row["data"].get("predicate"), row["data"].get("object")) for row in rows] == [
        ("B1", "S1", "Clusterin", "inhibits", "inflammation"),
        ("B2", "S2", "sleep quality", "predicts", "cognition"),
    ]
    assert "Replace only these existing tags: B2" in llm.calls[1]
    assert "REJECTED_ROW B2" in llm.calls[1]
    assert accepted not in llm.calls[1]
    assert "Return the complete corrected DSL for every supplied source unit" not in llm.calls[1]


@pytest.mark.asyncio
async def test_targeted_repair_retypes_objectless_result_to_source_exact_result_block():
    source = "In total, 149 MCI and 73 CNI individuals could not be retested."
    request = {"source_units": [{"id": "S1", "text": source}]}
    invalid = (
        "B T4 B1 | sub=149 MCI and 73 CNI individuals | "
        "pred=could_not_be_retested | obj= | unit=S1"
    )
    corrected = "B T36 B1 | sum=In total, 149 MCI and 73 CNI individuals could not be retested. | unit=S1"

    class IntransitiveResultRepairLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, system, user):
            self.calls.append(user)
            return invalid if len(self.calls) == 1 else corrected

    llm = IntransitiveResultRepairLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1"])

    assert step["retries"] == 1
    assert rows[0]["blockType"] == "result"
    assert rows[0]["tag"] == "B1"
    assert rows[0]["data"]["unit"] == "S1"
    assert rows[0]["data"]["resultsSummary"] == source
    assert any(
        finding["code"] == "objectless_t4_retyped"
        and finding["unit"] == "S1" and finding["tag"] == "B1"
        for finding in step["warnings"]
    )
    from knowledge_pipeline.prompts import DSL_SYSTEM
    assert "including objectless or nominalized findings" in " ".join(DSL_SYSTEM.split())
    assert "uncertainty about an argument's referent alone is not enough" in DSL_SYSTEM
    assert "reported empirical finding/result about a study group or outcome is T36" in DSL_SYSTEM
    assert "`sum=`—one row per atomic finding" in DSL_SYSTEM
    assert "S1 | emit_required=true | text=" + source in llm.calls[1]
    assert "Replace only these existing tags: B1" in llm.calls[1]


@pytest.mark.asyncio
async def test_multi_claim_objectless_clause_is_repaired_exactly_without_retyping_sibling():
    source = (
        "Participants reported increased anxiety symptoms, although the frequency "
        "of anxiety diagnosis did not vary significantly."
    )
    request = {"source_units": [{"id": "S1", "text": source}]}
    initial = "\n".join([
        "B T4 B1 | sub=participants | pred=reported | "
        "obj=increased anxiety symptoms | unit=S1",
        "B T4 B2 | sub=the frequency of anxiety diagnosis | "
        "pred=did_not_vary_significantly | obj= | unit=S1",
    ])

    class ExactClauseRepairLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, system, user):
            self.calls.append(user)
            return initial

    llm = ExactClauseRepairLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1"])

    assert len(llm.calls) == 1
    assert step["retries"] == 0
    assert [(row["tag"], row["blockType"]) for row in rows] == [
        ("B1", "statement"), ("B2", "result"),
    ]
    assert rows[0]["data"]["object"] == "increased anxiety symptoms"
    assert rows[1]["data"]["resultsSummary"] == (
        "the frequency of anxiety diagnosis did not vary significantly"
    )


@pytest.mark.asyncio
async def test_objectless_result_clause_is_repaired_with_only_typed_pvalue_siblings():
    source = "Alcohol use was reduced (p = 0.028 and p = 0.023)."
    request = {"source_units": [{"id": "S1", "text": source}]}
    initial = "\n".join([
        "B T4 B1 | sub=Alcohol use | pred=was_reduced | obj= | unit=S1",
        "B T27 B2 | p=0.028 | unit=S1",
        "B T27 B3 | p=0.023 | unit=S1",
    ])

    class ExactPvalueSiblingLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, system, user):
            self.calls.append(user)
            return initial

    llm = ExactPvalueSiblingLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1"])

    assert len(llm.calls) == 1
    assert step["retries"] == 0
    assert [row["blockType"] for row in rows] == [
        "result", "probability_value", "probability_value",
    ]
    assert rows[0]["data"]["resultsSummary"] == "Alcohol use was reduced"
    assert [row["data"]["pValue"] for row in rows[1:]] == [0.028, 0.023]


@pytest.mark.asyncio
async def test_likelihood_predicate_keeps_infinitive_as_object_and_pvalue_separate():
    source = (
        "Compared to the total participant pool, those who were followed up were "
        "younger, more likely to be women and less likely to live alone (p = 0.03)."
    )
    request = {"source_units": [{"id": "S1", "text": source}]}
    initial = "\n".join([
        "B T4 B1 | sub=those who were followed up | "
        "pred=were_less_likely_to_live_alone | obj= | ctx=p = 0.03 | unit=S1",
        "B T27 B2 | p=0.03 | unit=S1",
    ])

    class LikelihoodLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return initial

    rows, step = await extract_structural_rows(LikelihoodLLM(), request, ["S1"])

    assert step["retries"] == 0
    assert rows[0]["blockType"] == "statement"
    assert rows[0]["data"]["predicate"] == "were_less_likely_to"
    assert rows[0]["data"]["object"] == "live alone"
    assert rows[0]["data"]["context"] == "compared to the total participant pool"
    assert not rows[0]["data"].get("negated", False)
    assert rows[1]["blockType"] == "probability_value"
    assert rows[1]["data"]["pValue"] == 0.03


@pytest.mark.asyncio
async def test_nominalized_and_observed_outcomes_repair_to_exact_t36_clauses():
    source203 = (
        "In the dentate gyrus of mice, an increase in neuron and glia numbers was "
        "observed within 72 h of feeding a fasting-mimicking diet (FMD), along with "
        "a reduced IGF-1/PKA signaling [152,154]."
    )
    source204 = (
        "In addition, an increase in mesenchymal stem and progenitor cell number and "
        "proliferation were observed on FMD repeated feeding in aged animals, and in "
        "aged mice; rebalanced output from HSCs and progenitors were also observed "
        "[154,155]."
    )
    request = {"source_units": [
        {"id": "S203", "text": source203},
        {"id": "S204", "text": source204},
    ]}
    initial = "\n".join([
        "B T4 B1 | sub=neuron and glia numbers | pred=increased | obj= | unit=S203",
        "B T4 B2 | sub=IGF-1/PKA signaling | pred=reduced | obj= | unit=S203",
        "B T4 B3 | sub=mesenchymal stem and progenitor cell number and proliferation | "
        "pred=increased | obj= | unit=S204",
        "B T4 B4 | sub=rebalanced output from HSCs and progenitors | "
        "pred=were_observed | obj= | unit=S204",
    ])

    class NominalOutcomeLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return initial

    rows, step = await extract_structural_rows(
        NominalOutcomeLLM(), request, ["S203", "S204"],
    )

    assert step["retries"] == 0
    assert [row["blockType"] for row in rows] == ["result"] * 4
    summaries = [row["data"]["resultsSummary"] for row in rows]
    assert summaries == [
        "an increase in neuron and glia numbers was observed within 72 h of feeding "
        "a fasting-mimicking diet (FMD)",
        "a reduced IGF-1/PKA signaling [152,154]",
        "an increase in mesenchymal stem and progenitor cell number and proliferation "
        "were observed on FMD repeated feeding in aged animals, and in aged mice",
        "rebalanced output from HSCs and progenitors were also observed [154,155]",
    ]


@pytest.mark.asyncio
async def test_misassigned_observation_roles_and_exposure_causality_are_repaired():
    source203 = (
        "In the dentate gyrus of mice, an increase in neuron and glia numbers was "
        "observed within 72 h of feeding a fasting-mimicking diet (FMD), along with "
        "a reduced IGF-1/PKA signaling [152,154]."
    )
    source204 = (
        "In addition, an increase in mesenchymal stem and progenitor cell number and "
        "proliferation were observed on FMD repeated feeding in aged animals, and in "
        "aged mice; rebalanced output from HSCs and progenitors were also observed "
        "[154,155]."
    )
    request = {"source_units": [
        {"id": "S203", "text": source203},
        {"id": "S204", "text": source204},
    ]}
    initial = "\n".join([
        "B T4 B1 | sub=increase | pred=was_observed_in | "
        "obj=neuron and glia numbers | ctx=dentate gyrus of mice | unit=S203",
        "B T4 B2 | sub=72 h of feeding a fasting-mimicking diet | "
        "pred=resulted_in | obj=increase in neuron and glia numbers | unit=S203",
        "B T4 B3 | sub=reduced | pred=was_observed_in | "
        "obj=IGF-1/PKA signaling | ctx=dentate gyrus of mice | unit=S203",
        "B T4 B4 | sub=increase | pred=were_observed_in | "
        "obj=mesenchymal stem and progenitor cell number and proliferation | "
        "ctx=aged animals, aged mice | unit=S204",
        "B T4 B5 | sub=rebalanced output | pred=were_observed_in | "
        "obj=HSCs and progenitors | ctx=aged animals, aged mice | unit=S204",
        "B T4 B6 | sub=FMD repeated feeding | pred=resulted_in | "
        "obj=increase in mesenchymal stem and progenitor cell number and proliferation "
        "| unit=S204",
    ])

    class MisassignedObservationLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return initial

    rows, step = await extract_structural_rows(
        MisassignedObservationLLM(), request, ["S203", "S204"],
    )

    assert step["retries"] == 0
    assert [row["blockType"] for row in rows] == ["result"] * 4
    assert [row["data"]["resultsSummary"] for row in rows] == [
        "an increase in neuron and glia numbers was observed within 72 h of feeding "
        "a fasting-mimicking diet (FMD)",
        "a reduced IGF-1/PKA signaling [152,154]",
        "an increase in mesenchymal stem and progenitor cell number and proliferation "
        "were observed on FMD repeated feeding in aged animals, and in aged mice",
        "rebalanced output from HSCs and progenitors were also observed [154,155]",
    ]


@pytest.mark.asyncio
async def test_valid_but_misassigned_observed_within_on_rows_retype_and_restore_companion():
    source203 = (
        "In the dentate gyrus of mice, an increase in neuron and glia numbers was "
        "observed within 72 h of feeding a fasting-mimicking diet (FMD), along with "
        "a reduced IGF-1/PKA signaling [152,154]."
    )
    source204 = (
        "In addition, an increase in mesenchymal stem and progenitor cell number and "
        "proliferation were observed on FMD repeated feeding in aged animals, and in "
        "aged mice; rebalanced output from HSCs and progenitors were also observed "
        "[154,155]."
    )
    request = {"source_units": [
        {"id": "S203", "text": source203},
        {"id": "S204", "text": source204},
    ]}
    initial = "\n".join([
        "B T4 B1 | sub=an increase in neuron and glia numbers "
        "| pred=was_observed_within "
        "| obj=72 h of feeding a fasting-mimicking diet (FMD) "
        "| neg=false | epi=observation "
        "| ctx=along with a reduced IGF-1/PKA signaling | unit=S203",
        "B T4 B2 | sub=an increase in mesenchymal stem and progenitor cell number "
        "and proliferation | pred=were_observed_on | obj=FMD repeated feeding "
        "| neg=false | epi=observation "
        "| ctx=in aged animals, and in aged mice | unit=S204",
        "B T36 B3 | sum=rebalanced output from HSCs and progenitors were also observed "
        "[154,155] | unit=S204",
    ])

    class ValidButMisassignedObservationLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return initial

    rows, step = await extract_structural_rows(
        ValidButMisassignedObservationLLM(), request, ["S203", "S204"],
    )

    assert step["retries"] == 0
    assert [row["blockType"] for row in rows] == ["result"] * 4
    assert [row["data"]["resultsSummary"] for row in rows] == [
        "an increase in neuron and glia numbers was observed within 72 h of feeding "
        "a fasting-mimicking diet (FMD)",
        "a reduced IGF-1/PKA signaling [152,154]",
        "an increase in mesenchymal stem and progenitor cell number and proliferation "
        "were observed on FMD repeated feeding in aged animals, and in aged mice",
        "rebalanced output from HSCs and progenitors were also observed [154,155]",
    ]


@pytest.mark.asyncio
async def test_shared_existential_increases_are_split_into_atomic_results():
    source = (
        "Finally, there was an increase in those living alone within the CNI group "
        "(p = 0.003) and in the average number of major medical morbidities in both "
        "groups (p = 0.001 and p < 0.001 in CNI and MCI groups, respectively), "
        "possibly as a result of aging."
    )
    request = {"source_units": [{"id": "S171", "text": source}]}
    initial = "\n".join([
        "B T36 B1 | sum=there was an increase in those living alone within the CNI group, "
        "possibly as a result of aging | unit=S171",
        "B T27 B2 | p=0.003 | unit=S171",
        "B T36 B3 | sum=there was an increase in the average number of major medical "
        "morbidities in both groups, possibly as a result of aging | unit=S171",
        "B T27 B4 | p=0.001 | unit=S171",
        "B T27 B5 | p=<0.001 | unit=S171",
    ])

    class SharedExistentialLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return initial

    rows, step = await extract_structural_rows(
        SharedExistentialLLM(), request, ["S171"],
    )

    assert step["retries"] == 0
    summaries = [row["data"]["resultsSummary"] for row in rows
                 if row["blockType"] == "result"]
    assert summaries == [
        "there was an increase in those living alone within the CNI group, "
        "possibly as a result of aging",
        "there was an increase in the average number of major medical morbidities "
        "in both groups, possibly as a result of aging",
    ]
    assert [row["data"]["pValue"] for row in rows
            if row["blockType"] == "probability_value"] == [0.003, 0.001, "<0.001"]
    assert all("possibly as a result of aging" in summary for summary in summaries)


@pytest.mark.asyncio
async def test_relative_reveals_repairs_adjectival_empty_object_to_source_roles():
    source_units = [
        {
            "id": "S166",
            "text": "It is inferred from this that obesity plays a role in SNA "
                    "inhibition and it is due to tonic activity of NPY, which "
                    "further reveals an elevated α-MSH excitation [132].",
        },
        {
            "id": "S167",
            "text": "htNSCs are predominantly found adjacent to the PVN of the "
                    "hypothalamus (See Figure 2) lining the 3rd ventricle [133].",
        },
        {
            "id": "S168",
            "text": "Based on these studies, there is a need for detailed "
                    "investigation into the link between the variation in NSC "
                    "levels associated with different conditions, such as age, "
                    "diet etc., and sympathoexcitatory activity.",
        },
    ]
    initial = "\n".join([
        "B T4 B1 | sub=obesity | pred=plays_a_role_in | obj=SNA inhibition | "
        "ctx=tonic activity of NPY | unit=S166",
        "B T4 B2 | sub=α-MSH excitation | pred=is_elevated | obj= | "
        "ctx=further reveals | unit=S166",
        "B T4 B3 | sub=htNSCs | pred=are_found_adjacent_to | "
        "obj=PVN of the hypothalamus | ctx=lining the 3rd ventricle | unit=S167",
        "B T4 B4 | sub=NSC levels | pred=is_associated_with | "
        "obj=different conditions | ctx=age, diet etc. | unit=S168",
        "B T4 B5 | sub=sympathoexcitatory activity | "
        "pred=needs_detailed_investigation_into | "
        "obj=the link between the variation in NSC levels | unit=S168",
    ])

    class RelativeRevealLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return initial

    rows, step = await extract_structural_rows(
        RelativeRevealLLM(), {"source_units": source_units},
        ["S166", "S167", "S168"],
    )

    assert step["retries"] == 0
    repaired = next(row for row in rows if row["tag"] == "B2")
    assert repaired["blockType"] == "statement"
    assert repaired["data"]["subject"] == "tonic activity of NPY"
    assert repaired["data"]["predicate"] == "further_reveals"
    assert repaired["data"]["object"] == "an elevated α-MSH excitation"
    assert "context" not in repaired["data"]


def test_qualifier_only_result_is_removed_when_embedded_in_complete_result():
    from knowledge_pipeline.semantic_extraction import _deduplicate_exact_semantic_rows

    complete = (
        "there was an increase in those living alone within the CNI group "
        "(p = 0.003) and in the average number of major medical morbidities in "
        "both groups, possibly as a result of aging"
    )
    dsl = "\n".join([
        f"B T36 B1 | sum={complete} | unit=S171",
        "B T36 B2 | sum=possibly as a result of aging | unit=S171",
    ])
    rows = parse_dsl_rows(dsl, ["S171"])
    current_dsl = dict(zip(("B1", "B2"), dsl.splitlines(), strict=True))
    repaired, repaired_dsl, dropped = _deduplicate_exact_semantic_rows(
        rows, current_dsl,
    )

    assert [row["tag"] for row in repaired] == ["B1"]
    assert dropped == ["B2"]
    assert "B2" not in repaired_dsl


@pytest.mark.asyncio
async def test_rather_than_contrast_does_not_set_statement_negation():
    source = (
        "However, various studies showed that neuronal survival ability was altered "
        "by fasting rather than induction of NSC proliferation."
    )
    request = {"source_units": [{"id": "S1", "text": source}]}
    initial = (
        "B T4 B1 | sub=neuronal survival ability | pred=was_altered_by | "
        "obj=fasting | neg=true | epi=observation | "
        "ctx=induction of NSC proliferation | unit=S1"
    )

    class ContrastLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return initial

    rows, step = await extract_structural_rows(ContrastLLM(), request, ["S1"])

    assert step["retries"] == 0
    assert rows[0]["data"]["subject"] == "neuronal survival ability"
    assert rows[0]["data"]["predicate"] == "was_altered_by"
    assert rows[0]["data"]["object"] == "fasting"
    assert not rows[0]["data"].get("negated", False)
    assert rows[0]["data"]["context"] == "rather than induction of NSC proliferation"


@pytest.mark.asyncio
async def test_shared_modal_active_relative_and_also_passive_are_source_repaired():
    source_units = [
        {
            "id": "S130",
            "text": "Hence, replenishing new htNSC from a newborn mouse into the MBH "
                    "of a middle-aged mouse could enhance the lifespan and delay "
                    "age-associated physiological decline [81].",
        },
        {
            "id": "S131",
            "text": "Exogenous implantation of stem cells into the hypothalamus caused "
                    "secretion of microRNA-containing exosomes, which delayed "
                    "physiological deficits in aging.",
        },
        {
            "id": "S132",
            "text": "Suppression of NF-kB activation was achieved in neurons due to "
                    "these microRNAs, and GnRH secretion was also restored [81].",
        },
    ]
    initial = "\n".join([
        "B T4 B1 | sub=replenishing new htNSC from a newborn mouse into the MBH of a "
        "middle-aged mouse | pred=could_enhance | obj=lifespan | unit=S130",
        "B T4 B2 | sub=delay age-associated physiological decline | pred=could | "
        "obj= | unit=S130",
        "B T4 B3 | sub=exogenous implantation of stem cells into the hypothalamus | "
        "pred=caused | obj=secretion of microRNA-containing exosomes | unit=S131",
        "B T4 B4 | sub=physiological deficits in aging | pred=were_delayed | "
        "obj= | unit=S131",
        "B T4 B5 | sub=suppression of NF-kB activation | pred=was_achieved | "
        "obj=in neurons | unit=S132",
        "B T4 B6 | sub=GnRH secretion | pred=was_restored | obj= | unit=S132",
    ])

    class SourceRepairLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, system, user):
            self.calls.append(user)
            return initial

    llm = SourceRepairLLM()
    rows, step = await extract_structural_rows(
        llm, {"source_units": source_units}, ["S130", "S131", "S132"],
    )
    by_unit = {unit: [row for row in rows if row["data"]["unit"] == unit]
               for unit in ("S130", "S131", "S132")}

    assert len(llm.calls) == 1 and step["retries"] == 0
    shared_modal = by_unit["S130"][1]["data"]
    assert shared_modal["subject"].startswith("replenishing new htNSC")
    assert shared_modal["predicate"] == "could_delay"
    assert shared_modal["object"] == "age-associated physiological decline"
    active_relative = by_unit["S131"][1]["data"]
    assert active_relative["subject"] == "microRNA-containing exosomes"
    assert active_relative["predicate"] == "delayed"
    assert active_relative["object"] == "physiological deficits in aging"
    restored = by_unit["S132"][1]
    assert restored["blockType"] == "result"
    assert restored["data"]["resultsSummary"] == "GnRH secretion was also restored"


@pytest.mark.asyncio
async def test_targeted_repair_accepts_one_valid_retype_among_duplicate_tag_candidates():
    source = "In total, 149 MCI and 73 CNI individuals could not be retested."
    request = {"source_units": [{"id": "S1", "text": source}]}
    invalid = (
        "B T4 B1 | sub=149 MCI and 73 CNI individuals | "
        "pred=could_not_be_retested | obj= | unit=S1"
    )
    duplicate_candidates = "\n".join([
        invalid,
        "B T36 B1 | sum=In total, 149 MCI and 73 CNI individuals "
        "could not be retested. | unit=S1",
    ])

    class DuplicateTagRepairLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, system, user):
            self.calls.append(user)
            return invalid if len(self.calls) == 1 else duplicate_candidates

    llm = DuplicateTagRepairLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1"])

    assert step["retries"] == 1
    assert len(rows) == 1
    assert rows[0]["tag"] == "B1" and rows[0]["blockType"] == "result"
    assert rows[0]["data"]["resultsSummary"] == source
    assert "Every addition must use a unique tag" in llm.calls[1]


def test_targeted_repair_rejects_multiple_valid_candidates_for_one_tag():
    from knowledge_pipeline.semantic_extraction import (
        _accepted_targeted_rows, _row_validation_issues,
    )

    source = "The participants could not be retested."
    original = parse_dsl_rows(
        "B T4 B1 | sub=participants | pred=could_not_be_retested | obj= | unit=S1",
        ["S1"],
    )
    candidates = parse_dsl_rows("\n".join([
        "B T4 B1 | sub=participants | pred=could_not_be | obj=retested | unit=S1",
        "B T36 B1 | sum=The participants could not be retested. | unit=S1",
    ]), ["S1"], allow_duplicate_tags=True)

    accepted, errors = _accepted_targeted_rows(
        candidates, original, _row_validation_issues(original), [], [], [],
        source_units=[{"id": "S1", "text": source}],
    )

    assert accepted == []
    assert any("multiple valid repair rows used the same tag: B1" in error
               for error in errors)


@pytest.mark.asyncio
async def test_targeted_repair_moves_reported_pvalue_to_typed_dsl_row():
    source = "The result was significant (p = 0.059)."
    request = {"source_units": [{"id": "S1", "text": source}]}
    invalid = (
        "B T4 B1 | sub=result | pred=was | obj=significant | "
        "p=0.059 | unit=S1"
    )
    corrected = "\n".join([
        "B T4 B1 | sub=result | pred=was | obj=significant | unit=S1",
        "B T27 B2 | p=0.059 | unit=S1",
    ])

    class TypedPValueRepairLLM(FakeLLM):
        def __init__(self):
            super().__init__(calls=[])

        async def __call__(self, system, user):
            self.calls.append(user)
            return invalid if len(self.calls) == 1 else corrected

    llm = TypedPValueRepairLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1"])

    assert step["retries"] == 1
    assert [row["blockType"] for row in rows] == ["statement", "probability_value"]
    p_value_row = rows[1]
    assert p_value_row["data"]["pValue"] == 0.059
    assert p_value_row["data"]["unit"] == "S1"
    assert "MISSING_TYPED_PVALUES" in llm.calls[1]
    assert "S1: p=0.059" in llm.calls[1]


@pytest.mark.asyncio
async def test_split_doi_label_and_value_are_repaired_as_metadata_not_claims():
    source_units = [
        {"id": "S4", "text": "DOI"},
        {"id": "S5", "text": ":*"},
        {"id": "S6", "text": "* 10.3390/healthcare11050703"},
    ]
    llm = FakeLLM(
        "B T1 B1 | doi=10.3390/healthcare11050703 | unit=S6", calls=[],
    )

    rows, step = await extract_structural_rows(
        llm, {"source_units": source_units}, ["S4", "S5", "S6"],
    )

    doi_label = next(row for row in rows if row["data"]["unit"] == "S4")
    doi_value = next(row for row in rows if row["data"]["unit"] == "S6")
    assert doi_label["blockType"] == "text"
    assert doi_label["data"]["content"] == "DOI"
    assert doi_value["blockType"] == "metadata"
    assert doi_value["data"]["doi"] == "10.3390/healthcare11050703"
    assert step["retries"] == 0 and len(llm.calls) == 1


@pytest.mark.asyncio
async def test_ambiguous_role_clause_is_repaired_in_place_as_t4():
    source = (
        "These neurons are in arcuate nucleus (ArcN), which projects to various sites "
        "in the hypothalamus, including the PVN [117,118,119], and regulates autonomic "
        "activity; however, the role of PVN MC3/4 is ambiguous."
    )
    request = {"source_units": [{"id": "S156", "text": source}]}
    initial = "\n".join([
        "B T4 B6 | sub=these neurons | pred=are_in | obj=arcuate nucleus (ArcN) | unit=S156",
        "B T4 B7 | sub=arcuate nucleus (ArcN) | pred=projects_to "
        "| obj=various sites in the hypothalamus, including the PVN | unit=S156",
        "B T4 B8 | sub=arcuate nucleus (ArcN) | pred=regulates "
        "| obj=autonomic activity | unit=S156",
        "B T4 B9 | sub=PVN MC3/4 | pred=has_ambiguous_role | obj= | unit=S156",
    ])
    llm = FakeLLM(initial, calls=[])

    rows, step = await extract_structural_rows(llm, request, ["S156"])

    ambiguous = next(row for row in rows if row["data"].get("object") == "ambiguous")
    assert ambiguous["blockType"] == "statement"
    assert ambiguous["data"]["subject"] == "the role of PVN MC3/4"
    assert ambiguous["data"]["predicate"] == "is"
    assert step["retries"] == 0 and len(llm.calls) == 1


def test_targeted_repair_accepts_semantic_retype_for_warning_but_requires_sum():
    from knowledge_pipeline.semantic_extraction import (
        _accepted_targeted_rows, _row_validation_issues,
    )

    source = "149 MCI and 73 CNI individuals could not be retested."
    original_dsl = (
        "B T4 B1 | sub=149 MCI and 73 CNI individuals | "
        "pred=could_not_be_retested | obj= | unit=S1"
    )
    invented_dsl = "B T36 B1 | sum=The participants were not retested for unknown reasons. | unit=S1"
    rows = parse_dsl_rows(original_dsl, ["S1"])
    patch_rows = parse_dsl_rows(invented_dsl, ["S1"])
    reviewed = []
    accepted, errors = _accepted_targeted_rows(
        patch_rows, rows, _row_validation_issues(rows), [], [], [],
        source_units=[{"id": "S1", "text": source}],
        reviewed_objectless_retypes=reviewed,
    )

    assert [row["blockType"] for row in accepted] == ["result"]
    assert not errors
    assert reviewed == [("S1", "B1", "The participants were not retested for unknown reasons.")]

    missing_sum = parse_dsl_rows("B T36 B1 | sum= | unit=S1", ["S1"])
    accepted_missing, missing_errors = _accepted_targeted_rows(
        missing_sum, rows, _row_validation_issues(rows), [], [], [],
        source_units=[{"id": "S1", "text": source}],
    )
    assert accepted_missing == []
    assert any("lacks required fields: sum" in error for error in missing_errors)


@pytest.mark.asyncio
async def test_partial_targeted_repair_keeps_fixed_row_and_retries_only_remaining_tag():
    request = {"source_units": [
        {"id": "S1", "text": "Clusterin inhibits inflammation."},
        {"id": "S2", "text": "Sleep quality predicts cognition."},
        {"id": "S3", "text": "MCI is associated with dementia."},
    ]}
    initial = "\n".join([
        "B T4 B1 | sub=Clusterin | pred=inhibits | obj=inflammation | unit=S1",
        "B T4 B2 | sub=sleep quality | pred=predicts | obj= | unit=S2",
        "B T4 B3 | sub=MCI | pred=is_associated_with | obj= | unit=S3",
    ])

    class PartialRepairLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, system, user):
            self.calls.append(user)
            if len(self.calls) == 1:
                return initial
            if len(self.calls) == 2:
                return "\n".join([
                    "B T4 B2 | sub=sleep quality | pred=predicts | obj=cognition | unit=S2",
                    "B T4 B3 | sub=MCI | pred=is_associated_with | obj= | unit=S3",
                ])
            return "B T4 B3 | sub=MCI | pred=is_associated_with | obj=dementia | unit=S3"

    llm = PartialRepairLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1", "S2", "S3"])

    assert step["retries"] == 2
    assert [row["data"]["object"] for row in rows] == ["inflammation", "cognition", "dementia"]
    assert "Replace only these existing tags: B2, B3" in llm.calls[1]
    assert "Replace only these existing tags: B3" in llm.calls[2]
    assert "obj=cognition" not in llm.calls[2]


@pytest.mark.asyncio
async def test_source_grounded_passive_clause_is_repaired_without_model_retry():
    request = {"source_units": [{
        "id": "S1",
        "text": "Participants underwent evaluation. Medical history and sleep complaints were also recorded.",
    }]}

    class PassiveRepairLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, system, user):
            self.calls.append(user)
            return "\n".join([
                "B T4 B1 | sub=participants | pred=underwent | obj=evaluation | unit=S1",
                "B T4 B2 | sub=medical history and sleep complaints | pred=were_recorded | obj= | unit=S1",
            ])

    llm = PassiveRepairLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1"])

    assert step["retries"] == 0
    assert len(llm.calls) == 1
    assert [row["blockType"] for row in rows] == ["statement", "text"]
    assert rows[1]["data"]["content"] == "Medical history and sleep complaints were also recorded."


@pytest.mark.asyncio
async def test_observed_passive_clause_with_citation_is_preserved_as_typed_result():
    source = (
        "An increase in stem cell number was observed on FMD; rebalanced output from "
        "HSCs and progenitors were also observed [154,155]."
    )
    request = {"source_units": [{"id": "S1", "text": source}]}

    class ObservedPassiveLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return "\n".join([
                "B T4 B1 | sub=an increase in stem cell number | pred=was_observed_on | "
                "obj=FMD | unit=S1",
                "B T4 B2 | sub=rebalanced output from HSCs and progenitors | "
                "pred=were_observed | obj= | unit=S1",
            ])

    rows, step = await extract_structural_rows(ObservedPassiveLLM(), request, ["S1"])

    assert step["retries"] == 0
    assert rows[1]["blockType"] == "result"
    assert rows[1]["data"]["resultsSummary"] == (
        "rebalanced output from HSCs and progenitors were also observed [154,155]"
    )


@pytest.mark.asyncio
async def test_caption_figure_navigation_statement_is_context_not_a_forced_triple():
    source = "Participant diagnostic status during Phase II is also shown."
    request = {
        "source_units": [{"id": "S1", "text": source}],
        "caption_unit_ids": ["S1"],
    }

    class FigureNavigationLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return "B T4 B1 | sub=participant diagnostic status during Phase II | " \
                   "pred=is_shown | obj= | unit=S1"

    rows, step = await extract_structural_rows(FigureNavigationLLM(), request, ["S1"])

    assert step["retries"] == 0
    assert [row["blockType"] for row in rows] == ["text", "image"]
    assert rows[0]["data"]["content"] == source
    assert rows[1]["data"]["caption"] == source


@pytest.mark.asyncio
async def test_source_only_qualified_passives_are_preserved_without_invented_objects():
    gap = (
        "The relationship between htNSC dysregulation and sympathetic nerve response "
        "in obesity has never been studied."
    )
    qualified = (
        "As brain microglia activation is a predominant indicator of neuroinflammation "
        "in hypertension, restoring a normal population of glia and neurons within the "
        "cardiogenic centers of the brain cannot be ruled out."
    )
    request = {"source_units": [
        {"id": "S1", "text": gap},
        {"id": "S2", "text": qualified},
    ]}

    class QualifiedPassivesLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return "\n".join([
                "B T4 B1 | sub=the relationship between htNSC dysregulation and "
                "sympathetic nerve response in obesity | pred=has_never_been_studied "
                "| obj= | unit=S1",
                "B T4 B2 | sub=brain microglia activation | pred=is | "
                "obj=a predominant indicator of neuroinflammation in hypertension | unit=S2",
                "B T4 B3 | sub=restoring a normal population of glia and neurons within the "
                "cardiogenic centers of the brain | pred=cannot_be_ruled_out | obj= | unit=S2",
            ])

    rows, step = await extract_structural_rows(
        QualifiedPassivesLLM(), request, ["S1", "S2"],
    )

    assert step["retries"] == 0
    assert rows[0]["blockType"] == "text"
    assert rows[0]["data"]["content"] == gap
    assert rows[2]["blockType"] == "text"
    assert rows[2]["data"]["content"] == (
        "restoring a normal population of glia and neurons within the cardiogenic "
        "centers of the brain cannot be ruled out."
    )


@pytest.mark.asyncio
async def test_pipeline_discards_model_t49_rows_but_keeps_caption_claims():
    caption = "Figure 1: Clusterin reduces inflammation in aged mice."
    request = {
        "source_units": [
            {"id": "S1", "text": caption},
            {"id": "S2", "text": "Clusterin was measured in plasma."},
        ],
        "caption_unit_ids": ["S1"],
    }

    class CaptionRowsLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, _system, user):
            self.calls.append(user)
            return "\n".join([
                "B T49 B1 | caption=Figure 1 Clusterin reduces inflammation | unit=S1",
                "B T4 B2 | sub=Clusterin | pred=reduces | obj=inflammation in aged mice | unit=S1",
                "B T4 B3 | sub=Clusterin | pred=was measured in | obj=plasma | unit=S2",
            ])

    llm = CaptionRowsLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1", "S2"])

    assert step["retries"] == 0
    assert len(llm.calls) == 1
    assert sum(row["blockType"] == "image" for row in rows) == 1
    assert [row["data"].get("caption") for row in rows if row["blockType"] == "image"] == [caption]
    assert [row["data"].get("object") for row in rows if row["blockType"] == "statement"] == [
        "inflammation in aged mice", "plasma",
    ]


@pytest.mark.asyncio
async def test_intransitive_attrition_rows_use_explicit_source_complements():
    source = (
        "In total, 103 participants (27.3%) had passed away in the intervening years, "
        "56 persons (14.9%) could not be located, and 63 persons (16.7%) refused to "
        "participate, raising the total attrition rate (inability to participate for any "
        "reason) to 58.9%."
    )
    request = {"source_units": [{"id": "S1", "text": source}]}
    dsl = "\n".join([
        "B T4 B1 | sub=103 participants (27.3%) | pred=had_passed_away | "
        "obj=in the intervening years | unit=S1",
        "B T4 B2 | sub=56 persons (14.9%) | pred=could_not_be_located | obj= | unit=S1",
        "B T4 B3 | sub=63 persons (16.7%) | pred=refused_to_participate | obj= | unit=S1",
        "B T4 B4 | sub=total attrition rate | pred=was | obj=58.9% | unit=S1",
    ])

    class AttritionLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return dsl

    rows, step = await extract_structural_rows(AttritionLLM(), request, ["S1"])

    assert step["retries"] == 0
    assert rows[1]["data"]["predicate"] == "could_not_be"
    assert rows[1]["data"]["object"] == "located"
    assert rows[2]["data"]["predicate"] == "refused_to"
    assert rows[2]["data"]["object"] == "participate"


@pytest.mark.asyncio
async def test_passive_collected_clause_adds_other_conjunctive_claim():
    source = (
        "Demographic information and medical data were collected, and all participants "
        "were administered the Mini Mental State Examination (MMSE) test."
    )
    request = {"source_units": [{"id": "S1", "text": source}]}

    class CompoundPassiveLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, system, user):
            self.calls.append(user)
            if len(self.calls) == 1:
                return "B T4 B1 | sub=Demographic information and medical data | " \
                       "pred=were_collected | obj= | unit=S1"
            return "\n".join([
                "B T3 B1 | content=Demographic information and medical data were collected, | unit=S1",
                "B T4 B2 | sub=all participants | pred=were_administered | "
                "obj=the Mini Mental State Examination (MMSE) test | unit=S1",
            ])

    llm = CompoundPassiveLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1"])

    assert step["retries"] == 1
    assert [row["blockType"] for row in rows] == ["text", "statement"]
    assert rows[1]["data"]["object"] == "the Mini Mental State Examination (MMSE) test"
    assert "ADDITIONAL_SEMANTIC_CLAIM_UNITS" in llm.calls[1]
    assert (
        "B T3 B1 | content=Demographic information and medical data were collected, | unit=S1"
        in llm.calls[1]
    )


@pytest.mark.asyncio
async def test_malformed_resulted_in_object_gets_exact_source_grounded_repair():
    source = (
        "Along with anorexigenic response signaling, during fetal life, insulin and leptin "
        "help in neuronal development and their neurotrophic effects are mediated by the "
        "MAPK (ERK/MAPK) pathway that resulted in phosphorylation of ERK1/2 [113]."
    )
    request = {"source_units": [{"id": "S1", "text": source}]}
    initial = "\n".join([
        "B T4 B1 | sub=insulin and leptin | pred=help_in | obj=neuronal development | unit=S1",
        "B T4 B2 | sub=their neurotrophic effects | pred=are_mediated_by | "
        "obj=the MAPK (ERK/MAPK) pathway | unit=S1",
        "B T4 B3 | sub=MAPK_ERK_MAPK_pathway | pred=resulted_in | "
        "obj phosphorylation_of_ERK1_2 | unit=S1",
    ])

    class ResultedInRepairLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, system, user):
            self.calls.append(user)
            return initial

    llm = ResultedInRepairLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1"])

    assert step["retries"] == 0
    assert len(llm.calls) == 1
    assert rows[2]["data"]["subject"] == "the MAPK (ERK/MAPK) pathway"
    assert rows[2]["data"]["object"] == "phosphorylation of ERK1/2"


@pytest.mark.asyncio
async def test_similar_effects_are_repaired_from_their_source_without_retry():
    request = {"source_units": [{
        "id": "S1",
        "text": "Similar effects were observed in central IKKb knockout mice and, in the MBH, "
                "SOCS3 overexpression decreased the neural IKKb inhibition effect on obesity reduction.",
    }]}

    class SimilarEffectsRepairLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, system, user):
            self.calls.append(user)
            return "B T4 B1 | sub=central IKKb knockout mice | " \
                   "pred=similar_effects_were_observed_in | obj= | unit=S1"

    llm = SimilarEffectsRepairLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1"])

    assert step["retries"] == 0
    assert len(llm.calls) == 1
    assert rows[0]["data"]["subject"] == "Similar effects"
    assert rows[0]["data"]["predicate"] == "were_observed_in"
    assert rows[0]["data"]["object"] == "central IKKb knockout mice"


@pytest.mark.asyncio
async def test_shared_passive_preserves_both_coordinated_outcomes_from_source():
    source = (
        "Upon removal of senescent cells from HFD or obese mice deficient in leptin receptors, "
        "neurogenesis being restored and a decline in anxiety-related behavior was observed [16]."
    )
    request = {"source_units": [{"id": "S1", "text": source}]}
    initial = "\n".join([
        "B T4 B1 | sub=neurogenesis | pred=was_restored | obj= | unit=S1",
        "B T4 B2 | sub=a decline in anxiety-related behavior | pred=was_observed | obj= | unit=S1",
    ])

    class SharedPassiveLLM(FakeLLM):
        def __init__(self):
            self.calls = []

        async def __call__(self, system, user):
            self.calls.append(user)
            return initial

    llm = SharedPassiveLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1"])

    assert step["retries"] == 0
    assert len(llm.calls) == 1
    assert [(row["data"]["subject"], row["data"]["predicate"], row["data"]["object"])
            for row in rows] == [
        ("neurogenesis", "was_restored_after",
         "removal of senescent cells from HFD or obese mice deficient in leptin receptors"),
        ("a decline in anxiety-related behavior", "was_observed_after",
         "removal of senescent cells from HFD or obese mice deficient in leptin receptors"),
    ]


@pytest.mark.asyncio
async def test_shared_passive_repairs_inverted_patient_even_when_row_is_complete():
    context = "senescent cells from HFD or obese mice deficient in leptin receptors"
    source = (
        f"Upon removal of {context}, neurogenesis being restored and a decline in "
        "anxiety-related behavior was observed [16]."
    )
    request = {"source_units": [{"id": "S1", "text": source}]}
    inverted = "\n".join([
        f"B T4 B1 | sub=removal of {context} | pred=restored | obj=neurogenesis | unit=S1",
        f"B T4 B2 | sub=removal of {context} | pred=was_observed | "
        "obj=a decline in anxiety-related behavior | unit=S1",
    ])

    class InvertedSharedPassiveLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return inverted

    rows, step = await extract_structural_rows(
        InvertedSharedPassiveLLM(), request, ["S1"],
    )

    assert step["retries"] == 0
    assert [(row["data"]["subject"], row["data"]["predicate"])
            for row in rows] == [
        ("neurogenesis", "was_restored_after"),
        ("a decline in anxiety-related behavior", "was_observed_after"),
    ]
    assert all(row["data"]["object"] == f"removal of {context}" for row in rows)


@pytest.mark.asyncio
async def test_word_joining_underscores_are_normalized_only_in_free_text_fields():
    source = "α-MSH and glutamate are two major signals."
    request = {"source_units": [{"id": "S1", "text": source}]}

    class UnderscoredFreeTextLLM(FakeLLM):
        async def __call__(self, _system, _user):
            return "B T4 B1 | sub=α-MSH_and_glutamate | pred=are_major_signals " \
                   "| obj=two_major_signals | unit=S1"

    rows, step = await extract_structural_rows(
        UnderscoredFreeTextLLM(), request, ["S1"],
    )

    assert step["retries"] == 0
    assert rows[0]["data"]["subject"] == "α-MSH and glutamate"
    assert rows[0]["data"]["predicate"] == "are_major_signals"
    assert rows[0]["data"]["object"] == "two major signals"


@pytest.mark.asyncio
async def test_malformed_batch_is_self_corrected_once():
    request = {"source": TEXT, "source_units": [{"id": "S1", "text": TEXT},
                                                {"id": "S2", "text": TEXT_WITH_PVALUE}]}
    malformed = DSL.replace("unit=S1", "unit=S99")
    class CorrectingLLM(FakeLLM):
        def __init__(self):
            self.calls = []
        async def __call__(self, system, user):
            self.calls.append(user)
            return DSL if len(self.calls) > 1 else malformed
    rows, model_steps = await extract_structural_rows(CorrectingLLM(), request, ["S1", "S2"])
    assert len(rows) == 7
    assert model_steps["retries"] == 1
    assert all(r["data"]["unit"] in ("S1", "S2") for r in rows)

@pytest.mark.asyncio
async def test_stubborn_malformed_batch_raises_after_retries():
    request = {"source": TEXT, "source_units": [{"id": "S1", "text": TEXT}]}
    malformed = DSL.replace("unit=S1", "unit=S99")
    calls = []
    class StubbornLLM(FakeLLM):
        async def __call__(self, system, user):
            calls.append(user)
            return malformed
    with pytest.raises(ValidationError, match="still invalid after 3 corrections") as error:
        await extract_structural_rows(StubbornLLM(), request, ["S1"])
    assert len(calls) == 4
    assert error.value.rejected_dsl == (malformed, malformed, malformed, malformed)

@pytest.mark.asyncio
async def test_text_only_relation_skips_self_loop():
    dsl = "\n".join([
        "B T1 B1 | doi=10.1 | unit=S1",
        "B T4 B2 | sub=Clusterin | pred=inhibits | obj=inflammaging | unit=S1",
        "B T4 B3 | sub=aged mice | pred=show | obj=fibrosis | unit=S2",
        "B T58 B4 | src=Clusterin | tgt=inflammaging | rel=supports | unit=S1",
    ])
    _, _, blocks = build_blocks(dsl)
    graph = build_knowledge_map(blocks)
    assert graph["semantic_edges"] == []

@pytest.mark.asyncio
async def test_relation_edge_by_text_with_distinct_endpoint_rows():
    dsl = "\n".join([
        "B T1 B1 | doi=10.1 | unit=S1",
        "B T22 B2 | sub=Clusterin | pred=is_a | obj=protein | unit=S1",
        "B T4 B3 | sub=aged mice | pred=show | obj=fibrosis | unit=S2",
        "B T58 B4 | src=Clusterin | tgt=aged mice | rel=associates | unit=S1",
    ])
    _, _, blocks = build_blocks(dsl)
    graph = build_knowledge_map(blocks)
    by_tag = tags(blocks)
    assert len(graph["semantic_edges"]) == 1
    edge = graph["semantic_edges"][0]
    assert edge["resolution"] == "text"
    assert edge["source"] == by_tag["B2"] and edge["target"] == by_tag["B3"]

@pytest.mark.asyncio
async def test_unresolved_endpoint_produces_no_edge():
    dsl = "\n".join([
        "B T1 B1 | doi=10.1 | unit=S1",
        "B T4 B2 | sub=Clusterin | pred=inhibits | obj=inflammaging | unit=S1",
        "B T58 B4 | src=Clusterin | tgt=nonexistent result | rel=supports | unit=S1",
    ])
    _, _, blocks = build_blocks(dsl)
    assert build_knowledge_map(blocks)["semantic_edges"] == []

@pytest.mark.asyncio
async def test_undeclared_ref_rejected_at_builder_time():
    source, profile, blocks = build_blocks(DSL.replace("tgtRef=B9", "tgtRef=B99"))
    with pytest.raises(ValidationError, match="refs undeclared row B99"):
        build_knowledge_map(blocks)

@pytest.mark.asyncio
async def test_map_nodes_equal_blocks_and_display_text_present():
    _, _, blocks = build_blocks()
    graph = build_knowledge_map(blocks)
    validate_map(graph, blocks)
    assert {n["id"] for n in graph["nodes"]} == {b["instanceId"] for b in blocks}
    assert all(n["display_text"] for n in graph["nodes"])
    relation = graph["nodes"][5]
    assert "Clusterin" in relation["display_text"] and "supports" in relation["display_text"]

@pytest.mark.asyncio
async def test_quality_metrics_gates_and_review_boundaries():
    source, profile, blocks = build_blocks()
    report = evaluate_article_transformation(source, profile, blocks, build_knowledge_map(blocks))
    assert report["gates"]["passed"] is True
    assert report["linguistic"]["token_count"] == len(profile["tokens"])
    assert report["structural_rows"]["provenance_completeness"] == 1.0
    assert report["knowledge_map"]["orphan_node_count"] == 6
    assert 0.0 < report["quality"]["automated_score"] < 100.0
    assert report["manual_review"]["assertion_precision"] == "requires_gold_standard"

@pytest.mark.asyncio
async def test_quality_metrics_fail_provenance_gate_without_hiding_defect():
    source, profile, blocks = build_blocks()
    blocks[0]["data"]["provenance"]["source_spans"] = []
    report = evaluate_article_transformation(source, profile, blocks, build_knowledge_map(blocks))
    assert report["gates"]["passed"] is False
    assert report["structural_rows"]["provenance_completeness"] < 1.0


@pytest.mark.asyncio
async def test_caption_units_require_image_rows_and_are_measured_separately():
    caption_text = (
        "Figure 1: Rapamycin reduced fibrosis in aged mice.\n"
        "Table 1: Fibrosis score was lower after rapamycin treatment."
    )
    caption_dsl = "\n".join([
        "B T1 B1 | title=Caption study | unit=S1",
        "B T49 B2 | caption=Figure 1 Rapamycin reduced fibrosis in aged mice | unit=S1",
        "B T4 B3 | sub=Rapamycin | pred=reduces | obj=fibrosis | unit=S1",
        "B T49 B4 | caption=Table 1 Fibrosis score was lower after rapamycin treatment | unit=S2",
        "B T4 B5 | sub=Rapamycin treatment | pred=lowers | obj=fibrosis score | unit=S2",
    ])
    source = source_revision("caption-study", caption_text)
    profile = linguistic_profile(source, document(caption_text))
    rows = parse_dsl_rows(caption_dsl, [unit["id"] for unit in source_units(profile, caption_text)])
    blocks = materialize_rows(rows, source, profile)
    report = evaluate_article_transformation(source, profile, blocks, build_knowledge_map(blocks))
    assert report["gates"]["checks"]["caption_conversion_complete"] is True
    assert report["source_accounting"]["caption_unit_count"] == 2
    assert report["source_accounting"]["caption_image_coverage"] == 1.0
    assert report["structural_rows"]["caption_semantic_row_count"] == 2


@pytest.mark.asyncio
async def test_caption_image_row_is_added_without_model_output():
    caption_text = "Figure 1: Rapamycin reduced fibrosis in aged mice."
    source = source_revision("caption-study", caption_text)
    profile = linguistic_profile(source, document(caption_text))
    rows = parse_dsl_rows("\n".join([
        "B T1 B1 | title=Caption study | unit=S1",
        "B T4 B2 | sub=Rapamycin | pred=reduces | obj=fibrosis | unit=S1",
    ]), ["S1"])
    blocks = materialize_rows(rows, source, profile)
    report = evaluate_article_transformation(source, profile, blocks, build_knowledge_map(blocks))
    assert report["gates"]["checks"]["caption_conversion_complete"] is False

    snapshots = []
    async def checkpoint(result): snapshots.append(result)
    result = await ArticlePipeline(FakeNLP(), FakeLLM("\n".join([
        "B T1 B1 | title=Caption study | unit=S1",
        "B T4 B2 | sub=Rapamycin | pred=reduces | obj=fibrosis | unit=S1",
        ]))).run("caption-study", caption_text, checkpoint)
    assert result["success"] is True
    image = next(block for block in result["blocks"] if block["blockType"] == "image")
    assert image["data"]["caption"] == caption_text
    assert result["coverage"]["uncovered_caption_unit_ids"] == []


def test_html_figcaption_is_a_caption_source_unit():
    caption_text = "<figure><figcaption><strong>Figure 1</strong> Rapamycin reduced fibrosis.</figcaption></figure>"
    source = source_revision("html-caption-study", caption_text)
    profile = linguistic_profile(source, document(caption_text))
    assert caption_unit_ids(profile, caption_text) == {"S1", "S2"}


@pytest.mark.asyncio
async def test_pipeline_persists_stage_timing_and_prompt_metadata():
    snapshots = []

    async def checkpoint(result):
        snapshots.append(result)

    result = await ArticlePipeline(FakeNLP(), FakeLLM(DSL)).run(
        "timing-study", TEXT_WITH_PVALUE, checkpoint)
    assert result["timing"]["total_seconds"] >= 0
    assert result["timing"]["nlp_seconds"] >= 0
    assert result["timing"]["llm_seconds"] >= 0
    assert result["model_steps"][0]["prompt_id"] == "KM.ARTICLE_ROWS"
    assert result["model_steps"][0]["prompt_version"] == "147"

@pytest.mark.asyncio
async def test_text_block_missing_content_is_reconstructed_from_source():
    source, profile, _ = build_blocks()
    rows = [{"blockType": "text", "tag": "B1", "data": {"tag": "B1", "unit": "S1"}}]
    blocks = materialize_rows(rows, source, profile)
    sent = profile["sentences"][0]
    assert blocks[0]["data"]["content"] == source["text"][sent["start"]:sent["end"]]

@pytest.mark.asyncio
async def test_text_block_present_content_is_not_overridden():
    source, profile, _ = build_blocks()
    rows = [{"blockType": "text", "tag": "B1", "data": {"tag": "B1", "unit": "S1", "content": "kept"}}]
    blocks = materialize_rows(rows, source, profile)
    assert blocks[0]["data"]["content"] == "kept"

@pytest.mark.asyncio
async def test_structural_extraction_rejects_missing_required_fields_on_last_attempt():
    request = {"source": TEXT, "source_units": [{"id": "S1", "text": TEXT}]}
    calls = []
    class T4NoObjectLLM(FakeLLM):
        async def __call__(self, system, user):
            calls.append(user)
            return "B T4 B1 | sub=Clusterin | pred=inhibits | unit=S1"
    with pytest.raises(ValidationError, match=r"lacks required fields: obj \(JSON: object\)"):
        await extract_structural_rows(T4NoObjectLLM(), request, ["S1"])
    assert len(calls) == 4
    assert "obj (JSON: object)" in calls[1]
    assert "EXACT REPLACEMENT DSL KEYS (canonical short keys only" in calls[1]


def test_required_field_feedback_uses_dsl_key_and_keeps_storage_name_as_context():
    from knowledge_pipeline.dsl_rows import missing_required_fields

    row = {"blockType": "animal_group", "tag": "B7",
           "data": {"tag": "B7", "unit": "S1"}}
    assert missing_required_fields(row) == ["name (JSON: groupName)"]


def test_json_field_spelling_does_not_satisfy_dsl_required_field():
    from knowledge_pipeline.dsl_rows import missing_required_fields

    row = parse_dsl_rows(
        "B T4 B1 | sub=Clusterin | pred=inhibits | object=inflammaging | unit=S1", ["S1"])[0]
    assert row["data"]["_extra"] == {"object": "inflammaging"}
    assert missing_required_fields(row) == ["obj (JSON: object)"]


@pytest.mark.asyncio
async def test_extraction_rejects_json_alias_even_when_canonical_dsl_key_is_present():
    request = {"source": "Clusterin inhibits inflammation.",
               "source_units": [{"id": "S1", "text": "Clusterin inhibits inflammation."}]}
    dsl = ("B T4 B1 | sub=Clusterin | pred=inhibits | obj=inflammation | "
           "object=inflammation | unit=S1")

    with pytest.raises(ValidationError, match="unknown DSL fields: object"):
        await extract_structural_rows(FakeLLM(dsl), request, ["S1"])


def test_dsl_parser_diagnoses_fields_joined_without_pipe_delimiters():
    malformed = (
        "B T4 B1 | sub=Clusterin pred=inhibits obj=inflammation unit=S1"
    )
    with pytest.raises(ValidationError, match="non-pipe-delimited fields before pred="):
        parse_dsl_rows(malformed, ["S1"])


@pytest.mark.asyncio
async def test_semantic_audit_replaces_valid_but_incomplete_draft_with_complete_dsl():
    source = "71 participants were cognitively non-impaired and 80 had MCI."
    request = {"source_units": [{"id": "S1", "text": source}]}
    draft = "B T25 B1 | n=71 | unit=S1"
    reviewed = "\n".join([
        "B T25 B1 | n=71 | unit=S1",
        "B T36 B2 | sum=71 participants were cognitively non-impaired | unit=S1",
        "B T25 B3 | n=80 | unit=S1",
        "B T36 B4 | sum=80 participants had MCI | unit=S1",
    ])

    class AuditingLLM:
        semantic_audit_enabled = True

        def __init__(self):
            self.calls = []

        async def __call__(self, _system, user):
            self.calls.append(user)
            return draft if len(self.calls) == 1 else reviewed

    llm = AuditingLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1"])

    assert len(llm.calls) == 2
    assert "INDEPENDENT SEMANTIC AUDIT" in llm.calls[1]
    assert "CANDIDATE_DSL (untrusted draft)" in llm.calls[1]
    assert "Return the complete corrected DSL" in " ".join(llm.calls[1].split())
    assert [row["data"]["sampleSize"] for row in rows
            if row["blockType"] == "sample_size"] == ["71", "80"]
    assert [row["data"]["resultsSummary"] for row in rows
            if row["blockType"] == "result"] == [
                "71 participants were cognitively non-impaired",
                "80 participants had MCI",
            ]
    assert step["semantic_audit"] == "accepted"
    assert step["semantic_audit_attempts"] == 1


@pytest.mark.asyncio
async def test_semantic_audit_retains_validated_candidate_after_invalid_dsl_responses():
    source = "Clusterin inhibits inflammation."
    request = {"source_units": [{"id": "S1", "text": source}]}
    draft = "B T4 B1 | sub=Clusterin | pred=inhibits | obj=inflammation | unit=S1"

    class InvalidAuditingLLM:
        semantic_audit_enabled = True

        def __init__(self):
            self.calls = 0

        async def __call__(self, _system, _user):
            self.calls += 1
            return draft if self.calls == 1 else "The statement is complete."

    llm = InvalidAuditingLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1"])

    assert llm.calls == 4
    assert [(row["blockType"], row["data"]["subject"], row["data"]["object"])
            for row in rows if row["blockType"] == "statement"] == [
                ("statement", "Clusterin", "inflammation"),
            ]
    assert step["semantic_audit"] == "candidate_retained"
    assert any(item["code"] == "semantic_audit_unavailable"
               for item in step["warnings"])


@pytest.mark.asyncio
async def test_semantic_audit_inference_failure_keeps_candidate_as_warning():
    request = {"source_units": [{"id": "S1", "text": "Clusterin inhibits inflammation."}]}
    draft = "B T4 B1 | sub=Clusterin | pred=inhibits | obj=inflammation | unit=S1"

    class InterruptedAuditingLLM:
        semantic_audit_enabled = True

        def __init__(self):
            self.calls = 0

        async def __call__(self, _system, _user):
            self.calls += 1
            if self.calls == 1:
                return draft
            raise RuntimeError("upstream response.incomplete")

    llm = InterruptedAuditingLLM()
    rows, step = await extract_structural_rows(llm, request, ["S1"])

    assert llm.calls == 2
    assert len([row for row in rows if row["blockType"] == "statement"]) == 1
    assert step["semantic_audit"] == "candidate_retained"
    finding = next(item for item in step["warnings"]
                   if item["code"] == "semantic_audit_unavailable")
    assert finding["severity"] == "warning"
    assert "retained the structurally validated extraction candidate" in finding["message"]


@pytest.mark.asyncio
async def test_format_only_units_are_preserved_as_context_rows_without_llm_output():
    request = {
        "source": "\n\nClusterin inhibits inflammation.\n.\n# 4.\n## 1. Introduction\n</figure>",
        "source_units": [
            {"id": "S1", "text": "\n\n"},
            {"id": "S2", "text": "Clusterin inhibits inflammation."},
            {"id": "S3", "text": "."},
            {"id": "S4", "text": "# 4."},
            {"id": "S5", "text": "## 1. Introduction"},
            {"id": "S6", "text": "</figure>"},
        ],
    }
    prompts = []

    class OneSemanticRowLLM:
        async def __call__(self, _system, user):
            prompts.append(user)
            return "B T4 B1 | sub=Clusterin | pred=inhibits | obj=inflammation | unit=S2"

    rows, _metadata = await extract_structural_rows(
        OneSemanticRowLLM(), request, ["S1", "S2", "S3", "S4", "S5", "S6"])

    assert "UNIT_ORDER: S2" in prompts[0]
    assert all(f"{unit} |" not in prompts[0] for unit in ("S1", "S3", "S4", "S5", "S6"))
    assert [(row["blockType"], row["data"]["unit"], row["tag"]) for row in rows] == [
        ("text", "S1", "B1"), ("statement", "S2", "B2"),
        ("text", "S3", "B3"), ("text", "S4", "B4"), ("text", "S5", "B5"),
        ("text", "S6", "B6"),
    ]


@pytest.mark.asyncio
async def test_all_context_only_batch_returns_t3_without_calling_the_model():
    request = {"source_units": [{"id": "S1", "text": "## Methods"}]}

    class NoCallLLM:
        async def __call__(self, *_):
            raise AssertionError("context-only batches must not call the model")

    rows, step = await extract_structural_rows(NoCallLLM(), request, ["S1"])

    assert len(rows) == 1
    assert rows[0]["blockType"] == "text"
    assert rows[0]["data"]["unit"] == "S1"
    assert step["retries"] == 0


def test_unclosed_citation_in_text_value_cannot_hide_unit_field():
    rows = parse_dsl_rows(
        "B T4 B1 | sub=Depression | pred=related | obj=multimorbidity [35 | unit=S1",
        ["S1"],
    )

    assert rows[0]["data"]["object"] == "multimorbidity [35"
    assert rows[0]["data"]["unit"] == "S1"


def test_escaped_dsl_text_value_roundtrips_losslessly():
    rows = parse_dsl_rows(
        r"B T3 B1 | content=table A\|B\nnext\\path | unit=S1",
        ["S1"],
    )

    assert rows[0]["data"]["content"] == "table A|B\nnext\\path"


def test_p_value_comparator_is_preserved():
    rows = parse_dsl_rows("B T27 B1 | p=<0.001 | unit=S1", ["S1"])
    assert rows[0]["data"]["pValue"] == "<0.001"

@pytest.mark.asyncio
async def test_asset_roundtrip_is_deterministic():
    source, profile, blocks = build_blocks()
    loaded = json.loads(json.dumps({"source": source, "linguistic_profile": profile,
                                    "blocks": blocks, "graph": build_knowledge_map(blocks)}))
    validate_linguistic(loaded["linguistic_profile"], loaded["source"])
    validate_structural(loaded["blocks"], loaded["source"], loaded["linguistic_profile"]["sentences"])
    validate_map(loaded["graph"], loaded["blocks"])
    assert loaded["graph"] == build_knowledge_map(loaded["blocks"])

@pytest.mark.asyncio
async def test_duplicate_block_tag_rejected():
    dsl = DSL.replace("B T4 B4", "B T4 B2", 1)
    with pytest.raises(ValidationError, match="Duplicate"):
        parse_dsl_rows(dsl, ["S1", "S2"])

@pytest.mark.asyncio
async def test_materialize_rejects_unknown_unit():
    source, profile, _ = build_blocks()
    rows = [{"blockType": "metadata", "tag": "B1", "data": {"doi": "10.1", "unit": "S9"}}]
    with pytest.raises(ValidationError, match="unknown unit"):
        materialize_rows(rows, source, profile)

@pytest.mark.asyncio
async def test_failure_checkpoint_keeps_linguistic_profile():
    snapshots = []
    async def checkpoint(result): snapshots.append(copy.deepcopy(result))
    with pytest.raises(ValidationError):
        await ArticlePipeline(FakeNLP(), FakeLLM("B T99 B1 | unit=S1")).run("article", TEXT, checkpoint)
    assert snapshots[-1]["stage"] == "linguistic_profile"
    assert snapshots[-1]["linguistic_profile"]["source_revision_id"] == source_revision("article", TEXT)["id"]

@pytest.mark.asyncio
async def test_resume_after_failure_completes():
    snapshots = []
    async def checkpoint(result): snapshots.append(copy.deepcopy(result))
    with pytest.raises(ValidationError):
        await ArticlePipeline(FakeNLP(), FakeLLM(DSL.replace("B T58 B6", "B T99 B6"))).run(
            "article", TEXT, checkpoint)
    resume = snapshots[-1]
    assert resume["stage"] == "linguistic_profile"
    result = await ArticlePipeline(FakeNLP(), FakeLLM()).run(
        "article", TEXT, checkpoint, resume=resume)
    assert result["stage"] == "complete" and result["success"] is True
    assert result["version_id"] != resume["version_id"] or len(result["blocks"]) == 6
    assert not any(block["blockType"] == "probability_value"
                   for block in result["blocks"])

@pytest.mark.asyncio
async def test_literal_and_bool_normalization():
    _, _, blocks = build_blocks()
    p_value = next(b for b in blocks if b["blockType"] == "probability_value")
    assert p_value["data"]["pValue"] == 0.014
    negated = next(b for b in blocks
                   if b["blockType"] == "statement" and b["data"]["subject"] == "aged mice")
    assert negated["data"]["negated"] is True
    result_row = next(b for b in blocks if b["blockType"] == "finding")
    assert result_row["data"]["groupRefs"] == ["B2"]

@pytest.mark.asyncio
async def test_pipeline_rejects_wrong_article_text_in_nlp():
    async def nlp(text): return document(text + " changed")
    async def checkpoint(result): pass
    with pytest.raises(ValidationError, match="NLP changed original text"):
        await ArticlePipeline(nlp, FakeLLM()).run("article", TEXT, checkpoint)


async def _noop(result):
    del result


def test_strip_references_removes_trailing_bibliography():
    from knowledge_pipeline.reference_stripping import strip_references, strip_references_info
    text = "Body text stays here.\n\n# References\n[1] A. Author, Journal, 2024.\n[2] B. Author, Journal, 2025."
    assert strip_references(text) == "Body text stays here."
    stripped, info = strip_references_info(text)
    assert info == {"start_char": 23, "heading": "# References", "removed_chars": len(text) - 23}
    assert stripped == "Body text stays here."


def test_strip_references_heading_variants():
    from knowledge_pipeline.reference_stripping import strip_references
    for heading in ("References:", "BIBLIOGRAPHY", "Works Cited", "## Literature Cited",
                    "References [1–12]:", "Reference List"):
        assert strip_references(f"Lead sentence.\n\n{heading}\n[1] x") == "Lead sentence."


def test_strip_references_keeps_body_offsets_without_references_heading():
    from knowledge_pipeline.reference_stripping import strip_references, strip_references_info
    text = "No references section present."
    assert strip_references(text) == text
    assert strip_references_info(text) == (text, None)


def test_strip_references_is_idempotent():
    from knowledge_pipeline.reference_stripping import strip_references
    text = "Sentence one. Sentence two.\n\nReferences\n[1] Citation."
    once = strip_references(text)
    assert strip_references(once) == once


@pytest.mark.asyncio
async def test_pipeline_strips_references_before_nlp_and_llm():
    from knowledge_pipeline.reference_stripping import strip_references_info
    article = TEXT_WITH_PVALUE + "\n\n## References\n[1] Some, T. Journal 2024.\n"
    calls = []
    class RecordNLP(FakeNLP):
        def __init__(self):
            self.inputs = []
        async def __call__(self, text):
            self.inputs.append(text)
            return document(text)
    nlp = RecordNLP()
    result = await ArticlePipeline(nlp, FakeLLM(DSL, calls=calls)).run("article", article, _noop)
    assert all("References" not in inp for inp in nlp.inputs)
    assert all("References" not in user for user in calls)
    assert result["processing"]["references_removed"] == strip_references_info(article)[1]
    assert result["source"]["text"] == TEXT_WITH_PVALUE
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_extraction_rejects_batch_missing_source_units():
    partial = "\n".join([
        "B T1 B1 | doi=10.1 | title=Clusterin regulates inflammaging | authors=[A, B] | year=2024 | unit=S1",
        "B T4 B2 | sub=Clusterin | pred=inhibits | obj=inflammaging | unit=S1",
    ])
    from knowledge_pipeline.semantic_extraction import DslExtractionError
    with pytest.raises(DslExtractionError, match="missing source-unit rows: S2") as error:
        await ArticlePipeline(FakeNLP(), FakeLLM(partial)).run("article", TEXT, _noop)
    assert len(error.value.rejected_dsl) == 4


@pytest.mark.asyncio
async def test_strict_coverage_gate_can_use_one_row_per_sentence():
    full = "\n".join([
        "B T1 B1 | doi=10.1 | title=Clusterin regulates inflammaging | authors=[A, B] | year=2024 | unit=S1",
        "B T4 B2 | sub=Clusterin | pred=inhibits | obj=inflammaging | unit=S1",
        "B T4 B3 | sub=aged mice | pred=show | obj=fibrosis | neg=true | unit=S2",
    ])
    result = await ArticlePipeline(FakeNLP(), FakeLLM(full)).run("article", TEXT, _noop)
    assert result["status"] == "completed"
    assert result["coverage"]["uncovered_sentence_ids"] == []
    assert result["coverage"]["sentence_count"] == 2


@pytest.mark.asyncio
async def test_evidence_metric_is_deterministic_and_covered_by_quality():
    result = await ArticlePipeline(FakeNLP(), FakeLLM(DSL)).run(
        "article", TEXT_WITH_PVALUE, _noop)
    evidence = result["quality_metrics"]["evidence"]
    assert set(evidence) == {"blocks_supported", "blocks_total", "evidence_fraction", "details"}
    assert evidence["blocks_total"] == len(result["blocks"]) == 7
    assert result["quality_metrics"]["quality"]["semantic_fidelity"] == evidence["evidence_fraction"]
    assert isinstance(evidence["evidence_fraction"], float)


def test_coverage_gate_uncovered_ids_reported_in_deterministic_order():
    from knowledge_pipeline.pipeline import ArticlePipeline as AP
    profile = {"sentences": [{"id": "a", "start": 0, "end": 5}, {"id": "b", "start": 6, "end": 11},
                             {"id": "c", "start": 12, "end": 17}], "tokens": []}
    blocks = [{"data": {"provenance": {"unit_ids": ["S2"], "source_spans": []}}}]
    covered, uncovered = AP._sentence_coverage(profile, blocks)
    assert covered == {1}
    assert uncovered == ["S1", "S3"]


def _batch_rows(unit_id, tag, block_type="statement", fields=None):
    return f"B T4 B{tag} | sub=sub|{tag} | pred=affects | obj=obj | unit={unit_id}" \
        if block_type == "statement" else None


class BatchFakeLLM:
    def __init__(self, rows_by_unit):
        self.rows_by_unit, self.calls = rows_by_unit, []

    async def __call__(self, system, user):
        import re as _re
        units = _re.findall(r"^S\d+ \|.*\| text=", user, _re.M)
        unit_ids = _re.findall(r"^(S\d+) \|.*\| text=", user, _re.M)
        self.calls.append(user)
        lines = [self.rows_by_unit[u] for u in unit_ids if u in self.rows_by_unit]
        return "\n".join(lines) + "\n"


@pytest.mark.asyncio
async def test_batched_pipeline_covers_every_sentence_with_global_tags():
    rows_by_unit = {
        "S1": "B T4 B1 | sub=clusterin | pred=regulates | obj=inflammaging | unit=S1",
        "S2": "B T4 B2 | sub=aged mice | pred=show | obj=fibrosis | neg=true | unit=S2",
    }
    stages = []
    async def checkpoint(result):
        stages.append(result["stage"])
    result = await ArticlePipeline(FakeNLP(), BatchFakeLLM(rows_by_unit), batch_sentences=1).run(
        "article", TEXT, checkpoint)
    assert result["status"] == "completed"
    assert result["execution"]["mode"] == "batched_sentences"
    assert result["execution"]["batch_sentences"] == 1
    assert result["coverage"]["uncovered_sentence_ids"] == []
    assert result["coverage"]["sentence_count"] == 2
    tags = [b["data"]["tag"] for b in result["blocks"]]
    assert tags == ["B1", "B2"]
    assert len(result["model_steps"]) == 2
    assert [s["chunk"] for s in result["model_steps"]] == [0, 1]
    assert all(b["data"]["provenance"]["unit_ids"] for b in result["blocks"])


@pytest.mark.asyncio
async def test_batched_extraction_rejects_batch_that_drops_units():
    rows_by_unit = {"S1": "B T4 B1 | sub=clusterin | pred=regulates | obj=inflammaging | unit=S1"}
    from knowledge_pipeline.semantic_extraction import DslExtractionError
    with pytest.raises(DslExtractionError, match="missing source-unit rows: S2"):
        await ArticlePipeline(FakeNLP(), BatchFakeLLM(rows_by_unit), batch_sentences=2).run(
            "article", TEXT, _noop)


@pytest.mark.asyncio
async def test_batched_resume_reuses_completed_batches_without_rerunning_llm():
    import re as _re

    class FlakyBatchLLM(BatchFakeLLM):
        def __init__(self, rows_by_unit, fail_batch):
            super().__init__(rows_by_unit)
            self.fail_batch = fail_batch
        async def __call__(self, system, user):
            unit_ids = _re.findall(r"^(S\d+) \|.*\| text=", user, _re.M)
            if unit_ids and unit_ids[0].endswith(self.fail_batch):
                raise RuntimeError("llm unavailable on " + unit_ids[0])
            self.calls.append(user)
            lines = [self.rows_by_unit[u] for u in unit_ids if u in self.rows_by_unit]
            return "\n".join(lines) + "\n"

    rows_by_unit = {
        "S1": "B T4 B1 | sub=clusterin | pred=regulates | obj=inflammaging | unit=S1",
        "S2": "B T4 B2 | sub=aged mice | pred=show | obj=fibrosis | neg=true | unit=S2",
    }
    snapshots = []
    async def checkpoint(result):
        snapshots.append(copy.deepcopy(result))
    flaky = ArticlePipeline(FakeNLP(), FlakyBatchLLM(rows_by_unit, "S2"), batch_sentences=1)
    with pytest.raises(RuntimeError, match="llm unavailable"):
        await flaky.run("article", TEXT, checkpoint)
    partial = next(s for s in reversed(snapshots) if s.get("processed") == 1)
    assert partial["model_steps"][0]["rows"][0]["data"]["tag"] == "B1"
    assert "S2" not in partial["model_steps"]

    resumed = await ArticlePipeline(
        FakeNLP(), BatchFakeLLM(rows_by_unit), batch_sentences=1).run(
        "article", TEXT, checkpoint, resume=partial)
    assert resumed["status"] == "completed"
    assert [b["data"]["tag"] for b in resumed["blocks"]] == ["B1", "B2"]
    assert len(resumed["model_steps"]) == 2
    assert resumed["model_steps"][1]["chunk"] == 1


@pytest.mark.asyncio
async def test_resume_does_not_trust_recovered_rows_missing_required_fields():
    import json as _json

    rows_by_unit = {
        "S1": "B T4 B1 | sub=clusterin | pred=regulates | obj=inflammaging | unit=S1",
        "S2": "B T4 B2 | sub=aged mice | pred=show | obj=fibrosis | neg=true | unit=S2",
    }
    stages = []
    async def checkpoint(result):
        stages.append(copy.deepcopy(result))
    partial = {"source": source_revision("article", TEXT),
               "article_id": "article",
               "run_id": "00000000-0000-0000-0000-0000000000aa",
               "version_id": "00000000-0000-0000-0000-0000000000bb",
               "stage": "linguistic_profile", "status": "running",
               "execution": {"chunk_chars": None, "mode": "batched_sentences", "batch_sentences": 1,
                             "prompt_id": "KM.ARTICLE_ROWS", "prompt_version": "133"},
               "processing": {}, "schemaVersion": 2,
               "linguistic_profile": copy.deepcopy(build_blocks()[1]),
               "model_steps": [{
                   "chunk": 0, "start": 0, "end": 1, "retries": 0,
                   "rows": [{"blockType": "statement", "tag": "B1",
                             "data": {"tag": "B1", "sub": "clusterin",
                                      "pred": "regulates", "unit": "S1"}}],
               }]}
    resumed = await ArticlePipeline(
        FakeNLP(), BatchFakeLLM(rows_by_unit), batch_sentences=1).run(
        "article", TEXT, checkpoint, resume=partial)
    assert resumed["status"] == "completed"
    assert len(resumed["model_steps"]) == 2
    assert {b["data"]["tag"] for b in resumed["blocks"]} == {"B1", "B2"}


@pytest.mark.asyncio
async def test_resume_rejects_checkpoint_from_older_prompt_version():
    partial = {"source": source_revision("article", TEXT), "article_id": "article",
               "run_id": "00000000-0000-0000-0000-0000000000aa",
               "version_id": "00000000-0000-0000-0000-0000000000bb",
               "stage": "source", "status": "running", "schemaVersion": 2,
               "execution": {"chunk_chars": None, "mode": "batched_sentences", "batch_sentences": 1,
                             "prompt_id": "KM.ARTICLE_ROWS", "prompt_version": "40"}}

    async def checkpoint(_result):
        return None

    with pytest.raises(ValidationError, match="Cannot resume with older extraction mode"):
        await ArticlePipeline(FakeNLP(), BatchFakeLLM({}), batch_sentences=1).run(
            "article", TEXT, checkpoint, resume=partial)


def test_remap_local_tags_offsets_tags_and_refs():
    from knowledge_pipeline.renumbering import remap_local_tags
    rows = [
        {"blockType": "relation", "tag": "B2",
         "data": {"tag": "B2", "sourceRef": "B1", "targetRef": "B1", "unit": "S1"}},
        {"blockType": "statement", "tag": "B1",
         "data": {"tag": "B1", "unit": "S1"}},
        {"blockType": "finding", "tag": "B3",
         "data": {"tag": "B3", "groupRefs": ["B1", "B2"], "unit": "S2"}},
    ]
    out = remap_local_tags(rows, 5)
    tags = [r["data"]["tag"] for r in out]
    assert tags == ["B5", "B6", "B7"]
    relation = next(r for r in out if r["blockType"] == "relation")
    assert relation["data"]["sourceRef"] == "B6"
    assert relation["data"]["targetRef"] == "B6"
    finding = next(r for r in out if r["blockType"] == "finding")
    assert finding["data"]["groupRefs"] == ["B6", "B5"]
