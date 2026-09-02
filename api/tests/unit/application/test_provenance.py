"""Тесты конверта знания (application/generation/provenance.py) и метаданных."""

from application.generation import (
    LOGICAL,
    PATTERN,
    SYLLOGISM,
    THINKING,
    KNOWLEDGE_METHODS,
    METHOD_LABELS,
    method_metadata,
)
from application.generation.provenance import (
    as_generate_group,
    build_knowledge_result,
)


def test_knowledge_methods_enum():
    assert set(KNOWLEDGE_METHODS) == {PATTERN, LOGICAL, SYLLOGISM, THINKING}
    assert METHOD_LABELS[PATTERN] == "Паттерн"
    assert METHOD_LABELS[SYLLOGISM] == "Силлогизм"


def test_build_knowledge_result():
    r = build_knowledge_result(
        method=LOGICAL,
        operation="transitivity",
        operation_label="Транзитивность",
        source_statements=[{"subject_text": "A", "predicate": "causes", "object_text": "B"}],
        new_statements=[{"subject_text": "A", "predicate": "causes", "object_text": "C"}],
        description="Вывод",
    )
    assert r["knowledge_method"] == LOGICAL
    assert r["operation"] == "transitivity"
    assert r["provenance"]["method_label"] == "Логическая операция"
    assert r["provenance"]["source_count"] == 1
    assert r["provenance"]["new_count"] == 1


def test_method_metadata_has_four_methods_and_moduses():
    md = method_metadata()
    assert [m["value"] for m in md] == [PATTERN, LOGICAL, SYLLOGISM, THINKING]
    assert len(md[0]["operations"]) == 1  # pattern: один плейс-холдер
    assert all(m["operations"] for m in md)
    syll = next(m for m in md if m["value"] == SYLLOGISM)
    assert len(syll["moduses"]) == 24


def test_as_generate_group():
    g = as_generate_group("Логика", [
        build_knowledge_result(method=LOGICAL, operation="t", operation_label="T",
                               source_statements=[{"subject_text": "A", "predicate": "r", "object_text": "B"}],
                               new_statements=[{"subject_text": "A", "predicate": "r", "object_text": "C"}],
                               description="d"),
    ])
    assert g["label"] == "Логика"
    assert g["count"] == 1
    assert g["new_total"] == 1
