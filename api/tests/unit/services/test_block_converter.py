"""Unit-тесты для services.block_converter — канонический вывод триплетов из блоков."""
from __future__ import annotations

from services.block_converter import (
    blocks_to_statements,
    blocks_to_statements_raw,
    find_name_field,
    CONVERTERS,
    split_lines,
    kv_pairs,
)


def _b(bt: int, data: dict, *, iid: str = "b1", order: int = 0) -> dict:
    return {"instanceId": iid, "blockType": bt, "data": data, "order": order}


class TestHelpers:
    def test_split_lines_string(self):
        assert split_lines("a\nb\n\nc") == ["a", "b", "c"]

    def test_split_lines_non_string(self):
        assert split_lines(None) == []
        assert split_lines(42) == []

    def test_kv_pairs_dict(self):
        pairs = kv_pairs({"x": "1", "y": "2"})
        assert ("x", "1") in pairs
        assert ("y", "2") in pairs

    def test_kv_pairs_string(self):
        pairs = kv_pairs("k1: v1\nk2: v2")
        assert pairs[0] == ("k1", "v1")
        assert pairs[1] == ("k2", "v2")

    def test_kv_pairs_colon_in_value(self):
        pairs = kv_pairs("time: 2024-01-01T00:00:00")
        assert pairs[0] == ("time", "2024-01-01T00:00:00")


class TestFindNameField:
    def test_prefers_name(self):
        assert find_name_field(56, {"stepName": "X", "details": "Y"}) == "stepName"

    def test_falls_back_to_first_non_empty(self):
        data = {"prerequisites": "p1\np2"}
        assert find_name_field(8, data) == "prerequisites"

    def test_returns_none_for_empty(self):
        assert find_name_field(8, {}) is None


class TestConvertersExist:
    def test_all_block_types_have_converters(self):
        expected = {
            1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17,
            18, 19, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32,
            33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46,
            47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57,
        }
        assert set(CONVERTERS.keys()) == expected


class TestT1Metadata:
    def test_doi_title_authors(self):
        block = _b(1, {"doi": "10.1/x", "title": "T", "authors": "A;B\nC"})
        stmts = blocks_to_statements([block])
        preds = {s["predicate"] for s in stmts}
        assert "DOI" in preds
        assert "название статьи" in preds
        assert "авторы" in preds
        authors = [s["object_text"] for s in stmts if s["predicate"] == "авторы"]
        assert sorted(authors) == ["A", "B", "C"]

    def test_empty_block(self):
        assert blocks_to_statements([_b(1, {})]) == []


class TestT2Goal:
    def test_legacy_fallback(self):
        stmts = blocks_to_statements([_b(2, {"objective": "цель"})])
        assert len(stmts) == 1
        assert stmts[0]["subject_text"] == "Исследование"
        assert stmts[0]["predicate"] == "цель"

    def test_new_triplet(self):
        stmts = blocks_to_statements([_b(2, {"subject": "S", "predicate": "P", "object": "O"})])
        assert stmts[0]["subject_text"] == "S"


class TestT3FreeText:
    def test_no_triplets(self):
        assert blocks_to_statements([_b(3, {"content": "hello"})]) == []


class TestT4DirectTriplet:
    def test_produces_triplet(self):
        stmts = blocks_to_statements([_b(4, {"subject": "A", "predicate": "B", "object": "C"})])
        assert len(stmts) == 1
        assert stmts[0]["subject_text"] == "A"
        assert stmts[0]["type"] == "FACT"

    def test_missing_parts_no_triplet(self):
        assert blocks_to_statements([_b(4, {"subject": "A", "predicate": "", "object": "C"})]) == []


class TestT5T6Endpoints:
    def test_primary(self):
        stmts = blocks_to_statements([_b(5, {"endpoint": "死亡率"})])
        assert stmts[0]["predicate"] == "первая конечная точка"

    def test_secondary(self):
        stmts = blocks_to_statements([_b(6, {"endpoints": "a\nb"})])
        assert len(stmts) == 2


class TestT7Hypothesis:
    def test_hypothesis_and_disproof(self):
        stmts = blocks_to_statements([_b(7, {
            "hypothesis": "H",
            "disproofExplanation": "because",
        })])
        preds = {s["predicate"] for s in stmts}
        assert "гипотеза" in preds
        assert "требует опровежения потому что" in preds

    def test_no_hypothesis(self):
        assert blocks_to_statements([_b(7, {})]) == []


class TestT11Design:
    def test_all_fields(self):
        stmts = blocks_to_statements([_b(11, {
            "studyType": "RCT",
            "randomization": True,
            "blinding": "true",
        })])
        assert len(stmts) == 3
        preds = {s["predicate"] for s in stmts}
        assert preds == {"тип", "рандомизировано", "ослеплено"}


