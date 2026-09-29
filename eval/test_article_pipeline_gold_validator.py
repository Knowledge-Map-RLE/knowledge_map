from __future__ import annotations

import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR))

from validate_article_pipeline_gold import (  # noqa: E402
    _metadata_duplicate_coverage,
    _missing_source_unit_ids,
)


def test_only_content_bearing_source_units_block_coverage():
    source_unit_ids = ["S1", "S2", "S3", "S4", "S5", "S6"]
    unit_text = {
        "S1": "",
        "S2": "### 2.2.3.",
        "S3": "***",
        "S4": "77",
        "S5": "DOI",
        "S6": "The treatment increased survival.",
    }

    assert _missing_source_unit_ids(source_unit_ids, set(), unit_text, {}) == [
        "S4", "S5", "S6",
    ]


def test_only_an_exact_standalone_doi_may_be_covered_by_t1_metadata():
    rows = [{
        "blockType": "metadata",
        "tag": "B1",
        "data": {"doi": "10.1234/example.doi"},
    }]
    unit_text = {
        "S1": "* 10.1234/example.doi",
        "S2": "The DOI 10.1234/example.doi identifies this study.",
        "S3": "* 10.1234/a-different-doi",
    }

    assert _metadata_duplicate_coverage(rows, unit_text) == {"S1": "B1"}


def test_standalone_doi_url_and_prefix_match_the_same_metadata_value():
    rows = [{
        "blockType": "metadata",
        "tag": "B4",
        "data": {"doi": "10.3390/healthcare11050703"},
    }]

    assert _metadata_duplicate_coverage(
        rows,
        {
            "S6": "* 10.3390/healthcare11050703",
            "S7": "https://doi.org/10.3390/healthcare11050703",
            "S8": "DOI: 10.3390/healthcare11050703",
        },
    ) == {"S6": "B4", "S7": "B4", "S8": "B4"}
