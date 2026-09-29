import pytest

from knowledge_contracts.validation import ValidationError, validate_structural
from knowledge_pipeline.dsl_diagnostics import render_warning_report
from knowledge_pipeline.dsl_rows import parse_dsl_rows
from knowledge_pipeline.semantic_extraction import (
    _row_validation_issues,
    _merge_audit_rows_preserving_coverage,
    _renumber_dsl_row_tags,
    _semantic_warning_findings,
    extract_structural_rows,
)


def test_required_dsl_fields_remain_blocking_contract_errors():
    rows = parse_dsl_rows("B T21 B1 | unit=S1", ["S1"])

    issues = _row_validation_issues(rows)

    assert len(issues) == 1
    assert "meth (JSON: methods)" in issues[0][1]


def test_malformed_dsl_and_unknown_keys_remain_blocking_contract_errors():
    with pytest.raises(ValidationError):
        parse_dsl_rows("B T4 B1 | sub=subject | pred=relation", ["S1"])

    rows = parse_dsl_rows(
        "B T4 B1 | sub=subject | pred=relation | object=object | unit=S1",
        ["S1"],
    )

    issues = _row_validation_issues(rows)
    assert len(issues) == 1
    assert "unknown DSL fields: object" in issues[0][1]
    assert "lacks required fields: obj" in issues[0][1]


def test_relative_clause_heuristic_does_not_fail_structural_validation():
    source_text = "Identifying cells that regulate metabolism is useful."
    blocks = [{
        "instanceId": "row-1",
        "schemaVersion": 2,
        "blockType": "statement",
        "data": {
            "tag": "B1",
            "unit": "S1",
            "subject": "identifying cells that regulate metabolism",
            "predicate": "is",
            "object": "useful",
            "provenance": {
                "unit_ids": ["S1"],
                "source_spans": [{
                    "revision_id": "revision-1",
                    "start": 0,
                    "end": len(source_text),
                }],
            },
        },
        "order": 0,
    }]

    validate_structural(
        blocks,
        {"id": "revision-1", "text": source_text},
        [{"start": 0, "end": len(source_text)}],
    )


def test_semantic_coverage_and_numeric_diagnostics_are_warnings():
    source_units = [{
        "id": "S1",
        "text": "The treatment reduced mortality (p = 0.03).",
    }]
    rows = parse_dsl_rows(
        "B T3 B1 | content=The treatment reduced mortality (p = 0.03). | unit=S1",
        ["S1"],
    )

    warnings = _semantic_warning_findings(rows, source_units, None)

    assert _row_validation_issues(rows) == []
    assert all(item["severity"] == "warning" for item in warnings)
    assert {item["code"] for item in warnings} >= {
        "semantic_coverage", "pvalue_coverage",
    }


def test_adverbial_phrase_in_t4_object_is_warning_not_blocking_error():
    source_units = [{
        "id": "S1",
        "text": "Upon treatment, the pathway becomes active.",
    }]
    rows = parse_dsl_rows(
        "B T4 B1 | sub=the pathway | pred=becomes active "
        "| obj=upon treatment | unit=S1",
        ["S1"],
    )

    warnings = _semantic_warning_findings(rows, source_units, None)

    assert _row_validation_issues(rows) == []
    finding = next(item for item in warnings if item["code"] == "t4_adjunct_in_obj")
    assert finding["severity"] == "warning"
    assert finding["unit"] == "S1"
    assert finding["tag"] == "B1"
    assert "ctx=" in finding["message"]


def test_grammatical_object_does_not_trigger_t4_adjunct_warning():
    rows = parse_dsl_rows(
        "B T4 B1 | sub=the signal | pred=activates | obj=the pathway "
        "| ctx=after treatment | unit=S1",
        ["S1"],
    )

    warnings = _semantic_warning_findings(
        rows,
        [{"id": "S1", "text": "After treatment, the signal activates the pathway."}],
        None,
    )

    assert not any(item["code"] == "t4_adjunct_in_obj" for item in warnings)


