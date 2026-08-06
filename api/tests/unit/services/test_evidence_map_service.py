"""Тесты чистой логики EvidenceMap (нормализация, типизированный граф, JSON)."""

import pytest

from services.evidence_map_service import (
    EvidenceMapService,
    _extract_json,
    map_to_graph,
    norm_direction,
    norm_domain,
    norm_polarity,
    norm_significance,
    normalize_map,
)


class TestNorms:
    def test_domain_aliases(self):
        assert norm_domain("Liver fibrosis") == "liver"
        assert norm_domain("Печёночный фиброз") == "liver"
        assert norm_domain("thymus mass") == "thymus"
        assert norm_domain("неизвестная штука") == "other"

    def test_polarity(self):
        assert norm_polarity("beneficial") == "benefit"
        assert norm_polarity("противовоспалительный") == "benefit"
        assert norm_polarity("harmful") == "harm"
        assert norm_polarity("unknown") == "neutral"

    def test_direction(self):
        assert norm_direction("upregulated") == "up"
        assert norm_direction("понижено") == "down"
        assert norm_direction("no change") == "unchanged"

    def test_significance_by_p(self):
        assert norm_significance(None, 0.01) == "sig"
        assert norm_significance(None, 0.2) == "ns"
        assert norm_significance("ns", None) == "ns"
        assert norm_significance("significant", None) == "sig"


class TestExtractJson:
    def test_fenced(self):
        text = "Here you go:\n```json\n{\"a\": 1}\n```\nDone."
        assert _extract_json(text) == {"a": 1}

    def test_plain_object(self):
        assert _extract_json('{"x": [1, 2]} trailing') == {"x": [1, 2]}

    def test_invalid(self):
        assert _extract_json("no json here") is None
        assert _extract_json("{broken") is None


class TestNormalizeMap:
    def test_full_pipeline(self):
        raw = {
            "hypothesis": "Clusterin protects against aging",
            "goals": ["Test causality"],
            "claims": [
                {"subject": "Clusterin", "predicate": "protects", "object": "aging",
                 "negated": False, "domain": "serum", "confidence": 0.9},
            ],
            "experiments": [
                {"name": "CLU injection in vivo", "type": "in vivo",
                 "verdict": "подтвердилась", "control_groups": ["PBS"], "exp_groups": ["CLU"],
                 "findings": ["serum clusterin"]},
            ],
            "findings": [
                {"parameter": "Serum clusterin", "domain": "serum", "polarity": "benefit",
                 "direction": "up", "significance": "significant", "p": 0.01,
                 "group_role": "intervention", "claim_ref": 0, "experiment": 0},
            ],
            "method_flags": {"control": True, "statistics": True, "sample_size": False,
                             "p_value": True, "hypothesis": True},
            "verdict": "supported",
        }
        m = normalize_map(raw, "doc-1")
        assert m["doc_id"] == "doc-1"
        assert m["hypothesis"] == "Clusterin protects against aging"
        assert len(m["claims"]) == 1
        assert m["claims"][0]["domain"] == "serum"
        assert len(m["experiments"]) == 1
        assert m["experiments"][0]["type"] == "in_vivo"
        assert m["experiments"][0]["verdict"] == "supported"
        assert len(m["findings"]) == 1
        assert m["findings"][0]["significance"] == "sig"
        assert m["findings"][0]["p"] == 0.01
        assert m["findings"][0]["claim_ref"] == 0
        assert m["verdict"] == "supported"
        assert m["method_flags"]["control"] is True

    def test_drops_empty_claims(self):
        raw = {
            "claims": [{"subject": "", "predicate": "p", "object": "o"},
                       {"subject": "s", "predicate": "p", "object": "o"}],
            "findings": [],
            "experiments": [],
            "method_flags": {},
        }
        m = normalize_map(raw, "doc-1")
        assert len(m["claims"]) == 1
        assert m["method_flags"] == {k: False for k in (
            "control", "statistics", "sample_size", "p_value", "hypothesis")}