class TestT14Experiment:
    def test_experiment_triplets(self):
        stmts = blocks_to_statements([_b(14, {
            "experimentName": "Exp1",
            "experimentType": "Поведенческий",
            "outcomes": "rearing, grip strength",
            "duration": "2 weeks",
        })])
        preds = {s["predicate"] for s in stmts}
        assert "эксперимент" in preds
        assert "тип" in preds
        assert "измеряемые показатели" in preds
        assert "длительность" in preds

    def test_steps_and_findings_uuid_lists(self):
        import json
        stmts = blocks_to_statements([_b(14, {
            "steps": json.dumps(["uuid1", "uuid2"]),
            "findings": json.dumps(["uuid3"]),
        })])
        preds = {s["predicate"] for s in stmts}
        assert "шаг" in preds
        assert "результат" in preds

    def test_experimental_pairs(self):
        import json
        stmts = blocks_to_statements([_b(14, {
            "experimentalPairs": json.dumps([{"groupRef": "g1", "interventionRef": "iv1"}]),
        })])
        preds = [s["predicate"] for s in stmts]
        assert "экспериментальная группа" in preds
        assert "получает" in preds


class TestT38Claim:
    def test_negated(self):
        stmts = blocks_to_statements([_b(38, {
            "claimSubject": "Drug",
            "claimPredicate": "ингибирует",
            "claimObject": "target",
            "isNegated": True,
        })])
        assert stmts[0]["predicate"] == "не ингибирует"

    def test_with_confidence_notes(self):
        stmts = blocks_to_statements([_b(38, {
            "claimSubject": "Drug",
            "claimPredicate": "ингибирует",
            "claimObject": "target",
            "confidenceNotes": "N=3",
        })])
        assert stmts[0]["confidence"] == 0.8

    def test_missing_parts(self):
        assert blocks_to_statements([_b(38, {"claimSubject": "Drug"})]) == []


class TestT57Result:
    def test_direction_predicate(self):
        stmts = blocks_to_statements([_b(57, {
            "parameter": "p16+",
            "direction": "повышено",
            "subjectRef": "g1",
        })])
        assert stmts[0]["predicate"] == "повышено в"
        assert stmts[0]["object_text"] == "g1"

    def test_no_parameter_no_triplets(self):
        assert blocks_to_statements([_b(57, {"direction": "повышено"})]) == []


class TestRefResolution:
    def test_uuid_refs_resolved_subject(self):
        ref_block = _b(4, {"subject": "Drug", "predicate": "ингибирует", "object": "target"}, iid="ref1")
        consumer = _b(4, {
            "subject": "ref1",
            "predicate": "опирается на",
            "object": "ref1",
        }, iid="c1")
        stmts = blocks_to_statements([ref_block, consumer], resolve_refs=True)
        assert stmts[1]["subject_text"] == "Drug"
        assert stmts[1]["object_text"] == "Drug"

    def test_result_predicate_skips_object_ref(self):
        ref_block = _b(4, {"subject": "Drug", "predicate": "ингибирует", "object": "target"}, iid="ref1")
        consumer = _b(4, {
            "subject": "ref1",
            "predicate": "результат",
            "object": "ref1",
        }, iid="c1")
        stmts = blocks_to_statements([ref_block, consumer], resolve_refs=True)
        assert stmts[1]["predicate"] == "результат"
        assert stmts[1]["subject_text"] == "Drug"
        assert stmts[1]["object_text"] == "ref1"

    def test_step_predicate_skips_object_ref(self):
        ref_block = _b(4, {"subject": "Drug", "predicate": "ингибирует", "object": "target"}, iid="ref1")
        consumer = _b(56, {"stepName": "S", "details": "d", "duration": "1h", "sequence": '["ref1"]'}, iid="c1")
        stmts = blocks_to_statements([ref_block, consumer], resolve_refs=True)
        seq_stmts = [s for s in stmts if s["predicate"] == "последовательность"]
        assert seq_stmts[0]["object_text"] == "Drug"
        step_stmts = [s for s in stmts if s["predicate"] == "шаг"]
        assert step_stmts[0]["subject_text"] == "S"

    def test_article_uuid_replaces_statiya(self):
        block = _b(1, {"doi": "10.1/x"})
        stmts = blocks_to_statements([block], article_uuid="doc123")
        for s in stmts:
            if s["subject_text"] == "doc123":
                assert s["subject_text"] == "doc123"
                break
        else:
            raise AssertionError("No statement with article uuid")


class TestRawVsResolved:
    def test_raw_keeps_uuids(self):
        ref_block = _b(4, {"subject": "Drug", "predicate": "ингибирует", "object": "target"}, iid="ref1")
        consumer = _b(4, {
            "subject": "ref1",
            "predicate": "результат",
            "object": "ref1",
        }, iid="c1")
        stmts = blocks_to_statements_raw([ref_block, consumer])
        assert stmts[1]["subject_text"] == "ref1"
        assert stmts[1]["object_text"] == "ref1"


class TestExistingStatementsIdMap:
    def test_preserves_ids(self):
        existing = [{
            "id": "existing-id-1",
            "subject_text": "Drug",
            "predicate": "ингибирует",
            "object_text": "target",
            "sourceBlockId": "b1",
        }]
        block = _b(4, {"subject": "Drug", "predicate": "ингибирует", "object": "target"}, iid="b1")
        stmts = blocks_to_statements([block], existing_statements=existing)
        assert stmts[0]["id"] == "existing-id-1"
