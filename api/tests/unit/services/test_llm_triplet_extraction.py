"""Юнит-тесты postprocess-шагов LLM-извлечения структуры блоков.

Проверяют детерминированные правки поверх LLM-выхода:
- `_dedupe_t27` — схлопывание дублей T27 по значению pValue;
- `_add_deterministic_sections` — добавление T51/T47, если модель их не выдала;
- `_add_uuidrefs` — замена повторяющихся терминов на UUID определяющего T4.
"""

import json

import pytest

from services.llm_triplet_extraction_service import (
    LLMTripletExtractionService,
)


_uuid_counter = [0]


def _uid():
    _uuid_counter[0] += 1
    return f"00000000-0000-8000-8000-{_uuid_counter[0]:012d}"


def _b(block_type, data, uid=None):
    return {"blockType": block_type, "data": data, "uuid": uid or _uid()}


def _seq(uid):
    return json.dumps([uid])


class TestDedupeT27:
    def test_keeps_one_block_per_pvalue(self):
        blocks = [
            _b(27, {"pValue": 0.05}),
            _b(27, {"pValue": 0.05}),
            _b(27, {"pValue": 0.01}),
        ]
        out = LLMTripletExtractionService._dedupe_t27(blocks)
        assert len(out) == 2
        vals = sorted(b["data"]["pValue"] for b in out)
        assert vals == [0.01, 0.05]

    def test_remaps_t57_pvalue_ref(self):
        keep = _b(27, {"pValue": 0.05})
        drop = _b(27, {"pValue": 0.05})
        t57 = _b(57, {"parameter": "X", "pValue": drop["uuid"]})
        out = LLMTripletExtractionService._dedupe_t27([keep, drop, t57])
        assert len(out) == 2
        t57_out = next(b for b in out if b["blockType"] == 57)
        assert t57_out["data"]["pValue"] == keep["uuid"]

    def test_non_numeric_pvalues_untouched(self):
        blocks = [_b(27, {"pValue": ""}), _b(27, {"pValue": "abc"})]
        out = LLMTripletExtractionService._dedupe_t27(blocks)
        assert len(out) == 2


class TestAddDeterministicSections:
    def test_adds_t51_from_heading(self):
        text = "## Финансирование\n\n- Грант РФФИ 20-01-00001\n- Грант РНФ 22-15-00002"
        blocks = [_b(4, {"subject": "A", "predicate": "B", "object": "C"})]
        out = LLMTripletExtractionService._add_deterministic_sections(blocks, text)
        types = {b["blockType"] for b in out}
        assert 51 in types
        t51 = next(b for b in out if b["blockType"] == 51)
        assert "РФФИ 20-01-00001" in t51["data"]["funding"]

    def test_skips_t51_when_present(self):
        blocks = [_b(51, {"funding": "X"})]
        out = LLMTripletExtractionService._add_deterministic_sections(blocks, "## Финансирование\n- Y")
        assert len(out) == 1

    def test_adds_t47_wrapping_prior_t4(self):
        blocks = [
            _b(4, {"subject": "предыдущее исследование", "predicate": "сообщало", "object": "животные до 5 лет"}),
            _b(4, {"subject": "A", "predicate": "B", "object": "C"}),
        ]
        out = LLMTripletExtractionService._add_deterministic_sections(blocks, None)
        types = {b["blockType"] for b in out}
        assert 47 in types
        t47 = next(b for b in out if b["blockType"] == 47)
        assert json.loads(t47["data"]["sequence"]) == [blocks[0]["uuid"]]


class TestAddUuidrefs:
    def test_replaces_frequent_short_term_with_defining_uuid(self):
        defining = _b(4, {"subject": "мышь", "predicate": "помещали на", "object": "балку"})
        t4a = _b(4, {"subject": "мышь", "predicate": "проходила", "object": "тест"})
        t4b = _b(4, {"subject": "оценка", "predicate": "активности", "object": "мышь"})
        t4c = _b(4, {"subject": "A", "predicate": "B", "object": "C"})
        out = LLMTripletExtractionService._add_uuidrefs(
            [defining, t4a, t4b, t4c]
        )
        refs = {b["uuid"]: b["data"] for b in out if b["blockType"] == 4}
        assert refs[t4a["uuid"]]["subject"] == defining["uuid"]
        assert refs[t4b["uuid"]]["object"] == defining["uuid"]
        assert refs[defining["uuid"]]["subject"] == "мышь"
        assert refs[t4c["uuid"]]["object"] == "C"

    def test_defining_own_subject_kept(self):
        defining = _b(4, {"subject": "мышь", "predicate": "помещали на", "object": "балку"})
        out = LLMTripletExtractionService._add_uuidrefs([defining])
        assert out[0]["data"]["subject"] == "мышь"

    def test_multiword_term_not_replaced(self):
        defining = _b(4, {"subject": "кластерин", "predicate": "ингибирует", "object": "воспаление"})
        other = _b(4, {"subject": "накопление", "predicate": "кластерина", "object": "у стареющих a. russatus"})
        out = LLMTripletExtractionService._add_uuidrefs([defining, other])
        assert out[1]["data"]["object"] == "у стареющих a. russatus"

    def test_rare_term_not_replaced(self):
        defining = _b(4, {"subject": "мышь", "predicate": "помещали на", "object": "балку"})
        other = _b(4, {"subject": "мышь", "predicate": "проходила", "object": "тест"})
        out = LLMTripletExtractionService._add_uuidrefs([defining, other])
        assert out[1]["data"]["subject"] == "мышь"
