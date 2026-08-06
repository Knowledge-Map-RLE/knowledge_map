"""Тесты для api/services/gspan.py — частотный майнинг подграфов."""

import pytest

from services.gspan import (
    build_graph,
    canonical_key,
    contains_pattern,
    graph_from_key,
    match_graph,
    mine_frequent_subgraphs,
)


def _g(gid, edges, node_labels):
    """Собирает внешний граф из списка (u, v, elabel) и меток вершин."""
    nodes = [{"id": f"{gid}-n{i}", "label": lab} for i, lab in enumerate(node_labels)]
    e = [
        {"from": f"{gid}-n{u}", "to": f"{gid}-n{v}", "label": el}
        for u, v, el in edges
    ]
    return {"id": gid, "nodes": nodes, "edges": e}


class TestCanonicalKey:
    def test_isomorphic_graphs_same_key(self):
        g1 = build_graph(_g("a", [(0, 1, "r")], ["x", "y"]))
        g2 = build_graph(_g("b", [(0, 1, "r")], ["x", "y"]))
        assert canonical_key(g1.vertex_labels, [(0, 1, "r")]) == canonical_key(
            g2.vertex_labels, [(0, 1, "r")]
        )

    def test_permuted_edge_same_key(self):
        # одна и та же структура, но разный порядок вершин в списке рёбер
        k1 = canonical_key(["a", "b", "c"], [(0, 1, "e"), (1, 2, "e")])
        k2 = canonical_key(["a", "b", "c"], [(2, 1, "e"), (1, 0, "e")])
        assert k1 == k2

    def test_non_isomorphic_different_key(self):
        # путь из 3 вершин vs треугольник — разные ключи
        path = canonical_key(["a", "b", "c"], [(0, 1, "e"), (1, 2, "e")])
        tri = canonical_key(["a", "b", "c"], [(0, 1, "e"), (1, 2, "e"), (0, 2, "e")])
        assert path != tri

    def test_round_trip(self):
        vertices, edges = graph_from_key(canonical_key(["a", "b"], [(0, 1, "r")]))
        assert vertices == ["a", "b"]
        assert (0, 1, "r") in [tuple(e) for e in edges]

    def test_max_size_guard(self):
        with pytest.raises(ValueError):
            canonical_key([str(i) for i in range(10)], [])


class TestContainsPattern:
    def test_subgraph_found(self):
        g = build_graph(_g("g", [(0, 1, "r"), (1, 2, "s")], ["a", "b", "c"]))
        assert contains_pattern(g, ["a", "b"], [(0, 1, "r")])
        assert contains_pattern(g, ["b", "c"], [(0, 1, "s")])

    def test_missing_edge_not_found(self):
        g = build_graph(_g("g", [(0, 1, "r")], ["a", "b", "c"]))
        assert not contains_pattern(g, ["a", "c"], [(0, 1, "r")])

    def test_wrong_label_not_found(self):
        g = build_graph(_g("g", [(0, 1, "r")], ["a", "b"]))
        assert not contains_pattern(g, ["a", "z"], [(0, 1, "r")])


