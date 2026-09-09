"""Tests for domain.distances — невзвешенное графовое расстояние по BIBLIOGRAPHIC_LINK."""
import unittest
from workability.domain.statements import TemporalSnapshot, Article
from workability.domain.distances import shortest_path_docs, all_shortest_distances, build_doc_adjacency


def _snap(doc_edges, nodes=None, doc_of=None):
    """Build a minimal TemporalSnapshot for testing.

    - doc_edges: list[(from_doc, to_doc)] рёбра цитирования.
    - nodes:     список norm_key.
    - doc_of:    dict norm_key -> doc_id (какая статья содержит утверждение).
    """
    articles = {}
    for nk in (nodes or []):
        doc_id = (doc_of or {}).get(nk, f"doc_{nk}")
        art = articles.setdefault(doc_id, Article(doc_id=doc_id))
        art.statements.add(nk)
    art_years = {d: 2020 for d in articles}
    return TemporalSnapshot(
        year=2020,
        articles=articles,
        article_years=art_years,
        bibliographic_edges=set(doc_edges),
    )


class TestShortestPathDocs(unittest.TestCase):

    def test_same_doc(self):
        snap = _snap([("A", "B")], ["a", "b"], {"a": "A", "b": "B"})
        self.assertEqual(shortest_path_docs(snap, "A", "A"), 0)

    def test_direct_edge(self):
        snap = _snap([("A", "B")], ["a", "b"], {"a": "A", "b": "B"})
        self.assertEqual(shortest_path_docs(snap, "A", "B"), 1)

    def test_path_length_2(self):
        snap = _snap([("A", "B"), ("B", "C")], ["a", "b", "c"], {"a": "A", "b": "B", "c": "C"})
        self.assertEqual(shortest_path_docs(snap, "A", "C"), 2)

    def test_no_path(self):
        snap = _snap([("A", "B"), ("C", "D")], ["a", "b", "c", "d"], {"a": "A", "b": "B", "c": "C", "d": "D"})
        self.assertIsNone(shortest_path_docs(snap, "A", "C"))

    def test_cycle(self):
        snap = _snap([("A", "B"), ("B", "C"), ("C", "A")], ["a", "b", "c"], {"a": "A", "b": "B", "c": "C"})
        self.assertEqual(shortest_path_docs(snap, "A", "C"), 2)
        self.assertEqual(shortest_path_docs(snap, "C", "A"), 1)

    def test_diamond(self):
        edges = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]
        snap = _snap(edges, ["a", "b", "c", "d"], {"a": "A", "b": "B", "c": "C", "d": "D"})
        self.assertEqual(shortest_path_docs(snap, "A", "D"), 2)

    def test_long_path(self):
        edges = [(f"n{i}", f"n{i+1}") for i in range(20)]
        nodes = [f"s{i}" for i in range(21)]
        _doc_of = {f"s{i}": f"n{i}" for i in range(21)}
        snap = _snap(edges, nodes, _doc_of)
        self.assertEqual(shortest_path_docs(snap, "n0", "n20"), 20)

    def test_isolated_docs(self):
        snap = _snap([], ["x", "y", "z"], {"x": "X", "y": "Y", "z": "Z"})
        self.assertIsNone(shortest_path_docs(snap, "X", "Y"))


class TestAllShortestDistances(unittest.TestCase):

    def test_single_target(self):
        snap = _snap([("A", "B"), ("B", "C")], ["a", "c"], {"a": "A", "c": "C"})
        d = all_shortest_distances(snap, "a", ["c"])
        self.assertEqual(d, {"c": 2})

    def test_multiple_targets(self):
        edges = [("A", "B"), ("B", "C"), ("C", "D")]
        snap = _snap(edges, ["a", "b", "c", "d"], {"a": "A", "b": "B", "c": "C", "d": "D"})
        d = all_shortest_distances(snap, "a", ["c", "d", "b"])
        self.assertEqual(d, {"c": 2, "d": 3, "b": 1})

    def test_unreachable_target(self):
        snap = _snap([("A", "B")], ["a", "b", "z"], {"a": "A", "b": "B", "z": "Z"})
        d = all_shortest_distances(snap, "a", ["b", "z"])
        self.assertEqual(d["b"], 1)
        self.assertIsNone(d["z"])

    def test_source_and_target_same_doc(self):
        snap = _snap([("A", "B")], ["a", "b"], {"a": "A", "b": "A"})
        d = all_shortest_distances(snap, "a", ["b"])
        self.assertEqual(d["b"], 0)

    def test_target_in_source_doc_and_other_doc(self):
        edges = [("A", "B"), ("B", "C")]
        # b есть в A (источник) и в C (через B)
        snap = _snap(edges, ["a", "b"], {"a": "A", "b": "A"})
        snap.articles["C"] = Article(doc_id="C", statements={"b"})
        snap.article_years["C"] = 2020
        d = all_shortest_distances(snap, "a", ["b"])
        self.assertEqual(d["b"], 0)

    def test_empty_target_list(self):
        snap = _snap([("A", "B")], ["a", "b"], {"a": "A", "b": "B"})
        d = all_shortest_distances(snap, "a", [])
        self.assertEqual(d, {})

    def test_unknown_source(self):
        snap = _snap([("A", "B")], ["a", "b"], {"a": "A", "b": "B"})
        d = all_shortest_distances(snap, "ghost", ["b"])
        self.assertEqual(d, {"b": None})


class TestBuildDocAdjacency(unittest.TestCase):

    def test_basic_adj(self):
        snap = _snap([("A", "B"), ("A", "C")], ["a", "b", "c"], {"a": "A", "b": "B", "c": "C"})
        adj = build_doc_adjacency(snap)
        self.assertEqual(adj["A"], {"B", "C"})
        self.assertNotIn("B", adj)

    def test_no_edges(self):
        snap = _snap([], ["x"], {"x": "X"})
        adj = build_doc_adjacency(snap)
        self.assertEqual(adj, {})


if __name__ == "__main__":
    unittest.main()