@pytest.mark.asyncio
async def test_semantic_warnings_do_not_start_correction_or_fail_extraction():
    class FakeLlm:
        def __init__(self):
            self.calls = 0

        async def __call__(self, _system, _prompt):
            self.calls += 1
            return (
                "B T3 B1 | content=The treatment reduced mortality (p = 0.03). "
                "| unit=S1"
            )

    llm = FakeLlm()
    rows, step = await extract_structural_rows(
        llm,
        {"source_units": [{
            "id": "S1",
            "text": "The treatment reduced mortality (p = 0.03).",
        }]},
        ["S1"],
    )

    assert llm.calls == 1
    assert rows
    assert {item["code"] for item in step["warnings"]} >= {
        "semantic_coverage", "pvalue_coverage",
    }


@pytest.mark.asyncio
async def test_exact_t3_copy_is_removed_when_same_unit_has_explicit_t2_goals():
    source = (
        "In this review, we will summarize neurogenesis and explore therapy."
    )

    class GoalAndSignpostingLlm:
        async def __call__(self, _system, _user):
            return "\n".join([
                "B T2 B1 | sub=we | pred=will summarize | obj=neurogenesis | unit=S1",
                "B T3 B2 | content=" + source + " | unit=S1",
                "B T2 B3 | sub=we | pred=will explore | obj=therapy | unit=S1",
            ])

    rows, step = await extract_structural_rows(
        GoalAndSignpostingLlm(),
        {"source_units": [{"id": "S1", "text": source}]},
        ["S1"],
    )

    assert [row["blockType"] for row in rows] == ["goal", "goal"]
    assert [row["tag"] for row in rows] == ["B1", "B2"]
    assert "B T2 B2" in step["dsl"]
    assert "B T3 B2" not in step["dsl"]


def test_row_tag_renumbering_updates_references_and_warning_row_ids():
    rows = [
        {"blockType": "statement", "tag": "B1", "data": {"tag": "B1"}},
        {"blockType": "statement", "tag": "B3", "data": {
            "tag": "B3", "subjectStatementRef": "B1",
            "sourceRefs": ["B1", "B3"],
        }},
    ]
    warnings = [{"tag": "B3", "message": "Row B3 has a source-frame warning"}]

    mapping = _renumber_dsl_row_tags(rows, warnings)

    assert mapping == {"B1": "B1", "B3": "B2"}
    assert [row["tag"] for row in rows] == ["B1", "B2"]
    assert rows[1]["data"]["tag"] == "B2"
    assert rows[1]["data"]["subjectStatementRef"] == "B1"
    assert rows[1]["data"]["sourceRefs"] == ["B1", "B2"]
    assert warnings == [{"tag": "B2", "message": "Row B2 has a source-frame warning"}]


@pytest.mark.asyncio
async def test_goal_deduplication_preserves_distinct_t3_context_rows():
    source = "This review will summarize neurogenesis."

    class GoalWithSeparateHeadingLlm:
        async def __call__(self, _system, _user):
            return "\n".join([
                "B T2 B1 | sub=we | pred=will summarize | obj=neurogenesis | unit=S1",
                "B T3 B2 | content=Review scope | unit=S1",
            ])

    rows, _step = await extract_structural_rows(
        GoalWithSeparateHeadingLlm(),
        {"source_units": [{"id": "S1", "text": source}]},
        ["S1"],
    )

    assert [row["blockType"] for row in rows] == ["goal", "text"]


def test_warning_report_is_dsl_comments_only_and_sanitizes_article_text():
    report = render_warning_report(
        "PMC-1",
        "138",
        [{
            "severity": "warning",
            "code": "source_frame",
            "unit": "S7",
            "tag": "B12",
            "message": "Uncertain | frame\ncheck",
        }],
    )

    lines = report.splitlines()
    assert lines[0] == "# WARNING_REPORT case=PMC-1 prompt_version=138"
    assert lines[1].startswith("# WARNING code=source_frame unit=S7 row=B12 detail=")
    assert "\\|" in lines[1]
    assert all(line.startswith("#") for line in lines)
    assert len(lines) == 2
    with pytest.raises(ValidationError, match="no structural rows"):
        parse_dsl_rows(report, [])