class TestMining:
    def test_single_vertex_skipped_by_min_size(self):
        graphs = [_g("a", [], ["x"]), _g("b", [], ["x"])]
        pats = mine_frequent_subgraphs(graphs, min_support=2, min_size=2)
        assert pats == []

    def test_edge_recurring_in_two_graphs(self):
        g1 = _g("a", [(0, 1, "r")], ["x", "y"])
        g2 = _g("b", [(0, 1, "r")], ["x", "y"])
        pats = mine_frequent_subgraphs([g1, g2], min_support=2, min_size=2)
        assert len(pats) == 1
        p = pats[0]
        assert p["support"] == 2
        assert p["support_ratio"] == 1.0
        assert set(p["graphs"]) == {"a", "b"}
        assert sorted(p["nodes"]) == ["x", "y"]

    def test_support_fraction(self):
        g1 = _g("a", [(0, 1, "r")], ["x", "y"])
        g2 = _g("b", [(0, 1, "r")], ["x", "y"])
        g3 = _g("c", [(0, 1, "r")], ["x", "z"])
        pats = mine_frequent_subgraphs([g1, g2, g3], min_support=0.5, min_size=2)
        assert pats and pats[0]["support"] == 2

    def test_triangle_recurring(self):
        def tri(gid):
            return _g(gid, [(0, 1, "e"), (1, 2, "e"), (0, 2, "e")], ["a", "b", "c"])

        g1, g2 = tri("a"), tri("b")
        pats = mine_frequent_subgraphs([g1, g2], min_support=2, min_size=3, max_size=3)
        tri_pats = [p for p in pats if p["size"] == 3]
        assert tri_pats, pats
        assert tri_pats[0]["edges_count"] == 3

    def test_pattern_not_recurring_filtered(self):
        g1 = _g("a", [(0, 1, "r"), (1, 2, "s")], ["a", "b", "c"])
        g2 = _g("b", [(0, 1, "r")], ["a", "b"])
        pats = mine_frequent_subgraphs([g1, g2], min_support=2, min_size=3)
        # цепочка из 3 вершин есть только в g1 -> поддержка 1 < 2
        assert all(p["support"] == 2 for p in pats)
        assert not any(p["size"] == 3 for p in pats)

    def test_connectedness(self):
        # два несвязных ребра в одном графе не должны дать паттерн из 4 вершин
        g = _g("a", [(0, 1, "r"), (2, 3, "r")], ["a", "b", "a", "b"])
        pats = mine_frequent_subgraphs([g, g], min_support=2, min_size=4)
        assert not any(p["size"] == 4 for p in pats)

    def test_every_mined_pattern_is_contained(self):
        # паттерны не должны содержать фантомных рёбер: каждый майненный
        # подграф обязан реально существовать в исходном графе (регресс —
        # баг с перестановкой эмбеддингов в каноническую форму)
        g = _g(
            "a",
            [
                (0, 1, "goal"), (0, 2, "tested_by"), (1, 2, "evidence"),
                (2, 3, "measures"), (0, 4, "requires"),
            ],
            ["H", "G", "C", "F", "M"],
        )
        pats = mine_frequent_subgraphs([g], min_support=1.0, min_size=2, max_size=4, limit=1000)
        assert pats
        target = build_graph(g)
        for p in pats:
            vertices = [str(x) for x in p["nodes"]]
            edges = [tuple(e) for e in p["edges"]]
            assert contains_pattern(target, vertices, edges), f"фантомный паттерн {p}"

    def test_max_size_respected_with_backward_edges(self):
        # backward-расширение добавляет ребро внутри того же размера и должно
        # работать при size == max_size; без него треугольник не майнится
        tri = _g("a", [(0, 1, "e"), (1, 2, "e"), (0, 2, "e")], ["a", "b", "c"])
        pats = mine_frequent_subgraphs([tri], min_support=1.0, min_size=3, max_size=3)
        tri_pats = [p for p in pats if p["size"] == 3 and p["edges_count"] == 3]
        assert tri_pats, f"треугольник не найден: {pats}"
        for p in tri_pats:
            assert contains_pattern(build_graph(tri), [str(x) for x in p["nodes"]],
                                    [tuple(e) for e in p["edges"]])

    def test_mined_patterns_all_contained_multi(self):
        # подграф из нескольких вершин с рёбрами разных меток: все майненые
        # паттерны должны содержаться (фантомных рёбер нет)
        g = _g(
            "a",
            [
                (0, 1, "x"), (1, 2, "y"), (2, 3, "z"), (0, 3, "w"),
            ],
            ["p", "q", "r", "s"],
        )
        pats = mine_frequent_subgraphs([g], min_support=1.0, min_size=2, max_size=4, limit=1000)
        target = build_graph(g)
        for p in pats:
            assert contains_pattern(target, [str(x) for x in p["nodes"]],
                                    [tuple(e) for e in p["edges"]]), f"фантом {p}"


class TestMatch:
    def test_match_finds_and_filters(self):
        corpus = [
            _g("a", [(0, 1, "r"), (1, 2, "s")], ["x", "y", "z"]),
            _g("b", [(0, 1, "r")], ["x", "y"]),
        ]
        pats = mine_frequent_subgraphs(corpus, min_support=1, min_size=2)
        target = _g("t", [(0, 1, "r")], ["x", "y"])
        matched = match_graph(target, pats)
        ids = {m["pattern"] for m in matched}
        matched_pats = [p for p in pats if p["id"] in ids]
        # любой найденный паттерн должен реально содержаться в целевом графе
        for p in matched_pats:
            g = build_graph(target)
            assert contains_pattern(g, p["nodes"], [tuple(e) for e in p["edges"]])

    def test_match_empty_patterns(self):
        target = _g("t", [(0, 1, "r")], ["x", "y"])
        assert match_graph(target, []) == []
