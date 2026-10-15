from __future__ import annotations

from tools.run_full19_cohort_result_usage_permutation import _randomize_links


def test_randomized_links_preserve_operation_output_inventories_and_edge_count():
    row = {
        "operator_families": ["incidence_estimation", "survival_model_fitting"],
        "output_families": ["reported_frequency", "reported_model_parameter", "reported_association"],
        "graph_links": [
            ["incidence_estimation", "reported_frequency"],
            ["survival_model_fitting", "reported_model_parameter"],
        ],
    }

    randomized, changed = _randomize_links(row, seed=17)

    assert changed
    assert len(randomized["graph_links"]) == len(row["graph_links"])
    assert len({tuple(pair) for pair in randomized["graph_links"]}) == len(row["graph_links"])
    assert {pair[0] for pair in randomized["graph_links"]} <= set(row["operator_families"])
    assert {pair[1] for pair in randomized["graph_links"]} <= set(row["output_families"])
    assert randomized == _randomize_links(row, seed=17)[0]


def test_randomized_links_leave_saturated_pair_space_unchanged():
    row = {
        "operator_families": ["one_operation"],
        "output_families": ["one_output"],
        "graph_links": [["one_operation", "one_output"]],
    }

    randomized, changed = _randomize_links(row, seed=5)

    assert not changed
    assert randomized["graph_links"] == row["graph_links"]
