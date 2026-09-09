"""Tests for domain.metrics — ranking + distance statistics."""
import unittest
from workability.domain.metrics import (
    precision_at_k,
    recall_at_k,
    f1_at_k,
    mrr,
    hits_at_k,
    ranking_metrics,
    distance_stats,
    longrange_recall_at_k,
    aggregate_ranking_metrics,
)


class TestPrecisionAtK(unittest.TestCase):

    def test_perfect(self):
        # All top-2 are relevant
        self.assertAlmostEqual(precision_at_k(["a", "b"], ["a", "b", "c"], 2), 1.0)

    def test_partial(self):
        # 1 of top-2 relevant
        self.assertAlmostEqual(precision_at_k(["a", "x"], ["a", "b"], 2), 0.5)

    def test_empty_k(self):
        self.assertAlmostEqual(precision_at_k(["a"], ["b"], 0), 0.0)

    def test_more_k_than_predicted(self):
        self.assertAlmostEqual(precision_at_k(["a"], ["a"], 10), 1.0)


class TestRecallAtK(unittest.TestCase):

    def test_perfect(self):
        self.assertAlmostEqual(recall_at_k(["a", "b", "c"], ["a", "b", "c"], 3), 1.0)

    def test_partial(self):
        self.assertAlmostEqual(recall_at_k(["a", "x"], ["a", "b"], 2), 0.5)

    def test_no_relevant(self):
        self.assertAlmostEqual(recall_at_k(["x", "y"], ["a", "b"], 2), 0.0)

    def test_no_hits(self):
        self.assertAlmostEqual(recall_at_k(["x", "y"], ["a", "b"], 2), 0.0)


class TestMRR(unittest.TestCase):

    def test_first_position(self):
        self.assertAlmostEqual(mrr(["a", "b", "c"], ["a"]), 1.0)

    def test_second_position(self):
        self.assertAlmostEqual(mrr(["x", "a"], ["a"]), 0.5)

    def test_third_position(self):
        self.assertAlmostEqual(mrr(["x", "y", "a"], ["a"]), 1/3)

    def test_no_hit(self):
        self.assertAlmostEqual(mrr(["x", "y"], ["a"]), 0.0)


class TestHitsAtK(unittest.TestCase):

    def test_basic(self):
        # top-3 = ["a", "b", "c"], relevant = {"b", "d"} => only "b" in top-3
        self.assertEqual(hits_at_k(["a", "b", "c", "d"], ["b", "d"], 3), 1)

    def test_all_in_top_k(self):
        self.assertEqual(hits_at_k(["b", "d", "x"], ["b", "d"], 3), 2)

    def test_zero(self):
        self.assertEqual(hits_at_k(["x", "y"], ["a", "b"], 2), 0)


class TestRankingMetrics(unittest.TestCase):
    def test_output_keys(self):
        result = ranking_metrics(["a"], ["a"], 1)
        expected_keys = {"precision@1", "recall@1", "f1@1", "mrr", "hits@1"}
        self.assertEqual(set(result.keys()), expected_keys)


class TestDistanceStats(unittest.TestCase):

    def test_basic(self):
        d = distance_stats([1, 2, 3, 4, 5])
        self.assertAlmostEqual(d["mean"], 3.0)
        self.assertAlmostEqual(d["median"], 3.0)
        self.assertAlmostEqual(d["max"], 5.0)
        self.assertAlmostEqual(d["count"], 5)

    def test_empty(self):
        d = distance_stats([])
        self.assertEqual(d["count"], 0)
        self.assertAlmostEqual(d["mean"], 0.0)


class TestLongRangeRecall(unittest.TestCase):

    def test_basic(self):
        predicted = ["a", "b", "c", "d"]
        relevant = ["a", "b", "c"]
        distances = {"a": 1, "b": 10, "c": 20}
        # min_distance=10: only b,c are far enough; both predicted -> recall=1.0
        self.assertAlmostEqual(
            longrange_recall_at_k(predicted, relevant, distances, min_distance=10, k=4),
            1.0,
        )

    def test_none_far(self):
        predicted = ["a"]
        relevant = ["a"]
        distances = {"a": 1}
        self.assertAlmostEqual(
            longrange_recall_at_k(predicted, relevant, distances, min_distance=10, k=1),
            0.0,
        )


class TestAggregate(unittest.TestCase):
    def test_average(self):
        per_case = [
            {"precision@10": 0.2, "recall@10": 0.1},
            {"precision@10": 0.4, "recall@10": 0.3},
        ]
        agg = aggregate_ranking_metrics(per_case)
        self.assertAlmostEqual(agg["precision@10"], 0.3)
        self.assertAlmostEqual(agg["recall@10"], 0.2)


if __name__ == "__main__":
    unittest.main()
