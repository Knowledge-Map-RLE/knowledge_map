"""Direct test of negation handling without gRPC."""
import pytest
from src.extractor.rules.pipeline import Pipeline

pipeline = Pipeline(use_llm=False)

def extract_statements(text: str) -> list[dict]:
    result = pipeline.process(text, doc_id="test", use_llm=False)
    stmts = []
    for s in result.statements:
        stmts.append({
            "subject": s.subject_id,
            "predicate": s.predicate,
            "object": s.object_id,
        })
    return stmts

@pytest.mark.e2e
def test_negation_copular():
    stmts = extract_statements("aging is not a molecular disease.")
    for s in stmts:
        print(f"  {s['subject']} -> {s['predicate']} -> {s['object']}")
    assert any("not" in s["predicate"] for s in stmts), f"No negated statement found. Got: {stmts}"

@pytest.mark.e2e
def test_negation_active():
    stmts = extract_statements("hallmarks do not include mutations.")
    for s in stmts:
        print(f"  {s['subject']} -> {s['predicate']} -> {s['object']}")
    assert any(s["predicate"] == "not include" for s in stmts), f"No 'not include' statement found. Got: {stmts}"

@pytest.mark.e2e
def test_negation_copular_not_equal():
    stmts = extract_statements("they are not equal.")
    for s in stmts:
        print(f"  {s['subject']} -> {s['predicate']} -> {s['object']}")
    assert any(s["predicate"] == "be not" for s in stmts), f"No 'be not' found. Got: {stmts}"

@pytest.mark.e2e
def test_copular_no_negation():
    stmts = extract_statements("aging is a molecular disease.")
    for s in stmts:
        print(f"  {s['subject']} -> {s['predicate']} -> {s['object']}")
    assert any(s["predicate"] == "be" for s in stmts), f"No 'be' found. Got: {stmts}"
    negated = [s for s in stmts if s["predicate"] == "be not"]
    assert not negated, f"Unexpected 'be not': {negated}"

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
