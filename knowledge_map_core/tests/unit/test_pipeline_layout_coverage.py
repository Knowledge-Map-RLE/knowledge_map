from knowledge_pipeline.pipeline import ArticlePipeline
from knowledge_pipeline.semantic_extraction import (
    _add_pipeline_rows,
    is_layout_only_fragment,
)


def test_layout_only_fragment_excludes_markdown_artifacts_but_not_content_or_values():
    assert is_layout_only_fragment("\n\n")
    assert is_layout_only_fragment("***")
    assert is_layout_only_fragment("### 2.2.3.")
    assert is_layout_only_fragment("2.1.2.")
    assert not is_layout_only_fragment("DOI")
    assert not is_layout_only_fragment("Conclusions")
    assert not is_layout_only_fragment("77")


def test_pipeline_does_not_materialize_t3_rows_for_layout_only_units():
    source_units = [
        {"id": "S1", "text": "\n\n"},
        {"id": "S2", "text": "### 2.2.3."},
        {"id": "S3", "text": "DOI"},
    ]

    rows = _add_pipeline_rows(
        [], ["S1", "S2", "S3"], [], source_units, ["S1", "S2", "S3"],
    )

    assert [(row["blockType"], row["data"]["unit"]) for row in rows] == [
        ("text", "S3"),
    ]


def test_layout_only_units_do_not_fail_article_sentence_coverage():
    source_text = "*\n# 2.1.3.\nThe claim is supported."
    sentence_texts = ["*", "# 2.1.3.", "The claim is supported."]
    sentences = []
    offset = 0
    for fragment in sentence_texts:
        sentences.append({"start": offset, "end": offset + len(fragment)})
        offset += len(fragment) + 1
    profile = {"sentences": sentences}

    covered, missing = ArticlePipeline._sentence_coverage(
        profile, [], source_text,
    )

    assert covered == {0, 1}
    assert missing == ["S3"]
