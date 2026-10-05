"""Явно включаемая проверка обоих строгих контрактов на настроенном AI-сервисе."""
import json
import os

import pytest

from application.text_to_map import DEPENDENCY_PROMPT_PATH, PROMPT_PATH
from domain.article_maps import prepare_source
from domain.knowledge_map import apply_dependency_review, model_contract, parse_knowledge_map
from domain.knowledge_map_schema import extraction_map_json_schema
from infrastructure.article_map_model import ArticleMapDependencyModelGateway, ArticleMapModelGateway


@pytest.mark.skipif(os.environ.get("ARTICLE_MAP_MODEL_LIVE_TEST") != "1", reason="Нужен явный запуск LLM-проверки")
@pytest.mark.asyncio
async def test_configured_service_accepts_both_strict_schemas():
    text = ("# Averaging study\n\nThe method averages two readings. The study applied this method to "
            "baseline readings of 18 and 22. The resulting mean was 20. The authors used this result "
            "to conclude that the baseline mean exceeded their prespecified threshold of 19, subject "
            "to the limitation that only two readings were available.")
    source = prepare_source("strict-contract-check", text)
    request = {"article_id": source["article_id"], "article_text": text, "source_units": source["units"]}
    extraction = ArticleMapModelGateway(output_schema=extraction_map_json_schema(), strict_schema=True)
    dependencies = ArticleMapDependencyModelGateway()
    raw = await extraction(PROMPT_PATH.read_text(encoding="utf-8"), json.dumps(request))
    graph = parse_knowledge_map(raw, source)
    assert graph["edges"] == []
    assert all(not n["semantic"]["inputs"] for n in graph["nodes"])
    request["knowledge_map"] = model_contract(graph)
    reviewed = await dependencies(DEPENDENCY_PROMPT_PATH.read_text(encoding="utf-8"), json.dumps(request))
    final = apply_dependency_review(reviewed, graph, source)
    assert final["analysis"]["depth"] >= 4
    assert {"method", "operation", "result", "conclusion"} <= {n["kind"] for n in final["nodes"]}
    assert final["concepts"] == graph["concepts"]
    assert extraction.last_call["finish_reason"] == dependencies.last_call["finish_reason"] == "stop"
