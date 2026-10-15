"""Новый production-сценарий и офлайн-публикация без AI-клиентов."""
import asyncio
import copy
import json

import pytest

from application.publish_article_map import PublishArticleMap
from application.text_to_development_map import TextToMap, prompt_binding
from domain.article_maps import ArticleMapError, ArticleMapBusy, digest
from domain.knowledge_development import initialize_occurrences
from tests.unit.application.test_knowledge_development import TEXT, SOURCE, extracted, knowledge, transition
from tests.unit.application.test_text_to_map import Repository


class Source:
    async def read_text(self, article, owner):
        return TEXT


class Recorded:
    last_call = {"model": "test-double", "reasoning_effort": "max", "usage": {"total_tokens": 1}}

    def __init__(self, graph=None):
        self.graph = graph or extracted()
        self.requests = []

    async def __call__(self, system, user):
        self.requests.append((system, json.loads(user)))
        return json.dumps(self.graph)


class Review(Recorded):
    async def __call__(self, system, user):
        payload = json.loads(user)
        self.requests.append((system, payload))
        return json.dumps({"occurrences": [], "transitions": [transition("T1", ["B1"], "B2")]
                          if "K2" in payload["dependency_target_keys"] else []})


async def emit(event):
    pass


@pytest.mark.asyncio
async def test_default_production_build_uses_version6_and_new_prompts():
    repo, model, reviewer = Repository(), Recorded(), Review()
    result = await TextToMap(repo, Source(), model, reviewer).execute("article", "owner", emit)
    assert result["graph_schema_version"] == 6 and result["builder_version"] == "3"
    assert result["prompt"]["version"] == "3" and result["dependency_prompt"]["version"] == "15"
    assert result["graph"]["edges"] == [{"source": "B1", "target": "B2"}]
    assert reviewer.requests[0][1]["article_text"] == TEXT[:SOURCE["content_end"]]
    assert "146." in model.requests[0][0] and "175." in model.requests[0][0]
    assert not repo.locks


@pytest.mark.asyncio
async def test_cross_group_inputs_include_future_targets_and_complete_source():
    graph = extracted(*(knowledge(i) for i in range(1, 42)))
    class CrossReview(Review):
        async def __call__(self, system, user):
            payload = json.loads(user)
            self.requests.append((system, payload))
            transitions = [transition("T1", ["B41"], "B1")] if "K1" in payload["dependency_target_keys"] else []
            return json.dumps({"occurrences": [], "transitions": transitions})
    reviewer = CrossReview()
    result = await TextToMap(Repository(), Source(), Recorded(graph), reviewer).execute("article", "owner", emit)
    assert [len(request[1]["dependency_target_keys"]) for request in reviewer.requests] == [40, 1]
    assert all(len(request[1]["knowledge_map"]["knowledge"]) == 41 for request in reviewer.requests)
    assert result["graph"]["edges"] == [{"source": "B41", "target": "B1"}]


@pytest.mark.asyncio
async def test_offline_publisher_has_no_generation_port_and_preserves_structural_map(monkeypatch):
    import httpx
    def forbidden(*args, **kwargs):
        raise AssertionError("AI/network generation must not be called")
    monkeypatch.setattr(httpx.AsyncClient, "stream", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "post", forbidden)
    repo = Repository()
    structural = copy.deepcopy(repo.maps["structural_rows"])
    generation = {"kind": "codex_manual", "external_llm_calls": 0, "local_llm_calls": 0, "token_usage": None}
    result = await PublishArticleMap(repo, Source()).execute("article", "owner", initialize_occurrences(extracted(), SOURCE),
        expected_source_sha256=digest(TEXT), metadata=prompt_binding() | {"generation": generation},
        labels_ru={"K1": "Первое наблюдение", "K2": "Второе наблюдение"})
    assert result["translations"]["ru"]["labels"] == {"B1": "Первое наблюдение", "B2": "Второе наблюдение"}
    assert result["graph"]["knowledge"][0]["display_text"].startswith("Observation")
    assert repo.maps["structural_rows"] == structural
    assert result["generation"]["token_usage"] is None


@pytest.mark.asyncio
async def test_invalid_result_source_or_translation_never_replaces_success():
    repo = Repository()
    repo.maps["text_reified"] = {"previous": True}
    before = copy.deepcopy(repo.maps)
    publisher = PublishArticleMap(repo, Source())
    graph = initialize_occurrences(extracted(), SOURCE)
    for source_hash, labels in (("wrong", None), (digest(TEXT), {"K1": "Неполный перевод"})):
        with pytest.raises(ArticleMapError):
            await publisher.execute("article", "owner", graph, expected_source_sha256=source_hash,
                                    metadata={"generation": {"kind": "codex_manual"}}, labels_ru=labels)
        assert repo.maps == before and not repo.locks


@pytest.mark.asyncio
async def test_concurrent_build_and_cancellation_preserve_previous_result():
    started = asyncio.Event()
    class Waiting(Recorded):
        async def __call__(self, system, user):
            started.set()
            await asyncio.Event().wait()
    repo = Repository()
    before = copy.deepcopy(repo.maps)
    task = asyncio.create_task(TextToMap(repo, Source(), Waiting(), Review()).execute("article", "owner", emit))
    await started.wait()
    with pytest.raises(ArticleMapBusy):
        await TextToMap(repo, Source(), Recorded(), Review()).execute("article", "owner", emit)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert repo.maps == before and not repo.locks