def test_semantic_audit_preserves_omitted_unit_and_its_candidate_reference():
    candidate = parse_dsl_rows(
        "B T4 B1 | sub=aging | pred=is | obj=regulated | unit=S1\n"
        "B T4 B2 | sub=these findings | subop=identify_subjects | subref=B1 "
        "| pred=refer to | obj=aging | unit=S2",
        ["S1", "S2"],
    )
    audit = parse_dsl_rows(
        "B T4 B1 | sub=aging | pred=is | obj=regulated | unit=S1",
        ["S1", "S2"],
    )

    merged, restored_units = _merge_audit_rows_preserving_coverage(
        audit, candidate, ["S1", "S2"],
    )

    assert restored_units == ["S2"]
    assert {row["data"]["unit"] for row in merged} == {"S1", "S2"}
    assert len({row["tag"] for row in merged}) == len(merged)
    assert _row_validation_issues(merged) == []
    s2_row = next(row for row in merged if row["data"]["unit"] == "S2")
    target = next(row for row in merged if row["tag"] == s2_row["data"]["subjectStatementRef"])
    assert target["data"]["unit"] == "S1"


@pytest.mark.asyncio
async def test_missing_required_field_still_requests_a_repair():
    class FakeLlm:
        def __init__(self):
            self.calls = 0

        async def __call__(self, _system, _prompt):
            self.calls += 1
            if self.calls == 1:
                return "B T21 B1 | unit=S1"
            return "B T21 B1 | meth=Blood pressure was measured | unit=S1"

    llm = FakeLlm()
    rows, step = await extract_structural_rows(
        llm,
        {"source_units": [{
            "id": "S1",
            "text": "Blood pressure was measured.",
        }]},
        ["S1"],
    )

    assert llm.calls == 2
    assert rows[0]["data"]["methods"] == "Blood pressure was measured"
    assert step["warnings"] == []


@pytest.mark.asyncio
async def test_independent_audit_cannot_drop_an_entire_covered_source_unit():
    class FakeLlm:
        semantic_audit_enabled = True

        def __init__(self):
            self.calls = []

        async def __call__(self, _system, prompt):
            self.calls.append(prompt)
            if len(self.calls) == 1:
                return (
                    "B T4 B1 | sub=A | pred=regulates | obj=B | unit=S1\n"
                    "B T4 B2 | sub=C | pred=regulates | obj=D | unit=S2"
                )
            return "B T4 B1 | sub=A | pred=regulates | obj=B | unit=S1"

    llm = FakeLlm()
    rows, step = await extract_structural_rows(
        llm,
        {"source_units": [
            {"id": "S1", "text": "A regulates B."},
            {"id": "S2", "text": "C regulates D."},
        ]},
        ["S1", "S2"],
    )

    assert len(llm.calls) == 2
    assert "Never drop every candidate row" in llm.calls[1]
    assert step["semantic_audit"] == "accepted"
    assert {row["data"]["unit"] for row in rows} == {"S1", "S2"}
    assert [row["tag"] for row in rows] == ["B1", "B2"]


@pytest.mark.asyncio
async def test_nonassertional_caption_navigation_is_covered_by_pipeline_t49():
    class FakeLlm:
        semantic_audit_enabled = True

        def __init__(self):
            self.calls = 0

        async def __call__(self, _system, _prompt):
            self.calls += 1
            return "B T4 B1 | sub=participants | pred=complete | obj=the assessment | unit=S1"

    llm = FakeLlm()
    rows, step = await extract_structural_rows(
        llm,
        {
            "source_units": [
                {"id": "S1", "text": "Participants completed the assessment."},
                {"id": "S2", "text": "Participant status is also shown."},
            ],
            "caption_unit_ids": ["S2"],
        },
        ["S1", "S2"],
    )

    assert llm.calls == 2
    assert step["semantic_audit"] == "accepted"
    assert {row["data"]["unit"] for row in rows} == {"S1", "S2"}
    assert next(row for row in rows if row["data"]["unit"] == "S2")["blockType"] == "image"

