"""Direct test of negation handling through the legacy rule pipeline (no gRPC)."""
import pytest

from src.services.pipeline import Pipeline

pytestmark = pytest.mark.e2e

pipeline = Pipeline()


def _extract_statements(result: dict) -> list[dict]:
    return [
        {"subject": s.subject_id, "predicate": s.predicate, "object": s.object_id}
        for s in result.get("statements", [])
    ]


@pytest.mark.asyncio
async def test_negation_copular():
    stmts = _extract_statements(await pipeline.process("aging is not a molecular disease.", doc_id="test"))
    for s in stmts:
        print(f"  {s['subject']} -> {s['predicate']} -> {s['object']}")
    assert any("not" in s["predicate"] for s in stmts), f"No negated statement found. Got: {stmts}"


@pytest.mark.asyncio
async def test_negation_active():
    stmts = _extract_statements(await pipeline.process("hallmarks do not include mutations.", doc_id="test"))
    for s in stmts:
        print(f"  {s['subject']} -> {s['predicate']} -> {s['object']}")
    assert any(s["predicate"] == "not include" for s in stmts), f"No 'not include' statement found. Got: {stmts}"


@pytest.mark.asyncio
async def test_negation_copular_not_equal():
    stmts = _extract_statements(await pipeline.process("they are not equal.", doc_id="test"))
    for s in stmts:
        print(f"  {s['subject']} -> {s['predicate']} -> {s['object']}")
    assert any(s["predicate"] == "be not" for s in stmts), f"No 'be not' found. Got: {stmts}"


@pytest.mark.asyncio
async def test_copular_no_negation():
    stmts = _extract_statements(await pipeline.process("aging is a molecular disease.", doc_id="test"))
    for s in stmts:
        print(f"  {s['subject']} -> {s['predicate']} -> {s['object']}")
    assert any(s["predicate"] == "be" for s in stmts), f"No 'be' found. Got: {stmts}"
    negated = [s for s in stmts if s["predicate"] == "be not"]
    assert not negated, f"Unexpected 'be not': {negated}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
