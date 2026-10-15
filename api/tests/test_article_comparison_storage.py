"""Сжатое хранение сохраняет точную семантику и читает прежние результаты."""
import json

import pytest

from domain.article_maps import ArticleMapError
from infrastructure.neo4j.article_comparisons_repository import encode_pair, decode_pair, encode_groups, decode_group, Neo4jArticleComparisonsRepository


def test_compressed_pair_round_trip_is_exact_and_deterministic():
    pair = {"pair_id": "pair", "statement_matches": [{"left": "Утверждение", "roles": ["TNF", "CSF"], "score": .125}] * 40}
    encoded = encode_pair(pair)
    assert encoded == encode_pair(pair)
    assert len(encoded) < len(json.dumps(pair).encode()) / 4
    assert decode_pair({"compressed": encoded, "codec": "gzip-json-v1", "payload": None}) == pair
    assert decode_pair({"compressed": None, "codec": None, "payload": json.dumps(pair)}) == pair


def test_unknown_pair_codec_is_rejected():
    with pytest.raises(ArticleMapError, match="codec"):
        decode_pair({"compressed": b"invalid", "codec": "unknown", "payload": None})


def test_grouped_storage_preserves_pairs_and_rejects_duplicates():
    pairs = [{"pair_id":"p2","left_knowledge_id":"K1","right_article_id":"a","right_knowledge_id":"K2","score":.25},
             {"pair_id":"p1","left_knowledge_id":"K1","right_article_id":"a","right_knowledge_id":"K1","score":.5}]
    groups = encode_groups(pairs)
    assert groups == encode_groups(pairs) and len(groups) == 1 and groups[0]["count"] == 2
    assert decode_group(groups[0]["payload"]) == [pairs[1],pairs[0]]
    with pytest.raises(ArticleMapError,match="Duplicate"):
        encode_groups([pairs[0],pairs[0]])


def test_group_pages_keep_scores_filters_and_total_count():
    repo = object.__new__(Neo4jArticleComparisonsRepository)
    repo.get = lambda cid,user: {"pair_storage":"knowledge-chunks-gzip-base64-v1"}
    pairs = [{"left_knowledge_id":"K1","right_article_id":article,"right_knowledge_id":kid,"relations":["partial"],"hybrid_score":score}
             for article,kid,score in [("b","K1",.9),("a","K2",.7),("a","K1",.7)]]
    repo._group_pairs = lambda cid,left: iter(pairs)
    page = repo.pairs("c","owner",left_knowledge_id="K1",offset=1,limit=1)
    assert page["total"] == 3 and page["pairs"] == [pairs[2]]
    exact = repo.pairs("c","owner",source_article_id="a",right_knowledge_id="K2")
    assert exact["total"] == 1 and exact["pairs"] == [pairs[1]]