class TestMapToGraph:
    def test_node_labels_are_typed(self):
        m = normalize_map({
            "hypothesis": "h",
            "goals": ["g1"],
            "claims": [{"subject": "s", "predicate": "p", "object": "o",
                        "negated": False, "domain": "liver"}],
            "experiments": [{"name": "e1", "type": "in_vivo"}],
            "findings": [{"parameter": "x", "domain": "liver", "polarity": "benefit",
                          "direction": "up", "significance": "sig", "p": 0.01,
                          "claim_ref": 0, "experiment": 0}],
            "method_flags": {"control": True, "statistics": False, "sample_size": True,
                             "p_value": True, "hypothesis": True},
        }, "doc-1")
        g = m["graph"]
        labels = {n["label"] for n in g["nodes"]}
        assert "H" in labels
        assert "G" in labels
        assert "C:liver:0" in labels
        assert "E:in_vivo" in labels
        assert "F:liver:benefit:up:sig" in labels
        assert "M:control:ok" in labels
        assert "M:statistics:missing" in labels
        edge_pairs = {(e["from"], e["to"], e["label"]) for e in g["edges"]}
        assert ("c0", "f0", "evidence") in edge_pairs
        assert ("e0", "f0", "measures") in edge_pairs
        assert ("h", "c0", "tested_by") in edge_pairs

    def test_stable_labels_across_articles(self):
        m1 = normalize_map({
            "claims": [{"subject": "s", "predicate": "p", "object": "o",
                        "negated": False, "domain": "serum"}],
            "findings": [{"parameter": "clusterin", "domain": "Serum",
                          "polarity": "beneficial", "direction": "upregulated",
                          "significance": "significant", "p": 0.01, "claim_ref": 0}],
            "experiments": [], "method_flags": {},
        }, "doc-1")
        m2 = normalize_map({
            "claims": [{"subject": "s", "predicate": "p", "object": "o",
                        "negated": False, "domain": "serum"}],
            "findings": [{"parameter": "clusterin", "domain": "serum",
                          "polarity": "benefit", "direction": "up",
                          "significance": "sig", "p": 0.01, "claim_ref": 0}],
            "experiments": [], "method_flags": {},
        }, "doc-2")
        labels1 = {n["label"] for n in m1["graph"]["nodes"]}
        labels2 = {n["label"] for n in m2["graph"]["nodes"]}
        assert "F:serum:benefit:up:sig" in labels1
        assert labels1 == labels2


class TestMineWithHist:
    def test_histogram_propagates_verdicts(self):
        # графы корпуса несут вердикт на верхнем уровне (не в самих узлах);
        # _mine_with_hist должен перенести его в verdict_histogram паттернов
        graphs = [
            {"id": "a", "verdict": "supported",
             "nodes": [{"id": "h", "label": "H"}, {"id": "g", "label": "G"}],
             "edges": [{"from": "h", "to": "g", "label": "goal"}]},
            {"id": "b", "verdict": "refuted",
             "nodes": [{"id": "h", "label": "H"}, {"id": "g", "label": "G"}],
             "edges": [{"from": "h", "to": "g", "label": "goal"}]},
        ]
        svc = EvidenceMapService()
        pats = svc._mine_with_hist(graphs, min_support=1.0, min_size=2, max_size=3, limit=100)
        assert pats
        for p in pats:
            if set(p["graphs"]) == {"a", "b"}:
                assert p["verdict_histogram"] == {"supported": 1, "refuted": 1}
                break
        else:
            pytest.fail("общий паттерн не найден")

    def test_duplicate_docs_not_double_counted(self):
        # в корпусе не должно быть дублей одной статьи: словарь verdicts
        # ключуется по id графа, дубли дали бы завышенный счёт
        graphs = [
            {"id": "a", "verdict": "supported",
             "nodes": [{"id": "h", "label": "H"}, {"id": "g", "label": "G"}],
             "edges": [{"from": "h", "to": "g", "label": "goal"}]},
        ]
        svc = EvidenceMapService()
        pats = svc._mine_with_hist(graphs, min_support=1.0, min_size=2, max_size=3, limit=100)
        assert pats
        p = pats[0]
        assert p["support"] == 1
        assert p["verdict_histogram"] == {"supported": 1}
